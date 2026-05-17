"""Constraint optimization engine for benefit selection.

Uses an auditable exhaustive search for the demo, with scoring terms similar to
an ILP objective: value + urgency + success probability - document complexity.
"""
from __future__ import annotations

from itertools import combinations
from typing import Any, Dict, Iterable, List

from .models import BenefitEvaluation
from .optimizer import has_conflict


def solve_benefit_portfolio(evaluations: Iterable[BenefitEvaluation], max_items: int = 6) -> Dict[str, Any]:
    eligible = [e for e in evaluations if e.eligible]
    best: List[BenefitEvaluation] = []
    best_score = -10**18
    best_breakdown: Dict[str, Any] = {}
    max_r = min(max_items, len(eligible))
    for r in range(1, max_r + 1):
        for combo in combinations(eligible, r):
            items = list(combo)
            if has_conflict(items):
                continue
            value = sum(i.monthly_value for i in items)
            urgency = sum(i.priority for i in items) * 1000
            doc_penalty = sum(len(i.required_docs) for i in items) * 500
            diversity_bonus = len({i.domain for i in items}) * 5000
            score = value + urgency + diversity_bonus - doc_penalty
            if score > best_score:
                best = items
                best_score = score
                best_breakdown = {"value": value, "urgency_bonus": urgency, "diversity_bonus": diversity_bonus, "document_penalty": doc_penalty, "objective_score": score}
    return {
        "selected": [{"benefit_id": b.benefit_id, "name": b.name, "domain": b.domain, "monthly_value": b.monthly_value, "priority": b.priority, "required_docs": len(b.required_docs)} for b in best],
        "breakdown": best_breakdown,
        "conflict_free": not has_conflict(best),
        "method": "auditable_exhaustive_search_ilp_style_objective",
    }
