"""Reusable API contract examples for judges and integration demos."""
from __future__ import annotations

import json
from typing import Any, Dict

from .models import UserProfile


def profile_request_example() -> Dict[str, Any]:
    return {
        "profile": UserProfile().to_dict(),
        "question": "현재 받을 수 있는 혜택과 3개월 뒤 상실 위험을 알려줘",
    }


def response_example() -> Dict[str, Any]:
    return {
        "priority_score": 72,
        "priority_grade": "긴급",
        "monthly_support": 560000,
        "selected_benefits": ["청년월세 지원", "실업급여"],
        "actions": ["서류 준비", "소득 발생 월 재판정"],
    }


def examples_json() -> str:
    return json.dumps({"request": profile_request_example(), "response": response_example()}, ensure_ascii=False, indent=2)
