"""Actionable insights built on top of the deterministic rule engine."""
from __future__ import annotations

from typing import Dict, Iterable, List

from .models import BenefitEvaluation, UserProfile
from .optimizer import optimize_benefits
from .rule_engine import evaluate_all
from .simulator import simulate_income_cliff, simulate_timeline
from .utils import money, normalize_profile


def _risk_grade(score: int) -> str:
    if score >= 70:
        return "긴급"
    if score >= 45:
        return "주의"
    return "안정"


def compute_profile_insights(profile: UserProfile, benefits: Iterable[Dict]) -> Dict:
    """Compute competition-demo friendly summary metrics.

    The score is not a legal/credit score. It is an explainable operational
    priority index for triage: income gap, cliff risk, rent burden, credit
    fragility and upcoming eligibility change are combined deterministically.
    """
    profile = normalize_profile(profile)
    benefits_list = list(benefits)
    evaluations = evaluate_all(benefits_list, profile)
    plan = optimize_benefits(evaluations)
    timeline = simulate_timeline(profile, benefits_list, [0, 1, 3, 6, 12])
    cliff = simulate_income_cliff(profile, benefits_list)

    warnings = [w for row in cliff for w in row.warnings]
    lost_next = sorted({name for row in timeline[1:3] for name in row.lost})
    gained_next = sorted({name for row in timeline[1:3] for name in row.gained})
    rent_burden = round((profile.rent / max(1, profile.monthly_income + plan.total_monthly_value)) * 100, 1)
    cash_buffer = profile.monthly_income + plan.total_monthly_value - profile.rent - profile.debt_monthly_payment

    score = 0
    reasons: List[str] = []
    if profile.monthly_income == 0:
        score += 18
        reasons.append("현재 소득 공백")
    if profile.unemployment_benefit_receiving and profile.unemployment_benefit_days_left <= 60:
        score += 22
        reasons.append(f"실업급여 종료 D-{profile.unemployment_benefit_days_left}")
    if rent_burden >= 45:
        score += 18
        reasons.append(f"주거비 부담 {rent_burden}%")
    if profile.credit_score and profile.credit_score < 650:
        score += 10
        reasons.append("낮은 신용점수")
    if lost_next:
        score += 18
        reasons.append("1~3개월 내 상실 가능 혜택 존재")
    if warnings:
        score += 24
        reasons.append("복지 절벽 경고 발생")
    if profile.crisis_event:
        score += 15
        reasons.append("위기사유 입력")
    score = min(100, score)

    actions = recommend_next_actions(profile, plan.selected, lost_next, warnings)
    return {
        "priority_score": score,
        "priority_grade": _risk_grade(score),
        "reasons": reasons or ["즉시 감지된 고위험 신호는 낮음"],
        "current_support": plan.total_monthly_value,
        "selected_count": len(plan.selected),
        "eligible_count": sum(1 for ev in evaluations if ev.eligible),
        "rent_burden_percent": rent_burden,
        "cash_buffer": cash_buffer,
        "lost_next": lost_next,
        "gained_next": gained_next,
        "cliff_warning_count": len(warnings),
        "recommended_actions": actions,
    }


def recommend_next_actions(profile: UserProfile, selected: List[BenefitEvaluation], lost_next: List[str], cliff_warnings: List[str]) -> List[str]:
    actions: List[str] = []
    if profile.unemployment_benefit_receiving and profile.unemployment_benefit_days_left <= 60:
        actions.append("실업급여 종료 전 국민취업지원제도·직업훈련 전환 상담 예약")
    if any(b.domain == "주거" for b in selected):
        actions.append("임대차계약서·월세 이체내역·주민등록등본을 먼저 준비")
    if profile.expected_monthly_income > 0:
        actions.append("예상 소득 발생 월에 맞춰 근로계약서/급여명세와 자산형성 혜택을 재판정")
    if lost_next:
        actions.append("1~3개월 내 상실 위험 혜택을 기준으로 신청 순서 재조정")
    if cliff_warnings:
        actions.append("소득 증가 전후 순효과가 줄어드는 구간을 피하도록 근로시간·신청시점 시뮬레이션")
    if not actions:
        actions.append("월 1회 프로필 업데이트 후 신규 공고와 지자체 혜택 재탐색")
    return actions[:5]


def make_document_checklist(selected: List[BenefitEvaluation]) -> List[Dict[str, str]]:
    docs: Dict[str, List[str]] = {}
    for benefit in selected:
        for doc in benefit.required_docs or ["본인확인", "소득자료"]:
            docs.setdefault(doc, []).append(benefit.name)
    return [
        {"서류": doc, "관련 혜택": ", ".join(names), "상태": "준비 필요"}
        for doc, names in sorted(docs.items(), key=lambda x: (-len(x[1]), x[0]))
    ]
