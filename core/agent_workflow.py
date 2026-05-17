"""LangGraph-style deterministic agent workflow trace."""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Dict, List

from .agent import build_agent_plan
from .audit import build_trust_audit
from .models import UserProfile
from .rule_engine import evaluate_all
from .validation import validate_profile


@dataclass
class WorkflowStep:
    order: int
    node: str
    tool: str
    status: str
    input_summary: str
    output_summary: str
    confidence: float
    needs_human_review: bool = False


def build_agent_workflow(profile: UserProfile, benefits: List[Dict[str, Any]], question: str = "") -> Dict[str, Any]:
    profile, warnings = validate_profile(profile)
    evaluations = evaluate_all(benefits, profile)
    eligible = [e for e in evaluations if e.eligible]
    plan = build_agent_plan(profile, benefits, question=question)
    audit = build_trust_audit(profile, benefits, plan)
    review_required = bool(warnings or audit.get("audit_score", 0) < 80 or profile.crisis_event)
    steps = [
        WorkflowStep(1, "Profile Intake", "parse_or_load_profile", "completed", "자연어/JSON/CSV/폼 입력", f"{profile.region} {profile.age}세 프로필 생성", 0.94),
        WorkflowStep(2, "Data Validation", "validate_profile", "completed", "프로필 범위·단위 점검", f"경고 {len(warnings)}건", 0.91, bool(warnings)),
        WorkflowStep(3, "Eligibility", "deterministic_rule_engine", "completed", f"정책 {len(benefits)}개", f"가능 혜택 {len(eligible)}개", 0.99),
        WorkflowStep(4, "Conflict Resolver", "constraint_optimizer", "completed", "상호배타·충돌 그룹", f"선택 {plan.get('selected_count', 0)}개", 0.96),
        WorkflowStep(5, "Cliff Risk", "life_transition_simulator", "completed", "소득·실업급여 변화", f"우선 액션 {len(plan.get('actions', []))}개", 0.88),
        WorkflowStep(6, "Evidence Retrieval", "semantic_policy_retrieval", "completed", question or "기본 근거 검색", "정책 근거 검색 완료", 0.84),
        WorkflowStep(7, "Human Review Gate", "risk_gate", "needs_review" if review_required else "auto_approved", "감사·검증 결과", "상담사 검토 필요" if review_required else "자동 리포트 가능", 0.90, review_required),
    ]
    return {
        "workflow_name": "LifePass Human-in-the-loop Welfare Agent Graph",
        "human_review_required": review_required,
        "steps": [asdict(s) for s in steps],
        "validation_warnings": warnings,
        "audit_score": audit.get("audit_score"),
        "agent_plan": plan,
    }
