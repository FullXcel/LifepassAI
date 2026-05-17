"""Typed output guardrails for parser and agent outputs."""
from __future__ import annotations

from typing import Any, Dict, List

PROFILE_NUMERIC_RANGES = {
    "age": (0, 120),
    "household_size": (1, 20),
    "monthly_income": (0, 100_000_000),
    "expected_monthly_income": (0, 100_000_000),
    "rent": (0, 50_000_000),
    "deposit": (0, 10_000_000_000),
    "credit_score": (0, 1000),
}


def validate_structured_payload(payload: Dict[str, Any], schema_name: str = "UserProfile") -> Dict[str, Any]:
    errors: List[str] = []
    warnings: List[str] = []
    clean = dict(payload or {})
    if schema_name == "UserProfile":
        for key, (lo, hi) in PROFILE_NUMERIC_RANGES.items():
            if key in clean:
                try:
                    value = int(clean[key])
                    if value < lo or value > hi:
                        warnings.append(f"{key}={value} is outside recommended range [{lo}, {hi}]")
                    clean[key] = max(lo, min(value, hi))
                except Exception:
                    errors.append(f"{key} must be numeric")
        if "region" in clean and not str(clean["region"]).strip():
            errors.append("region must not be empty")
    return {"ok": not errors, "schema": schema_name, "clean_payload": clean, "errors": errors, "warnings": warnings}
