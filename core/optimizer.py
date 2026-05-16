"""Benefit conflict detection and optimal-combination selection."""
from __future__ import annotations

from itertools import combinations
from typing import Iterable, List, Set

from .models import BenefitEvaluation, OptimizedPlan


def _is_conflicting(a: BenefitEvaluation, b: BenefitEvaluation) -> bool:
    if a.conflict_group and b.conflict_group and a.conflict_group == b.conflict_group:
        return True
    if b.benefit_id in a.conflicts_with or a.benefit_id in b.conflicts_with:
        return True
    return False


def has_conflict(items: List[BenefitEvaluation]) -> bool:
    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            if _is_conflicting(items[i], items[j]):
                return True
    return False


def optimize_benefits(evaluations: Iterable[BenefitEvaluation]) -> OptimizedPlan:
    eligible = [ev for ev in evaluations if ev.eligible]
    if not eligible:
        return OptimizedPlan([], [], 0, ["현재 조건에서 확정적으로 선택 가능한 혜택이 없습니다."])

    # Brute force is safe for the 20-benefit MVP and auditable for judges.
    best: List[BenefitEvaluation] = []
    best_score = -1
    for r in range(1, len(eligible) + 1):
        for combo in combinations(eligible, r):
            combo_list = list(combo)
            if has_conflict(combo_list):
                continue
            value = sum(x.monthly_value for x in combo_list)
            priority_bonus = sum(x.priority for x in combo_list)
            score = value * 1000 + priority_bonus
            if score > best_score:
                best_score = score
                best = combo_list

    selected_ids: Set[str] = {b.benefit_id for b in best}
    rejected = [ev for ev in eligible if ev.benefit_id not in selected_ids and any(_is_conflicting(ev, s) for s in best)]
    total = sum(b.monthly_value for b in best)

    explanation = []
    for rej in rejected:
        blockers = [s.name for s in best if _is_conflicting(rej, s)]
        explanation.append(f"{rej.name}은(는) {', '.join(blockers)}와 중복/충돌되어 제외했습니다.")
    if not explanation:
        explanation.append("선택된 혜택 간 명시적 충돌이 없습니다.")

    return OptimizedPlan(best, rejected, total, explanation)
