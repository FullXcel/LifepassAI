"""Human-readable report generation for app and CLI."""
from __future__ import annotations

from typing import Dict, Iterable, List

from .models import ScenarioResult, UserProfile
from .optimizer import optimize_benefits
from .rag import explain_with_evidence
from .rule_engine import evaluate_all
from .simulator import build_application_strategy, generate_timeline_events, simulate_income_cliff, simulate_timeline
from .utils import money, normalize_profile


def make_markdown_report(profile: UserProfile, benefits: Iterable[Dict]) -> str:
    profile = normalize_profile(profile)
    benefits = list(benefits)
    evaluations = evaluate_all(benefits, profile)
    plan = optimize_benefits(evaluations)
    timeline = simulate_timeline(profile, benefits)
    cliff = simulate_income_cliff(profile, benefits)
    events = generate_timeline_events(profile, benefits)
    strategy = build_application_strategy(profile, benefits)

    lines: List[str] = []
    lines.append("# LifePass AI 분석 리포트")
    lines.append("")
    lines.append(f"- 프로필: 만 {profile.age}세 / {profile.region} / {profile.household_size}인가구 / {profile.employment_status}")
    lines.append(f"- 현재 월소득: {money(profile.monthly_income)} / 월세: {money(profile.rent)} / 기준중위소득 비율(데모): {profile.income_percent_median}%")
    lines.append("")
    lines.append("## 1. 현재 최적 혜택 조합")
    if plan.selected:
        for b in plan.selected:
            lines.append(f"- {b.name}: {money(b.monthly_value)} / {b.domain}")
    else:
        lines.append("- 현재 확정 추천 조합 없음")
    lines.append(f"- 월 환산효과 합계: {money(plan.total_monthly_value)}")
    lines.append("")
    lines.append("## 2. 충돌/중복 처리")
    for e in plan.explanation:
        lines.append(f"- {e}")
    lines.append("")
    lines.append("## 3. 생애전환 타임라인")
    for row in timeline:
        gained = ", ".join(row.gained) if row.gained else "없음"
        lost = ", ".join(row.lost) if row.lost else "없음"
        lines.append(f"- {row.label}: 소득 {money(row.income)}, 혜택 {money(row.benefit_value)}, 순효과 {money(row.net_effect)} / 신규 {gained} / 상실 {lost}")
    lines.append("")
    lines.append("## 4. 복지 절벽 시뮬레이션")
    for row in cliff:
        warn = " / ".join(row.warnings) if row.warnings else ""
        lines.append(f"- {row.label}: 혜택 {money(row.benefit_value)}, 순효과 {money(row.net_effect)} {warn}")
    lines.append("")
    lines.append("## 5. 실행 타임라인")
    for ev in events:
        lines.append(f"- M+{ev.month} [{ev.risk_level}] {ev.title}: {ev.description}")
        for action in ev.action_items:
            lines.append(f"  - {action}")
    lines.append("")
    lines.append("## 6. 신청 준비 체크리스트")
    for benefit_name, items in strategy.items():
        lines.append(f"### {benefit_name}")
        for item in items:
            lines.append(f"- {item}")
    lines.append("")
    lines.append("## 7. 근거 검색 요약")
    lines.append(explain_with_evidence("복지절벽 실업급여 청년월세 국민취업지원 소득"))
    lines.append("")
    lines.append("> 주의: 본 MVP의 혜택 DB와 기준값은 대회 시연용 데모 데이터입니다. 실제 서비스에서는 복지로·정부24·고용24 등 최신 공고/API와 기관 검증 절차를 연결해야 합니다.")
    return "\n".join(lines)
