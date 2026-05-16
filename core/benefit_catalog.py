"""Benefit catalog loader and validation."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

DEFAULT_CATALOG_PATH = Path(__file__).resolve().parents[1] / "data" / "benefits.json"

REQUIRED_KEYS = {"id", "name", "domain", "estimated_monthly_value", "priority", "rule"}


class CatalogError(ValueError):
    pass


def load_benefits(path: str | Path = DEFAULT_CATALOG_PATH) -> List[Dict[str, Any]]:
    path = Path(path)
    with path.open("r", encoding="utf-8") as f:
        benefits = json.load(f)
    validate_benefits(benefits)
    return benefits


def validate_benefits(benefits: List[Dict[str, Any]]) -> None:
    seen = set()
    for idx, benefit in enumerate(benefits):
        missing = REQUIRED_KEYS - set(benefit)
        if missing:
            raise CatalogError(f"Benefit #{idx} missing keys: {sorted(missing)}")
        if benefit["id"] in seen:
            raise CatalogError(f"Duplicate benefit id: {benefit['id']}")
        seen.add(benefit["id"])
        if not isinstance(benefit["estimated_monthly_value"], int) or benefit["estimated_monthly_value"] < 0:
            raise CatalogError(f"Invalid monthly value for {benefit['id']}")
        if not isinstance(benefit["priority"], int):
            raise CatalogError(f"Invalid priority for {benefit['id']}")
        if "exclusive_group" not in benefit:
            benefit["exclusive_group"] = None
        if "conflicts_with" not in benefit:
            benefit["conflicts_with"] = []
        if not isinstance(benefit.get("conflicts_with", []), list):
            raise CatalogError(f"conflicts_with must be list: {benefit['id']}")


def benefits_by_id(benefits: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    return {b["id"]: b for b in benefits}
