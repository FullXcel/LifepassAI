"""Lightweight observability events compatible with tracing dashboards."""
from __future__ import annotations

import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, asdict
from typing import Any, Dict, Iterator, List

_TRACE_EVENTS: List[Dict[str, Any]] = []


@dataclass
class TraceEvent:
    trace_id: str
    span_id: str
    name: str
    started_at: float
    ended_at: float
    duration_ms: float
    attributes: Dict[str, Any]


@contextmanager
def trace_span(name: str, **attributes: Any) -> Iterator[str]:
    trace_id = attributes.pop("trace_id", str(uuid.uuid4()))
    span_id = str(uuid.uuid4())[:12]
    start = time.time()
    try:
        yield trace_id
    finally:
        end = time.time()
        _TRACE_EVENTS.append(asdict(TraceEvent(trace_id, span_id, name, start, end, round((end - start) * 1000, 2), attributes)))
        if len(_TRACE_EVENTS) > 500:
            del _TRACE_EVENTS[:-500]


def recent_traces(limit: int = 50) -> List[Dict[str, Any]]:
    return list(reversed(_TRACE_EVENTS[-limit:]))
