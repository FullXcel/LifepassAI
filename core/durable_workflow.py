"""Lightweight durable workflow engine for benefit application tracking."""
from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

from .models import BenefitEvaluation, UserProfile


@dataclass
class WorkflowTask:
    step_id: str
    title: str
    status: str
    owner: str
    due_in_days: int
    retry_count: int
    next_run_at: str
    failure_policy: str


def build_application_workflow(profile: UserProfile, selected: List[BenefitEvaluation]) -> Dict[str, Any]:
    now = datetime.now(timezone.utc)
    tasks: List[WorkflowTask] = [
        WorkflowTask("intake", "프로필·동의 확인", "completed", "system", 0, 0, now.isoformat(timespec="seconds"), "no_retry"),
        WorkflowTask("evidence", "공통 증빙서류 수집", "pending", "user", 3, 0, (now + timedelta(days=3)).isoformat(timespec="seconds"), "remind_every_2_days"),
    ]
    for idx, benefit in enumerate(selected, start=1):
        tasks.append(
            WorkflowTask(
                f"apply_{idx}",
                f"{benefit.name} 신청서 작성·제출",
                "pending",
                "counselor" if benefit.monthly_value >= 300000 or profile.crisis_event else "user",
                7 + idx,
                0,
                (now + timedelta(days=7 + idx)).isoformat(timespec="seconds"),
                "retry_3_then_human_review",
            )
        )
    tasks.append(WorkflowTask("followup", "승인/보완 요청 추적", "waiting", "system", 14, 0, (now + timedelta(days=14)).isoformat(timespec="seconds"), "poll_or_manual_update"))
    return {"workflow_id": f"wf_{profile.region}_{profile.age}_{len(selected)}", "durable": True, "tasks": [asdict(t) for t in tasks]}
