"""Policy provenance, versioning and catalog diff utilities."""
from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, Iterable, List


def fingerprint_payload(payload: Any) -> str:
    if isinstance(payload, str):
        text = payload
    else:
        text = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def policy_version_hash(benefit: Dict[str, Any]) -> str:
    significant = {
        "id": benefit.get("id"),
        "name": benefit.get("name"),
        "estimated_monthly_value": benefit.get("estimated_monthly_value"),
        "priority": benefit.get("priority"),
        "rule": benefit.get("rule"),
        "conflicts_with": benefit.get("conflicts_with"),
        "exclusive_group": benefit.get("exclusive_group"),
    }
    return fingerprint_payload(significant)[:16]


def add_provenance(benefits: Iterable[Dict[str, Any]], *, source_system: str, source_url: str = "", raw_hash: str = "", collected_at: str = "") -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for benefit in benefits:
        item = dict(benefit)
        item["provenance"] = {
            "source_system": source_system,
            "source_url": source_url,
            "raw_hash": raw_hash,
            "collected_at": collected_at,
            "version_hash": policy_version_hash(item),
        }
        out.append(item)
    return out


def diff_catalogs(old: Iterable[Dict[str, Any]], new: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    old_by_id = {b.get("id"): b for b in old}
    new_by_id = {b.get("id"): b for b in new}
    added = [new_by_id[k] for k in new_by_id.keys() - old_by_id.keys()]
    removed = [old_by_id[k] for k in old_by_id.keys() - new_by_id.keys()]
    changed = []
    unchanged = []
    for key in old_by_id.keys() & new_by_id.keys():
        if policy_version_hash(old_by_id[key]) != policy_version_hash(new_by_id[key]):
            changed.append({"id": key, "old": old_by_id[key], "new": new_by_id[key]})
        else:
            unchanged.append(new_by_id[key])
    return {
        "added_count": len(added),
        "removed_count": len(removed),
        "changed_count": len(changed),
        "unchanged_count": len(unchanged),
        "added": added,
        "removed": removed,
        "changed": changed,
    }
