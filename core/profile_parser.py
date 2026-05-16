"""Lightweight Korean natural-language onboarding parser.

This parser is deliberately deterministic and dependency-free. It extracts the
fields needed for the MVP from short KakaoTalk-style messages, then the UI lets
users edit the structured profile.
"""
from __future__ import annotations

import re
from typing import Dict

from .models import UserProfile
from .utils import normalize_region
from .validation import validate_profile

REGION_KEYWORDS = ["서울", "경기", "인천", "부산", "대구", "대전", "광주", "울산", "세종", "전북", "전남", "충북", "충남", "경북", "경남", "강원", "제주"]


def _money_to_int(text: str, *, default_unit: str = "원") -> int:
    """Convert Korean money expressions into KRW.

    In welfare 상담 문장에서는 "월세 55", "보증금 500"처럼 단위를 생략하면
    보통 만원 단위로 말한다. keyword-specific 파싱에서는 default_unit="만원"을
    사용해 이런 입력을 안전하게 처리한다.
    """
    text = text.replace(",", "").strip()
    m = re.search(r"(\d+(?:\.\d+)?)\s*(만원|천원|원)?", text)
    if not m:
        return 0
    value = float(m.group(1))
    unit = m.group(2)
    if unit is None:
        unit = default_unit
    if unit == "만원":
        return int(value * 10000)
    if unit == "천원":
        return int(value * 1000)
    return int(value)

def parse_onboarding_text(text: str) -> UserProfile:
    t = text.strip()
    profile: Dict[str, object] = {}

    age = re.search(r"(?:만\s*)?(\d{2})\s*(?:세|살)", t)
    if age:
        profile["age"] = int(age.group(1))

    for region in REGION_KEYWORDS:
        if region in t:
            profile["region"] = normalize_region(region)
            break

    household = re.search(r"(\d+)\s*인\s*가구", t)
    if household:
        profile["household_size"] = int(household.group(1))
    elif "혼자" in t or "자취" in t or "1인가구" in t:
        profile["household_size"] = 1

    if any(word in t for word in ["실업급여", "구직급여"]):
        profile["unemployment_benefit_receiving"] = True
        profile["employment_status"] = "unemployed"
    if any(word in t for word in ["실직", "퇴사", "무직"]):
        profile["employment_status"] = "unemployed"
        profile["has_recent_unemployment"] = True
    if any(word in t for word in ["취준", "구직"]):
        profile["employment_status"] = "job_seeker"
    if any(word in t for word in ["알바", "아르바이트", "파트타임"]):
        profile["employment_status"] = "part_time"
    if any(word in t for word in ["프리랜서", "프리"]):
        profile["employment_status"] = "freelancer"
    if any(word in t for word in ["직장인", "정규직", "계약직"]):
        profile["employment_status"] = "employed"
    if any(word in t for word in ["학생", "대학생", "휴학생"]):
        profile["employment_status"] = "student"

    days_left = re.search(r"(?:실업급여|구직급여|수급)[^,.。\n]{0,20}?(\d+)\s*일", t)
    if days_left:
        profile["unemployment_benefit_days_left"] = int(days_left.group(1))
    month_left = re.search(r"(?:실업급여|구직급여|수급)[^,.。\n]{0,20}?(\d+)\s*개월", t)
    if month_left and "unemployment_benefit_days_left" not in profile:
        profile["unemployment_benefit_days_left"] = int(month_left.group(1)) * 30

    # Future income phrases are parsed before current income to avoid treating
    # "3개월 뒤 알바 월소득 80만원" as current income.
    future_income = re.search(
        r"(\d+)\s*개월\s*(?:뒤|후)[^,.。\n]{0,40}?(?:월소득|소득|수입|월급)?\s*(\d+(?:\.\d+)?\s*(?:만원|천원|원))",
        t,
    )
    future_span = None
    if future_income:
        profile["expected_income_start_month"] = int(future_income.group(1))
        profile["expected_monthly_income"] = _money_to_int(future_income.group(2), default_unit="만원")
        future_span = future_income.span()

    current_text = t
    if future_span:
        current_text = t[:future_span[0]] + t[future_span[1]:]
    income = re.search(r"(?:현재\s*)?(?:월소득|소득|수입|월급)\s*(?:은|이|:)?\s*(\d+(?:\.\d+)?\s*(?:만원|천원|원)?)", current_text)
    if income:
        profile["monthly_income"] = _money_to_int(income.group(1), default_unit="만원")
    elif any(word in current_text for word in ["소득 없음", "소득없음", "무소득", "월소득 0", "소득 0"]):
        profile["monthly_income"] = 0

    if "expected_monthly_income" not in profile:
        expected = re.search(r"(?:예정|예상|시작)[^,.。\n]{0,40}?(\d+(?:\.\d+)?\s*(?:만원|천원|원))", t)
        if expected:
            profile["expected_monthly_income"] = _money_to_int(expected.group(1), default_unit="만원")

    expected_month = re.search(r"(\d+)\s*개월\s*(?:뒤|후).*?(?:알바|취업|소득|수입|월급)", t)
    if expected_month and "expected_income_start_month" not in profile:
        profile["expected_income_start_month"] = int(expected_month.group(1))

    rent = re.search(r"(?:월세|임대료)\s*(?:는|가|:)?\s*(\d+(?:\.\d+)?\s*(?:만원|천원|원)?)", t)
    if rent:
        profile["rent"] = _money_to_int(rent.group(1), default_unit="만원")
        profile["has_housing_contract"] = True

    deposit = re.search(r"(?:보증금)\s*(?:은|이|:)?\s*(\d+(?:\.\d+)?\s*(?:만원|천원|원)?)", t)
    if deposit:
        profile["deposit"] = _money_to_int(deposit.group(1), default_unit="만원")

    medical = re.search(r"(?:의료비|병원비)\s*(?:가|는|:)?\s*(\d+(?:\.\d+)?\s*(?:만원|천원|원)?)", t)
    if medical:
        profile["medical_expense_3m"] = _money_to_int(medical.group(1), default_unit="만원")

    credit = re.search(r"(?:신용점수|신용)\s*(?:는|이|:)?\s*(\d{3,4})", t)
    if credit:
        profile["credit_score"] = int(credit.group(1))

    debt = re.search(r"(?:상환|대출상환|월상환)\s*(?:은|이|:)?\s*(\d+(?:\.\d+)?\s*(?:만원|천원|원)?)", t)
    if debt:
        profile["debt_monthly_payment"] = _money_to_int(debt.group(1), default_unit="만원")

    if any(word in t for word in ["위기", "생계곤란", "긴급", "월세밀림", "연체"]):
        profile["crisis_event"] = True
    if "기초생활" in t or "수급자" in t:
        profile["is_basic_livelihood"] = True
    if "차상위" in t:
        profile["is_near_poverty"] = True
    if any(word in t for word in ["훈련", "교육", "직업훈련", "자격증"]):
        profile["wants_job_training"] = True

    # If the message says the user is currently receiving unemployment benefit,
    # future work phrases such as "3개월 뒤 알바" must not overwrite the current
    # employment state.
    if profile.get("unemployment_benefit_receiving") and profile.get("employment_status") in {None, "part_time", "employed", "freelancer"}:
        profile["employment_status"] = "unemployed"

    profile["notes"] = t
    parsed = UserProfile.from_dict(profile)
    parsed, _ = validate_profile(parsed)
    return parsed
