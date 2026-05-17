"""Policy impact digital twin for v5.

Simulates how a proposed policy change affects sample citizens, budget, and
benefit-cliff risk before the policy is published.
"""
from __future__ import annotations

import copy
from typing import Any, Dict, Iterable, List

from core.models import UserProfile
from core.optimizer import optimize_benefits
from core.rule_engine import evaluate_all


def _patch_youth_age_rule(benefit: Dict[str, Any], max_age: int) -> Dict[str, Any]:
    b = copy.deepcopy(benefit)
    for clause in b.get("rule", {}).get("all", []):
        label = str(clause.get("label", ""))
        if clause.get("field") == "age" and clause.get("op") == "between" and isinstance(clause.get("value"), list):
            if "청년" in b.get("name", "") or "youth" in b.get("id", "") or "만" in label:
                clause["value"] = [int(clause["value"][0]), int(max_age)]
                clause["label"] = f"만 {clause['value'][0]}~{max_age}세"
    return b


def build_policy_scenario(benefits: List[Dict[str, Any]], *, age_upper: int = 39, value_multiplier: float = 1.0) -> List[Dict[str, Any]]:
    scenario = []
    for benefit in benefits:
        patched = _patch_youth_age_rule(benefit, age_upper)
        if "청년" in patched.get("name", "") or "youth" in patched.get("id", ""):
            patched["estimated_monthly_value"] = int(float(patched.get("estimated_monthly_value", 0)) * value_multiplier)
            patched.setdefault("provenance", {})["scenario"] = f"youth_age_upper_{age_upper}_value_x_{value_multiplier}"
        scenario.append(patched)
    return scenario


def simulate_policy_impact(profiles: Iterable[UserProfile], benefits: List[Dict[str, Any]], *, age_upper: int = 39, value_multiplier: float = 1.0) -> Dict[str, Any]:
    scenario_benefits = build_policy_scenario(benefits, age_upper=age_upper, value_multiplier=value_multiplier)
    rows: List[Dict[str, Any]] = []
    total_delta = 0
    newly_supported = 0
    lost_support = 0
    for idx, profile in enumerate(profiles, start=1):
        base_plan = optimize_benefits(evaluate_all(benefits, profile))
        new_plan = optimize_benefits(evaluate_all(scenario_benefits, profile))
        delta = int(new_plan.total_monthly_value - base_plan.total_monthly_value)
        total_delta += delta
        if base_plan.total_monthly_value == 0 and new_plan.total_monthly_value > 0:
            newly_supported += 1
        if base_plan.total_monthly_value > 0 and new_plan.total_monthly_value == 0:
            lost_support += 1
        rows.append({
            "case_id": f"case_{idx:03d}",
            "age": profile.age,
            "region": profile.region,
            "base_support": base_plan.total_monthly_value,
            "scenario_support": new_plan.total_monthly_value,
            "delta": delta,
            "base_selected": len(base_plan.selected),
            "scenario_selected": len(new_plan.selected),
            "impact": "신규/증가" if delta > 0 else ("감소" if delta < 0 else "변화없음"),
        })
    count = max(len(rows), 1)
    return {
        "scenario": {"youth_age_upper": age_upper, "value_multiplier": value_multiplier},
        "metrics": {
            "profiles_simulated": len(rows),
            "newly_supported": newly_supported,
            "lost_support": lost_support,
            "monthly_budget_delta": total_delta,
            "annualized_budget_delta": total_delta * 12,
            "average_delta_per_profile": round(total_delta / count, 1),
        },
        "rows": rows,
        "decision_use": "정책 시행 전 영향받는 대상자 수, 예산 변화, 신규 지원 규모를 사전 검증",
    }
