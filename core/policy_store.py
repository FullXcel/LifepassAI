"""Persistent policy catalog store with provenance and diff history.

This module moves policy synchronization beyond a JSON overwrite.  It stores
live/cached/sample status, source URL, version hashes and each sync diff so the
platform can prove which policy version was used for an eligibility decision.
The default implementation uses SQLite for zero-ops local runs; the table shape
mirrors the PostgreSQL DDL used in production deployments.
"""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Optional

from .policy_provenance import diff_catalogs, policy_version_hash, summarize_diff
from .public_api_clients import FetchResult, fetch_all_enabled_sources, fetch_source_policies
from .persistence import now_iso

DEFAULT_POLICY_STORE_PATH = Path(__file__).resolve().parents[1] / "data" / "policy_catalog_store.sqlite3"


@contextmanager
def policy_store_connection(path: str | Path | None = None) -> Iterator[sqlite3.Connection]:
    db_path = Path(path) if path else DEFAULT_POLICY_STORE_PATH
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_policy_store(path: str | Path | None = None) -> Path:
    with policy_store_connection(path) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS policy_catalog_live (
                policy_id TEXT PRIMARY KEY,
                benefit_json TEXT NOT NULL,
                provenance_json TEXT NOT NULL,
                version_hash TEXT NOT NULL,
                source_system TEXT NOT NULL,
                source_url TEXT DEFAULT '',
                source_document_url TEXT DEFAULT '',
                source_date TEXT DEFAULT '',
                is_demo INTEGER DEFAULT 0,
                human_review_required INTEGER DEFAULT 0,
                active INTEGER DEFAULT 1,
                first_seen_at TEXT NOT NULL,
                last_seen_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS policy_sync_runs (
                run_id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_id TEXT NOT NULL,
                mode TEXT NOT NULL,
                status TEXT NOT NULL,
                query TEXT DEFAULT '',
                limit_count INTEGER DEFAULT 0,
                payload_hash TEXT DEFAULT '',
                endpoint_used TEXT DEFAULT '',
                live_required INTEGER DEFAULT 0,
                diff_json TEXT NOT NULL,
                warnings_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_policy_catalog_live_source ON policy_catalog_live(source_system, active);
            CREATE INDEX IF NOT EXISTS idx_policy_catalog_live_demo ON policy_catalog_live(is_demo, active);
            CREATE INDEX IF NOT EXISTS idx_policy_sync_runs_source ON policy_sync_runs(source_id, created_at);
            """
        )
    return Path(path) if path else DEFAULT_POLICY_STORE_PATH


def _decode_policy_row(row: sqlite3.Row) -> Dict[str, Any]:
    item = json.loads(row["benefit_json"])
    item["provenance"] = json.loads(row["provenance_json"] or "{}")
    item.setdefault("source_system", row["source_system"])
    item.setdefault("source_document_url", row["source_document_url"])
    item.setdefault("is_demo", bool(row["is_demo"]))
    item.setdefault("human_review_required", bool(row["human_review_required"]))
    return item


def list_policy_catalog(
    *,
    include_inactive: bool = False,
    include_demo: bool = True,
    source_id: str | None = None,
    limit: int = 500,
    path: str | Path | None = None,
) -> List[Dict[str, Any]]:
    init_policy_store(path)
    clauses = [] if include_inactive else ["active = 1"]
    params: List[Any] = []
    if not include_demo:
        clauses.append("is_demo = 0")
    if source_id:
        clauses.append("source_system = ?")
        params.append(source_id)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    sql = f"SELECT * FROM policy_catalog_live {where} ORDER BY last_seen_at DESC LIMIT ?"
    params.append(limit)
    with policy_store_connection(path) as conn:
        rows = conn.execute(sql, params).fetchall()
    return [_decode_policy_row(row) for row in rows]


def get_policy(policy_id: str, path: str | Path | None = None) -> Optional[Dict[str, Any]]:
    init_policy_store(path)
    with policy_store_connection(path) as conn:
        row = conn.execute("SELECT * FROM policy_catalog_live WHERE policy_id = ?", (policy_id,)).fetchone()
    return _decode_policy_row(row) if row else None


def upsert_policy_catalog(
    benefits: Iterable[Dict[str, Any]],
    *,
    source_id: str,
    deactivate_missing: bool = False,
    path: str | Path | None = None,
) -> Dict[str, Any]:
    """Upsert policies and return a before/after diff."""
    init_policy_store(path)
    incoming = [dict(b) for b in benefits]
    before = list_policy_catalog(include_inactive=False, include_demo=True, source_id=source_id, limit=10_000, path=path)
    diff = diff_catalogs(before, incoming)
    seen_ids = {str(b.get("id")) for b in incoming if b.get("id") is not None}
    timestamp = now_iso()
    with policy_store_connection(path) as conn:
        for benefit in incoming:
            policy_id = str(benefit.get("id"))
            provenance = benefit.get("provenance") if isinstance(benefit.get("provenance"), dict) else {}
            version_hash = provenance.get("version_hash") or policy_version_hash(benefit)
            conn.execute(
                """
                INSERT INTO policy_catalog_live(
                    policy_id, benefit_json, provenance_json, version_hash, source_system,
                    source_url, source_document_url, source_date, is_demo,
                    human_review_required, active, first_seen_at, last_seen_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
                ON CONFLICT(policy_id) DO UPDATE SET
                    benefit_json = excluded.benefit_json,
                    provenance_json = excluded.provenance_json,
                    version_hash = excluded.version_hash,
                    source_system = excluded.source_system,
                    source_url = excluded.source_url,
                    source_document_url = excluded.source_document_url,
                    source_date = excluded.source_date,
                    is_demo = excluded.is_demo,
                    human_review_required = excluded.human_review_required,
                    active = 1,
                    last_seen_at = excluded.last_seen_at
                """,
                (
                    policy_id,
                    json.dumps(benefit, ensure_ascii=False, sort_keys=True),
                    json.dumps(provenance, ensure_ascii=False, sort_keys=True),
                    version_hash,
                    str(provenance.get("source_system") or benefit.get("source_system") or source_id),
                    str(provenance.get("source_url") or ""),
                    str(provenance.get("source_document_url") or benefit.get("source_document_url") or benefit.get("apply_url") or ""),
                    str(provenance.get("source_date") or benefit.get("announcement_date") or ""),
                    1 if benefit.get("is_demo") else 0,
                    1 if benefit.get("human_review_required") else 0,
                    timestamp,
                    timestamp,
                ),
            )
        if deactivate_missing and seen_ids:
            placeholders = ",".join("?" for _ in seen_ids)
            conn.execute(
                f"UPDATE policy_catalog_live SET active = 0, last_seen_at = ? WHERE source_system = ? AND policy_id NOT IN ({placeholders})",
                [timestamp, source_id, *sorted(seen_ids)],
            )
    return {"summary": summarize_diff(diff), "diff": diff}


def save_policy_sync_run(
    result: FetchResult,
    *,
    query: str,
    limit: int,
    diff: Dict[str, Any],
    path: str | Path | None = None,
) -> int:
    init_policy_store(path)
    with policy_store_connection(path) as conn:
        cur = conn.execute(
            """
            INSERT INTO policy_sync_runs(
                source_id, mode, status, query, limit_count, payload_hash, endpoint_used,
                live_required, diff_json, warnings_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                result.source_id,
                result.mode,
                "ok" if result.ok else "failed",
                query,
                limit,
                result.payload_hash,
                result.endpoint_used,
                1 if result.live_required else 0,
                json.dumps(diff, ensure_ascii=False, sort_keys=True),
                json.dumps(result.warnings, ensure_ascii=False),
                result.fetched_at,
            ),
        )
        return int(cur.lastrowid)


def sync_source_to_store(
    source_id: str,
    *,
    query: str = "",
    limit: int = 50,
    require_live: bool | None = None,
    deactivate_missing: bool = False,
    path: str | Path | None = None,
) -> Dict[str, Any]:
    result = fetch_source_policies(source_id, query=query, limit=limit, require_live=require_live)
    diff_result = {"summary": {"added": 0, "removed": 0, "changed": 0, "unchanged": 0}, "diff": {}}
    if result.ok and result.benefits:
        diff_result = upsert_policy_catalog(result.benefits, source_id=source_id, deactivate_missing=deactivate_missing, path=path)
    run_id = save_policy_sync_run(result, query=query, limit=limit, diff=diff_result.get("diff", {}), path=path)
    return {
        "run_id": run_id,
        "fetch": result.to_dict(),
        "diff_summary": diff_result["summary"],
        "diff": diff_result["diff"],
        "stored_count": len(result.benefits) if result.ok else 0,
    }


def sync_all_sources_to_store(query: str = "", limit: int = 50, require_live: bool | None = None, path: str | Path | None = None) -> Dict[str, Any]:
    outputs = []
    for result in fetch_all_enabled_sources(query=query, limit=limit, require_live=require_live):
        diff_result = {"summary": {"added": 0, "removed": 0, "changed": 0, "unchanged": 0}, "diff": {}}
        if result.ok and result.benefits:
            diff_result = upsert_policy_catalog(result.benefits, source_id=result.source_id, path=path)
        run_id = save_policy_sync_run(result, query=query, limit=limit, diff=diff_result.get("diff", {}), path=path)
        outputs.append({"run_id": run_id, "source_id": result.source_id, "mode": result.mode, "ok": result.ok, "stored_count": len(result.benefits), "diff_summary": diff_result["summary"], "warnings": result.warnings})
    return {"sources": outputs, "count": len(outputs), "catalog_summary": policy_store_summary(path=path)}


def list_policy_sync_runs(limit: int = 30, path: str | Path | None = None) -> List[Dict[str, Any]]:
    init_policy_store(path)
    with policy_store_connection(path) as conn:
        rows = conn.execute("SELECT * FROM policy_sync_runs ORDER BY run_id DESC LIMIT ?", (limit,)).fetchall()
    out: List[Dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        item["diff"] = json.loads(item.pop("diff_json") or "{}")
        item["warnings"] = json.loads(item.pop("warnings_json") or "[]")
        out.append(item)
    return out


def policy_store_summary(path: str | Path | None = None) -> Dict[str, Any]:
    init_policy_store(path)
    with policy_store_connection(path) as conn:
        totals = conn.execute(
            """
            SELECT
                COUNT(*) AS total,
                SUM(CASE WHEN active = 1 THEN 1 ELSE 0 END) AS active,
                SUM(CASE WHEN is_demo = 1 AND active = 1 THEN 1 ELSE 0 END) AS active_demo,
                SUM(CASE WHEN is_demo = 0 AND active = 1 THEN 1 ELSE 0 END) AS active_live_or_cached,
                SUM(CASE WHEN human_review_required = 1 AND active = 1 THEN 1 ELSE 0 END) AS review_required
            FROM policy_catalog_live
            """
        ).fetchone()
        by_source = conn.execute(
            """
            SELECT source_system, COUNT(*) AS count,
                   SUM(CASE WHEN is_demo = 1 THEN 1 ELSE 0 END) AS demo_count,
                   MAX(last_seen_at) AS last_seen_at
            FROM policy_catalog_live
            WHERE active = 1
            GROUP BY source_system
            ORDER BY count DESC
            """
        ).fetchall()
    return {
        "total": int(totals["total"] or 0),
        "active": int(totals["active"] or 0),
        "active_demo": int(totals["active_demo"] or 0),
        "active_live_or_cached": int(totals["active_live_or_cached"] or 0),
        "human_review_required": int(totals["review_required"] or 0),
        "by_source": [dict(row) for row in by_source],
        "store_path": str(Path(path) if path else DEFAULT_POLICY_STORE_PATH),
    }


def evidence_links_for_benefits(benefit_ids: Iterable[str], path: str | Path | None = None) -> List[Dict[str, Any]]:
    ids = [str(x) for x in benefit_ids if x]
    if not ids:
        return []
    init_policy_store(path)
    placeholders = ",".join("?" for _ in ids)
    with policy_store_connection(path) as conn:
        rows = conn.execute(
            f"SELECT policy_id, benefit_json, provenance_json, source_document_url, source_date, version_hash, is_demo FROM policy_catalog_live WHERE policy_id IN ({placeholders})",
            ids,
        ).fetchall()
    evidence = []
    for row in rows:
        benefit = json.loads(row["benefit_json"])
        provenance = json.loads(row["provenance_json"] or "{}")
        evidence.append({
            "policy_id": row["policy_id"],
            "name": benefit.get("name"),
            "source_document_url": row["source_document_url"] or benefit.get("apply_url"),
            "source_date": row["source_date"] or benefit.get("announcement_date"),
            "version_hash": row["version_hash"],
            "is_demo": bool(row["is_demo"]),
            "provenance": provenance,
        })
    return evidence
