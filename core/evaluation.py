"""Recommendation benchmark and quality evaluation."""
from __future__ import annotations

from typing import Any, Dict, List, Set

from .demo_data import load_sample_profiles
from .models import UserProfile
from .optimizer import has_conflict, optimize_benefits
from .rule_engine import evaluate_all

# Demo gold labels used to show how a production benchmark would be managed.
GOLD_KEYWORDS = {
    "서울 청년 1인가구": {"월세", "실업급여"},
    "실업급여 종료 임박자": {"국민취업", "월세"},
    "월세 부담 청년": {"월세", "주거"},
}


def _keyword_hit(selected_names: List[str], gold_keywords: Set[str]) -> int:
    return sum(1 for kw in gold_keywords if any(kw in name for name in selected_names))


def run_benchmark(benefits: List[Dict[str, Any]]) -> Dict[str, Any]:
    rows: List[Dict[str, Any]] = []
    precision_scores: List[float] = []
    recall_scores: List[float] = []
    violations = 0
    for sample in load_sample_profiles():
        name = sample["name"]
        p = UserProfile.from_dict(sample["profile"])
        plan = optimize_benefits(evaluate_all(benefits, p))
        selected_names = [b.name for b in plan.selected]
        gold = GOLD_KEYWORDS.get(name, set())
        hits = _keyword_hit(selected_names, gold)
        precision = hits / max(len(selected_names), 1)
        recall = hits / max(len(gold), 1) if gold else 1.0
        conflict = has_conflict(plan.selected)
        violations += int(conflict)
        precision_scores.append(precision)
        recall_scores.append(recall)
        rows.append({"case": name, "selected_count": len(selected_names), "gold_keywords": ", ".join(gold), "keyword_hits": hits, "precision_proxy": round(precision, 3), "recall_proxy": round(recall, 3), "conflict_violation": conflict, "monthly_value": plan.total_monthly_value})
    return {
        "rows": rows,
        "metrics": {
            "cases": len(rows),
            "precision_proxy_avg": round(sum(precision_scores) / max(len(precision_scores), 1), 3),
            "recall_proxy_avg": round(sum(recall_scores) / max(len(recall_scores), 1), 3),
            "conflict_violation_rate": round(violations / max(len(rows), 1), 3),
            "coverage": round(sum(1 for r in rows if r["selected_count"] > 0) / max(len(rows), 1), 3),
        },
    }
