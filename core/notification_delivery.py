"""Notification outbox and optional delivery adapters.

Production services should not send email/SMS directly inside eligibility logic.
This outbox pattern records idempotent notification jobs first, then dispatches
through environment-configured adapters.
"""
from __future__ import annotations

import json
import os
import sqlite3
import urllib.request
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List

from .persistence import now_iso

DEFAULT_NOTIFICATION_PATH = Path(__file__).resolve().parents[1] / "data" / "notification_outbox.sqlite3"
VALID_CHANNELS = {"app", "email", "sms", "webhook"}


@contextmanager
def notification_connection(path: str | Path | None = None) -> Iterator[sqlite3.Connection]:
    db_path = Path(path) if path else DEFAULT_NOTIFICATION_PATH
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_notification_store(path: str | Path | None = None) -> Path:
    with notification_connection(path) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS notification_outbox (
                notification_id INTEGER PRIMARY KEY AUTOINCREMENT,
                idempotency_key TEXT UNIQUE NOT NULL,
                channel TEXT NOT NULL,
                destination TEXT NOT NULL,
                template TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                severity TEXT DEFAULT 'medium',
                status TEXT NOT NULL DEFAULT 'queued',
                attempts INTEGER DEFAULT 0,
                last_error TEXT DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_notification_outbox_status ON notification_outbox(status, updated_at);
            """
        )
    return Path(path) if path else DEFAULT_NOTIFICATION_PATH


def enqueue_notification(
    *,
    channel: str,
    destination: str,
    template: str,
    payload: Dict[str, Any],
    severity: str = "medium",
    idempotency_key: str = "",
    path: str | Path | None = None,
) -> Dict[str, Any]:
    if channel not in VALID_CHANNELS:
        raise ValueError(f"Unsupported notification channel: {channel}")
    init_notification_store(path)
    timestamp = now_iso()
    key = idempotency_key or f"{channel}:{destination}:{template}:{json.dumps(payload, ensure_ascii=False, sort_keys=True)}"
    with notification_connection(path) as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO notification_outbox(idempotency_key, channel, destination, template, payload_json, severity, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, 'queued', ?, ?)
            """,
            (key, channel, destination, template, json.dumps(payload, ensure_ascii=False, sort_keys=True), severity, timestamp, timestamp),
        )
        row = conn.execute("SELECT * FROM notification_outbox WHERE idempotency_key = ?", (key,)).fetchone()
    return _row_to_dict(row)


def enqueue_notifications(rows: Iterable[Dict[str, Any]], *, default_destination: str = "", path: str | Path | None = None) -> List[Dict[str, Any]]:
    out = []
    for row in rows:
        out.append(enqueue_notification(
            channel=str(row.get("channel", "app")),
            destination=str(row.get("destination") or default_destination or "in_app_inbox"),
            template=str(row.get("trigger") or row.get("template") or "generic_reminder"),
            payload=dict(row),
            severity=str(row.get("severity", "medium")),
            path=path,
        ))
    return out


def _row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
    item = dict(row)
    item["payload"] = json.loads(item.pop("payload_json") or "{}")
    return item


def list_notifications(status: str = "queued", limit: int = 100, path: str | Path | None = None) -> List[Dict[str, Any]]:
    init_notification_store(path)
    with notification_connection(path) as conn:
        if status:
            rows = conn.execute("SELECT * FROM notification_outbox WHERE status = ? ORDER BY notification_id LIMIT ?", (status, limit)).fetchall()
        else:
            rows = conn.execute("SELECT * FROM notification_outbox ORDER BY notification_id DESC LIMIT ?", (limit,)).fetchall()
    return [_row_to_dict(row) for row in rows]


def _deliver_webhook(destination: str, payload: Dict[str, Any]) -> None:
    endpoint = destination or os.getenv("LIFEPASS_NOTIFICATION_WEBHOOK_URL", "")
    if not endpoint:
        raise RuntimeError("Webhook destination is not configured")
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(endpoint, data=body, headers={"Content-Type": "application/json", "User-Agent": "LifePassAI/5.1 notification"}, method="POST")
    with urllib.request.urlopen(req, timeout=8) as resp:  # noqa: S310 - operator-configured webhook
        if resp.status >= 400:
            raise RuntimeError(f"Webhook failed with HTTP {resp.status}")


def dispatch_pending_notifications(limit: int = 20, dry_run: bool = True, path: str | Path | None = None) -> Dict[str, Any]:
    init_notification_store(path)
    rows = list_notifications(status="queued", limit=limit, path=path)
    sent: List[Dict[str, Any]] = []
    failed: List[Dict[str, Any]] = []
    with notification_connection(path) as conn:
        for item in rows:
            try:
                if dry_run:
                    pass
                elif item["channel"] == "webhook":
                    _deliver_webhook(item["destination"], item["payload"])
                else:
                    # Email/SMS adapters are intentionally environment-backed.
                    # Until configured, keep a durable record and mark as exported.
                    if not os.getenv("LIFEPASS_ENABLE_EXTERNAL_NOTIFICATIONS", "0").lower() in {"1", "true", "yes"}:
                        raise RuntimeError("External notification adapter is not enabled")
                conn.execute(
                    "UPDATE notification_outbox SET status = ?, attempts = attempts + 1, updated_at = ? WHERE notification_id = ?",
                    ("dry_run" if dry_run else "sent", now_iso(), item["notification_id"]),
                )
                sent.append(item)
            except Exception as exc:  # noqa: BLE001
                conn.execute(
                    "UPDATE notification_outbox SET status = 'failed', attempts = attempts + 1, last_error = ?, updated_at = ? WHERE notification_id = ?",
                    (str(exc)[:1000], now_iso(), item["notification_id"]),
                )
                item["error"] = str(exc)
                failed.append(item)
    return {"dry_run": dry_run, "processed": len(rows), "sent_or_exported": len(sent), "failed": len(failed), "failures": failed[:5]}


def notification_status(path: str | Path | None = None) -> Dict[str, Any]:
    init_notification_store(path)
    with notification_connection(path) as conn:
        rows = conn.execute("SELECT status, COUNT(*) AS count FROM notification_outbox GROUP BY status ORDER BY status").fetchall()
    return {"by_status": [dict(row) for row in rows], "store_path": str(Path(path) if path else DEFAULT_NOTIFICATION_PATH)}
