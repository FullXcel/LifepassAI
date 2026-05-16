"""LifePass AI Streamlit MVP+.

Run:
    streamlit run app.py

This upgraded version focuses on demo stability and presentation quality:
- Robust natural-language onboarding with validation guardrails
- Safe Streamlit number inputs that never crash on parsed out-of-range values
- Deterministic welfare/finance eligibility rule engine
- Conflict-aware optimal benefit combination
- 3/6/12-month life-transition simulation
- Benefit cliff scenario simulation
- Actionable priority score, document checklist, and JSON import/export
- Bright green CSS theme for competition demo videos
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, List

import pandas as pd
import streamlit as st

from core.admin import build_admin_metrics
from core.benefit_catalog import load_benefits
from core.demo_data import load_sample_profiles, sample_profiles_as_models
from core.insights import compute_profile_insights, make_document_checklist
from core.models import UserProfile
from core.optimizer import optimize_benefits
from core.profile_parser import parse_onboarding_text
from core.rag import explain_with_evidence
from core.report import make_markdown_report
from core.rule_engine import evaluate_all
from core.simulator import build_application_strategy, generate_timeline_events, simulate_income_cliff, simulate_timeline
from core.utils import money, normalize_profile
from core.validation import safe_widget_bounds, validate_profile

st.set_page_config(page_title="LifePass AI", page_icon="🧭", layout="wide")

BENEFITS = load_benefits()
SAMPLES = load_sample_profiles()

REGIONS = ["서울", "경기", "인천", "부산", "대구", "대전", "광주", "울산", "세종", "전북", "전남", "충북", "충남", "경북", "경남", "강원", "제주"]
EMPLOYMENT_STATUSES = ["unemployed", "job_seeker", "part_time", "employed", "freelancer", "student"]
NO_DATA_TEXT = "해당 데이터 없음"


def inject_theme_css() -> None:
    st.markdown(
        """
        <style>
        :root {
            --lp-green-900: #064e3b;
            --lp-green-800: #065f46;
            --lp-green-700: #047857;
            --lp-green-600: #059669;
            --lp-green-500: #10b981;
            --lp-green-300: #6ee7b7;
            --lp-green-100: #d1fae5;
            --lp-lime-100: #ecfccb;
            --lp-mint: #f0fdf4;
            --lp-ink: #0f172a;
        }
        .stApp {
            background:
                radial-gradient(circle at top left, rgba(16,185,129,0.22), transparent 28rem),
                radial-gradient(circle at top right, rgba(132,204,22,0.22), transparent 24rem),
                linear-gradient(135deg, #f7fee7 0%, #ecfdf5 42%, #f8fafc 100%);
            color: var(--lp-ink);
        }
        [data-testid="stSidebar"] {
            background: linear-gradient(180deg, #064e3b 0%, #047857 45%, #10b981 100%);
        }
        /* Do NOT apply color to every sidebar descendant. Streamlit widgets
           contain nested buttons/inputs; a global wildcard made uploader text
           almost invisible on a white widget background. */
        [data-testid="stSidebar"] h1,
        [data-testid="stSidebar"] h2,
        [data-testid="stSidebar"] h3,
        [data-testid="stSidebar"] p,
        [data-testid="stSidebar"] label,
        [data-testid="stSidebar"] .stMarkdown,
        [data-testid="stSidebar"] [data-testid="stCaptionContainer"] {
            color: #f7fee7 !important;
        }
        [data-testid="stSidebar"] [data-testid="stWidgetLabel"] p {
            color: #f7fee7 !important;
            font-weight: 800;
        }
        [data-testid="stSidebar"] input,
        [data-testid="stSidebar"] textarea,
        [data-testid="stSidebar"] [data-baseweb="select"] *,
        [data-testid="stSidebar"] [data-testid="stFileUploader"] section *,
        [data-testid="stSidebar"] [data-testid="stFileUploader"] button {
            color: #0f172a !important;
        }
        [data-testid="stSidebar"] [data-testid="stFileUploader"] section {
            background: #ffffff !important;
            border: 1px solid rgba(209,250,229,0.95) !important;
            border-radius: 14px !important;
        }
        [data-testid="stSidebar"] [data-testid="stFileUploader"] button {
            background: #ecfdf5 !important;
            border: 1px solid #86efac !important;
            border-radius: 12px !important;
            font-weight: 800 !important;
            color: #064e3b !important;
        }
        [data-testid="stSidebar"] [data-testid="stFileUploader"] small,
        [data-testid="stSidebar"] [data-testid="stFileUploader"] span,
        [data-testid="stSidebar"] [data-testid="stFileUploader"] p,
        [data-testid="stSidebar"] [data-testid="stFileUploader"] div {
            color: #0f172a !important;
        }
        [data-testid="stSidebar"] [data-baseweb="select"] > div,
        [data-testid="stSidebar"] input,
        [data-testid="stSidebar"] textarea {
            background: #ffffff !important;
            color: #0f172a !important;
            border-radius: 12px !important;
        }
        .hero-card {
            padding: 1.4rem 1.6rem;
            border-radius: 28px;
            background: linear-gradient(135deg, rgba(6,95,70,0.96), rgba(16,185,129,0.90)),
                        radial-gradient(circle at 85% 20%, rgba(236,252,203,0.75), transparent 14rem);
            box-shadow: 0 24px 70px rgba(6,95,70,0.28);
            color: white;
            margin-bottom: 1.1rem;
        }
        .hero-card h1 { margin: 0 0 .35rem 0; font-size: 2.4rem; color: white; }
        .hero-card p { margin: 0; font-size: 1.02rem; color: #ecfdf5; }
        .insight-card {
            min-height: 126px;
            padding: 1.1rem 1.15rem;
            border-radius: 24px;
            background: rgba(255,255,255,0.84);
            border: 1px solid rgba(16,185,129,0.22);
            box-shadow: 0 16px 40px rgba(15,118,110,0.10);
        }
        .insight-card .label { color: #047857; font-size: .86rem; font-weight: 800; letter-spacing: .02em; }
        .insight-card .value { color: #052e16; font-size: 1.65rem; font-weight: 900; margin-top: .24rem; }
        .insight-card .desc { color: #475569; font-size: .88rem; margin-top: .45rem; }
        .status-pill {
            display: inline-flex;
            align-items: center;
            gap: .35rem;
            padding: .28rem .66rem;
            border-radius: 999px;
            background: #dcfce7;
            color: #166534;
            font-weight: 800;
            font-size: .82rem;
        }
        div[data-testid="stMetric"] {
            background: rgba(255,255,255,0.88);
            border: 1px solid rgba(16,185,129,0.20);
            border-radius: 22px;
            padding: 1rem 1.1rem;
            box-shadow: 0 12px 34px rgba(5,150,105,0.10);
        }
        div[data-testid="stMetric"] label { color: #047857 !important; font-weight: 800 !important; }
        .stTabs [data-baseweb="tab-list"] { gap: .4rem; }
        .stTabs [data-baseweb="tab"] {
            background: rgba(255,255,255,.72);
            border-radius: 999px;
            padding: .45rem .95rem;
            border: 1px solid rgba(16,185,129,.20);
        }
        .stTabs [aria-selected="true"] {
            background: linear-gradient(135deg, #16a34a, #10b981) !important;
            color: white !important;
            font-weight: 800;
        }
        .stButton > button, .stDownloadButton > button {
            border-radius: 999px !important;
            border: 0 !important;
            background: linear-gradient(135deg, #16a34a, #059669) !important;
            color: white !important;
            font-weight: 800 !important;
            box-shadow: 0 12px 26px rgba(5,150,105,.22);
        }
        .stAlert {
            border-radius: 18px;
        }
        .small-note {
            color: #64748b;
            font-size: .86rem;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def init_state() -> None:
    if "profile" not in st.session_state:
        profile, warnings = validate_profile(UserProfile.from_dict(SAMPLES[0]["profile"]))
        st.session_state.profile = profile
        st.session_state.profile_warnings = warnings
    if "onboarding_text" not in st.session_state:
        st.session_state.onboarding_text = (
            "만 27세 서울 1인가구, 실업급여 45일 남았고 월소득 0원입니다. "
            "3개월 뒤 알바 월소득 80만원 예정, 월세 55만원, 보증금 500만원, 신용점수 690점입니다."
        )
    if "last_parse_summary" not in st.session_state:
        st.session_state.last_parse_summary = "기본 샘플 프로필이 적용되어 있습니다."


def _safe_index(options: List[str], value: str, default: int = 0) -> int:
    return options.index(value) if value in options else default


def safe_number_input(
    label: str,
    min_value: int,
    max_value: int,
    value: Any,
    *,
    step: int = 1,
    key: str | None = None,
    help: str | None = None,
) -> int:
    lo, hi, safe_value = safe_widget_bounds(int(value or 0), min_value, max_value)
    return int(st.number_input(label, int(lo), int(hi), int(safe_value), step=step, key=key, help=help))


def dataframe_key(label: str, df: pd.DataFrame) -> str:
    schema = "|".join(f"{col}:{df[col].dtype}" for col in df.columns)
    digest = hashlib.md5(f"{label}|{df.shape}|{schema}".encode("utf-8")).hexdigest()[:10]
    return f"df_{digest}"


def _no_data(label: str, reason: str | None = None) -> None:
    """Show a quiet user-facing empty-state instead of Streamlit tracebacks."""
    st.info(f"{label}: {NO_DATA_TEXT}")
    if reason:
        st.caption(reason)


def render_df(df: pd.DataFrame | list[dict[str, Any]] | None, *, label: str, height: int | None = None) -> None:
    """Render a dataframe safely.

    Rules:
    - Missing/empty data is shown as '해당 데이터 없음'.
    - Streamlit 1.4x rejects height=None, so height is omitted unless valid.
    - If the interactive dataframe renderer fails, fall back to a static table.
    """
    if df is None:
        _no_data(label)
        return
    if not isinstance(df, pd.DataFrame):
        try:
            df = pd.DataFrame(df)
        except Exception as exc:  # noqa: BLE001 - UI guard
            _no_data(label, f"데이터 변환 실패: {exc}")
            return
    if df.empty or len(df.columns) == 0:
        _no_data(label)
        return

    st.caption(f"{label}: {len(df):,}건")
    dataframe_kwargs: dict[str, Any] = {
        "use_container_width": True,
        "hide_index": True,
        "key": dataframe_key(label, df),
    }
    if height is not None:
        try:
            safe_height = int(height)
        except (TypeError, ValueError):
            safe_height = 280
        dataframe_kwargs["height"] = max(1, safe_height)

    try:
        st.dataframe(df, **dataframe_kwargs)
    except Exception as exc:  # noqa: BLE001 - keep demo screen clean
        st.caption(f"{label}: 인터랙티브 표 렌더링 실패, 정적 표로 대체합니다.")
        try:
            st.table(df.head(200))
        except Exception:
            _no_data(label, f"표 렌더링 실패: {exc}")


def safe_section(label: str, render_fn, *args, **kwargs) -> None:
    """Prevent one missing dataset from breaking the full dashboard."""
    try:
        render_fn(*args, **kwargs)
    except Exception as exc:  # noqa: BLE001 - user-facing dashboard guard
        _no_data(label, f"화면 생성 중 데이터가 비어 있거나 형식이 맞지 않습니다. 내부 오류: {exc}")


def render_hero(profile: UserProfile) -> None:
    insights = compute_profile_insights(profile, BENEFITS)
    st.markdown(
        f"""
        <div class="hero-card">
            <h1>🧭 LifePass AI</h1>
            <p>청년 1인가구의 소득공백, 복지 절벽, 신청 순서를 한 번에 계산하는 생애전환 복지 코파일럿</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.markdown(
            f"<div class='insight-card'><div class='label'>상담 우선도</div><div class='value'>{insights['priority_score']}점 · {insights['priority_grade']}</div><div class='desc'>{', '.join(insights['reasons'][:2])}</div></div>",
            unsafe_allow_html=True,
        )
    with c2:
        st.markdown(
            f"<div class='insight-card'><div class='label'>현재 월 지원효과</div><div class='value'>{money(insights['current_support'])}</div><div class='desc'>선택 혜택 {insights['selected_count']}개 / 가능 혜택 {insights['eligible_count']}개</div></div>",
            unsafe_allow_html=True,
        )
    with c3:
        st.markdown(
            f"<div class='insight-card'><div class='label'>월 현금 버퍼</div><div class='value'>{money(insights['cash_buffer'])}</div><div class='desc'>소득+지원-월세-상환 기준</div></div>",
            unsafe_allow_html=True,
        )
    with c4:
        st.markdown(
            f"<div class='insight-card'><div class='label'>복지 절벽 경고</div><div class='value'>{insights['cliff_warning_count']}건</div><div class='desc'>주거비 부담 {insights['rent_burden_percent']}%</div></div>",
            unsafe_allow_html=True,
        )


def profile_editor(profile: UserProfile) -> UserProfile:
    st.subheader("구조화 프로필")
    profile, warnings = validate_profile(profile)
    if warnings:
        with st.expander("입력값 검증 경고", expanded=True):
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
        rent = safe_number_input("월세", 0, 20_000_000, profile.rent, step=50_000, key="rent", help="자연어 파싱값이 커도 UI가 터지지 않도록 최대값을 자동 확장합니다.")
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


def metric_cards(profile: UserProfile) -> None:
    evaluations = evaluate_all(BENEFITS, profile)
    plan = optimize_benefits(evaluations)
    timeline = simulate_timeline(profile, BENEFITS, [0, 3, 6, 12])
    cliff = simulate_income_cliff(profile, BENEFITS)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("현재 최적 월 환산효과", money(plan.total_monthly_value))
    c2.metric("선택 혜택 수", f"{len(plan.selected)}개")
    c3.metric("3개월 후 순효과", money(timeline[1].net_effect if len(timeline) > 1 else 0))
    c4.metric("복지 절벽 경고", f"{sum(1 for r in cliff if r.warnings)}건")


def render_insights(profile: UserProfile) -> None:
    st.header("0. AI 상담 인사이트")
    insights = compute_profile_insights(profile, BENEFITS)
    c1, c2 = st.columns([1, 2])
    with c1:
        st.subheader("상담 우선도")
        st.progress(insights["priority_score"] / 100)
        st.metric("우선도 점수", f"{insights['priority_score']}점", insights["priority_grade"])
        st.write("주요 사유")
        for reason in insights["reasons"]:
            st.write(f"- {reason}")
    with c2:
        st.subheader("즉시 권장 액션")
        for idx, action in enumerate(insights["recommended_actions"], start=1):
            st.success(f"{idx}. {action}")
        rows = [
            {"항목": "현재 월 지원효과", "값": money(insights["current_support"])},
            {"항목": "월 현금 버퍼", "값": money(insights["cash_buffer"])},
            {"항목": "주거비 부담률", "값": f"{insights['rent_burden_percent']}%"},
            {"항목": "1~3개월 내 신규 가능", "값": ", ".join(insights["gained_next"]) or "없음"},
            {"항목": "1~3개월 내 상실 위험", "값": ", ".join(insights["lost_next"]) or "없음"},
        ]
        render_df(pd.DataFrame(rows), label="상담 요약", height=230)


def render_current(profile: UserProfile) -> None:
    st.header("1. 현재 자격 판정·최적 조합")
    evaluations = evaluate_all(BENEFITS, profile)
    plan = optimize_benefits(evaluations)
    metric_cards(profile)

    selected_df = pd.DataFrame([
        {"혜택": b.name, "영역": b.domain, "월 환산효과": b.monthly_value, "충돌그룹": b.conflict_group or "-", "경고": ", ".join(b.warnings)}
        for b in plan.selected
    ])
    st.subheader("충돌을 제거한 최적 조합")
    render_df(selected_df, label="최적 조합")
    st.info("\n".join(plan.explanation))

    st.subheader("신청 서류 통합 체크리스트")
    checklist = make_document_checklist(plan.selected)
    render_df(pd.DataFrame(checklist), label="서류 체크리스트", height=260)

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
    st.header("2. 3·6·12개월 생애전환 예측")
    rows = simulate_timeline(profile, BENEFITS, [0, 1, 3, 6, 12])
    df = pd.DataFrame([
        {
            "시점": r.label,
            "월소득": r.income,
            "혜택 월 환산": r.benefit_value,
            "순효과": r.net_effect,
            "신규 가능": ", ".join(r.gained),
            "상실 위험": ", ".join(r.lost),
            "경고": ", ".join(r.warnings),
        }
        for r in rows
    ])
    st.line_chart(df.set_index("시점")[["월소득", "혜택 월 환산", "순효과"]])
    render_df(df, label="생애전환 예측", height=300)

    st.subheader("실행 타임라인")
    for ev in generate_timeline_events(profile, BENEFITS):
        with st.expander(f"M+{ev.month} · {ev.title} · {ev.risk_level}", expanded=ev.risk_level in {"warning", "danger"}):
            st.write(ev.description)
            st.write("해야 할 일")
            for item in ev.action_items:
                st.write(f"- {item}")


def render_cliff(profile: UserProfile) -> None:
    st.header("3. 복지 절벽 시뮬레이터")
    rows = simulate_income_cliff(profile, BENEFITS)
    df = pd.DataFrame([
        {
            "시나리오": r.label,
            "월소득": r.income,
            "혜택 월 환산": r.benefit_value,
            "순효과": r.net_effect,
            "상실 혜택": ", ".join(r.lost),
            "신규 혜택": ", ".join(r.gained),
            "경고": ", ".join(r.warnings),
        }
        for r in rows
    ])
    st.bar_chart(df.set_index("시나리오")[["월소득", "혜택 월 환산", "순효과"]])
    render_df(df, label="복지 절벽 시나리오", height=340)
    if any(r.warnings for r in rows):
        st.warning("일부 소득 구간에서 혜택 상실로 순효과가 감소하거나 둔화됩니다. 신청 순서와 근로 시작 시점을 재검토하세요.")
    else:
        st.success("현재 시나리오에서는 명확한 역전형 복지 절벽이 감지되지 않았습니다.")


def render_strategy(profile: UserProfile) -> None:
    st.header("4. 신청 전략·근거 설명")
    strategy = build_application_strategy(profile, BENEFITS)
    for benefit_name, items in strategy.items():
        with st.expander(benefit_name, expanded=True):
            for item in items:
                st.write(f"- {item}")
    st.subheader("근거 검색 요약")
    query = st.text_input("근거 검색 질문", "실업급여 종료 후 국민취업지원 청년월세 복지절벽")
    st.markdown(explain_with_evidence(query))

    report = make_markdown_report(profile, BENEFITS)
    st.download_button("분석 리포트 Markdown 다운로드", report, file_name="lifepass_report.md", mime="text/markdown")


def render_admin() -> None:
    st.header("5. 기관/운영자 대시보드")
    profiles = sample_profiles_as_models()
    metrics = build_admin_metrics(profiles, BENEFITS)
    c1, c2, c3 = st.columns(3)
    c1.metric("데모 사용자 수", metrics.total_profiles)
    c2.metric("복지 절벽 고위험", metrics.high_cliff_risk)
    c3.metric("평균 월 지원효과", money(metrics.average_monthly_support))

    st.subheader("상위 추천 혜택")
    render_df(pd.DataFrame(metrics.top_benefits), label="상위 추천 혜택", height=320)
    st.subheader("지역별 요약")
    render_df(pd.DataFrame(metrics.region_summary), label="지역별 요약", height=320)
    st.subheader("우선 상담 큐")
    render_df(pd.DataFrame(metrics.pending_actions), label="우선 상담 큐", height=320)


def render_json_tools(profile: UserProfile) -> None:
    st.header("6. JSON·연동 도구")
    payload = profile.to_dict()
    st.json(payload)
    c1, c2 = st.columns(2)
    with c1:
        st.download_button("프로필 JSON 다운로드", json.dumps(payload, ensure_ascii=False, indent=2), "profile.json", mime="application/json")
    with c2:
        export = {
            "profile": payload,
            "insights": compute_profile_insights(profile, BENEFITS),
            "report_markdown": make_markdown_report(profile, BENEFITS),
        }
        st.download_button("분석 결과 패키지 다운로드", json.dumps(export, ensure_ascii=False, indent=2), "lifepass_export.json", mime="application/json")
    st.caption("향후 REST API/공공데이터 API 연동 시 이 JSON 구조를 그대로 request/response 계약으로 확장할 수 있습니다.")


def handle_sidebar() -> None:
    with st.sidebar:
        st.header("샘플·데이터")
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
            except Exception as exc:  # noqa: BLE001 - user-facing upload guard
                st.warning(f"JSON 업로드 실패: 업로드 데이터 없음 또는 형식 오류입니다. ({exc})")

        st.divider()


def main() -> None:
    inject_theme_css()
    init_state()
    handle_sidebar()

    profile, warnings = validate_profile(st.session_state.profile)
    st.session_state.profile = profile
    st.session_state.profile_warnings = warnings
    render_hero(profile)

    st.subheader("카카오톡 스타일 온보딩")
    text = st.text_area("사용자 메시지", value=st.session_state.onboarding_text, height=110)
    c1, c2 = st.columns([1, 4])
    with c1:
        if st.button("메시지 입력"):
            parsed = parse_onboarding_text(text)
            parsed, parse_warnings = validate_profile(parsed)
            st.session_state.onboarding_text = text
            st.session_state.profile = parsed
            st.session_state.profile_warnings = parse_warnings
            st.session_state.last_parse_summary = (
                f"파싱 완료: 만 {parsed.age}세 / {parsed.region} / {parsed.household_size}인가구 / "
                f"월소득 {money(parsed.monthly_income)} / 월세 {money(parsed.rent)} / 보증금 {money(parsed.deposit)}"
            )
            st.rerun()
    with c2:
        st.write("예: `만 27세 서울 1인가구, 실업급여 45일 남음, 3개월 뒤 알바 월소득 80만원, 월세 55만원, 보증금 500만원`")
        st.caption(st.session_state.last_parse_summary)

    if st.session_state.profile_warnings:
        with st.expander("파싱·업로드 입력값 경고", expanded=True):
            for warning in st.session_state.profile_warnings:
                st.warning(warning)

    st.session_state.profile = profile_editor(st.session_state.profile)
    profile = normalize_profile(st.session_state.profile)

    tabs = st.tabs(["인사이트", "현재 판정", "생애전환", "복지 절벽", "신청 전략", "운영자 대시보드", "JSON"])
    with tabs[0]:
        safe_section("인사이트", render_insights, profile)
    with tabs[1]:
        safe_section("현재 판정", render_current, profile)
    with tabs[2]:
        safe_section("생애전환", render_timeline, profile)
    with tabs[3]:
        safe_section("복지 절벽", render_cliff, profile)
    with tabs[4]:
        safe_section("신청 전략", render_strategy, profile)
    with tabs[5]:
        safe_section("운영자 대시보드", render_admin)
    with tabs[6]:
        safe_section("JSON", render_json_tools, profile)


if __name__ == "__main__":
    main()
