"""Causal intervention and quality-ops utilities for v5."""
from __future__ import annotations

from typing import Any, Dict, Iterable, List

from core.models import UserProfile


def estimate_intervention_effects(profile: UserProfile) -> Dict[str, Any]:
    """Heuristic uplift model for counseling interventions.

    This is not a black-box ML claim; it demonstrates how the platform would rank
    operational interventions using transparent features until real outcome data
    are available.
    """
    base_risk = 0.25
    base_risk += 0.18 if profile.monthly_income <= 0 else 0
    base_risk += 0.14 if profile.rent > max(profile.monthly_income * 0.35, 1) else 0
    base_risk += 0.16 if profile.unemployment_benefit_receiving and profile.unemployment_benefit_days_left <= 60 else 0
    base_risk += 0.10 if profile.crisis_event or profile.medical_expense_3m > 1_000_000 else 0
    base_risk = min(0.92, base_risk)
    interventions = [
        {"intervention": "상담사 1:1 신청 동행", "cost": 18000, "uplift": 0.18 if base_risk > 0.45 else 0.08, "why": "고위험/마감 임박 케이스의 신청 완료율 개선"},
        {"intervention": "서류 체크리스트 자동 발송", "cost": 1200, "uplift": 0.07, "why": "서류 누락에 의한 이탈 감소"},
        {"intervention": "D-7/D-1 마감 리마인더", "cost": 300, "uplift": 0.05 if profile.unemployment_benefit_days_left <= 45 else 0.025, "why": "신청 시점 누락 방지"},
        {"intervention": "근로·훈련 연계 안내", "cost": 2500, "uplift": 0.09 if profile.expected_monthly_income > 0 or profile.wants_job_training else 0.035, "why": "생애전환 시 신규 혜택 연결"},
    ]
    for row in interventions:
        row["expected_benefit_score"] = round((base_risk * row["uplift"] * 100000) - row["cost"], 1)
        row["roi_proxy"] = round(max(0, (base_risk * row["uplift"] * 100000) / max(row["cost"], 1)), 2)
    interventions.sort(key=lambda r: r["expected_benefit_score"], reverse=True)
    return {"base_dropoff_risk": round(base_risk, 3), "recommended_interventions": interventions, "method": "transparent_uplift_proxy_until_observed_outcomes"}


def data_contract() -> Dict[str, Any]:
    required = {
        "age": "integer[0,120]",
        "region": "string[korean_region]",
        "household_size": "integer[1,10]",
        "monthly_income": "integer[KRW>=0]",
        "rent": "integer[KRW>=0]",
    }
    optional = {
        "expected_monthly_income": "integer[KRW>=0]",
        "unemployment_benefit_days_left": "integer>=0",
        "credit_score": "integer[0,1000]",
        "medical_expense_3m": "integer[KRW>=0]",
    }
    checks = [
        {"check": "schema_required_columns", "status": "enforced"},
        {"check": "unit_detection_krw_vs_manwon", "status": "enforced_in_mapper"},
        {"check": "outlier_warning_not_crash", "status": "enforced"},
        {"check": "null_safe_defaults", "status": "enforced"},
        {"check": "policy_rule_schema_validation", "status": "enforced"},
    ]
    return {"contract_name": "LifePassUserProfile.v1", "required": required, "optional": optional, "checks": checks}


def model_card() -> Dict[str, Any]:
    return {
        "name": "LifePass deterministic eligibility + agentic operations",
        "decision_boundary": "자격 판정은 룰엔진이 수행하며 LLM은 설명·요약·상담 보조에만 사용",
        "intended_use": ["복지 혜택 사전 탐색", "상담사 업무 큐 생성", "정책 변경 영향 시뮬레이션"],
        "not_for": ["법적 최종 수급 판정", "서류 심사 대체", "민감정보 기반 차별적 선별"],
        "human_review": "고위험/고액/불확실 케이스는 상담사 승인 큐로 전환",
        "monitoring": ["추천 충돌 위반률", "누락 혜택율", "상담 완료율", "정책 버전 변경 영향"],
    }


def sla_incident_playbook() -> List[Dict[str, Any]]:
    return [
        {"signal": "policy_api_failure_rate > 10%", "severity": "medium", "fallback": "cached_policy_catalog", "owner": "policy_ops"},
        {"signal": "agent_human_review_rate > 35%", "severity": "medium", "fallback": "rule_only_mode", "owner": "ai_ops"},
        {"signal": "conflict_violation_rate > 0", "severity": "high", "fallback": "block_recommendation_release", "owner": "quality"},
        {"signal": "db_write_latency_p95 > 500ms", "severity": "medium", "fallback": "outbox_buffering", "owner": "platform"},
    ]


def quality_ops_pack() -> Dict[str, Any]:
    return {"data_contract": data_contract(), "model_card": model_card(), "sla_playbook": sla_incident_playbook()}
