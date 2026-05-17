"""Smart schema mapper for external CSV datasets."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Tuple

import pandas as pd

from .models import UserProfile
from .validation import validate_profile

STANDARD_FIELDS: Dict[str, List[str]] = {
    "age": ["age", "나이", "만나이", "연령", "user_age"],
    "region": ["region", "지역", "시도", "주소", "거주지역", "city"],
    "household_size": ["household_size", "가구원수", "가구원", "household", "family_size"],
    "employment_status": ["employment_status", "고용상태", "직업상태", "취업상태", "job_status"],
    "monthly_income": ["monthly_income", "월소득", "소득", "income", "salary", "income_krw"],
    "expected_monthly_income": ["expected_monthly_income", "예상월소득", "예상 소득", "future_income"],
    "rent": ["rent", "월세", "월임대료", "housing_cost", "monthly_rent", "rent_fee"],
    "deposit": ["deposit", "보증금", "임대보증금", "security_deposit"],
    "unemployment_benefit_days_left": ["unemployment_benefit_days_left", "실업급여잔여일", "잔여일", "days_left"],
    "credit_score": ["credit_score", "신용점수", "credit", "kcb", "nice_score"],
    "debt_monthly_payment": ["debt_monthly_payment", "월상환", "대출상환", "debt_payment"],
}

BOOL_FIELDS = {"unemployment_benefit_receiving", "crisis_event", "is_basic_livelihood", "is_near_poverty", "has_housing_contract", "wants_job_training"}


def _norm(s: str) -> str:
    return re.sub(r"[^0-9a-zA-Z가-힣]+", "", str(s)).lower()


def infer_mapping(columns: Iterable[str]) -> Tuple[Dict[str, str], List[Dict[str, Any]]]:
    columns = list(columns)
    normalized = {_norm(c): c for c in columns}
    mapping: Dict[str, str] = {}
    suggestions: List[Dict[str, Any]] = []
    for field, aliases in STANDARD_FIELDS.items():
        best = None
        best_score = 0
        for alias in aliases:
            na = _norm(alias)
            for nc, original in normalized.items():
                score = 0
                if na == nc:
                    score = 100
                elif na in nc or nc in na:
                    score = 80
                elif any(tok and tok in nc for tok in re.split(r"[_\s]+", alias.lower())):
                    score = 55
                if score > best_score:
                    best = original
                    best_score = score
        if best:
            mapping[field] = best
            suggestions.append({"standard_field": field, "source_column": best, "confidence": best_score})
        else:
            suggestions.append({"standard_field": field, "source_column": "", "confidence": 0})
    return mapping, suggestions


def _to_int_money(v: Any) -> int:
    if pd.isna(v):
        return 0
    raw = str(v).strip().replace(",", "")
    if not raw:
        return 0
    has_manwon = "만원" in raw or "만" in raw
    nums = re.findall(r"-?\d+(?:\.\d+)?", raw)
    if not nums:
        return 0
    val = float(nums[0])
    if has_manwon or (0 < val < 10000 and any(key in raw for key in ["소득", "월세", "보증금", "상환"])):
        val *= 10000
    return int(val)


def _clean_value(field: str, value: Any) -> Any:
    if field in {"monthly_income", "expected_monthly_income", "rent", "deposit", "debt_monthly_payment"}:
        return _to_int_money(value)
    if field in {"age", "household_size", "unemployment_benefit_days_left", "credit_score"}:
        try:
            return int(float(str(value).replace(",", "")))
        except Exception:
            return 0
    if field == "employment_status":
        text = str(value).lower()
        if any(k in text for k in ["무직", "실업", "unemployed"]):
            return "unemployed"
        if any(k in text for k in ["구직", "job"]):
            return "job_seeker"
        if any(k in text for k in ["학생", "student"]):
            return "student"
        if any(k in text for k in ["알바", "part"]):
            return "part_time"
        return "employed"
    return value


def map_dataframe_to_profiles(df: pd.DataFrame, mapping: Dict[str, str] | None = None) -> Tuple[List[UserProfile], pd.DataFrame, List[str]]:
    mapping = mapping or infer_mapping(df.columns)[0]
    profiles: List[UserProfile] = []
    warnings: List[str] = []
    rows: List[Dict[str, Any]] = []
    for idx, row in df.iterrows():
        payload: Dict[str, Any] = {}
        for field, col in mapping.items():
            if col in df.columns:
                payload[field] = _clean_value(field, row[col])
        if "unemployment_benefit_days_left" in payload and payload["unemployment_benefit_days_left"] > 0:
            payload["unemployment_benefit_receiving"] = True
        try:
            profile, ws = validate_profile(UserProfile.from_dict(payload))
            profiles.append(profile)
            rows.append({"row": int(idx) + 1, **profile.to_dict(), "warning_count": len(ws)})
            warnings.extend([f"row {idx + 1}: {w}" for w in ws])
        except Exception as exc:
            warnings.append(f"row {idx + 1}: 프로필 변환 실패 - {exc}")
    return profiles, pd.DataFrame(rows), warnings
