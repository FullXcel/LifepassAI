"""Deterministic AI-agent style orchestration.

No black-box LLM is required for the MVP.  Instead, the agent exposes an
explainable tool plan: validate profile -> eligibility -> optimizer -> timeline
-> cliff simulation -> evidence retrieval -> action queue.  This makes the demo
look like an AI agent while keeping decisions reproducible for judges.
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, List

from .insights import compute_profile_insights, make_document_checklist
from .models import UserProfile
from .optimizer import optimize_benefits
from .rag import retrieve
from .rule_engine import evaluate_all
from .simulator import build_application_strategy, generate_timeline_events, simulate_income_cliff, simulate_timeline
from .utils import money, normalize_profile
from .validation import validate_profile


def _tool(name: str, status: str, detail: str) -> Dict[str, str]:
    return {"tool": name, "status": status, "detail": detail}


def build_agent_plan(profile: UserProfile, benefits: Iterable[Dict[str, Any]], question: str = "") -> Dict[str, Any]:
    benefits_list = list(benefits)
    tool_trace: List[Dict[str, str]] = []
    safe_profile, warnings = validate_profile(profile)
    safe_profile = normalize_profile(safe_profile)
    tool_trace.append(_tool("validate_profile", "ok", f"입력값 검증 완료, 경고 {len(warnings)}건"))

    evaluations = evaluate_all(benefits_list, safe_profile)
    eligible = [ev for ev in evaluations if ev.eligible]
    tool_trace.append(_tool("eligibility_rule_engine", "ok", f"{len(evaluations)}개 정책 중 {len(eligible)}개 가능"))

    plan = optimize_benefits(evaluations)
    tool_trace.append(_tool("conflict_aware_optimizer", "ok", f"충돌 제거 후 {len(plan.selected)}개 선택, 월 {money(plan.total_monthly_value)}"))

    timeline = simulate_timeline(safe_profile, benefits_list, [0, 1, 3, 6, 12])
    transition_count = sum(len(t.gained) + len(t.lost) for t in timeline)
    tool_trace.append(_tool("life_transition_simulator", "ok", f"1/3/6/12개월 변화 {transition_count}건 탐지"))

    cliff = simulate_income_cliff(safe_profile, benefits_list)
    cliff_warning_count = sum(1 for row in cliff if row.warnings)
    tool_trace.append(_tool("benefit_cliff_detector", "ok", f"복지 절벽 경고 {cliff_warning_count}건"))

    evidence_query = question or " ".join([b.name for b in plan.selected[:3]]) or "복지 절벽 신청 전략"
    docs = retrieve(evidence_query)
    tool_trace.append(_tool("local_rag_retriever", "ok", f"근거 문서 {len(docs)}개 검색"))

    insights = compute_profile_insights(safe_profile, benefits_list)
    events = generate_timeline_events(safe_profile, benefits_list)
    checklist = make_document_checklist(plan.selected)
    strategy = build_application_strategy(safe_profile, benefits_list)

    actions: List[Dict[str, Any]] = []
    for idx, action in enumerate(insights["recommended_actions"], start=1):
        actions.append({"rank": idx, "type": "agent_recommendation", "priority": insights["priority_grade"], "action": action, "due": "즉시"})
    for event in events[:5]:
        actions.append({"rank": len(actions) + 1, "type": "timeline", "priority": event.risk_level, "action": f"M+{event.month}: {event.title}", "due": f"M+{event.month}"})
    for row in checklist[:5]:
        actions.append({"rank": len(actions) + 1, "type": "document", "priority": "todo", "action": f"서류 준비: {row['서류']}", "due": "신청 전"})

    answer = make_agent_answer(safe_profile, insights, plan, cliff_warning_count, docs, question)
    return {
        "profile": safe_profile.to_dict(),
        "question": question,
        "tool_trace": tool_trace,
        "answer_markdown": answer,
        "priority_score": insights["priority_score"],
        "priority_grade": insights["priority_grade"],
        "monthly_support": plan.total_monthly_value,
        "selected_benefits": [b.name for b in plan.selected],
        "rejected_due_to_conflict": [b.name for b in plan.rejected_due_to_conflict],
        "actions": actions,
        "strategy": strategy,
        "evidence": docs,
        "warnings": warnings,
    }


def make_agent_answer(profile: UserProfile, insights: Dict[str, Any], plan: Any, cliff_warning_count: int, docs: List[Dict[str, Any]], question: str = "") -> str:
    selected = ", ".join([b.name for b in plan.selected[:5]]) or "해당 데이터 없음"
    reasons = ", ".join(insights["reasons"][:3])
    evidence_titles = ", ".join([d.get("title", "근거") for d in docs[:3]]) or "로컬 근거 없음"
    q_line = f"질문: {question}\n\n" if question else ""
    return (
        f"{q_line}### Agent 판단 요약\n"
        f"- 상담 우선도는 **{insights['priority_score']}점({insights['priority_grade']})**입니다. 주요 사유는 {reasons}입니다.\n"
        f"- 충돌 제거 후 현재 최적 조합의 월 환산효과는 **{money(plan.total_monthly_value)}**입니다.\n"
        f"- 우선 검토 혜택은 **{selected}**입니다.\n"
        f"- 복지 절벽 경고는 **{cliff_warning_count}건**이며, 소득 발생 시점과 실업급여 종료 시점을 함께 봐야 합니다.\n"
        f"- 근거 검색은 `{evidence_titles}` 문서를 참고했습니다.\n\n"
        "### 다음 액션\n"
        + "\n".join([f"{i+1}. {a}" for i, a in enumerate(insights['recommended_actions'])])
    )
