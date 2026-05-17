"""Persistence layer with SQLite default and PostgreSQL-ready schema.

For local demos, SQLite keeps the project zero-ops. For production, set
``LIFEPASS_DATABASE_URL=postgresql://...`` and install psycopg. The same tables
are used conceptually: users, profiles, analysis_runs, application_tasks.
"""
from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Optional

from .models import BenefitEvaluation, UserProfile

DEFAULT_SQLITE_PATH = Path(__file__).resolve().parents[1] / "data" / "lifepass.sqlite3"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def database_url() -> str:
    return os.getenv("LIFEPASS_DATABASE_URL") or f"sqlite:///{DEFAULT_SQLITE_PATH}"


def is_postgres_url(url: str | None = None) -> bool:
    url = url or database_url()
    return url.startswith("postgresql://") or url.startswith("postgres://")


def sqlite_path_from_url(url: str | None = None) -> Path:
    url = url or database_url()
    if url.startswith("sqlite:///"):
        return Path(url.replace("sqlite:///", "", 1))
    return DEFAULT_SQLITE_PATH


@contextmanager
def sqlite_connection(path: str | Path | None = None) -> Iterator[sqlite3.Connection]:
    db_path = Path(path) if path else sqlite_path_from_url()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db(path: str | Path | None = None) -> Path:
    """Create local SQLite tables. PostgreSQL uses the same DDL conceptually."""
    with sqlite_connection(path) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS profiles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                name TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(id)
            );
            CREATE TABLE IF NOT EXISTS analysis_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                profile_id INTEGER,
                profile_name TEXT NOT NULL,
                summary_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(profile_id) REFERENCES profiles(id)
            );
            CREATE TABLE IF NOT EXISTS application_tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                profile_id INTEGER,
                benefit_name TEXT NOT NULL,
                task TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'todo',
                due_month INTEGER DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(profile_id) REFERENCES profiles(id)
            );
            """
        )
    return Path(path) if path else sqlite_path_from_url()


def upsert_user(email: str, name: str, path: str | Path | None = None) -> int:
    init_db(path)
    email = (email or "demo@lifepass.local").strip().lower()
    name = (name or "데모 사용자").strip()
    with sqlite_connection(path) as conn:
        row = conn.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
        if row:
            conn.execute("UPDATE users SET name = ? WHERE id = ?", (name, row["id"]))
            return int(row["id"])
        cur = conn.execute("INSERT INTO users(email, name, created_at) VALUES (?, ?, ?)", (email, name, now_iso()))
        return int(cur.lastrowid)


def save_profile(profile: UserProfile, name: str = "현재 프로필", user_id: Optional[int] = None, path: str | Path | None = None) -> int:
    init_db(path)
    payload = json.dumps(profile.to_dict(), ensure_ascii=False)
    with sqlite_connection(path) as conn:
        cur = conn.execute(
            "INSERT INTO profiles(user_id, name, payload_json, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
            (user_id, name, payload, now_iso(), now_iso()),
        )
        return int(cur.lastrowid)


def list_profiles(limit: int = 50, path: str | Path | None = None) -> List[Dict[str, Any]]:
    init_db(path)
    with sqlite_connection(path) as conn:
        rows = conn.execute("SELECT id, user_id, name, payload_json, created_at, updated_at FROM profiles ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    out: List[Dict[str, Any]] = []
    for row in rows:
        payload = json.loads(row["payload_json"])
        out.append({
            "id": row["id"],
            "user_id": row["user_id"],
            "name": row["name"],
            "region": payload.get("region"),
            "age": payload.get("age"),
            "monthly_income": payload.get("monthly_income"),
            "rent": payload.get("rent"),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        })
    return out


def save_analysis_run(profile_id: Optional[int], profile_name: str, summary: Dict[str, Any], path: str | Path | None = None) -> int:
    init_db(path)
    with sqlite_connection(path) as conn:
        cur = conn.execute(
            "INSERT INTO analysis_runs(profile_id, profile_name, summary_json, created_at) VALUES (?, ?, ?, ?)",
            (profile_id, profile_name, json.dumps(summary, ensure_ascii=False), now_iso()),
        )
        return int(cur.lastrowid)


def create_tasks_from_benefits(profile_id: Optional[int], benefits: Iterable[BenefitEvaluation], path: str | Path | None = None) -> int:
    init_db(path)
    created = 0
    with sqlite_connection(path) as conn:
        for benefit in benefits:
            docs = benefit.required_docs or ["본인확인", "소득자료"]
            task_text = f"{benefit.name} 신청 준비: {', '.join(docs[:4])}"
            conn.execute(
                "INSERT INTO application_tasks(profile_id, benefit_name, task, status, due_month, created_at, updated_at) VALUES (?, ?, ?, 'todo', 0, ?, ?)",
                (profile_id, benefit.name, task_text, now_iso(), now_iso()),
            )
            created += 1
    return created


def list_tasks(limit: int = 100, path: str | Path | None = None) -> List[Dict[str, Any]]:
    init_db(path)
    with sqlite_connection(path) as conn:
        rows = conn.execute(
            "SELECT id, profile_id, benefit_name, task, status, due_month, created_at, updated_at FROM application_tasks ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(row) for row in rows]


def update_task_status(task_id: int, status: str, path: str | Path | None = None) -> None:
    init_db(path)
    with sqlite_connection(path) as conn:
        conn.execute("UPDATE application_tasks SET status = ?, updated_at = ? WHERE id = ?", (status, now_iso(), task_id))


def db_status(path: str | Path | None = None) -> Dict[str, Any]:
    url = database_url()
    status = {"database_url": url, "mode": "postgresql-ready" if is_postgres_url(url) else "sqlite-local", "tables": {}}
    if is_postgres_url(url):
        status["note"] = "PostgreSQL URL이 설정되었습니다. 배포 환경에서는 psycopg/SQLAlchemy 연결로 확장하세요. 이 MVP UI는 로컬 검증을 위해 SQLite 함수를 기본 사용합니다."
        return status
    init_db(path)
    with sqlite_connection(path) as conn:
        for table in ["users", "profiles", "analysis_runs", "application_tasks"]:
            count = conn.execute(f"SELECT COUNT(*) AS c FROM {table}").fetchone()["c"]
            status["tables"][table] = int(count)
    status["path"] = str(sqlite_path_from_url())
    return status
