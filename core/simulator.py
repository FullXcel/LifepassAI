"""Future transition, benefit cliff, and timeline simulation."""
from __future__ import annotations

from dataclasses import replace
from typing import Dict, Iterable, List, Sequence

from .models import ScenarioResult, TimelineEvent, UserProfile
from .optimizer import optimize_benefits
from .rule_engine import evaluate_all
from .utils import estimate_income_percent, money, normalize_profile, project_profile

DEFAULT_CHECKPOINTS = [0, 1, 3, 6, 12]
DEFAULT_INCOME_SCENARIOS = [0, 600000, 800000, 1200000, 1800000, 2300000, 3000000]


def evaluate_month(profile: UserProfile, benefits: Iterable[Dict], month: int) -> ScenarioResult:
    projected = project_profile(profile, month)
    evaluations = evaluate_all(benefits, projected)
    plan = optimize_benefits(evaluations)
    warnings: List[str] = []
    for ev in evaluations:
        if ev.eligible:
            warnings.extend(ev.warnings)
    return ScenarioResult(
        label=f"{month}개월 후" if month else "현재",
        month=month,
        income=projected.monthly_income,
        benefit_value=plan.total_monthly_value,
        net_effect=projected.monthly_income + plan.total_monthly_value,
        selected_benefits=[b.name for b in plan.selected],
        warnings=sorted(set(warnings)),
    )


def simulate_timeline(profile: UserProfile, benefits: Iterable[Dict], checkpoints: Sequence[int] = DEFAULT_CHECKPOINTS) -> List[ScenarioResult]:
    results = [evaluate_month(profile, benefits, m) for m in checkpoints]
    prev_set = set(results[0].selected_benefits) if results else set()
    for idx, result in enumerate(results):
        if idx == 0:
            continue
        current = set(result.selected_benefits)
        result.gained = sorted(current - prev_set)
        result.lost = sorted(prev_set - current)
        prev_set = current
    return results


def simulate_income_cliff(profile: UserProfile, benefits: Iterable[Dict], incomes: Sequence[int] = DEFAULT_INCOME_SCENARIOS) -> List[ScenarioResult]:
    base = normalize_profile(profile)
    results: List[ScenarioResult] = []
    prev: ScenarioResult | None = None
    for income in incomes:
        status = base.employment_status
        if income > 0 and status in {"unemployed", "job_seeker"}:
            status = "part_time" if income < 1800000 else "employed"
        scenario_profile = replace(
            base,
            monthly_income=income,
            employment_status=status,
            unemployment_benefit_receiving=False if income > 0 else base.unemployment_benefit_receiving,
            income_percent_median=estimate_income_percent(income, base.household_size),
        )
        evaluations = evaluate_all(benefits, scenario_profile)
        plan = optimize_benefits(evaluations)
        result = ScenarioResult(
            label=f"월소득 {money(income)}",
            month=0,
            income=income,
            benefit_value=plan.total_monthly_value,
            net_effect=income + plan.total_monthly_value,
            selected_benefits=[b.name for b in plan.selected],
        )
        if prev:
            curr_set = set(result.selected_benefits)
            prev_set = set(prev.selected_benefits)
            result.gained = sorted(curr_set - prev_set)
            result.lost = sorted(prev_set - curr_set)
            income_gain = result.income - prev.income
            net_gain = result.net_effect - prev.net_effect
            if income_gain > 0 and net_gain < 0:
                result.warnings.append(
                    f"복지 절벽 감지: 명목소득은 {money(income_gain)} 증가했지만 순효과는 {money(abs(net_gain))} 감소"
                )
            elif result.lost and net_gain < income_gain * 0.5:
                result.warnings.append("혜택 상실로 순증가분이 크게 줄어듭니다.")
        results.append(result)
        prev = result
    return results


def generate_timeline_events(profile: UserProfile, benefits: Iterable[Dict]) -> List[TimelineEvent]:
    profile = normalize_profile(profile)
    events: List[TimelineEvent] = []

    if profile.unemployment_benefit_receiving and profile.unemployment_benefit_days_left > 0:
        days = profile.unemployment_benefit_days_left
        if days <= 60:
            events.append(TimelineEvent(
                month=0,
                title=f"실업급여 종료 D-{days}",
                description="실업급여 종료 후 취업지원제도 전환 가능성이 생기므로 종료 전 서류를 준비해야 합니다.",
                action_items=["수급 종료 예정일 확인", "구직활동 자료 정리", "국민취업지원제도 II유형 사전 상담", "월세/소득 증빙 파일 준비"],
                risk_level="warning",
            ))
        else:
            events.append(TimelineEvent(
                month=max(0, (days - 45) // 30),
                title="실업급여 종료 45일 전 알림 예약",
                description="종료 45일 전부터 전환 신청 준비를 시작하도록 예약합니다.",
                action_items=["전환 알림 설정", "취업지원서비스 비교", "훈련 희망 분야 정리"],
            ))

    monthly_results = simulate_timeline(profile, benefits, [0, 3, 6, 12])
    for result in monthly_results[1:]:
        if result.gained or result.lost:
            level = "danger" if result.lost and not result.gained else "success"
            events.append(TimelineEvent(
                month=result.month,
                title=f"{result.month}개월 후 자격 변화",
                description=f"새로 가능: {', '.join(result.gained) if result.gained else '없음'} / 상실 위험: {', '.join(result.lost) if result.lost else '없음'}",
                action_items=["변화된 소득·고용상태 재검토", "충돌 혜택 중 우선순위 재계산", "필요 서류 갱신"],
                risk_level=level,
            ))

    if profile.expected_monthly_income > 0:
        events.append(TimelineEvent(
            month=profile.expected_income_start_month,
            title="예상 소득 발생 시점",
            description="소득 발생으로 자산형성 혜택은 생기지만 일부 저소득 지원은 상실될 수 있습니다.",
            action_items=["근로계약/급여명세 확보", "청년내일저축·근로장려금 가능성 확인", "주거/생계성 혜택 상실 여부 재시뮬레이션"],
            risk_level="warning",
        ))

    if not events:
        events.append(TimelineEvent(
            month=0,
            title="현재 조건 기준 정기 재판정 권장",
            description="명확한 전환점이 입력되지 않았습니다. 소득·고용·주거 변화가 생기면 즉시 재시뮬레이션하세요.",
            action_items=["월 1회 프로필 업데이트", "소득 변화 입력", "지역 공고 확인"],
        ))

    return sorted(events, key=lambda e: e.month)


def build_application_strategy(profile: UserProfile, benefits: Iterable[Dict]) -> Dict[str, List[str]]:
    evaluations = evaluate_all(benefits, profile)
    plan = optimize_benefits(evaluations)
    strategy: Dict[str, List[str]] = {}
    for benefit in plan.selected:
        docs = benefit.required_docs or ["본인확인", "소득자료"]
        strategy[benefit.name] = [
            f"예상 월 환산효과: {money(benefit.monthly_value)}",
            "필요서류: " + ", ".join(docs),
            "충돌검토: " + ("/".join(benefit.conflicts_with) if benefit.conflicts_with else "명시적 충돌 없음"),
            "신청 전 실제 공고의 최신 자격조건을 확인하세요.",
        ]
    return strategy
