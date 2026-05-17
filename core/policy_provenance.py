"""Policy provenance, versioning and catalog diff utilities.

This module is intentionally dependency-free because it is used by both the
Streamlit demo and the FastAPI backend.  Production deployments should preserve
these fields in a DB table so every eligibility decision can be tied back to an
exact policy source, collection time and version hash.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, Iterable, List, Tuple


def fingerprint_payload(payload: Any) -> str:
    """Return a stable SHA-256 fingerprint for arbitrary API/file payloads."""
    if isinstance(payload, str):
        text = payload
    else:
        text = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _stable_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _stable_value(value[k]) for k in sorted(value)}
    if isinstance(value, list):
        return [_stable_value(v) for v in value]
    return value


def policy_version_hash(benefit: Dict[str, Any]) -> str:
    """Hash only the fields that can change eligibility/result semantics.

    The previous MVP hash used only a small subset of fields.  For production
    sync, source URL, target text, application URL, required documents and dates
    also matter because they are displayed as legal/operational evidence.
    """
    significant = {
        "id": benefit.get("id"),
        "name": benefit.get("name"),
        "domain": benefit.get("domain"),
        "estimated_monthly_value": benefit.get("estimated_monthly_value"),
        "priority": benefit.get("priority"),
        "description": benefit.get("description"),
        "target": benefit.get("target"),
        "required_docs": benefit.get("required_docs"),
        "apply_url": benefit.get("apply_url"),
        "source_document_url": benefit.get("source_document_url"),
        "announcement_date": benefit.get("announcement_date"),
        "effective_start_date": benefit.get("effective_start_date"),
        "effective_end_date": benefit.get("effective_end_date"),
        "rule": benefit.get("rule"),
        "conflicts_with": benefit.get("conflicts_with"),
        "exclusive_group": benefit.get("exclusive_group"),
    }
    return fingerprint_payload(_stable_value(significant))[:20]


def add_provenance(
    benefits: Iterable[Dict[str, Any]],
    *,
    source_system: str,
    source_url: str = "",
    raw_hash: str = "",
    collected_at: str = "",
    mode: str = "unknown",
    is_demo: bool | None = None,
) -> List[Dict[str, Any]]:
    """Attach normalized provenance metadata to benefits.

    ``is_demo`` is explicit because a production judge/operator must be able to
    distinguish live/cached public records from bundled sample data at a glance.
    """
    out: List[Dict[str, Any]] = []
    for benefit in benefits:
        item = dict(benefit)
        existing = item.get("provenance") if isinstance(item.get("provenance"), dict) else {}
        source_document_url = item.get("source_document_url") or item.get("source_url") or item.get("apply_url") or source_url
        demo_flag = is_demo
        if demo_flag is None:
            demo_flag = bool(item.get("is_demo") or source_system == "bundled_sample" or mode == "bundled_sample")
        item["is_demo"] = bool(demo_flag)
        item["source_system"] = source_system
        item["source_document_url"] = source_document_url
        item["provenance"] = {
            **existing,
            "source_system": source_system,
            "source_url": source_url,
            "source_document_url": source_document_url,
            "source_name": item.get("source_name") or existing.get("source_name") or source_system,
            "source_date": item.get("announcement_date") or item.get("source_date") or existing.get("source_date") or "",
            "raw_hash": raw_hash,
            "collected_at": collected_at,
            "mode": mode,
            "is_demo": bool(demo_flag),
            "version_hash": policy_version_hash(item),
        }
        out.append(item)
    return out


def changed_fields(old: Dict[str, Any], new: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Return field-level diff for UI and audit logs."""
    fields = [
        "name",
        "domain",
        "estimated_monthly_value",
        "priority",
        "description",
        "target",
        "required_docs",
        "apply_url",
        "source_document_url",
        "announcement_date",
        "effective_start_date",
        "effective_end_date",
        "rule",
        "conflicts_with",
        "exclusive_group",
    ]
    diffs: List[Dict[str, Any]] = []
    for field in fields:
        if _stable_value(old.get(field)) != _stable_value(new.get(field)):
            diffs.append({"field": field, "old": old.get(field), "new": new.get(field)})
    return diffs


def diff_catalogs(old: Iterable[Dict[str, Any]], new: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    """Compare two policy catalogs using semantic version hashes."""
    old_by_id = {str(b.get("id")): b for b in old if b.get("id") is not None}
    new_by_id = {str(b.get("id")): b for b in new if b.get("id") is not None}
    added = [new_by_id[k] for k in sorted(new_by_id.keys() - old_by_id.keys())]
    removed = [old_by_id[k] for k in sorted(old_by_id.keys() - new_by_id.keys())]
    changed = []
    unchanged = []
    for key in sorted(old_by_id.keys() & new_by_id.keys()):
        old_item = old_by_id[key]
        new_item = new_by_id[key]
        if policy_version_hash(old_item) != policy_version_hash(new_item):
            changed.append({
                "id": key,
                "old_version": policy_version_hash(old_item),
                "new_version": policy_version_hash(new_item),
                "fields": changed_fields(old_item, new_item),
                "old": old_item,
                "new": new_item,
            })
        else:
            unchanged.append(new_item)
    return {
        "added_count": len(added),
        "removed_count": len(removed),
        "changed_count": len(changed),
        "unchanged_count": len(unchanged),
        "added": added,
        "removed": removed,
        "changed": changed,
    }


def summarize_diff(diff: Dict[str, Any]) -> Dict[str, int]:
    """Compact diff summary for dashboards and sync responses."""
    return {
        "added": int(diff.get("added_count", 0)),
        "removed": int(diff.get("removed_count", 0)),
        "changed": int(diff.get("changed_count", 0)),
        "unchanged": int(diff.get("unchanged_count", 0)),
    }
