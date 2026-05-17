"""Privacy, access-control and synthetic-data utilities for v5."""
from __future__ import annotations

import hashlib
import math
import random
from typing import Any, Dict, Iterable, List

from core.models import UserProfile
from core.utils import project_profile


ROLE_PERMISSIONS = {
    "citizen": {"read:self", "export:self"},
    "counselor": {"read:assigned", "write:case_note", "create:application_task"},
    "supervisor": {"read:tenant", "approve:high_risk", "read:audit"},
    "auditor": {"read:audit", "read:masked_profile", "export:compliance"},
    "admin": {"*"},
}

PURPOSE_ALLOWLIST = {
    "eligibility_screening": {"age", "region", "household_size", "monthly_income", "rent", "employment_status"},
    "application_support": {"age", "region", "household_size", "monthly_income", "rent", "deposit", "has_housing_contract"},
    "audit": {"age", "region", "household_size", "employment_status"},
    "analytics": {"age", "region", "household_size", "monthly_income", "rent"},
}


def check_access(role: str, action: str, purpose: str, fields: Iterable[str]) -> Dict[str, Any]:
    permissions = ROLE_PERMISSIONS.get(role, set())
    fields = set(fields)
    allowed_by_role = "*" in permissions or action in permissions or any(action.startswith(p.replace("*", "")) for p in permissions if p.endswith("*"))
    allowed_fields = PURPOSE_ALLOWLIST.get(purpose, set())
    denied_fields = sorted(fields - allowed_fields)
    ok = bool(allowed_by_role and not denied_fields)
    return {
        "ok": ok,
        "role": role,
        "action": action,
        "purpose": purpose,
        "requested_fields": sorted(fields),
        "denied_fields": denied_fields,
        "decision": "allow" if ok else "deny_or_require_redaction",
        "reason": "role_and_purpose_match" if ok else "role_permission_or_purpose_scope_violation",
    }


def privacy_budget_table() -> List[Dict[str, Any]]:
    return [
        {"query": "region_summary", "epsilon": 0.7, "sensitivity": 1, "release": "approved", "note": "지역별 집계"},
        {"query": "benefit_uptake", "epsilon": 0.5, "sensitivity": 1, "release": "approved", "note": "혜택별 선택 건수"},
        {"query": "high_risk_queue", "epsilon": 0.0, "sensitivity": 1, "release": "blocked", "note": "개별 상담 큐는 DP 집계 대상 아님"},
        {"query": "policy_impact", "epsilon": 0.8, "sensitivity": 1, "release": "approved", "note": "정책 변경 영향 집계"},
    ]


def dp_count(count: int, epsilon: float = 1.0, seed: int = 42) -> int:
    """Lightweight Laplace mechanism for demo aggregate counts."""
    if epsilon <= 0:
        return count
    random.seed(seed + count)
    u = random.random() - 0.5
    noise = -math.copysign(math.log(1 - 2 * abs(u)), u) / epsilon
    return max(0, int(round(count + noise)))


def synthetic_profiles(seed_profile: UserProfile, n: int = 8) -> List[Dict[str, Any]]:
    """Generate non-identifying synthetic demo profiles around one seed."""
    rows: List[Dict[str, Any]] = []
    for i in range(n):
        month = i % 6
        p = project_profile(seed_profile, month)
        age = max(18, min(90, p.age + ((i % 5) - 2)))
        rent = max(0, int(p.rent * (0.78 + 0.08 * (i % 6))))
        income = max(0, int(p.monthly_income * (0.8 + 0.1 * (i % 5))))
        token = hashlib.sha256(f"synthetic-{seed_profile.region}-{i}".encode()).hexdigest()[:10]
        rows.append({
            "synthetic_id": f"syn_{token}",
            "age": age,
            "region": p.region,
            "household_size": p.household_size,
            "employment_status": p.employment_status,
            "monthly_income": income,
            "rent": rent,
            "deposit": int(p.deposit),
            "unemployment_benefit_days_left": max(0, p.unemployment_benefit_days_left - 10 * i),
            "privacy_note": "synthetic_non_identifying_demo_record",
        })
    return rows


def privacy_security_pack(profile: UserProfile) -> Dict[str, Any]:
    fields = ["age", "region", "household_size", "monthly_income", "rent", "deposit"]
    access = check_access("counselor", "read:assigned", "eligibility_screening", fields)
    return {
        "access_decision": access,
        "privacy_budget": privacy_budget_table(),
        "synthetic_profiles": synthetic_profiles(profile),
        "dp_demo": {"true_count": 42, "epsilon": 0.7, "released_count": dp_count(42, epsilon=0.7)},
        "controls": [
            "purpose_based_access_control",
            "least_privilege_roles",
            "differential_privacy_for_public_aggregates",
            "synthetic_data_for_demo_and_testing",
            "audit_log_required_for_profile_access",
        ],
    }
