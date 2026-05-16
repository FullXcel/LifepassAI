from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class UserProfile:
    """Structured state collected from conversational onboarding."""

    age: int = 27
    region: str = "서울"
    district: str = "관악구"
    household_size: int = 1
    household_type: str = "1인가구"
    employment_status: str = "실업급여 수급 중"
    days_until_unemployment_benefit_end: int = 45
    monthly_income: int = 0
    expected_monthly_income: int = 800_000
    rent_monthly: int = 550_000
    deposit: int = 5_000_000
    assets: int = 18_000_000
    has_housing_contract: bool = True
    health_expense_monthly: int = 80_000
    student_or_jobseeker: bool = True
    has_mobile_id: bool = False
    consent_policy_lookup: bool = True
    notes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Benefit:
    id: str
    name: str
    category: str
    provider: str
    description: str
    monthly_value: int
    one_time_value: int
    duration_months: int
    apply_url: str
    required_documents: List[str]
    rules: Dict[str, Any]
    incompatibilities: List[str] = field(default_factory=list)
    depends_on: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)

    @property
    def annualized_value(self) -> int:
        return self.one_time_value + self.monthly_value * max(self.duration_months, 1)


@dataclass
class RuleResult:
    benefit_id: str
    eligible: bool
    score: float
    passed: List[str]
    failed: List[str]
    warnings: List[str]
    missing: List[str]


@dataclass
class Recommendation:
    benefit: Benefit
    result: RuleResult
    status: str
    expected_value: int
    reason_summary: str


@dataclass
class ScenarioResult:
    name: str
    month: int
    projected_income: int
    retained_benefits_value: int
    lost_benefits_value: int
    newly_available_value: int
    net_effect: int
    eligible_benefits: List[str]
    lost_benefits: List[str]
    warnings: List[str]


@dataclass
class TimelineStep:
    day_offset: int
    title: str
    action: str
    reason: str
    related_benefits: List[str]
    priority: str = "중요"


@dataclass
class Conflict:
    benefit_a: str
    benefit_b: str
    message: str
    severity: str

