"""LifePass AI Agent Platform v5.

Run:
    docker compose up -d --build

Fast local fallback:
    streamlit run app.py

Competition-grade upgrade highlights:
- stable green UI with no invisible sidebar text and no height=None dataframe crash
- Korean natural-language onboarding + structured profile editor + JSON upload
- external multi-user CSV batch analysis
- policy feed CSV ingestion into the same rule-engine catalog schema
- optional SQLite persistence layer and PostgreSQL-ready deployment note
- application task tracking and an explainable AI-agent style tool trace
- optional REST API backend in api.py
- v5 event mesh, policy digital twin, zero-trust privacy/security, causal ops and quality ops
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, List

import pandas as pd
import streamlit as st

from core.agent import build_agent_plan
from core.api_contract import examples_json
from core.admin import build_admin_metrics
from core.batch import analyze_profiles, template_csv_bytes
from core.benefit_catalog import load_benefits
from core.demo_data import load_sample_profiles, sample_profiles_as_models
from core.insights import compute_profile_insights, make_document_checklist
from core.models import UserProfile
from core.optimizer import optimize_benefits
from core.persistence import (
    create_tasks_from_benefits,
    db_status,
    init_db,
    list_profiles,
    list_tasks,
    save_analysis_run,
    save_profile,
    update_task_status,
    upsert_user,
)
from core.policy_ingestion import (
    benefits_from_dataframe,
    load_imported_benefits,
    save_imported_benefits,
    template_policy_csv_bytes,
)
from core.audit import build_trust_audit, controls_dataframe_rows
from core.observability import recent_traces, trace_span
from core.policy_provenance import diff_catalogs
from core.privacy import consent_packet, mask_text, pseudonymize_identifier
from core.public_api_clients import fetch_source_policies, load_source_specs, source_status_rows
from core.tool_manifest import tool_manifest
from core.vector_search import search_policies
from core.whatif import build_counterfactuals
from core.agent_workflow import build_agent_workflow
from core.constraint_solver import solve_benefit_portfolio
from core.dbms import POSTGRES_PGVECTOR_DDL, dbms_capabilities, deployment_readiness
from core.document_parser import draft_benefit_from_text, extract_policy_facts
from core.durable_workflow import build_application_workflow
from core.evaluation import run_benchmark
from core.guardrails import validate_structured_payload
from core.knowledge_graph import build_eligibility_graph, graph_rows
from core.multitenancy import current_tenant, tenant_rows
from core.notifications import plan_notifications
from core.sdk import curl_examples
from core.smart_mapper import infer_mapping, map_dataframe_to_profiles

from core.v5_event_mesh import event_ops_dashboard
from core.v5_policy_digital_twin import simulate_policy_impact
from core.v5_privacy_security import privacy_security_pack, check_access
from core.v5_causal_ops import estimate_intervention_effects, quality_ops_pack
from core.profile_parser import parse_onboarding_text
from core.rag import explain_with_evidence
from core.report import make_markdown_report
from core.rule_engine import evaluate_all
from core.simulator import build_application_strategy, generate_timeline_events, simulate_income_cliff, simulate_timeline
from core.utils import money, normalize_profile
from core.validation import safe_widget_bounds, validate_profile

st.set_page_config(page_title="LifePass AI Agent", page_icon="🧭", layout="wide")

BASE_BENEFITS = load_benefits()
SAMPLES = load_sample_profiles()

REGIONS = ["서울", "경기", "인천", "부산", "대구", "대전", "광주", "울산", "세종", "전북", "전남", "충북", "충남", "경북", "경남", "강원", "제주"]
EMPLOYMENT_STATUSES = ["unemployed", "job_seeker", "part_time", "employed", "freelancer", "student"]


def active_benefits() -> List[Dict[str, Any]]:
    benefits = list(BASE_BENEFITS)
    if st.session_state.get("use_imported_policies", True):
        try:
            imported = load_imported_benefits()
            existing_ids = {b["id"] for b in benefits}
            benefits.extend([b for b in imported if b["id"] not in existing_ids])
        except Exception as exc:  # noqa: BLE001
            st.session_state.setdefault("policy_load_warning", str(exc))
    return benefits


def inject_theme_css() -> None:
    st.markdown(
        """
        <style>
        :root {
            --lp-ink: #0f172a;
            --lp-muted: #475569;
            --lp-green-950: #022c22;
            --lp-green-900: #064e3b;
            --lp-green-800: #065f46;
            --lp-green-700: #047857;
            --lp-green-600: #059669;
            --lp-green-500: #10b981;
            --lp-lime-300: #bef264;
            --lp-mint-50: #f0fdf4;
            --lp-card: rgba(255, 255, 255, .90);
        }
        .stApp {
            background:
              radial-gradient(circle at 8% 0%, rgba(52,211,153,.28), transparent 28rem),
              radial-gradient(circle at 92% 5%, rgba(190,242,100,.25), transparent 24rem),
              linear-gradient(135deg, #f7fee7 0%, #ecfdf5 48%, #f8fafc 100%);
            color: var(--lp-ink);
        }
        [data-testid="stSidebar"] {
            background: linear-gradient(180deg, #064e3b 0%, #047857 50%, #10b981 100%);
        }
        [data-testid="stSidebar"] h1,
        [data-testid="stSidebar"] h2,
        [data-testid="stSidebar"] h3,
        [data-testid="stSidebar"] p,
        [data-testid="stSidebar"] label,
        [data-testid="stSidebar"] .stMarkdown,
        [data-testid="stSidebar"] [data-testid="stCaptionContainer"] {
            color: #ecfdf5 !important;
        }
        [data-testid="stSidebar"] input,
        [data-testid="stSidebar"] textarea,
        [data-testid="stSidebar"] [data-baseweb="select"] *,
        [data-testid="stSidebar"] [data-testid="stFileUploader"] section,
        [data-testid="stSidebar"] [data-testid="stFileUploader"] section *,
        [data-testid="stSidebar"] [data-testid="stFileUploader"] button,
        [data-testid="stSidebar"] [data-testid="stFileUploader"] small {
            color: #0f172a !important;
        }
        [data-testid="stSidebar"] [data-testid="stFileUploader"] section {
            background: rgba(255,255,255,.94) !important;
            border-radius: 16px !important;
            border: 1px solid rgba(187,247,208,.65) !important;
        }
        .hero-card {
            padding: 1.4rem 1.6rem;
            border-radius: 30px;
            background: linear-gradient(135deg, rgba(6,95,70,.98), rgba(16,185,129,.92)), radial-gradient(circle at 88% 20%, rgba(236,252,203,.85), transparent 15rem);
            color: white;
            box-shadow: 0 22px 60px rgba(6,95,70,.28);
            margin-bottom: 1.1rem;
        }
        .hero-card h1 { margin: .15rem 0 .35rem 0; font-size: 2.45rem; color: white; }
        .hero-card p { margin: .15rem 0 0 0; color: #ecfdf5; font-size: 1.02rem; }
        .status-pill {
            display: inline-flex; align-items: center; gap: .4rem;
            padding: .32rem .75rem; border-radius: 999px;
            background: rgba(236,252,203,.92); color: #14532d; font-weight: 900; font-size: .84rem;
        }
        .agent-card, .insight-card, .soft-card {
            background: var(--lp-card);
            border: 1px solid rgba(16,185,129,.22);
            border-radius: 24px;
            box-shadow: 0 16px 38px rgba(5,150,105,.10);
            padding: 1rem 1.1rem;
            margin-bottom: .75rem;
        }
        .agent-card strong, .insight-card strong { color: #065f46; }
        .insight-card { min-height: 126px; }
        .insight-card .label { color: #047857; font-size: .86rem; font-weight: 900; }
        .insight-card .value { color: #052e16; font-size: 1.55rem; font-weight: 950; margin-top: .25rem; }
        .insight-card .desc { color: #475569; font-size: .86rem; margin-top: .45rem; }
        .chat-row { display: flex; margin: .45rem 0; }
        .chat-bot, .chat-user { padding: .72rem .9rem; border-radius: 18px; max-width: 82%; box-shadow: 0 8px 20px rgba(5,150,105,.08); }
        .chat-bot { background: #dcfce7; color: #064e3b; border-bottom-left-radius: 4px; }
        .chat-user { background: #ffffff; color: #0f172a; margin-left: auto; border-bottom-right-radius: 4px; }
        div[data-testid="stMetric"] {
            background: rgba(255,255,255,.92);
            border: 1px solid rgba(16,185,129,.20);
            border-radius: 22px;
            padding: .95rem 1rem;
            box-shadow: 0 12px 30px rgba(5,150,105,.10);
        }
        div[data-testid="stMetric"] label { color: #047857 !important; font-weight: 900 !important; }
        .stTabs [data-baseweb="tab-list"] { gap: .36rem; flex-wrap: wrap; }
        .stTabs [data-baseweb="tab"] {
            background: rgba(255,255,255,.76);
            border: 1px solid rgba(16,185,129,.22);
            border-radius: 999px;
            padding: .45rem .85rem;
        }
        .stTabs [aria-selected="true"] {
            background: linear-gradient(135deg, #16a34a, #10b981) !important;
            color: white !important;
            font-weight: 900 !important;
        }
        .stButton > button, .stDownloadButton > button {
            border-radius: 999px !important;
            border: 0 !important;
            background: linear-gradient(135deg, #16a34a, #059669) !important;
            color: white !important;
            font-weight: 900 !important;
            box-shadow: 0 12px 26px rgba(5,150,105,.22);
        }
        .stAlert { border-radius: 18px; }
        .small-note { color: #64748b; font-size: .86rem; }
        </style>
        """,
        unsafe_allow_html=True,
    )


def init_state() -> None:
    if "profile" not in st.session_state:
        profile, warnings = validate_profile(UserProfile.from_dict(SAMPLES[0]["profile"]))
        st.session_state.profile = profile
        st.session_state.profile_warnings = warnings
    st.session_state.setdefault(
        "onboarding_text",
        "만 27세 서울 1인가구, 실업급여 45일 남았고 월소득 0원입니다. 3개월 뒤 알바 월소득 80만원 예정, 월세 55만원, 보증금 500만원, 신용점수 690점입니다.",
    )
    st.session_state.setdefault("last_parse_summary", "기본 샘플 프로필이 적용되어 있습니다.")
    st.session_state.setdefault("use_imported_policies", True)
    st.session_state.setdefault("demo_user_email", "demo@lifepass.local")
    st.session_state.setdefault("demo_user_name", "데모 상담사")
    st.session_state.setdefault("last_profile_id", None)
    st.session_state.setdefault("batch_result_df", pd.DataFrame())


def _safe_index(options: List[str], value: str, default: int = 0) -> int:
    return options.index(value) if value in options else default


def safe_number_input(label: str, min_value: int, max_value: int, value: Any, *, step: int = 1, key: str | None = None, help: str | None = None) -> int:
    lo, hi, safe_value = safe_widget_bounds(int(value or 0), min_value, max_value)
    return int(st.number_input(label, int(lo), int(hi), int(safe_value), step=step, key=key, help=help))


def dataframe_key(label: str, df: pd.DataFrame) -> str:
    schema = "|".join(f"{col}:{df[col].dtype}" for col in df.columns)
    digest = hashlib.md5(f"{label}|{df.shape}|{schema}".encode("utf-8")).hexdigest()[:12]
    return f"df_{digest}"


def render_df(df: pd.DataFrame | None, *, label: str, height: int | None = None) -> None:
    """Stable table renderer: no height=None, no traceback for empty data."""
    if df is None or df.empty:
        st.info(f"{label}: 해당 데이터 없음")
        return
    st.caption(f"{label}: {len(df):,}건")
    kwargs: Dict[str, Any] = {"use_container_width": True, "hide_index": True, "key": dataframe_key(label, df)}
    if isinstance(height, int) and height > 0:
        kwargs["height"] = height
    try:
        st.dataframe(df, **kwargs)
    except Exception:  # noqa: BLE001
        st.info(f"{label}: 인터랙티브 표 렌더링 실패로 정적 표를 표시합니다.")
        st.table(df)


def render_hero(profile: UserProfile) -> None:
    benefits = active_benefits()
    insights = compute_profile_insights(profile, benefits)
    st.markdown(
        """
        <div class="hero-card">
            <div class="status-pill">🌿 Agentic Public-Welfare Copilot · v5</div>
            <h1>🧭 LifePass AI Agent</h1>
            <p>자연어 상담 → 자격판정 룰엔진 → 복지 절벽 예측 → 신청 태스크 관리 → 외부 데이터/API 연동까지 이어지는 생애전환 복지 AI 운영 플랫폼</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    c1, c2, c3, c4 = st.columns(4)
    cards = [
        ("상담 우선도", f"{insights['priority_score']}점 · {insights['priority_grade']}", ", ".join(insights["reasons"][:2])),
        ("현재 월 지원효과", money(insights["current_support"]), f"선택 {insights['selected_count']}개 / 가능 {insights['eligible_count']}개"),
        ("월 현금 버퍼", money(insights["cash_buffer"]), "소득+지원-월세-상환 기준"),
        ("적재 정책 수", f"{len(benefits)}개", "기본 정책 + 외부 업로드 정책"),
    ]
    for col, (label, value, desc) in zip([c1, c2, c3, c4], cards):
        with col:
            st.markdown(f"<div class='insight-card'><div class='label'>{label}</div><div class='value'>{value}</div><div class='desc'>{desc}</div></div>", unsafe_allow_html=True)


def profile_editor(profile: UserProfile) -> UserProfile:
    st.subheader("구조화 프로필 직접 조작")
    profile, warnings = validate_profile(profile)
    if warnings:
        with st.expander("입력값 검증 경고", expanded=False):
            for warning in warnings:
                st.warning(warning)

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        age = safe_number_input("나이", 0, 120, profile.age, key="age")
        region = st.selectbox("지역", REGIONS, index=_safe_index(REGIONS, profile.region), key="region")
        household_size = safe_number_input("가구원 수", 1, 10, profile.household_size, key="household_size")
    with c2:
        employment_status = st.selectbox("고용상태", EMPLOYMENT_STATUSES, index=_safe_index(EMPLOYMENT_STATUSES, profile.employment_status), key="employment_status")
        monthly_income = safe_number_input("현재 월소득", 0, 50_000_000, profile.monthly_income, step=100_000, key="monthly_income")
        expected_monthly_income = safe_number_input("예상 월소득", 0, 50_000_000, profile.expected_monthly_income, step=100_000, key="expected_monthly_income")
        expected_income_start_month = safe_number_input("예상 소득 발생 월(M+)", 0, 60, profile.expected_income_start_month, key="expected_income_start_month")
    with c3:
        rent = safe_number_input("월세", 0, 20_000_000, profile.rent, step=50_000, key="rent")
        deposit = safe_number_input("보증금", 0, 5_000_000_000, profile.deposit, step=1_000_000, key="deposit")
        assets_million = safe_number_input("자산(백만원)", 0, 1_000_000, int(profile.assets_million), step=10, key="assets_million")
        has_housing_contract = st.checkbox("임대차계약 있음", value=bool(profile.has_housing_contract), key="has_housing_contract")
    with c4:
        unemployment_benefit_receiving = st.checkbox("실업급여 수급 중", value=bool(profile.unemployment_benefit_receiving), key="unemployment_benefit_receiving")
        unemployment_benefit_days_left = safe_number_input("실업급여 잔여일", 0, 3650, profile.unemployment_benefit_days_left, key="unemployment_days")
        medical_expense_3m = safe_number_input("최근 3개월 의료비", 0, 500_000_000, profile.medical_expense_3m, step=100_000, key="medical")
        credit_score = safe_number_input("신용점수", 0, 1000, profile.credit_score, key="credit")
        debt_monthly_payment = safe_number_input("월 대출상환", 0, 50_000_000, profile.debt_monthly_payment, step=50_000, key="debt")

    c5, c6, c7, c8 = st.columns(4)
    with c5:
        crisis_event = st.checkbox("위기사유 있음", value=bool(profile.crisis_event), key="crisis")
    with c6:
        is_basic_livelihood = st.checkbox("기초생활수급", value=bool(profile.is_basic_livelihood), key="basic")
    with c7:
        is_near_poverty = st.checkbox("차상위/취약계층", value=bool(profile.is_near_poverty), key="near_poverty")
    with c8:
        wants_job_training = st.checkbox("직업훈련 희망", value=bool(profile.wants_job_training), key="training")

    updated = UserProfile(
        age=int(age), region=region, household_size=int(household_size), employment_status=employment_status,
        monthly_income=int(monthly_income), expected_monthly_income=int(expected_monthly_income),
        expected_income_start_month=int(expected_income_start_month), rent=int(rent), deposit=int(deposit),
        assets_million=float(assets_million), unemployment_benefit_receiving=bool(unemployment_benefit_receiving),
        unemployment_benefit_days_left=int(unemployment_benefit_days_left), crisis_event=bool(crisis_event),
        medical_expense_3m=int(medical_expense_3m), credit_score=int(credit_score),
        debt_monthly_payment=int(debt_monthly_payment), is_basic_livelihood=bool(is_basic_livelihood),
        is_near_poverty=bool(is_near_poverty), has_housing_contract=bool(has_housing_contract),
        wants_job_training=bool(wants_job_training), notes=profile.notes,
    )
    updated, warnings = validate_profile(updated)
    st.session_state.profile_warnings = warnings
    return updated


def render_onboarding(profile: UserProfile) -> UserProfile:
    st.header("1. 카카오톡 스타일 온보딩·입력 통합")
    c1, c2 = st.columns([1.1, 1.4])
    with c1:
        st.markdown("<div class='chat-row'><div class='chat-bot'>안녕하세요! 상황을 한 문장으로 말해주시면 받을 수 있는 혜택과 상실 위험을 계산해드릴게요.</div></div>", unsafe_allow_html=True)
        st.markdown(f"<div class='chat-row'><div class='chat-user'>{st.session_state.onboarding_text}</div></div>", unsafe_allow_html=True)
        text = st.text_area("사용자 메시지", value=st.session_state.onboarding_text, height=140)
        if st.button("자연어 파싱해서 프로필 갱신"):
            parsed = parse_onboarding_text(text)
            parsed, parse_warnings = validate_profile(parsed)
            st.session_state.onboarding_text = text
            st.session_state.profile = parsed
            st.session_state.profile_warnings = parse_warnings
            st.session_state.last_parse_summary = (
                f"파싱 완료: 만 {parsed.age}세 / {parsed.region} / {parsed.household_size}인가구 / 월소득 {money(parsed.monthly_income)} / 월세 {money(parsed.rent)}"
            )
            st.rerun()
        st.caption(st.session_state.last_parse_summary)
        if st.session_state.profile_warnings:
            for warning in st.session_state.profile_warnings:
                st.warning(warning)
    with c2:
        updated = profile_editor(profile)
    return updated


def metric_cards(profile: UserProfile) -> None:
    benefits = active_benefits()
    evaluations = evaluate_all(benefits, profile)
    plan = optimize_benefits(evaluations)
    timeline = simulate_timeline(profile, benefits, [0, 3, 6, 12])
    cliff = simulate_income_cliff(profile, benefits)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("현재 최적 월 환산효과", money(plan.total_monthly_value))
    c2.metric("선택 혜택 수", f"{len(plan.selected)}개")
    c3.metric("3개월 후 순효과", money(timeline[1].net_effect if len(timeline) > 1 else 0))
    c4.metric("복지 절벽 경고", f"{sum(1 for r in cliff if r.warnings)}건")


def render_agent(profile: UserProfile) -> None:
    st.header("0. AI Agent 의사결정 코파일럿")
    st.caption("LLM이 임의로 자격을 판정하는 구조가 아니라, 각 도구 호출이 추적되는 deterministic agent pipeline입니다.")
    q = st.text_input("Agent에게 물어보기", "현재 가장 먼저 신청해야 하는 혜택과 3개월 뒤 상실 위험을 설명해줘")
    plan = build_agent_plan(profile, active_benefits(), question=q)
    c1, c2, c3 = st.columns(3)
    c1.metric("Agent 우선도", f"{plan['priority_score']}점", plan["priority_grade"])
    c2.metric("월 환산효과", money(plan["monthly_support"]))
    c3.metric("자동 액션", f"{len(plan['actions'])}개")
    st.markdown(f"<div class='agent-card'>{plan['answer_markdown']}</div>", unsafe_allow_html=True)

    col1, col2 = st.columns([1, 1.25])
    with col1:
        st.subheader("Agent tool trace")
        render_df(pd.DataFrame(plan["tool_trace"]), label="Agent 도구 호출", height=260)
    with col2:
        st.subheader("Next-best action queue")
        render_df(pd.DataFrame(plan["actions"]), label="자동 액션 큐", height=260)

    with st.expander("근거 문서와 선택 혜택"):
        render_df(pd.DataFrame([{"selected_benefit": x} for x in plan["selected_benefits"]]), label="선택 혜택")
        evidence_rows = [{"title": d.get("title"), "source": d.get("source", "local"), "snippet": d.get("text", "")[:220]} for d in plan["evidence"]]
        render_df(pd.DataFrame(evidence_rows), label="RAG 근거")


def render_current(profile: UserProfile) -> None:
    st.header("2. 현재 자격 판정·최적 조합")
    benefits = active_benefits()
    evaluations = evaluate_all(benefits, profile)
    plan = optimize_benefits(evaluations)
    metric_cards(profile)
    selected_df = pd.DataFrame([
        {"혜택": b.name, "영역": b.domain, "월 환산효과": b.monthly_value, "충돌그룹": b.conflict_group or "-", "경고": ", ".join(b.warnings)}
        for b in plan.selected
    ])
    st.subheader("충돌을 제거한 최적 조합")
    render_df(selected_df, label="최적 조합")
    if plan.explanation:
        st.info("\n".join(plan.explanation))

    st.subheader("신청 서류 통합 체크리스트")
    render_df(pd.DataFrame(make_document_checklist(plan.selected)), label="서류 체크리스트", height=260)

    st.subheader("전체 혜택 판정표")
    all_df = pd.DataFrame([
        {
            "혜택": ev.name,
            "영역": ev.domain,
            "가능": "✅" if ev.eligible else "❌",
            "월 환산효과": ev.monthly_value,
            "충족 조건": ", ".join(ev.matched[:3]),
            "미충족 조건": ", ".join(ev.unmet[:3]),
            "경고": ", ".join(ev.warnings),
        }
        for ev in evaluations
    ])
    render_df(all_df, label="전체 혜택 판정표", height=460)


def render_timeline(profile: UserProfile) -> None:
    st.header("3. 생애전환·복지 절벽 예측")
    benefits = active_benefits()
    rows = simulate_timeline(profile, benefits, [0, 1, 3, 6, 12])
    df = pd.DataFrame([
        {"시점": r.label, "월소득": r.income, "혜택 월 환산": r.benefit_value, "순효과": r.net_effect, "신규 가능": ", ".join(r.gained), "상실 위험": ", ".join(r.lost), "경고": ", ".join(r.warnings)}
        for r in rows
    ])
    if not df.empty:
        st.line_chart(df.set_index("시점")[["월소득", "혜택 월 환산", "순효과"]])
    render_df(df, label="생애전환 예측", height=300)

    st.subheader("실행 타임라인")
    for ev in generate_timeline_events(profile, benefits):
        with st.expander(f"M+{ev.month} · {ev.title} · {ev.risk_level}", expanded=ev.risk_level in {"warning", "danger"}):
            st.write(ev.description)
            for item in ev.action_items:
                st.write(f"- {item}")

    st.subheader("소득별 복지 절벽 시뮬레이터")
    cliff_rows = simulate_income_cliff(profile, benefits)
    cliff_df = pd.DataFrame([
        {"시나리오": r.label, "월소득": r.income, "혜택 월 환산": r.benefit_value, "순효과": r.net_effect, "상실 혜택": ", ".join(r.lost), "신규 혜택": ", ".join(r.gained), "경고": ", ".join(r.warnings)}
        for r in cliff_rows
    ])
    if not cliff_df.empty:
        st.bar_chart(cliff_df.set_index("시나리오")[["월소득", "혜택 월 환산", "순효과"]])
    render_df(cliff_df, label="복지 절벽 시나리오", height=340)
    if any(r.warnings for r in cliff_rows):
        st.warning("일부 소득 구간에서 혜택 상실로 순효과가 감소하거나 둔화됩니다. 신청 순서와 근로 시작 시점을 재검토하세요.")
    else:
        st.success("현재 시나리오에서는 명확한 역전형 복지 절벽이 감지되지 않았습니다.")


def render_batch() -> None:
    st.header("4. 외부 데이터셋 CSV 일괄 분석")
    st.caption("기관이 보유한 여러 사용자 데이터를 CSV로 업로드하면 같은 룰엔진·Agent 파이프라인으로 상담 우선순위를 계산합니다.")
    st.download_button("프로필 CSV 템플릿 다운로드", template_csv_bytes(), file_name="lifepass_profile_template.csv", mime="text/csv")
    uploaded = st.file_uploader("다수 사용자 CSV 업로드", type=["csv"], key="batch_csv")
    df = None
    if uploaded is not None:
        try:
            df = pd.read_csv(uploaded)
        except Exception as exc:  # noqa: BLE001
            st.error(f"CSV 읽기 실패: {exc}")
    if df is None:
        df = pd.read_csv(__import__("io").BytesIO(template_csv_bytes()))
        st.info("업로드된 CSV가 없어 템플릿 예시 데이터로 미리보기를 표시합니다.")
    st.subheader("원본 데이터 미리보기")
    render_df(df.head(30), label="업로드 원본", height=260)
    result_df, profiles = analyze_profiles(df, active_benefits())
    st.subheader("Agent 상담 큐")
    render_df(result_df, label="일괄 분석 결과", height=430)
    st.session_state.batch_result_df = result_df
    if not result_df.empty:
        st.download_button("상담 큐 CSV 다운로드", result_df.to_csv(index=False).encode("utf-8-sig"), file_name="lifepass_batch_result.csv", mime="text/csv")
    if profiles and st.button("일괄 분석 프로필을 DB에 저장"):
        user_id = upsert_user(st.session_state.demo_user_email, st.session_state.demo_user_name)
        for idx, p in enumerate(profiles, start=1):
            save_profile(p, name=f"batch_profile_{idx}", user_id=user_id)
        st.success(f"{len(profiles)}개 프로필을 저장했습니다.")


def render_policy_center() -> None:
    st.header("5. 정책 데이터 수집·정제 센터")
    st.caption("실제 공공 API/크롤러 결과를 CSV로 받아 내부 JSON 룰 카탈로그로 변환하는 데모 파이프라인입니다.")
    st.download_button("정책 피드 CSV 템플릿 다운로드", template_policy_csv_bytes(), file_name="lifepass_policy_feed_template.csv", mime="text/csv")
    uploaded = st.file_uploader("정책/공고 CSV 업로드", type=["csv"], key="policy_csv")
    if uploaded is not None:
        try:
            feed_df = pd.read_csv(uploaded)
            benefits, warnings = benefits_from_dataframe(feed_df)
            st.subheader("변환된 정책 미리보기")
            preview = pd.DataFrame([{k: b.get(k) for k in ["id", "name", "domain", "estimated_monthly_value", "priority"]} for b in benefits])
            render_df(preview, label="정책 변환 결과", height=260)
            if warnings:
                for warning in warnings:
                    st.warning(warning)
            if st.button("외부 정책을 imported_benefits.json으로 저장"):
                path = save_imported_benefits(benefits)
                st.session_state.use_imported_policies = True
                st.success(f"{len(benefits)}개 정책을 저장했습니다: {path}")
                st.rerun()
        except Exception as exc:  # noqa: BLE001
            st.error(f"정책 피드 처리 실패: {exc}")
    else:
        st.info("정책 CSV를 업로드하면 내부 룰엔진용 JSON으로 변환합니다. 현재는 예시 템플릿을 내려받아 구조를 확인하세요.")

    try:
        imported = load_imported_benefits()
    except Exception as exc:  # noqa: BLE001
        imported = []
        st.warning(f"저장된 외부 정책 로딩 실패: {exc}")
    st.subheader("현재 적재된 외부 정책")
    render_df(pd.DataFrame([{k: b.get(k) for k in ["id", "name", "domain", "estimated_monthly_value", "priority"]} for b in imported]), label="외부 정책 카탈로그", height=260)


def render_db_tasks(profile: UserProfile) -> None:
    st.header("6. 로그인·DB 저장·신청 상태 추적")
    st.caption("MVP는 SQLite로 즉시 실행되고, 배포 시 PostgreSQL 연결로 확장하는 구조입니다.")
    c1, c2 = st.columns([.9, 1.4])
    with c1:
        st.subheader("데모 로그인")
        st.session_state.demo_user_name = st.text_input("사용자/상담사 이름", st.session_state.demo_user_name)
        st.session_state.demo_user_email = st.text_input("이메일", st.session_state.demo_user_email)
        if st.button("DB 초기화/사용자 저장"):
            init_db()
            user_id = upsert_user(st.session_state.demo_user_email, st.session_state.demo_user_name)
            st.success(f"사용자 ID {user_id} 준비 완료")
        status = db_status()
        st.json(status)
    with c2:
        st.subheader("현재 분석 결과 저장")
        benefits = active_benefits()
        evaluations = evaluate_all(benefits, profile)
        plan = optimize_benefits(evaluations)
        insights = compute_profile_insights(profile, benefits)
        if st.button("현재 프로필·분석·신청 태스크 저장"):
            user_id = upsert_user(st.session_state.demo_user_email, st.session_state.demo_user_name)
            profile_id = save_profile(profile, name=f"{profile.region}_{profile.age}세_프로필", user_id=user_id)
            st.session_state.last_profile_id = profile_id
            save_analysis_run(profile_id, "현재 프로필", {"insights": insights, "selected_benefits": [b.name for b in plan.selected], "monthly_support": plan.total_monthly_value})
            created = create_tasks_from_benefits(profile_id, plan.selected)
            st.success(f"profile_id={profile_id}, 신청 태스크 {created}개 생성")

    st.subheader("저장된 프로필")
    render_df(pd.DataFrame(list_profiles()), label="DB 프로필", height=260)
    st.subheader("신청 태스크 보드")
    tasks = pd.DataFrame(list_tasks())
    render_df(tasks, label="신청 태스크", height=320)
    if not tasks.empty:
        c3, c4, c5 = st.columns([.6, .8, 1.4])
        with c3:
            task_id = st.number_input("상태 변경 task_id", min_value=1, value=int(tasks.iloc[0]["id"]))
        with c4:
            status = st.selectbox("새 상태", ["todo", "in_progress", "submitted", "approved", "rejected"])
        with c5:
            if st.button("태스크 상태 변경"):
                update_task_status(int(task_id), status)
                st.success("상태를 변경했습니다.")
                st.rerun()


def render_strategy(profile: UserProfile) -> None:
    st.header("7. 신청 전략·근거 설명·API 계약")
    benefits = active_benefits()
    strategy = build_application_strategy(profile, benefits)
    if not strategy:
        st.info("신청 전략: 해당 데이터 없음")
    for benefit_name, items in strategy.items():
        with st.expander(benefit_name, expanded=True):
            for item in items:
                st.write(f"- {item}")
    st.subheader("근거 검색 요약")
    query = st.text_input("근거 검색 질문", "실업급여 종료 후 국민취업지원 청년월세 복지절벽")
    st.markdown(explain_with_evidence(query))
    c1, c2 = st.columns(2)
    with c1:
        report = make_markdown_report(profile, benefits)
        st.download_button("분석 리포트 Markdown 다운로드", report, file_name="lifepass_report.md", mime="text/markdown")
    with c2:
        export = {"profile": profile.to_dict(), "agent_plan": build_agent_plan(profile, benefits, query)}
        st.download_button("Agent 결과 JSON 다운로드", json.dumps(export, ensure_ascii=False, indent=2), file_name="lifepass_agent_export.json", mime="application/json")
    st.subheader("REST API 계약 예시")
    st.code(examples_json(), language="json")
    st.caption("api.py 실행: `uvicorn api:app --reload --port 8000` 후 `/api/v1/analyze`, `/api/v1/batch/analyze`, `/api/v1/policies/preview` 사용")


def render_admin() -> None:
    st.header("8. 기관/운영자 대시보드")
    profiles = sample_profiles_as_models()
    metrics = build_admin_metrics(profiles, active_benefits())
    c1, c2, c3 = st.columns(3)
    c1.metric("데모 사용자 수", metrics.total_profiles)
    c2.metric("복지 절벽 고위험", metrics.high_cliff_risk)
    c3.metric("평균 월 지원효과", money(metrics.average_monthly_support))
    render_df(pd.DataFrame(metrics.top_benefits), label="상위 추천 혜택", height=300)
    render_df(pd.DataFrame(metrics.region_summary), label="지역별 요약", height=300)
    render_df(pd.DataFrame(metrics.pending_actions), label="우선 상담 큐", height=300)



def render_public_api_gateway() -> None:
    st.header("9. 공공 API Gateway·라이브 정책 동기화")
    st.caption("복지로·정부24·고용24·지자체 API 또는 기관 Gateway를 환경변수 기반 커넥터로 직접 호출하고, 응답을 내부 JSON 룰 카탈로그로 변환합니다.")

    st.subheader("Source registry / 연결 상태")
    status_df = pd.DataFrame(source_status_rows())
    render_df(status_df, label="공공 API 소스 상태", height=260)

    c1, c2, c3 = st.columns([.9, 1.2, .7])
    specs = load_source_specs()
    source_options = [s.source_id for s in specs]
    with c1:
        source_id = st.selectbox("호출 소스", source_options, index=0, key="live_source_id")
    with c2:
        query = st.text_input("검색어/동기화 키워드", "청년 주거 구직 생활안정", key="live_query")
    with c3:
        limit = safe_number_input("최대 수집", 1, 200, 20, key="live_limit")

    st.info("실제 기관 API 엔드포인트와 키가 있으면 환경변수(LIFEPASS_BOKJIRO_ENDPOINT 등)를 설정해 live call을 수행합니다. 설정이 없으면 동일 파이프라인을 검증하기 위해 bundled sample mode로 동작합니다.")

    if st.button("공공 API 호출·정책 룰 변환 실행", key="fetch_public_api"):
        with trace_span("ui.public_api_fetch", source_id=source_id, query=query):
            result = fetch_source_policies(source_id, query=query, limit=int(limit))
        st.session_state.last_fetch_result = result.to_dict()
        st.success(f"수집 모드: {result.mode}, 변환 정책 {len(result.benefits)}개, payload hash {result.payload_hash[:12]}")

    result_payload = st.session_state.get("last_fetch_result")
    if result_payload:
        st.subheader("API 응답 정규화 결과")
        meta = {k: result_payload.get(k) for k in ["source_id", "ok", "mode", "fetched_at", "payload_hash", "endpoint_used"]}
        st.json(meta)
        if result_payload.get("warnings"):
            with st.expander("수집·변환 경고", expanded=False):
                for warning in result_payload["warnings"]:
                    st.warning(warning)
        render_df(pd.DataFrame(result_payload.get("rows", [])).head(20), label="원본 응답 rows", height=260)
        preview_rows = [{k: b.get(k) for k in ["id", "name", "domain", "estimated_monthly_value", "priority", "target"]} for b in result_payload.get("benefits", [])]
        render_df(pd.DataFrame(preview_rows), label="룰 카탈로그 변환 결과", height=260)
        if st.button("변환 정책을 imported_benefits.json으로 저장", key="save_live_benefits"):
            before = load_imported_benefits()
            save_imported_benefits(result_payload.get("benefits", []))
            after = load_imported_benefits()
            st.session_state.use_imported_policies = True
            st.session_state.last_policy_diff = diff_catalogs(before, after)
            st.success(f"외부 정책 {len(after)}개를 저장했습니다.")
            st.rerun()

    st.subheader("카탈로그 변경 diff")
    diff = st.session_state.get("last_policy_diff")
    if diff:
        c4, c5, c6, c7 = st.columns(4)
        c4.metric("추가", diff.get("added_count", 0))
        c5.metric("변경", diff.get("changed_count", 0))
        c6.metric("삭제", diff.get("removed_count", 0))
        c7.metric("유지", diff.get("unchanged_count", 0))
    else:
        st.info("정책 저장 후 diff 결과가 표시됩니다.")


def render_advanced_ai(profile: UserProfile) -> None:
    st.header("10. 고급 AI·신뢰성·운영기술")
    benefits = active_benefits()
    question = st.text_input("정책 의미 검색", "실업급여 종료 후 청년 월세 구직 훈련", key="semantic_query")
    st.subheader("Local semantic policy retrieval")
    render_df(pd.DataFrame(search_policies(question, benefits, top_k=8)), label="정책 의미 검색 결과", height=300)

    st.subheader("Counterfactual what-if 엔진")
    cf_rows = build_counterfactuals(profile, benefits)
    render_df(pd.DataFrame(cf_rows), label="조건 변경 시나리오", height=300)
    if cf_rows:
        best = cf_rows[0]
        if int(best.get("delta", 0)) > 0:
            st.success(f"가장 유리한 조건 변경: {best['scenario']} / 예상 변화 {best['delta_label']}")
        else:
            st.info("현재 조건에서 추가적인 월 환산효과 증가 시나리오가 크지 않습니다.")

    st.subheader("Trust audit / Responsible AI pack")
    agent_plan = build_agent_plan(profile, benefits, question="trust audit")
    audit = build_trust_audit(profile, benefits, agent_plan)
    c1, c2, c3 = st.columns(3)
    c1.metric("Audit score", f"{audit['audit_score']}점")
    c2.metric("Audit status", audit["status"])
    c3.metric("Agent tools", f"{len(agent_plan.get('tool_trace', []))}개")
    render_df(pd.DataFrame(controls_dataframe_rows(audit)), label="AI 신뢰성 통제", height=330)

    st.subheader("MCP-style tool manifest")
    manifest = tool_manifest()
    render_df(pd.DataFrame(manifest["tools"]), label="Agent tool manifest", height=320)
    st.download_button("tool_manifest.json 다운로드", json.dumps(manifest, ensure_ascii=False, indent=2), file_name="lifepass_tool_manifest.json", mime="application/json")

    st.subheader("Privacy·consent packet")
    packet = consent_packet(profile.to_dict())
    st.json(packet)
    masked_note = mask_text(profile.notes or "demo@lifepass.local / 010-1234-5678 포함 상담 메모 예시")
    st.caption(f"PII masking 예시: {masked_note}")
    st.caption(f"Pseudonymous profile id: {pseudonymize_identifier(profile.region + str(profile.age) + str(profile.rent))}")

    st.subheader("Observability traces")
    with trace_span("ui.advanced_ai_panel", profile_region=profile.region, benefit_count=len(benefits)):
        pass
    render_df(pd.DataFrame(recent_traces()), label="최근 trace events", height=260)


def render_v4_platform(profile: UserProfile) -> None:
    st.header("11. v4 운영형 플랫폼 강화: DBMS·Agent Workflow·신청 자동화")
    benefits = active_benefits()
    evaluations = evaluate_all(benefits, profile)
    plan = optimize_benefits(evaluations)

    st.subheader("PostgreSQL + pgvector-ready DBMS")
    st.caption("로컬 시연은 SQLite로 즉시 실행되며, 운영 배포에서는 PostgreSQL + pgvector로 정책 문서 RAG·Agent 감사로그·멀티테넌트 저장소를 구성합니다.")
    render_df(pd.DataFrame(dbms_capabilities()), label="DBMS capability matrix", height=260)
    with st.expander("PostgreSQL/pgvector DDL 미리보기", expanded=False):
        st.code(POSTGRES_PGVECTOR_DDL, language="sql")
        st.json(deployment_readiness()["recommended_env"])

    st.subheader("Human-in-the-loop Agent Workflow")
    workflow = build_agent_workflow(profile, benefits, question="복지 절벽을 막기 위한 우선 액션을 결정")
    c1, c2, c3 = st.columns(3)
    c1.metric("Human review", "필요" if workflow["human_review_required"] else "불필요")
    c2.metric("Audit score", f"{workflow['audit_score']}점")
    c3.metric("Workflow steps", f"{len(workflow['steps'])}개")
    render_df(pd.DataFrame(workflow["steps"]), label="Agent workflow trace", height=340)

    st.subheader("Durable Application Workflow + Deadline Notification")
    app_wf = build_application_workflow(profile, plan.selected)
    notifications = plan_notifications(profile, app_wf)
    c4, c5, c6 = st.columns(3)
    c4.metric("신청 workflow task", f"{len(app_wf['tasks'])}개")
    c5.metric("알림 예약", f"{len(notifications)}개")
    c6.metric("Workflow durability", "enabled")
    render_df(pd.DataFrame(app_wf["tasks"]), label="신청 durable workflow", height=320)
    render_df(pd.DataFrame(notifications), label="Deadline-aware notification queue", height=260)

    st.subheader("Constraint Optimization Engine")
    portfolio = solve_benefit_portfolio(evaluations)
    b1, b2, b3 = st.columns(3)
    b1.metric("Objective score", portfolio.get("breakdown", {}).get("objective_score", 0))
    b2.metric("Conflict free", "Yes" if portfolio.get("conflict_free") else "No")
    b3.metric("Selected", len(portfolio.get("selected", [])))
    render_df(pd.DataFrame(portfolio.get("selected", [])), label="ILP-style 최적 혜택 포트폴리오", height=260)
    with st.expander("목적함수 breakdown", expanded=False):
        st.json(portfolio.get("breakdown", {}))

    st.subheader("Multi-tenant deployment")
    st.json(current_tenant())
    render_df(pd.DataFrame(tenant_rows()), label="테넌트 구성", height=220)


def render_v4_data_intelligence(profile: UserProfile) -> None:
    st.header("12. v4 데이터 인텔리전스: 스마트 매퍼·문서파서·지식그래프")
    benefits = active_benefits()

    st.subheader("Smart Data Mapper for external CSV")
    st.caption("기관·기업마다 다른 컬럼명을 표준 UserProfile schema로 자동 매핑합니다. 예: 월세/monthly_rent/housing_cost → rent")
    sample_mapper = pd.DataFrame({
        "만나이": [27, 32],
        "거주지역": ["서울", "경기"],
        "가구원수": [1, 2],
        "월소득": ["0원", "180만원"],
        "월임대료": ["55만원", "70만원"],
        "보증금": ["500만원", "3000만원"],
        "실업급여잔여일": [45, 0],
        "신용점수": [690, 720],
    })
    uploaded = st.file_uploader("외부 사용자 CSV 업로드 - 스마트 매핑", type=["csv"], key="smart_mapper_csv")
    mapper_df = pd.read_csv(uploaded) if uploaded is not None else sample_mapper
    mapping, suggestions = infer_mapping(mapper_df.columns)
    render_df(pd.DataFrame(suggestions), label="컬럼 자동 매핑 후보", height=260)
    profiles, mapped_df, warnings = map_dataframe_to_profiles(mapper_df, mapping)
    render_df(mapped_df.head(20), label="표준 UserProfile 변환 결과", height=320)
    if warnings:
        with st.expander("매핑·검증 경고", expanded=False):
            for warning in warnings[:30]:
                st.warning(warning)
    if profiles:
        batch_result, _ = analyze_profiles(mapper_df.rename(columns={v: k for k, v in mapping.items()}), benefits)
        render_df(batch_result, label="스마트 매퍼 기반 일괄 상담 큐", height=320)

    st.subheader("Policy Document Parser")
    default_doc = """정책명: 서울 청년 전월세 안정 지원\n대상: 만 19세~34세 서울 거주 청년\n지원: 매월 20만원\n서류: 주민등록등본, 임대차계약서, 소득자료\n신청: 온라인 접수"""
    doc_text = st.text_area("정책 공고문/PDF 추출 텍스트", default_doc, height=150, key="policy_doc_text")
    facts = extract_policy_facts(doc_text)
    draft = draft_benefit_from_text(doc_text)
    c1, c2 = st.columns(2)
    with c1:
        st.json(facts)
    with c2:
        st.json({k: draft.get(k) for k in ["id", "name", "domain", "estimated_monthly_value", "required_docs"]})
    st.caption("문서 파서 결과는 review_status=draft_requires_human_review 상태로 생성되어 운영자 검수 후 정책 카탈로그에 반영됩니다.")

    st.subheader("Eligibility Knowledge Graph")
    graph = build_eligibility_graph(profile, evaluate_all(benefits, profile))
    g1, g2, g3 = st.columns(3)
    g1.metric("Nodes", len(graph["nodes"]))
    g2.metric("Edges", len(graph["edges"]))
    g3.metric("Eligible edges", sum(1 for e in graph["edges"] if e.get("relation") == "eligible_for"))
    render_df(pd.DataFrame(graph_rows(graph)).head(80), label="자격판정 지식그래프 edge/node", height=380)
    st.download_button("eligibility_graph.json 다운로드", json.dumps(graph, ensure_ascii=False, indent=2), file_name="eligibility_graph.json", mime="application/json")


def render_v4_quality_api(profile: UserProfile) -> None:
    st.header("13. v4 품질평가·Guardrails·API-first SDK")
    benefits = active_benefits()

    st.subheader("Recommendation Evaluation & Benchmark Suite")
    benchmark = run_benchmark(benefits)
    m = benchmark["metrics"]
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Cases", m["cases"])
    c2.metric("Precision proxy", m["precision_proxy_avg"])
    c3.metric("Recall proxy", m["recall_proxy_avg"])
    c4.metric("Conflict violation", m["conflict_violation_rate"])
    render_df(pd.DataFrame(benchmark["rows"]), label="추천 품질 benchmark", height=330)

    st.subheader("Typed Output Guardrails")
    payload = profile.to_dict()
    guard = validate_structured_payload(payload, schema_name="UserProfile")
    c5, c6, c7 = st.columns(3)
    c5.metric("Schema", guard["schema"])
    c6.metric("Valid", "Yes" if guard["ok"] else "No")
    c7.metric("Warnings", len(guard["warnings"]))
    if guard["errors"]:
        for err in guard["errors"]:
            st.error(err)
    if guard["warnings"]:
        for warning in guard["warnings"]:
            st.warning(warning)
    with st.expander("Guardrail clean payload", expanded=False):
        st.json(guard["clean_payload"])

    st.subheader("API-first SDK & OpenAPI integration")
    st.caption("대시보드뿐 아니라 지자체 상담 시스템, 모바일 앱, 챗봇, 콜센터 시스템이 REST API로 같은 엔진을 호출할 수 있습니다.")
    st.code(curl_examples(), language="bash")
    st.code("""from core.sdk import LifePassClient\nclient = LifePassClient('http://localhost:8000')\nresult = client.analyze({'age': 27, 'region': '서울', 'monthly_income': 0, 'rent': 550000})\nprint(result['monthly_support'])""", language="python")

    st.subheader("OpenTelemetry-style observability snapshot")
    with trace_span("ui.v4_quality_api", profile_age=profile.age, policy_count=len(benefits)):
        pass
    render_df(pd.DataFrame(recent_traces()), label="Agent/API trace events", height=300)


def render_v5_realtime_digital_twin(profile: UserProfile) -> None:
    st.header("14. v5 실시간 Event Mesh · 정책 Digital Twin")
    st.caption("정적 추천 화면을 넘어, life-signal 이벤트가 들어오면 자격 판정·마감 알림·감사 로그가 outbox/event mesh로 흘러가는 운영 구조를 시연합니다.")
    event_pack = event_ops_dashboard(profile)
    m = event_pack["metrics"]
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Generated events", m["events_generated"])
    c2.metric("Event types", m["event_types"])
    c3.metric("Outbox ready", m["outbox_ready"])
    c4.metric("DLQ", m["dead_letter"])
    render_df(pd.DataFrame(event_pack["events"]), label="이벤트 envelope", height=280)
    render_df(pd.DataFrame(event_pack["outbox"]["rows"]), label="Transactional outbox", height=260)
    render_df(pd.DataFrame(event_pack["consumers"]), label="Event consumer topology", height=240)

    st.subheader("정책 Digital Twin: 시행 전 영향 시뮬레이션")
    st.caption("정책 연령 상한·지원금 변동이 사용자군, 예산, 신규 지원 규모에 미치는 영향을 사전에 계산합니다.")
    age_upper = st.slider("청년 정책 연령 상한 시나리오", 34, 45, 39)
    value_multiplier = st.slider("청년 정책 지원액 배수", 0.5, 2.0, 1.0, step=0.1)
    profiles = [UserProfile.from_dict(item["profile"]) for item in SAMPLES]
    impact = simulate_policy_impact(profiles, active_benefits(), age_upper=age_upper, value_multiplier=value_multiplier)
    im = impact["metrics"]
    d1, d2, d3, d4 = st.columns(4)
    d1.metric("Simulated cases", im["profiles_simulated"])
    d2.metric("Newly supported", im["newly_supported"])
    d3.metric("월 예산 변화", money(im["monthly_budget_delta"]))
    d4.metric("연 환산 변화", money(im["annualized_budget_delta"]))
    render_df(pd.DataFrame(impact["rows"]), label="정책 변경 영향 대상자", height=320)
    with st.expander("Digital Twin scenario JSON", expanded=False):
        st.json({"scenario": impact["scenario"], "metrics": impact["metrics"], "decision_use": impact["decision_use"]})


def render_v5_security_causal_quality(profile: UserProfile) -> None:
    st.header("15. v5 Zero-Trust 보안 · Causal Ops · 품질운영")
    st.caption("복지·공공 영역에 필요한 접근통제, 개인정보 보호 집계, 상담 개입효과 추정, 운영 품질 관리 체계를 한 화면에 통합합니다.")

    st.subheader("Purpose-based RBAC/ABAC + Differential Privacy")
    security = privacy_security_pack(profile)
    a1, a2, a3 = st.columns(3)
    a1.metric("Access decision", security["access_decision"]["decision"])
    a2.metric("DP ε demo", security["dp_demo"]["epsilon"])
    a3.metric("Synthetic records", len(security["synthetic_profiles"]))
    st.json(security["access_decision"])
    render_df(pd.DataFrame(security["privacy_budget"]), label="Privacy budget ledger", height=230)
    render_df(pd.DataFrame(security["synthetic_profiles"]), label="비식별 synthetic profile", height=260)

    st.subheader("Causal Intervention Ranking")
    causal = estimate_intervention_effects(profile)
    c1, c2 = st.columns(2)
    c1.metric("Drop-off risk proxy", causal["base_dropoff_risk"])
    c2.metric("Best action", causal["recommended_interventions"][0]["intervention"] if causal["recommended_interventions"] else "해당 데이터 없음")
    render_df(pd.DataFrame(causal["recommended_interventions"]), label="상담 개입 uplift·ROI proxy", height=280)
    st.caption("실제 운영 데이터가 축적되면 uplift model, doubly robust estimator, A/B test 결과로 교체 가능한 구조입니다.")

    st.subheader("Data Contract · Model Card · Incident Playbook")
    ops = quality_ops_pack()
    left, right = st.columns(2)
    with left:
        st.json(ops["data_contract"])
    with right:
        st.json(ops["model_card"])
    render_df(pd.DataFrame(ops["sla_playbook"]), label="SLA/Incident playbook", height=240)

    st.subheader("Access-control interactive check")
    role = st.selectbox("Role", ["citizen", "counselor", "supervisor", "auditor", "admin"], index=1, key="v5_role")
    purpose = st.selectbox("Purpose", ["eligibility_screening", "application_support", "audit", "analytics"], index=0, key="v5_purpose")
    fields = st.multiselect("Requested fields", ["age", "region", "household_size", "monthly_income", "rent", "deposit", "credit_score", "medical_expense_3m"], default=["age", "region", "monthly_income", "rent", "deposit"], key="v5_fields")
    st.json(check_access(role, "read:assigned", purpose, fields))

def handle_sidebar() -> None:
    with st.sidebar:
        st.header("LifePass Control")
        st.session_state.use_imported_policies = st.toggle("외부 업로드 정책 포함", value=st.session_state.use_imported_policies)
        st.caption(f"현재 정책 수: {len(active_benefits())}개")
        sample_names = [s["name"] for s in SAMPLES]
        selected = st.selectbox("샘플 페르소나", sample_names)
        if st.button("샘플 적용"):
            item = next(s for s in SAMPLES if s["name"] == selected)
            profile, warnings = validate_profile(UserProfile.from_dict(item["profile"]))
            st.session_state.profile = profile
            st.session_state.profile_warnings = warnings
            st.session_state.last_parse_summary = f"샘플 '{selected}' 적용 완료"
            st.rerun()

        uploaded = st.file_uploader("프로필 JSON 업로드", type=["json"])
        if uploaded is not None:
            try:
                payload = json.load(uploaded)
                raw_profile = payload.get("profile", payload) if isinstance(payload, dict) else {}
                profile, warnings = validate_profile(UserProfile.from_dict(raw_profile))
                st.session_state.profile = profile
                st.session_state.profile_warnings = warnings
                st.session_state.last_parse_summary = "업로드 JSON 프로필 적용 완료"
                st.success("업로드 프로필을 적용했습니다.")
            except Exception as exc:  # noqa: BLE001
                st.warning(f"JSON 업로드 실패: {exc}")
        st.divider()
        st.markdown("**대상급 포인트**")
        st.caption("Docker Compose 기반 DBMS, 이벤트 아키텍처, 정책 Digital Twin, Zero-Trust 보안, Causal Ops, 품질운영까지 한 흐름으로 시연합니다.")


def main() -> None:
    inject_theme_css()
    init_state()
    handle_sidebar()

    profile, warnings = validate_profile(st.session_state.profile)
    profile = normalize_profile(profile)
    st.session_state.profile = profile
    st.session_state.profile_warnings = warnings
    render_hero(profile)

    tabs = st.tabs(["AI Agent", "온보딩/프로필", "현재 판정", "생애전환/절벽", "CSV 일괄분석", "정책 수집", "DB/신청관리", "전략·API", "운영자", "공공 API Gateway", "고급 AI/신뢰성", "v4 운영플랫폼", "v4 데이터지능", "v4 품질/API", "v5 실시간·정책트윈", "v5 보안·인과·품질"] )
    with tabs[0]:
        render_agent(profile)
    with tabs[1]:
        st.session_state.profile = render_onboarding(st.session_state.profile)
    with tabs[2]:
        render_current(normalize_profile(st.session_state.profile))
    with tabs[3]:
        render_timeline(normalize_profile(st.session_state.profile))
    with tabs[4]:
        render_batch()
    with tabs[5]:
        render_policy_center()
    with tabs[6]:
        render_db_tasks(normalize_profile(st.session_state.profile))
    with tabs[7]:
        render_strategy(normalize_profile(st.session_state.profile))
    with tabs[8]:
        render_admin()
    with tabs[9]:
        render_public_api_gateway()
    with tabs[10]:
        render_advanced_ai(normalize_profile(st.session_state.profile))
    with tabs[11]:
        render_v4_platform(normalize_profile(st.session_state.profile))
    with tabs[12]:
        render_v4_data_intelligence(normalize_profile(st.session_state.profile))
    with tabs[13]:
        render_v4_quality_api(normalize_profile(st.session_state.profile))
    with tabs[14]:
        render_v5_realtime_digital_twin(normalize_profile(st.session_state.profile))
    with tabs[15]:
        render_v5_security_causal_quality(normalize_profile(st.session_state.profile))


if __name__ == "__main__":
    main()
