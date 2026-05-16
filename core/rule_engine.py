"""Deterministic JSON rule engine for welfare eligibility.

LLMs are useful for summarizing and explaining policies, but eligibility must be
computed by deterministic rules. This engine supports enough JSON logic to make
competition demos auditable.
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, List, Tuple

from .models import BenefitEvaluation, RuleTrace, UserProfile
from .utils import normalize_profile


OPS = {"==", "!=", ">", ">=", "<", "<=", "between", "in", "not_in", "exists", "contains"}


def _value(profile: UserProfile, field: str) -> Any:
    return getattr(profile, field, None)


def _compare(actual: Any, op: str, expected: Any) -> bool:
    if op not in OPS:
        raise ValueError(f"Unsupported operator: {op}")
    if op == "exists":
        return actual is not None and actual != ""
    if actual is None:
        return False
    if op == "==":
        return actual == expected
    if op == "!=":
        return actual != expected
    if op == ">":
        return actual > expected
    if op == ">=":
        return actual >= expected
    if op == "<":
        return actual < expected
    if op == "<=":
        return actual <= expected
    if op == "between":
        lo, hi = expected
        return lo <= actual <= hi
    if op == "in":
        return actual in expected
    if op == "not_in":
        return actual not in expected
    if op == "contains":
        return expected in actual
    return False


def evaluate_rule(rule: Dict[str, Any], profile: UserProfile) -> Tuple[bool, List[RuleTrace]]:
    profile = normalize_profile(profile)
    traces: List[RuleTrace] = []

    def walk(node: Dict[str, Any]) -> bool:
        if "all" in node:
            child_results = [walk(child) for child in node["all"]]
            return all(child_results)
        if "any" in node:
            child_results = [walk(child) for child in node["any"]]
            return any(child_results)
        if "not" in node:
            result = not walk(node["not"])
            label = node.get("label", "NOT condition")
            traces.append(RuleTrace(label=label, passed=result, detail="negated group"))
            return result

        field = node["field"]
        op = node["op"]
        expected = node.get("value")
        actual = _value(profile, field)
        passed = _compare(actual, op, expected)
        label = node.get("label", f"{field} {op} {expected}")
        traces.append(RuleTrace(label=label, passed=passed, detail=f"actual={actual!r}, expected={expected!r}"))
        return passed

    return walk(rule), traces


def evaluate_benefit(benefit: Dict[str, Any], profile: UserProfile) -> BenefitEvaluation:
    eligible, trace = evaluate_rule(benefit["rule"], profile)
    matched = [t.label for t in trace if t.passed]
    unmet = [t.label for t in trace if not t.passed]
    warnings: List[str] = []
    if benefit.get("warning_rule"):
        warning_passed, warning_trace = evaluate_rule(benefit["warning_rule"], profile)
        if warning_passed:
            warnings.extend([t.label for t in warning_trace if t.passed])
    return BenefitEvaluation(
        benefit_id=benefit["id"],
        name=benefit["name"],
        eligible=eligible,
        monthly_value=int(benefit.get("estimated_monthly_value", 0)),
        domain=benefit.get("domain", "기타"),
        priority=int(benefit.get("priority", 0)),
        unmet=unmet,
        matched=matched,
        trace=trace,
        warnings=warnings,
        conflict_group=benefit.get("exclusive_group"),
        conflicts_with=benefit.get("conflicts_with", []),
        required_docs=benefit.get("required_docs", []),
        apply_url=benefit.get("apply_url", ""),
        description=benefit.get("description", ""),
    )


def evaluate_all(benefits: Iterable[Dict[str, Any]], profile: UserProfile) -> List[BenefitEvaluation]:
    return [evaluate_benefit(b, profile) for b in benefits]


def eligible_only(evaluations: Iterable[BenefitEvaluation]) -> List[BenefitEvaluation]:
    return [ev for ev in evaluations if ev.eligible]
