"""Policy document parser that drafts a rule-catalog entry from raw text."""
from __future__ import annotations

import hashlib
import re
from typing import Any, Dict, List


def extract_policy_facts(text: str) -> Dict[str, Any]:
    text = text or ""
    title_match = re.search(r"(?:정책명|사업명|제목)[:：]?\s*([^\n]+)", text)
    title = title_match.group(1).strip() if title_match else (text.strip().splitlines()[0][:60] if text.strip() else "업로드 정책")
    age_match = re.search(r"(?:만\s*)?(\d{1,2})\s*[~\-세부터]+\s*(?:만\s*)?(\d{1,2})\s*세", text)
    amount_match = re.search(r"(?:월|매월)?\s*(\d{1,4})\s*만\s*원", text)
    region = "전국"
    for cand in ["서울", "경기", "인천", "부산", "대구", "대전", "광주", "울산", "세종", "제주"]:
        if cand in text:
            region = cand
            break
    docs = []
    for d in ["주민등록등본", "소득자료", "임대차계약서", "통장사본", "재학증명서", "구직활동 증빙"]:
        if d in text:
            docs.append(d)
    return {
        "title": title,
        "age_range": [int(age_match.group(1)), int(age_match.group(2))] if age_match else [0, 120],
        "monthly_value": int(amount_match.group(1)) * 10000 if amount_match else 0,
        "region": region,
        "required_docs": docs or ["소득자료", "본인확인"],
        "content_hash": hashlib.sha256(text.encode("utf-8")).hexdigest(),
    }


def draft_benefit_from_text(text: str, source_url: str = "uploaded://policy-doc") -> Dict[str, Any]:
    facts = extract_policy_facts(text)
    policy_id = "doc_" + facts["content_hash"][:12]
    rule_all: List[Dict[str, Any]] = []
    if facts["age_range"] != [0, 120]:
        rule_all.append({"field": "age", "op": "between", "value": facts["age_range"], "label": f"만 {facts['age_range'][0]}~{facts['age_range'][1]}세"})
    if facts["region"] != "전국":
        rule_all.append({"field": "region", "op": "==", "value": facts["region"], "label": f"{facts['region']} 거주"})
    if not rule_all:
        rule_all.append({"field": "age", "op": ">=", "value": 0, "label": "기본 검토 대상"})
    return {
        "id": policy_id,
        "name": facts["title"],
        "domain": "문서수집",
        "estimated_monthly_value": facts["monthly_value"],
        "priority": 60,
        "description": "업로드 정책 문서에서 자동 생성된 rule draft입니다. 운영자 검수 후 확정 등록합니다.",
        "target": "문서 파서 추출 대상",
        "required_docs": facts["required_docs"],
        "apply_url": source_url,
        "exclusive_group": None,
        "conflicts_with": [],
        "rule": {"all": rule_all},
        "provenance": {"source_url": source_url, "content_hash": facts["content_hash"], "review_status": "draft_requires_human_review"},
    }
