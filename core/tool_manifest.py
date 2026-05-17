"""MCP-style tool manifest for the LifePass decision agent."""
from __future__ import annotations

from typing import Any, Dict, List


def tool_manifest() -> Dict[str, Any]:
    tools: List[Dict[str, Any]] = [
        {
            "name": "parse_onboarding_text",
            "description": "Korean natural-language 상담 문장을 UserProfile schema로 변환한다.",
            "input_schema": {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]},
        },
        {
            "name": "eligibility_rule_engine",
            "description": "JSON policy rules를 deterministic하게 평가하고 충족/미충족 조건 trace를 반환한다.",
            "input_schema": {"type": "object", "properties": {"profile": {"type": "object"}, "benefits": {"type": "array"}}, "required": ["profile"]},
        },
        {
            "name": "conflict_aware_optimizer",
            "description": "중복 수급·상호배타 조건을 제거해 월 환산효과가 큰 조합을 선택한다.",
            "input_schema": {"type": "object", "properties": {"evaluations": {"type": "array"}}, "required": ["evaluations"]},
        },
        {
            "name": "benefit_cliff_detector",
            "description": "소득 변화와 생애전환에 따른 혜택 상실·신규 가능성을 시뮬레이션한다.",
            "input_schema": {"type": "object", "properties": {"profile": {"type": "object"}}, "required": ["profile"]},
        },
        {
            "name": "public_policy_api_fetcher",
            "description": "복지로·정부24·고용24·지자체 API/CSV Gateway에서 정책 피드를 수집해 내부 rule schema로 정규화한다.",
            "input_schema": {"type": "object", "properties": {"source_id": {"type": "string"}, "query": {"type": "string"}}, "required": ["source_id"]},
        },
        {
            "name": "trust_audit",
            "description": "정책 provenance, 입력 검증, rule coverage, human-in-the-loop 통제 상태를 점검한다.",
            "input_schema": {"type": "object", "properties": {"profile": {"type": "object"}}, "required": ["profile"]},
        },
    ]
    return {"name": "lifepass-ai-agent-tools", "version": "3.0.0", "tools": tools}
