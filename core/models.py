"""Data models for LifePass AI.

The project intentionally keeps the core logic independent from Streamlit so that
competition judges can verify the rule engine and simulations from the command
line.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional


@dataclass
class UserProfile:
    """Normalized user state used by the rule engine.

    Monetary values are KRW/month unless the field name says otherwise.
    ``income_percent_median`` is a demo-friendly normalized ratio against a
    simplified median-income table. In production, it should be replaced by an
    official household-size/year-specific table.
    """

    age: int = 27
    region: str = "서울"
    district: str = ""
    household_size: int = 1
    employment_status: str = "unemployed"  # unemployed, job_seeker, part_time, employed, freelancer, student
    monthly_income: int = 0
    expected_monthly_income: int = 0
    expected_income_start_month: int = 3
    rent: int = 0
    deposit: int = 0
    assets_million: float = 0.0
    income_percent_median: Optional[float] = None
    unemployment_benefit_receiving: bool = False
    unemployment_benefit_days_left: int = 0
    crisis_event: bool = False
    medical_expense_3m: int = 0
    credit_score: int = 750
    debt_monthly_payment: int = 0
    is_basic_livelihood: bool = False
    is_near_poverty: bool = False
    has_housing_contract: bool = True
    wants_job_training: bool = True
    has_recent_unemployment: bool = False
    guardian_mode: bool = False
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "UserProfile":
        allowed = {field.name for field in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        clean = {k: v for k, v in payload.items() if k in allowed}
        return cls(**clean)


@dataclass
class RuleTrace:
    label: str
    passed: bool
    detail: str


@dataclass
class BenefitEvaluation:
    benefit_id: str
    name: str
    eligible: bool
    monthly_value: int
    domain: str
    priority: int
    unmet: List[str] = field(default_factory=list)
    matched: List[str] = field(default_factory=list)
    trace: List[RuleTrace] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    conflict_group: Optional[str] = None
    conflicts_with: List[str] = field(default_factory=list)
    required_docs: List[str] = field(default_factory=list)
    apply_url: str = ""
    description: str = ""


@dataclass
class OptimizedPlan:
    selected: List[BenefitEvaluation]
    rejected_due_to_conflict: List[BenefitEvaluation]
    total_monthly_value: int
    explanation: List[str]


@dataclass
class ScenarioResult:
    label: str
    month: int
    income: int
    benefit_value: int
    net_effect: int
    selected_benefits: List[str]
    gained: List[str] = field(default_factory=list)
    lost: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


@dataclass
class TimelineEvent:
    month: int
    title: str
    description: str
    action_items: List[str]
    risk_level: str = "info"  # info, warning, danger, success


@dataclass
class AdminMetrics:
    total_profiles: int
    high_cliff_risk: int
    average_monthly_support: float
    top_benefits: List[Dict[str, Any]]
    region_summary: List[Dict[str, Any]]
    pending_actions: List[Dict[str, Any]]
