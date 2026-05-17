"""Application case and human-review workflow store."""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List

from .models import UserProfile
from .persistence import now_iso

DEFAULT_CASE_PATH = Path(__file__).resolve().parents[1] / "data" / "application_cases.sqlite3"
CASE_STATUSES = {"draft", "submitted", "needs_human_review", "approved", "rejected", "sent_to_agency", "closed"}


@contextmanager
def case_connection(path: str | Path | None = None) -> Iterator[sqlite3.Connection]:
    db_path = Path(path) if path else DEFAULT_CASE_PATH
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_case_store(path: str | Path | None = None) -> Path:
    with case_connection(path) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS application_cases (
                case_id INTEGER PRIMARY KEY AUTOINCREMENT,
                profile_hash TEXT NOT NULL,
                profile_json TEXT NOT NULL,
                selected_benefits_json TEXT NOT NULL,
                status TEXT NOT NULL,
                risk_level TEXT NOT NULL DEFAULT 'normal',
                assigned_role TEXT NOT NULL DEFAULT 'counselor',
                reviewer_email TEXT DEFAULT '',
                decision_reason TEXT DEFAULT '',
                created_by TEXT DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS application_case_events (
                event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                case_id INTEGER NOT NULL,
                actor TEXT NOT NULL,
                event_type TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(case_id) REFERENCES application_cases(case_id)
            );
            CREATE INDEX IF NOT EXISTS idx_application_cases_status ON application_cases(status, updated_at);
            """
        )
    return Path(path) if path else DEFAULT_CASE_PATH


def _profile_hash(profile: UserProfile) -> str:
    import hashlib

    return hashlib.sha256(json.dumps(profile.to_dict(), ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()[:16]


def _risk_level(benefits: Iterable[Dict[str, Any]]) -> str:
    benefit_list = list(benefits)
    if any(b.get("human_review_required") for b in benefit_list):
        return "review_required"
    if any(b.get("is_demo") for b in benefit_list):
        return "demo_data_blocked"
    if len(benefit_list) >= 5:
        return "high_volume"
    return "normal"


def _case_row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
    item = dict(row)
    item["profile"] = json.loads(item.pop("profile_json"))
    item["selected_benefits"] = json.loads(item.pop("selected_benefits_json"))
    return item


def create_application_case(
    profile: UserProfile,
    selected_benefits: Iterable[Dict[str, Any]],
    *,
    created_by: str = "system",
    submit: bool = False,
    path: str | Path | None = None,
) -> Dict[str, Any]:
    init_case_store(path)
    benefits = [dict(b) for b in selected_benefits]
    risk = _risk_level(benefits)
    status = "needs_human_review" if risk in {"review_required", "demo_data_blocked"} else ("submitted" if submit else "draft")
    timestamp = now_iso()
    with case_connection(path) as conn:
        cur = conn.execute(
            """
            INSERT INTO application_cases(profile_hash, profile_json, selected_benefits_json, status, risk_level, created_by, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (_profile_hash(profile), json.dumps(profile.to_dict(), ensure_ascii=False), json.dumps(benefits, ensure_ascii=False), status, risk, created_by, timestamp, timestamp),
        )
        case_id = int(cur.lastrowid)
        conn.execute(
            "INSERT INTO application_case_events(case_id, actor, event_type, payload_json, created_at) VALUES (?, ?, ?, ?, ?)",
            (case_id, created_by, "case_created", json.dumps({"status": status, "risk_level": risk}, ensure_ascii=False), timestamp),
        )
        row = conn.execute("SELECT * FROM application_cases WHERE case_id = ?", (case_id,)).fetchone()
    return _case_row_to_dict(row)


def list_application_cases(status: str = "", limit: int = 100, path: str | Path | None = None) -> List[Dict[str, Any]]:
    init_case_store(path)
    with case_connection(path) as conn:
        if status:
            rows = conn.execute("SELECT * FROM application_cases WHERE status = ? ORDER BY updated_at DESC LIMIT ?", (status, limit)).fetchall()
        else:
            rows = conn.execute("SELECT * FROM application_cases ORDER BY updated_at DESC LIMIT ?", (limit,)).fetchall()
    return [_case_row_to_dict(row) for row in rows]


def review_application_case(
    case_id: int,
    *,
    decision: str,
    reviewer_email: str,
    reason: str = "",
    path: str | Path | None = None,
) -> Dict[str, Any]:
    if decision not in CASE_STATUSES:
        raise ValueError(f"Unsupported decision: {decision}")
    init_case_store(path)
    timestamp = now_iso()
    with case_connection(path) as conn:
        row = conn.execute("SELECT * FROM application_cases WHERE case_id = ?", (case_id,)).fetchone()
        if not row:
            raise ValueError(f"Case not found: {case_id}")
        conn.execute(
            "UPDATE application_cases SET status = ?, reviewer_email = ?, decision_reason = ?, updated_at = ? WHERE case_id = ?",
            (decision, reviewer_email, reason, timestamp, case_id),
        )
        conn.execute(
            "INSERT INTO application_case_events(case_id, actor, event_type, payload_json, created_at) VALUES (?, ?, ?, ?, ?)",
            (case_id, reviewer_email, "case_reviewed", json.dumps({"decision": decision, "reason": reason}, ensure_ascii=False), timestamp),
        )
        updated = conn.execute("SELECT * FROM application_cases WHERE case_id = ?", (case_id,)).fetchone()
    return _case_row_to_dict(updated)


def case_events(case_id: int, path: str | Path | None = None) -> List[Dict[str, Any]]:
    init_case_store(path)
    with case_connection(path) as conn:
        rows = conn.execute("SELECT * FROM application_case_events WHERE case_id = ? ORDER BY event_id", (case_id,)).fetchall()
    out = []
    for row in rows:
        item = dict(row)
        item["payload"] = json.loads(item.pop("payload_json") or "{}")
        out.append(item)
    return out
