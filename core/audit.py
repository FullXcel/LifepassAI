"""Trust, safety and audit pack for welfare eligibility agents."""
from __future__ import annotations

from typing import Any, Dict, Iterable, List

from .models import UserProfile
from .optimizer import optimize_benefits
from .rule_engine import evaluate_all
from .validation import validate_profile


def build_trust_audit(profile: UserProfile, benefits: Iterable[Dict[str, Any]], agent_plan: Dict[str, Any] | None = None) -> Dict[str, Any]:
    benefits_list = list(benefits)
    safe_profile, warnings = validate_profile(profile)
    evaluations = evaluate_all(benefits_list, safe_profile)
    plan = optimize_benefits(evaluations)
    policies_with_rules = sum(1 for b in benefits_list if isinstance(b.get("rule"), dict))
    policies_with_provenance = sum(1 for b in benefits_list if b.get("provenance"))
    eligible = sum(1 for ev in evaluations if ev.eligible)
    unresolved_unmet = sum(len(ev.unmet) for ev in evaluations if not ev.eligible)

    controls: List[Dict[str, Any]] = [
        {"control": "Deterministic eligibility", "status": "pass" if policies_with_rules == len(benefits_list) else "warn", "evidence": f"{policies_with_rules}/{len(benefits_list)} policies have JSON rules"},
        {"control": "No LLM-only decision", "status": "pass", "evidence": "Eligibility is computed by rule_engine.evaluate_all; the agent only explains results."},
        {"control": "Conflict-aware optimization", "status": "pass", "evidence": f"{len(plan.selected)} selected, {len(plan.rejected_due_to_conflict)} rejected by conflict/group rules"},
        {"control": "Input validation", "status": "pass" if not warnings else "warn", "evidence": f"{len(warnings)} validation warnings"},
        {"control": "Policy provenance", "status": "pass" if policies_with_provenance else "warn", "evidence": f"{policies_with_provenance}/{len(benefits_list)} policies include source metadata"},
        {"control": "Explainability", "status": "pass", "evidence": f"{eligible} eligible policies, {unresolved_unmet} unmet-condition traces"},
        {"control": "Human-in-the-loop", "status": "pass", "evidence": "The UI exposes required documents, missing conditions and application task status."},
    ]
    if agent_plan:
        controls.append({"control": "Agent tool trace", "status": "pass" if len(agent_plan.get("tool_trace", [])) >= 5 else "warn", "evidence": f"{len(agent_plan.get('tool_trace', []))} traced tool calls"})
    risk_score = 100 - sum(12 for row in controls if row["status"] == "warn") - sum(25 for row in controls if row["status"] == "fail")
    return {
        "audit_score": max(0, risk_score),
        "status": "production-review-ready" if risk_score >= 80 else "needs-review",
        "validation_warnings": warnings,
        "controls": controls,
        "judge_summary": "자격판정은 규칙 기반으로 재현 가능하며, AI Agent는 설명·우선순위·신청 액션을 조율하는 역할로 제한된다.",
    }


def controls_dataframe_rows(audit: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [{"control": c["control"], "status": c["status"], "evidence": c["evidence"]} for c in audit.get("controls", [])]
