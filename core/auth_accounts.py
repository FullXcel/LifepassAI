"""Minimal production-shaped authentication and role layer.

No external dependency is used on purpose.  Passwords are stored with PBKDF2 and
session tokens are signed with HMAC.  In a commercial deployment this can be
replaced by OIDC/SAML without changing the surrounding API contract.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Iterator, Optional

from .persistence import now_iso

DEFAULT_AUTH_PATH = Path(__file__).resolve().parents[1] / "data" / "auth_accounts.sqlite3"
ALLOWED_ROLES = {"citizen", "counselor", "supervisor", "auditor", "admin"}


@contextmanager
def auth_connection(path: str | Path | None = None) -> Iterator[sqlite3.Connection]:
    db_path = Path(path) if path else DEFAULT_AUTH_PATH
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_auth_store(path: str | Path | None = None) -> Path:
    with auth_connection(path) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS user_accounts (
                user_id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE NOT NULL,
                display_name TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'citizen',
                tenant_key TEXT NOT NULL DEFAULT 'default',
                password_hash TEXT NOT NULL,
                salt TEXT NOT NULL,
                disabled INTEGER DEFAULT 0,
                created_at TEXT NOT NULL,
                last_login_at TEXT
            );
            CREATE TABLE IF NOT EXISTS auth_events (
                event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT NOT NULL,
                event_type TEXT NOT NULL,
                success INTEGER NOT NULL,
                detail TEXT DEFAULT '',
                created_at TEXT NOT NULL
            );
            """
        )
    return Path(path) if path else DEFAULT_AUTH_PATH


def _secret() -> bytes:
    # Default is deterministic only for local development.  Production must set it.
    return os.getenv("LIFEPASS_AUTH_SECRET", "dev-only-change-me").encode("utf-8")


def _hash_password(password: str, salt: str) -> str:
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 200_000)
    return base64.urlsafe_b64encode(digest).decode("ascii")


def _audit_auth_event(email: str, event_type: str, success: bool, detail: str = "", path: str | Path | None = None) -> None:
    init_auth_store(path)
    with auth_connection(path) as conn:
        conn.execute(
            "INSERT INTO auth_events(email, event_type, success, detail, created_at) VALUES (?, ?, ?, ?, ?)",
            (email.lower().strip(), event_type, 1 if success else 0, detail[:500], now_iso()),
        )


def register_user(
    email: str,
    password: str,
    display_name: str = "",
    role: str = "citizen",
    tenant_key: str = "default",
    path: str | Path | None = None,
) -> Dict[str, Any]:
    init_auth_store(path)
    email = email.lower().strip()
    if role not in ALLOWED_ROLES:
        raise ValueError(f"Unsupported role: {role}")
    if len(password) < 8:
        raise ValueError("Password must be at least 8 characters")
    display_name = display_name.strip() or email.split("@")[0]
    salt = secrets.token_urlsafe(24)
    password_hash = _hash_password(password, salt)
    with auth_connection(path) as conn:
        cur = conn.execute(
            """
            INSERT INTO user_accounts(email, display_name, role, tenant_key, password_hash, salt, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (email, display_name, role, tenant_key, password_hash, salt, now_iso()),
        )
        user_id = int(cur.lastrowid)
    _audit_auth_event(email, "register", True, role, path=path)
    return {"user_id": user_id, "email": email, "display_name": display_name, "role": role, "tenant_key": tenant_key}


def _encode_payload(payload: Dict[str, Any]) -> str:
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _decode_payload(token_part: str) -> Dict[str, Any]:
    padded = token_part + "=" * (-len(token_part) % 4)
    return json.loads(base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8"))


def issue_token(user: Dict[str, Any], expires_in_seconds: int = 60 * 60 * 8) -> str:
    payload = {
        "sub": str(user["user_id"]),
        "email": user["email"],
        "role": user["role"],
        "tenant_key": user.get("tenant_key", "default"),
        "iat": int(time.time()),
        "exp": int(time.time()) + expires_in_seconds,
    }
    body = _encode_payload(payload)
    sig = hmac.new(_secret(), body.encode("ascii"), hashlib.sha256).digest()
    signature = base64.urlsafe_b64encode(sig).decode("ascii").rstrip("=")
    return f"lp.{body}.{signature}"


def verify_token(token: str) -> Dict[str, Any]:
    token = token.replace("Bearer ", "").strip()
    parts = token.split(".")
    if len(parts) != 3 or parts[0] != "lp":
        raise ValueError("Invalid token format")
    _, body, signature = parts
    expected = base64.urlsafe_b64encode(hmac.new(_secret(), body.encode("ascii"), hashlib.sha256).digest()).decode("ascii").rstrip("=")
    if not hmac.compare_digest(signature, expected):
        raise ValueError("Invalid token signature")
    payload = _decode_payload(body)
    if int(payload.get("exp", 0)) < int(time.time()):
        raise ValueError("Token expired")
    return payload


def authenticate_user(email: str, password: str, path: str | Path | None = None) -> Dict[str, Any]:
    init_auth_store(path)
    email = email.lower().strip()
    with auth_connection(path) as conn:
        row = conn.execute("SELECT * FROM user_accounts WHERE email = ?", (email,)).fetchone()
        if not row or row["disabled"]:
            _audit_auth_event(email, "login", False, "not_found_or_disabled", path=path)
            raise ValueError("Invalid credentials")
        password_hash = _hash_password(password, row["salt"])
        if not hmac.compare_digest(password_hash, row["password_hash"]):
            _audit_auth_event(email, "login", False, "password_mismatch", path=path)
            raise ValueError("Invalid credentials")
        conn.execute("UPDATE user_accounts SET last_login_at = ? WHERE user_id = ?", (now_iso(), row["user_id"]))
    user = {"user_id": int(row["user_id"]), "email": row["email"], "display_name": row["display_name"], "role": row["role"], "tenant_key": row["tenant_key"]}
    _audit_auth_event(email, "login", True, "", path=path)
    return {"user": user, "access_token": issue_token(user), "token_type": "Bearer"}


def require_role(token: str, allowed_roles: set[str]) -> Dict[str, Any]:
    payload = verify_token(token)
    role = str(payload.get("role", ""))
    if role not in allowed_roles and "admin" not in allowed_roles:
        raise PermissionError(f"Role {role} is not allowed")
    return payload


def get_user_by_token(token: str, path: str | Path | None = None) -> Optional[Dict[str, Any]]:
    payload = verify_token(token)
    init_auth_store(path)
    with auth_connection(path) as conn:
        row = conn.execute("SELECT user_id, email, display_name, role, tenant_key, disabled, created_at, last_login_at FROM user_accounts WHERE user_id = ?", (payload.get("sub"),)).fetchone()
    return dict(row) if row else None


def auth_status(path: str | Path | None = None) -> Dict[str, Any]:
    init_auth_store(path)
    with auth_connection(path) as conn:
        total = conn.execute("SELECT COUNT(*) AS c FROM user_accounts").fetchone()["c"]
        by_role = conn.execute("SELECT role, COUNT(*) AS count FROM user_accounts GROUP BY role ORDER BY count DESC").fetchall()
    return {
        "user_count": int(total),
        "by_role": [dict(row) for row in by_role],
        "secret_configured": os.getenv("LIFEPASS_AUTH_SECRET") not in (None, "", "dev-only-change-me"),
        "store_path": str(Path(path) if path else DEFAULT_AUTH_PATH),
    }
