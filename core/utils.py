"""Utility helpers shared by LifePass AI modules."""
from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict

from .models import UserProfile

# Demo-only household median table. Replace with official table in production.
DEMO_MEDIAN_INCOME_BY_HOUSEHOLD = {
    1: 2228000,
    2: 3682000,
    3: 4715000,
    4: 5729000,
    5: 6695000,
}


def normalize_region(region: str) -> str:
    region = (region or "").strip()
    aliases = {
        "서울시": "서울",
        "서울특별시": "서울",
        "경기도": "경기",
        "인천광역시": "인천",
        "부산광역시": "부산",
        "대구광역시": "대구",
        "대전광역시": "대전",
        "광주광역시": "광주",
        "울산광역시": "울산",
        "세종특별자치시": "세종",
        "전라북도": "전북",
        "전북특별자치도": "전북",
        "전라남도": "전남",
        "충청북도": "충북",
        "충청남도": "충남",
        "경상북도": "경북",
        "경상남도": "경남",
        "강원특별자치도": "강원",
        "강원도": "강원",
        "제주특별자치도": "제주",
    }
    return aliases.get(region, region)


def estimate_income_percent(monthly_income: int, household_size: int) -> float:
    median = DEMO_MEDIAN_INCOME_BY_HOUSEHOLD.get(min(max(household_size, 1), 5), DEMO_MEDIAN_INCOME_BY_HOUSEHOLD[1])
    return round((monthly_income / median) * 100, 1)


def normalize_profile(profile: UserProfile) -> UserProfile:
    clone = deepcopy(profile)
    clone.region = normalize_region(clone.region)
    if clone.income_percent_median is None:
        clone.income_percent_median = estimate_income_percent(clone.monthly_income, clone.household_size)
    return clone


def project_profile(profile: UserProfile, month: int) -> UserProfile:
    """Project a profile into a future month.

    This is intentionally deterministic for demo/test repeatability. Future
    production versions can replace this with a probabilistic transition model.
    """
    projected = normalize_profile(profile)
    projected = deepcopy(projected)

    if projected.unemployment_benefit_receiving and projected.unemployment_benefit_days_left <= month * 30:
        projected.unemployment_benefit_receiving = False
        projected.unemployment_benefit_days_left = 0
        projected.has_recent_unemployment = True
        if projected.employment_status == "unemployed":
            projected.employment_status = "job_seeker"
    elif projected.unemployment_benefit_receiving:
        projected.unemployment_benefit_days_left = max(0, projected.unemployment_benefit_days_left - month * 30)

    if projected.expected_monthly_income and month >= projected.expected_income_start_month:
        projected.monthly_income = projected.expected_monthly_income
        if projected.employment_status in {"unemployed", "job_seeker"}:
            projected.employment_status = "part_time" if projected.expected_monthly_income < 1800000 else "employed"

    projected.income_percent_median = estimate_income_percent(projected.monthly_income, projected.household_size)
    return projected


def money(value: int | float) -> str:
    return f"{int(round(value)):,}원"


def profile_from_any(payload: Dict[str, Any] | UserProfile) -> UserProfile:
    if isinstance(payload, UserProfile):
        return payload
    return UserProfile.from_dict(payload)
