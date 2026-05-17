"""Batch CSV analysis for LifePass AI.

This module turns CSV rows from an external institution into ``UserProfile``
objects, runs the same rule/optimizer/agent pipeline used by the single-user UI,
and returns an operations-ready 상담 큐 table.
"""
from __future__ import annotations

import io
from typing import Any, Dict, Iterable, List, Tuple

import pandas as pd

from .insights import compute_profile_insights
from .models import UserProfile
from .optimizer import optimize_benefits
from .rule_engine import evaluate_all
from .simulator import generate_timeline_events, simulate_income_cliff
from .utils import money, normalize_profile
from .validation import validate_profile

COLUMN_ALIASES: Dict[str, List[str]] = {
    "name": ["name", "성명", "이름", "profile_name", "고객명", "상담자"],
    "age": ["age", "나이", "만나이"],
    "region": ["region", "지역", "시도", "주소_시도"],
    "district": ["district", "시군구", "구", "주소_시군구"],
    "household_size": ["household_size", "가구원수", "가구원 수", "household"],
    "employment_status": ["employment_status", "고용상태", "취업상태", "employment"],
    "monthly_income": ["monthly_income", "현재월소득", "현재 월소득", "월소득", "income"],
    "expected_monthly_income": ["expected_monthly_income", "예상월소득", "예상 월소득", "future_income"],
    "expected_income_start_month": ["expected_income_start_month", "예상소득발생월", "소득발생월", "income_start_m"],
    "rent": ["rent", "월세", "monthly_rent"],
    "deposit": ["deposit", "보증금"],
    "assets_million": ["assets_million", "자산백만원", "자산(백만원)", "assets"],
    "unemployment_benefit_receiving": ["unemployment_benefit_receiving", "실업급여수급", "실업급여 수급 중"],
    "unemployment_benefit_days_left": ["unemployment_benefit_days_left", "실업급여잔여일", "실업급여 잔여일"],
    "crisis_event": ["crisis_event", "위기사유", "위기상황"],
    "medical_expense_3m": ["medical_expense_3m", "최근3개월의료비", "의료비"],
    "credit_score": ["credit_score", "신용점수"],
    "debt_monthly_payment": ["debt_monthly_payment", "월대출상환", "월 대출상환"],
    "is_basic_livelihood": ["is_basic_livelihood", "기초생활수급"],
    "is_near_poverty": ["is_near_poverty", "차상위", "취약계층"],
    "has_housing_contract": ["has_housing_contract", "임대차계약", "임대차계약 있음"],
    "wants_job_training": ["wants_job_training", "직업훈련희망", "훈련희망"],
}

BOOL_TRUE = {"1", "true", "t", "yes", "y", "예", "네", "있음", "수급", "수급중", "o", "○"}
BOOL_FALSE = {"0", "false", "f", "no", "n", "아니오", "아니요", "없음", "미수급", "x", "×"}

EMPLOYMENT_KO = {
    "무직": "unemployed",
    "실업": "unemployed",
    "구직": "job_seeker",
    "구직중": "job_seeker",
    "알바": "part_time",
    "파트타임": "part_time",
    "재직": "employed",
    "직장인": "employed",
    "프리랜서": "freelancer",
    "학생": "student",
}


def _first_value(row: Dict[str, Any], logical_name: str, default: Any = None) -> Any:
    for key in COLUMN_ALIASES.get(logical_name, [logical_name]):
        if key in row and pd.notna(row[key]) and row[key] != "":
            return row[key]
    return default


def _to_int(value: Any, default: int = 0) -> int:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return default
    if isinstance(value, str):
        cleaned = value.replace(",", "").replace("원", "").replace(" ", "")
        multiplier = 1
        if "만원" in cleaned:
            multiplier = 10_000
            cleaned = cleaned.replace("만원", "")
        elif cleaned.endswith("만"):
            multiplier = 10_000
            cleaned = cleaned[:-1]
        try:
            return int(float(cleaned) * multiplier)
        except ValueError:
            return default
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return default


def _to_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in BOOL_TRUE:
        return True
    if text in BOOL_FALSE:
        return False
    return default


def _employment(value: Any) -> str:
    text = str(value or "unemployed").strip()
    return EMPLOYMENT_KO.get(text, text if text else "unemployed")


def profile_from_row(row: Dict[str, Any]) -> Tuple[str, UserProfile, List[str]]:
    """Create a validated profile from a CSV row with Korean/English aliases."""
    name = str(_first_value(row, "name", "익명 사용자"))
    profile = UserProfile(
        age=_to_int(_first_value(row, "age", 27), 27),
        region=str(_first_value(row, "region", "서울")),
        district=str(_first_value(row, "district", "")),
        household_size=max(1, _to_int(_first_value(row, "household_size", 1), 1)),
        employment_status=_employment(_first_value(row, "employment_status", "unemployed")),
        monthly_income=_to_int(_first_value(row, "monthly_income", 0)),
        expected_monthly_income=_to_int(_first_value(row, "expected_monthly_income", 0)),
        expected_income_start_month=_to_int(_first_value(row, "expected_income_start_month", 3), 3),
        rent=_to_int(_first_value(row, "rent", 0)),
        deposit=_to_int(_first_value(row, "deposit", 0)),
        assets_million=_to_float(_first_value(row, "assets_million", 0.0)),
        unemployment_benefit_receiving=_to_bool(_first_value(row, "unemployment_benefit_receiving", False)),
        unemployment_benefit_days_left=_to_int(_first_value(row, "unemployment_benefit_days_left", 0)),
        crisis_event=_to_bool(_first_value(row, "crisis_event", False)),
        medical_expense_3m=_to_int(_first_value(row, "medical_expense_3m", 0)),
        credit_score=_to_int(_first_value(row, "credit_score", 750), 750),
        debt_monthly_payment=_to_int(_first_value(row, "debt_monthly_payment", 0)),
        is_basic_livelihood=_to_bool(_first_value(row, "is_basic_livelihood", False)),
        is_near_poverty=_to_bool(_first_value(row, "is_near_poverty", False)),
        has_housing_contract=_to_bool(_first_value(row, "has_housing_contract", True), True),
        wants_job_training=_to_bool(_first_value(row, "wants_job_training", True), True),
    )
    safe, warnings = validate_profile(profile)
    return name, normalize_profile(safe), warnings


def analyze_profiles(df: pd.DataFrame, benefits: Iterable[Dict[str, Any]]) -> Tuple[pd.DataFrame, List[UserProfile]]:
    """Analyze many external profiles and produce an operations table."""
    benefits_list = list(benefits)
    records: List[Dict[str, Any]] = []
    profiles: List[UserProfile] = []
    if df is None or df.empty:
        return pd.DataFrame(), []

    for idx, (_, row) in enumerate(df.iterrows(), start=1):
        name, profile, warnings = profile_from_row(row.to_dict())
        profiles.append(profile)
        evaluations = evaluate_all(benefits_list, profile)
        plan = optimize_benefits(evaluations)
        insights = compute_profile_insights(profile, benefits_list)
        cliff = simulate_income_cliff(profile, benefits_list)
        events = generate_timeline_events(profile, benefits_list)
        top_selected = [b.name for b in plan.selected[:3]]
        first_action = insights["recommended_actions"][0] if insights["recommended_actions"] else "월 1회 재판정"
        records.append({
            "row_id": idx,
            "name": name,
            "region": profile.region,
            "age": profile.age,
            "employment_status": profile.employment_status,
            "monthly_income": profile.monthly_income,
            "rent": profile.rent,
            "priority_score": insights["priority_score"],
            "priority_grade": insights["priority_grade"],
            "eligible_count": insights["eligible_count"],
            "selected_count": len(plan.selected),
            "monthly_support": plan.total_monthly_value,
            "cash_buffer": insights["cash_buffer"],
            "cliff_warnings": sum(1 for r in cliff if r.warnings),
            "top_benefits": ", ".join(top_selected) if top_selected else "해당 데이터 없음",
            "next_action": first_action,
            "next_event": events[0].title if events else "정기 재판정",
            "validation_warnings": " / ".join(warnings),
        })
    out = pd.DataFrame(records)
    if not out.empty:
        out = out.sort_values(["priority_score", "cliff_warnings", "monthly_support"], ascending=[False, False, False]).reset_index(drop=True)
    return out, profiles


def template_dataframe() -> pd.DataFrame:
    return pd.DataFrame([
        {
            "name": "서울 청년 A",
            "age": 27,
            "region": "서울",
            "household_size": 1,
            "employment_status": "unemployed",
            "monthly_income": 0,
            "expected_monthly_income": 800000,
            "expected_income_start_month": 3,
            "rent": 550000,
            "deposit": 5000000,
            "assets_million": 20,
            "unemployment_benefit_receiving": True,
            "unemployment_benefit_days_left": 45,
            "credit_score": 690,
            "debt_monthly_payment": 0,
            "has_housing_contract": True,
            "wants_job_training": True,
        },
        {
            "name": "부산 프리랜서 B",
            "age": 31,
            "region": "부산",
            "household_size": 1,
            "employment_status": "freelancer",
            "monthly_income": 1200000,
            "expected_monthly_income": 1800000,
            "expected_income_start_month": 6,
            "rent": 420000,
            "deposit": 3000000,
            "assets_million": 12,
            "unemployment_benefit_receiving": False,
            "unemployment_benefit_days_left": 0,
            "credit_score": 610,
            "debt_monthly_payment": 180000,
            "has_housing_contract": True,
            "wants_job_training": True,
        },
    ])


def template_csv_bytes() -> bytes:
    return template_dataframe().to_csv(index=False).encode("utf-8-sig")
