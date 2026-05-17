"""Consent, access audit, redaction and retention helpers."""
from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List

from .persistence import now_iso
from .v5_privacy_security import check_access

DEFAULT_PRIVACY_PATH = Path(__file__).resolve().parents[1] / "data" / "privacy_audit.sqlite3"
SENSITIVE_FIELDS = {"monthly_income", "expected_monthly_income", "rent", "deposit", "assets_million", "medical_expense_3m", "debt_monthly_payment", "notes"}
DIRECT_IDENTIFIERS = {"name", "email", "phone", "resident_registration_number", "address"}


@contextmanager
def privacy_connection(path: str | Path | None = None) -> Iterator[sqlite3.Connection]:
    db_path = Path(path) if path else DEFAULT_PRIVACY_PATH
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_privacy_store(path: str | Path | None = None) -> Path:
    with privacy_connection(path) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS consent_records (
                consent_id INTEGER PRIMARY KEY AUTOINCREMENT,
                subject_hash TEXT NOT NULL,
                purpose TEXT NOT NULL,
                granted INTEGER NOT NULL,
                scope_json TEXT NOT NULL,
                expires_at TEXT DEFAULT '',
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS privacy_access_logs (
                access_id INTEGER PRIMARY KEY AUTOINCREMENT,
                actor_id TEXT NOT NULL,
                role TEXT NOT NULL,
                action TEXT NOT NULL,
                purpose TEXT NOT NULL,
                subject_hash TEXT NOT NULL,
                fields_json TEXT NOT NULL,
                decision TEXT NOT NULL,
                reason TEXT DEFAULT '',
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_privacy_access_subject ON privacy_access_logs(subject_hash, created_at);
            """
        )
    return Path(path) if path else DEFAULT_PRIVACY_PATH


def subject_hash(subject: str | Dict[str, Any]) -> str:
    if isinstance(subject, dict):
        raw = json.dumps(subject, ensure_ascii=False, sort_keys=True)
    else:
        raw = str(subject)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]


def record_consent(
    subject: str | Dict[str, Any],
    *,
    purpose: str,
    granted: bool,
    scope: Iterable[str],
    expires_at: str = "",
    path: str | Path | None = None,
) -> Dict[str, Any]:
    init_privacy_store(path)
    timestamp = now_iso()
    with privacy_connection(path) as conn:
        cur = conn.execute(
            "INSERT INTO consent_records(subject_hash, purpose, granted, scope_json, expires_at, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (subject_hash(subject), purpose, 1 if granted else 0, json.dumps(sorted(set(scope)), ensure_ascii=False), expires_at, timestamp),
        )
        row = conn.execute("SELECT * FROM consent_records WHERE consent_id = ?", (cur.lastrowid,)).fetchone()
    item = dict(row)
    item["scope"] = json.loads(item.pop("scope_json") or "[]")
    item["granted"] = bool(item["granted"])
    return item


def audit_profile_access(
    *,
    actor_id: str,
    role: str,
    action: str,
    purpose: str,
    subject: str | Dict[str, Any],
    fields: Iterable[str],
    path: str | Path | None = None,
) -> Dict[str, Any]:
    init_privacy_store(path)
    field_list = sorted(set(str(f) for f in fields))
    decision = check_access(role, action, purpose, field_list)
    with privacy_connection(path) as conn:
        cur = conn.execute(
            """
            INSERT INTO privacy_access_logs(actor_id, role, action, purpose, subject_hash, fields_json, decision, reason, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (actor_id, role, action, purpose, subject_hash(subject), json.dumps(field_list, ensure_ascii=False), decision["decision"], decision["reason"], now_iso()),
        )
    decision["access_id"] = int(cur.lastrowid)
    return decision


def redact_profile_payload(payload: Dict[str, Any], *, purpose: str = "analytics", role: str = "auditor") -> Dict[str, Any]:
    allowed = check_access(role, "read:masked_profile", purpose, payload.keys())
    denied = set(allowed.get("denied_fields", [])) | DIRECT_IDENTIFIERS
    redacted: Dict[str, Any] = {}
    for key, value in payload.items():
        if key in denied:
            redacted[key] = "[REDACTED]"
        elif key in SENSITIVE_FIELDS:
            redacted[key] = "[MASKED]"
        else:
            redacted[key] = value
    return redacted


def privacy_retention_plan() -> List[Dict[str, Any]]:
    return [
        {"table": "profile_snapshots", "retention": "계약/동의 종료 후 90일 내 삭제", "basis": "서비스 제공과 분쟁 대응 최소 기간"},
        {"table": "analysis_runs", "retention": "1년 보관 후 비식별 집계만 유지", "basis": "상담 품질 감사"},
        {"table": "policy_catalog_live", "retention": "정책 버전 이력 5년", "basis": "판정 근거 재현"},
        {"table": "privacy_access_logs", "retention": "3년", "basis": "개인정보 접근 감사"},
        {"table": "notification_outbox", "retention": "발송/실패 후 180일", "basis": "민원 대응과 재발송 방지"},
    ]


def privacy_audit_status(path: str | Path | None = None) -> Dict[str, Any]:
    init_privacy_store(path)
    with privacy_connection(path) as conn:
        consent_count = conn.execute("SELECT COUNT(*) AS c FROM consent_records").fetchone()["c"]
        access_count = conn.execute("SELECT COUNT(*) AS c FROM privacy_access_logs").fetchone()["c"]
        decisions = conn.execute("SELECT decision, COUNT(*) AS count FROM privacy_access_logs GROUP BY decision").fetchall()
    return {"consent_count": int(consent_count), "access_count": int(access_count), "decisions": [dict(row) for row in decisions], "store_path": str(Path(path) if path else DEFAULT_PRIVACY_PATH)}
