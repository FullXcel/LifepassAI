"""Admin dashboard analytics for demo populations."""
from __future__ import annotations

from collections import Counter, defaultdict
from typing import Dict, Iterable, List

from .models import AdminMetrics, UserProfile
from .optimizer import optimize_benefits
from .rule_engine import evaluate_all
from .simulator import simulate_income_cliff
from .utils import normalize_profile


def detect_high_cliff_risk(profile: UserProfile, benefits: Iterable[Dict]) -> bool:
    results = simulate_income_cliff(profile, benefits)
    return any(r.warnings for r in results)


def build_admin_metrics(profiles: List[UserProfile], benefits: Iterable[Dict]) -> AdminMetrics:
    benefit_counter: Counter[str] = Counter()
    region_counts: defaultdict[str, int] = defaultdict(int)
    region_support: defaultdict[str, int] = defaultdict(int)
    pending_actions: List[Dict] = []
    supports: List[int] = []
    high_risk = 0
    benefits_list = list(benefits)

    for idx, profile in enumerate(profiles):
        profile = normalize_profile(profile)
        evaluations = evaluate_all(benefits_list, profile)
        plan = optimize_benefits(evaluations)
        supports.append(plan.total_monthly_value)
        region_counts[profile.region] += 1
        region_support[profile.region] += plan.total_monthly_value
        if detect_high_cliff_risk(profile, benefits_list):
            high_risk += 1
            pending_actions.append({
                "profile_index": idx,
                "region": profile.region,
                "action": "소득 변화 전 복지 절벽 재상담 필요",
                "priority": "high",
            })
        for benefit in plan.selected:
            benefit_counter[benefit.name] += 1

    top_benefits = [{"benefit": name, "count": count} for name, count in benefit_counter.most_common(10)]
    region_summary = [
        {
            "region": region,
            "profiles": count,
            "avg_support": round(region_support[region] / count) if count else 0,
        }
        for region, count in sorted(region_counts.items())
    ]
    avg = sum(supports) / len(supports) if supports else 0
    return AdminMetrics(
        total_profiles=len(profiles),
        high_cliff_risk=high_risk,
        average_monthly_support=round(avg, 1),
        top_benefits=top_benefits,
        region_summary=region_summary,
        pending_actions=pending_actions[:20],
    )
