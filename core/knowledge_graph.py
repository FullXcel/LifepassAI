"""Eligibility knowledge graph data builder."""
from __future__ import annotations

from typing import Any, Dict, List

from .models import BenefitEvaluation, UserProfile


def build_eligibility_graph(profile: UserProfile, evaluations: List[BenefitEvaluation]) -> Dict[str, List[Dict[str, Any]]]:
    nodes: List[Dict[str, Any]] = [
        {"id": "user", "label": f"{profile.region} {profile.age}세", "type": "profile"},
        {"id": "income", "label": f"월소득 {profile.monthly_income:,}원", "type": "condition"},
        {"id": "housing", "label": f"월세 {profile.rent:,}원", "type": "condition"},
    ]
    edges: List[Dict[str, Any]] = [
        {"source": "user", "target": "income", "relation": "has_condition"},
        {"source": "user", "target": "housing", "relation": "has_condition"},
    ]
    for ev in evaluations[:30]:
        bid = f"benefit:{ev.benefit_id}"
        nodes.append({"id": bid, "label": ev.name, "type": "benefit", "eligible": ev.eligible, "monthly_value": ev.monthly_value})
        edges.append({"source": "user", "target": bid, "relation": "eligible_for" if ev.eligible else "not_eligible_for"})
        for idx, label in enumerate(ev.matched[:3]):
            cid = f"cond:{ev.benefit_id}:m{idx}"
            nodes.append({"id": cid, "label": label, "type": "matched_condition"})
            edges.append({"source": cid, "target": bid, "relation": "supports"})
        for conflict in ev.conflicts_with[:3]:
            edges.append({"source": bid, "target": f"benefit:{conflict}", "relation": "conflicts_with"})
    return {"nodes": nodes, "edges": edges}


def graph_rows(graph: Dict[str, List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    return [{"kind": "node", **n} for n in graph.get("nodes", [])] + [{"kind": "edge", **e} for e in graph.get("edges", [])]
