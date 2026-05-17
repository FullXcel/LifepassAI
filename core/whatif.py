"""Counterfactual and what-if analysis for application strategy."""
from __future__ import annotations

from dataclasses import replace
from typing import Any, Dict, Iterable, List

from .models import UserProfile
from .optimizer import optimize_benefits
from .rule_engine import evaluate_all
from .utils import money, normalize_profile


def _plan_value(profile: UserProfile, benefits: Iterable[Dict[str, Any]]) -> tuple[int, set[str]]:
    plan = optimize_benefits(evaluate_all(list(benefits), normalize_profile(profile)))
    return plan.total_monthly_value, {b.name for b in plan.selected}


def build_counterfactuals(profile: UserProfile, benefits: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    benefits_list = list(benefits)
    base_value, base_names = _plan_value(profile, benefits_list)
    scenarios = [
        ("예상 소득 발생을 1개월 늦춤", replace(profile, expected_income_start_month=profile.expected_income_start_month + 1)),
        ("월소득을 10만원 낮춘 구간", replace(profile, monthly_income=max(0, profile.monthly_income - 100_000))),
        ("월소득을 10만원 높인 구간", replace(profile, monthly_income=profile.monthly_income + 100_000)),
        ("월세 계약 증빙 확보", replace(profile, has_housing_contract=True, rent=max(profile.rent, 1))),
        ("직업훈련 희망 표시", replace(profile, wants_job_training=True)),
        ("위기사유 증빙 등록", replace(profile, crisis_event=True)),
    ]
    rows: List[Dict[str, Any]] = []
    for name, scenario_profile in scenarios:
        value, names = _plan_value(scenario_profile, benefits_list)
        gained = sorted(names - base_names)
        lost = sorted(base_names - names)
        rows.append({
            "scenario": name,
            "monthly_support": value,
            "delta": value - base_value,
            "delta_label": money(value - base_value),
            "gained": ", ".join(gained) or "-",
            "lost": ", ".join(lost) or "-",
        })
    rows.sort(key=lambda x: x["delta"], reverse=True)
    return rows
