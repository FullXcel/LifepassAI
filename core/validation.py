"""Profile validation and guardrails for UI/runtime safety.

The Streamlit layer can crash when a widget receives a value outside its
min/max range. Natural-language parsing is intentionally permissive, so all
parsed or uploaded profiles pass through this module before being rendered.
"""
from __future__ import annotations

from dataclasses import replace
from typing import Dict, List, Tuple

from .models import UserProfile
from .utils import normalize_region

HARD_LIMITS: Dict[str, Tuple[int | float, int | float]] = {
    "age": (0, 120),
    "household_size": (1, 10),
    "monthly_income": (0, 50_000_000),
    "expected_monthly_income": (0, 50_000_000),
    "expected_income_start_month": (0, 60),
    "rent": (0, 20_000_000),
    "deposit": (0, 5_000_000_000),
    "assets_million": (0, 1_000_000),
    "unemployment_benefit_days_left": (0, 3650),
    "medical_expense_3m": (0, 500_000_000),
    "credit_score": (0, 1000),
    "debt_monthly_payment": (0, 50_000_000),
}

SOFT_WARNINGS: Dict[str, Tuple[int | float, str]] = {
    "rent": (3_000_000, "월세가 300만원을 초과합니다. 월세와 보증금이 뒤바뀐 값은 아닌지 확인하세요."),
    "monthly_income": (20_000_000, "현재 월소득이 매우 큽니다. 원/만원 단위가 맞는지 확인하세요."),
    "expected_monthly_income": (20_000_000, "예상 월소득이 매우 큽니다. 원/만원 단위가 맞는지 확인하세요."),
    "deposit": (1_000_000_000, "보증금이 10억원을 초과합니다. 단위가 맞는지 확인하세요."),
    "medical_expense_3m": (50_000_000, "최근 3개월 의료비가 매우 큽니다. 입력 단위를 확인하세요."),
    "debt_monthly_payment": (10_000_000, "월 대출상환액이 매우 큽니다. 입력 단위를 확인하세요."),
}

VALID_EMPLOYMENT = {"unemployed", "job_seeker", "part_time", "employed", "freelancer", "student"}


def _to_number(value: object, default: int | float) -> int | float:
    if value is None:
        return default
    try:
        if isinstance(default, int):
            return int(float(value))
        return float(value)
    except (TypeError, ValueError):
        return default


def _clamp(value: int | float, lo: int | float, hi: int | float) -> int | float:
    return max(lo, min(hi, value))


def validate_profile(profile: UserProfile) -> tuple[UserProfile, List[str]]:
    """Return a safe profile plus human-readable validation warnings."""
    warnings: List[str] = []
    data = profile.to_dict()

    for field, (lo, hi) in HARD_LIMITS.items():
        original = data.get(field)
        default = getattr(UserProfile(), field)
        value = _to_number(original, default)
        safe = _clamp(value, lo, hi)
        if safe != value:
            warnings.append(f"{field} 값 {original!r}을(를) 허용 범위 {lo:,}~{hi:,} 안으로 보정했습니다.")
        data[field] = int(safe) if isinstance(default, int) else float(safe)

    data["region"] = normalize_region(str(data.get("region") or "서울"))
    if data.get("employment_status") not in VALID_EMPLOYMENT:
        warnings.append(f"고용상태 {data.get('employment_status')!r}을(를) unemployed로 보정했습니다.")
        data["employment_status"] = "unemployed"

    if data["credit_score"] and data["credit_score"] < 300:
        warnings.append("신용점수가 300 미만입니다. 실제 KCB/NICE 점수 체계의 범위가 맞는지 확인하세요.")

    for field, (threshold, message) in SOFT_WARNINGS.items():
        if data.get(field, 0) > threshold:
            warnings.append(message)

    if data["monthly_income"] == 0 and data["expected_monthly_income"] > 0 and data["expected_income_start_month"] == 0:
        warnings.append("예상 소득 발생 월이 0개월로 입력되어 현재 소득과 같은 시점으로 해석될 수 있습니다.")

    return UserProfile.from_dict(data), warnings


def safe_widget_bounds(value: int | float, minimum: int | float, maximum: int | float, *, pad_ratio: float = 0.2) -> tuple[int | float, int | float, int | float]:
    """Return min/max/value that never violates Streamlit widget constraints.

    If a parsed/uploaded value is above the nominal UI maximum, the max is
    expanded instead of crashing. This is the direct fix for
    StreamlitValueAboveMaxError.
    """
    try:
        v = type(minimum)(value)
    except Exception:
        v = minimum
    if v < minimum:
        v = minimum
    dynamic_max = maximum
    if v > maximum:
        dynamic_max = v + max(1, int(abs(v) * pad_ratio))
    return minimum, dynamic_max, v
