"""Privacy utilities for demo data, exports and judge-facing governance."""
from __future__ import annotations

import hashlib
import re
from typing import Any, Dict

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
PHONE_RE = re.compile(r"01[016789]-?\d{3,4}-?\d{4}")


def mask_text(text: str) -> str:
    text = EMAIL_RE.sub("***@***", text or "")
    text = PHONE_RE.sub("010-****-****", text)
    return text


def pseudonymize_identifier(value: str, salt: str = "lifepass-demo") -> str:
    digest = hashlib.sha256(f"{salt}:{value}".encode("utf-8")).hexdigest()[:12]
    return f"lp_{digest}"


def consent_packet(profile_payload: Dict[str, Any]) -> Dict[str, Any]:
    fields = sorted(profile_payload.keys())
    return {
        "purpose": "복지 혜택 자격판정, 신청 우선순위 산정, 상담 이력 관리",
        "data_fields": fields,
        "retention": "MVP 데모 기본값: 로컬 SQLite. 운영 배포 시 기관 정책에 따라 보존기간 설정",
        "human_review_required": True,
        "automated_decision_notice": "최종 신청·승인 판단은 담당 기관과 사용자의 확인 절차를 거친다.",
    }
