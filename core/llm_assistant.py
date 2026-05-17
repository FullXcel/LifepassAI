"""LLM placement layer for LifePass.

LLM use is intentionally constrained. The model can summarize retrieved policy
context, explain rule-engine results in citizen-friendly language, and draft
counseling guidance. It must not decide eligibility, override rule traces, or
invent application approval guarantees.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any, Dict, Iterable, List

from .embedding_rag import build_rag_context
from .models import UserProfile
from .optimizer import optimize_benefits
from .rule_engine import evaluate_all
from .utils import money, normalize_profile
from .validation import validate_profile


SYSTEM_PROMPT = """당신은 한국 복지·정책 상담 보조 AI입니다.
반드시 지켜야 할 규칙:
1. 최종 자격 판정은 제공된 rule_engine 결과만 근거로 설명한다.
2. 검색 근거에 없는 정책명, 금액, 신청 조건을 새로 만들어내지 않는다.
3. 행정적 승인 가능성을 단정하지 않는다.
4. 불확실하거나 민감한 케이스는 상담사 확인이 필요하다고 안내한다.
5. 답변은 쉬운 한국어로 작성하고, 신청 전 확인해야 할 서류와 다음 행동을 구분한다.
"""


def llm_status() -> Dict[str, Any]:
    provider = os.getenv("LIFEPASS_LLM_PROVIDER", "template").strip().lower()
    model = os.getenv("LIFEPASS_LLM_MODEL", "gpt-4o-mini")
    configured = provider in {"template", "local_template", "mock"} or bool(os.getenv("OPENAI_API_KEY"))
    return {
        "provider": provider,
        "model": model if provider == "openai" else "deterministic-template",
        "configured": configured,
        "uses_llm_for": ["정책 설명", "근거 요약", "상담 문장 생성", "서류 안내", "질문 응답"],
        "not_used_for": ["최종 수급 자격 판정", "소득 기준 확정", "중복 수급 가능 여부 확정", "행정 승인 단정"],
    }


def _openai_chat(messages: List[Dict[str, str]], temperature: float = 0.2) -> str:
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not configured")
    payload = json.dumps({
        "model": os.getenv("LIFEPASS_LLM_MODEL", "gpt-4o-mini"),
        "messages": messages,
        "temperature": temperature,
        "max_tokens": int(os.getenv("LIFEPASS_LLM_MAX_TOKENS", "900")),
    }, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=payload,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=float(os.getenv("LIFEPASS_OPENAI_TIMEOUT", "30"))) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:  # pragma: no cover - requires external API
        detail = exc.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"OpenAI chat API error: {exc.code} {detail[:300]}") from exc
    return body["choices"][0]["message"]["content"].strip()


def _template_response(question: str, profile: UserProfile, selected_names: List[str], monthly_support: int, context: str, warnings: List[str]) -> str:
    selected = ", ".join(selected_names[:5]) or "해당 데이터 없음"
    warning_line = " / ".join(warnings[:3]) if warnings else "중대한 입력 경고 없음"
    return (
        "### LLM 보조 상담 요약\n"
        "현재 실행 환경에서는 외부 LLM API 키가 없어 deterministic template 모드로 답변합니다. "
        "OPENAI_API_KEY와 LIFEPASS_LLM_PROVIDER=openai를 설정하면 같은 위치에서 LLM이 근거 기반 설명문을 생성합니다.\n\n"
        f"- 질문: {question or '일반 상담'}\n"
        f"- 사용자 조건: {profile.age}세, {profile.region}, {profile.household_size}인가구, 월소득 {money(profile.monthly_income)}, 월세 {money(profile.rent)}\n"
        f"- rule_engine이 선택한 우선 혜택: {selected}\n"
        f"- 충돌 제거 후 월 환산효과: {money(monthly_support)}\n"
        f"- 입력 검증 경고: {warning_line}\n\n"
        "### 검색 근거 요약\n"
        f"{context[:1200] if context else '해당 데이터 없음'}\n\n"
        "### 다음 행동\n"
        "1. 구조화 프로필의 소득·월세·보증금 단위를 다시 확인합니다.\n"
        "2. 선택 혜택의 신청 서류를 먼저 준비합니다.\n"
        "3. 소득 발생 예정 또는 실업급여 종료가 있으면 생애전환/복지절벽 탭에서 상실 위험을 확인합니다.\n"
        "4. 최종 신청 전에는 해당 기관 공고와 상담사 검토를 거칩니다."
    )


def generate_grounded_response(
    *,
    question: str,
    profile: UserProfile,
    selected_benefits: List[str],
    monthly_support: int,
    rag_context: str,
    rule_summary: str,
    validation_warnings: List[str] | None = None,
) -> Dict[str, Any]:
    validation_warnings = validation_warnings or []
    provider = os.getenv("LIFEPASS_LLM_PROVIDER", "template").strip().lower()
    if provider == "openai" and os.getenv("OPENAI_API_KEY"):
        user_prompt = f"""
질문: {question or '현재 사용자의 복지 상담 요약을 작성해줘.'}

[사용자 프로필]
{json.dumps(profile.to_dict(), ensure_ascii=False, indent=2)}

[룰엔진 판정 요약]
{rule_summary}

[선택 혜택]
{', '.join(selected_benefits) or '해당 데이터 없음'}
월 환산효과: {monthly_support}원

[입력 검증 경고]
{validation_warnings}

[검색 근거]
{rag_context}

위 정보만 사용해서 1) 현재 판정 요약, 2) 추천 근거, 3) 신청 준비, 4) 상담사 확인 필요사항을 작성해라.
"""
        try:
            text = _openai_chat([
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ])
            return {"mode": "openai", "answer_markdown": text, "warning": ""}
        except Exception as exc:  # noqa: BLE001
            text = _template_response(question, profile, selected_benefits, monthly_support, rag_context, validation_warnings)
            return {"mode": "template_fallback", "answer_markdown": text, "warning": str(exc)}
    text = _template_response(question, profile, selected_benefits, monthly_support, rag_context, validation_warnings)
    return {"mode": "template", "answer_markdown": text, "warning": ""}


def answer_policy_question(question: str, raw_profile: UserProfile | Dict[str, Any], benefits: Iterable[Dict[str, Any]], top_k: int = 5) -> Dict[str, Any]:
    profile = raw_profile if isinstance(raw_profile, UserProfile) else UserProfile.from_dict(raw_profile)
    profile, warnings = validate_profile(profile)
    profile = normalize_profile(profile)
    benefits_list = list(benefits)
    evaluations = evaluate_all(benefits_list, profile)
    plan = optimize_benefits(evaluations)
    selected_names = [b.name for b in plan.selected]
    rule_summary = (
        f"총 {len(evaluations)}개 정책 판정, 가능 {sum(1 for ev in evaluations if ev.eligible)}개, "
        f"충돌 제거 선택 {len(plan.selected)}개, 충돌 제외 {len(plan.rejected_due_to_conflict)}개."
    )
    retrieval = build_rag_context(question or " ".join(selected_names) or "복지 상담", benefits_list, profile, top_k=top_k)
    llm = generate_grounded_response(
        question=question,
        profile=profile,
        selected_benefits=selected_names,
        monthly_support=plan.total_monthly_value,
        rag_context=retrieval.get("context", ""),
        rule_summary=rule_summary,
        validation_warnings=warnings,
    )
    return {
        "question": question,
        "profile": profile.to_dict(),
        "rule_summary": rule_summary,
        "selected_benefits": selected_names,
        "monthly_support": plan.total_monthly_value,
        "retrieval": retrieval,
        "llm": {**llm_status(), "mode": llm["mode"], "warning": llm.get("warning", "")},
        "answer_markdown": llm["answer_markdown"],
        "safety_boundary": "LLM은 설명·요약·상담 문장 생성에만 사용되며 자격 판정은 rule_engine 결과를 따른다.",
    }
