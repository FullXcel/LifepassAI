"""v5 event-driven operating layer for LifePass.

The module is intentionally dependency-light so the competition demo runs without
Kafka/Redis, while the data shape mirrors a real outbox/event-mesh design.
"""
from __future__ import annotations

import hashlib
import json
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List

from core.models import UserProfile


def _stable_hash(payload: Dict[str, Any]) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:18]


def make_event_envelope(event_type: str, subject_id: str, payload: Dict[str, Any], *, source: str = "lifepass-ui") -> Dict[str, Any]:
    """Create an idempotent event envelope similar to a production event bus."""
    body = {
        "event_type": event_type,
        "subject_id": subject_id,
        "payload": payload,
        "source": source,
    }
    event_id = f"evt_{_stable_hash(body)}"
    return {
        "event_id": event_id,
        "idempotency_key": event_id,
        "event_type": event_type,
        "subject_id": subject_id,
        "source": source,
        "occurred_at": datetime.now(timezone.utc).isoformat(),
        "schema_version": "lifepass.event.v1",
        "payload": payload,
        "routing_key": f"welfare.{event_type}",
        "trace_id": f"trc_{_stable_hash({'event_id': event_id, 't': int(time.time())})}",
    }


def simulate_profile_events(profile: UserProfile) -> List[Dict[str, Any]]:
    """Generate deterministic demo events from a profile.

    These events demonstrate how life-signal changes would enter the platform in
    production from web forms, public data, counselor updates, or partner APIs.
    """
    subject = f"profile_{_stable_hash(profile.to_dict())[:8]}"
    base = [
        ("profile.updated", {"field": "monthly_income", "value": profile.monthly_income}),
        ("housing.rent_verified", {"rent": profile.rent, "deposit": profile.deposit, "has_contract": profile.has_housing_contract}),
        ("benefit.screening_requested", {"region": profile.region, "household_size": profile.household_size}),
    ]
    if profile.unemployment_benefit_receiving:
        base.append(("risk.deadline_detected", {"kind": "unemployment_benefit_end", "days_left": profile.unemployment_benefit_days_left}))
    if profile.expected_monthly_income > profile.monthly_income:
        base.append(("life_transition.income_expected", {"months_until_change": profile.expected_income_start_month, "expected_income": profile.expected_monthly_income}))
    if profile.medical_expense_3m > 0 or profile.crisis_event:
        base.append(("crisis.signal_detected", {"medical_expense_3m": profile.medical_expense_3m, "crisis_event": profile.crisis_event}))
    return [make_event_envelope(t, subject, p) for t, p in base]


def build_outbox(events: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    """Return an outbox view with delivery, retry and dead-letter semantics."""
    rows: List[Dict[str, Any]] = []
    for i, event in enumerate(events, start=1):
        rows.append({
            "seq": i,
            "event_id": event["event_id"],
            "routing_key": event["routing_key"],
            "status": "ready_to_publish",
            "retry_count": 0,
            "next_attempt_at": (datetime.now(timezone.utc) + timedelta(seconds=i * 3)).isoformat(),
            "dead_letter_on": "max_retry_exceeded_or_schema_invalid",
            "idempotency_key": event["idempotency_key"],
        })
    return {
        "pattern": "transactional_outbox",
        "delivery_guarantee": "idempotent_at-least-once",
        "rows": rows,
        "ready_count": len(rows),
        "dead_letter_count": 0,
    }


def event_ops_dashboard(profile: UserProfile) -> Dict[str, Any]:
    events = simulate_profile_events(profile)
    outbox = build_outbox(events)
    metrics = {
        "events_generated": len(events),
        "event_types": len({e["event_type"] for e in events}),
        "outbox_ready": outbox["ready_count"],
        "dead_letter": outbox["dead_letter_count"],
        "avg_publish_latency_ms_demo": 38,
        "consumer_lag_demo": 0,
    }
    consumers = [
        {"consumer": "eligibility-worker", "topic": "welfare.benefit.screening_requested", "action": "자격 재판정", "sla": "< 2s"},
        {"consumer": "deadline-worker", "topic": "welfare.risk.deadline_detected", "action": "마감 알림 생성", "sla": "< 1s"},
        {"consumer": "profile-feature-worker", "topic": "welfare.profile.updated", "action": "프로필 feature state 갱신", "sla": "< 2s"},
        {"consumer": "audit-worker", "topic": "welfare.*", "action": "감사 로그 및 lineage 저장", "sla": "async"},
    ]
    return {"metrics": metrics, "events": events, "outbox": outbox, "consumers": consumers}
