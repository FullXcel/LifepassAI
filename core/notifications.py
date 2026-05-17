"""Deadline-aware notification engine."""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Dict, List

from .models import UserProfile


@dataclass
class Notification:
    channel: str
    trigger: str
    severity: str
    message: str
    scheduled_in_days: int


def plan_notifications(profile: UserProfile, workflow: Dict[str, Any]) -> List[Dict[str, Any]]:
    notifications: List[Notification] = []
    if profile.unemployment_benefit_receiving and profile.unemployment_benefit_days_left <= 45:
        notifications.append(Notification("app", "unemployment_d_minus_30", "high", "실업급여 종료 전 구직·주거 지원 전환 신청을 안내합니다.", max(profile.unemployment_benefit_days_left - 30, 0)))
    if profile.expected_monthly_income > 0:
        notifications.append(Notification("app", "income_change_before_m1", "medium", "예상 소득 발생 전 자격 변화와 복지 절벽 위험을 재점검합니다.", max(profile.expected_income_start_month * 30 - 30, 0)))
    for task in workflow.get("tasks", []):
        if task.get("status") in {"pending", "waiting"}:
            notifications.append(Notification("email", f"task_{task['step_id']}", "medium", f"{task['title']} 마감 전 리마인더", max(int(task.get("due_in_days", 7)) - 2, 0)))
    return [asdict(n) for n in notifications]
