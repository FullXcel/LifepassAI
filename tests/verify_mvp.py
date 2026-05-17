"""Self-verification suite for LifePass AI MVP.

Run from project root:
    python tests/verify_mvp.py

No pytest dependency is required. The script fails fast with AssertionError when
any core function is broken.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.admin import build_admin_metrics, detect_high_cliff_risk  # noqa: E402
from core.benefit_catalog import load_benefits  # noqa: E402
from core.demo_data import load_sample_profiles, sample_profiles_as_models  # noqa: E402
from core.optimizer import has_conflict, optimize_benefits  # noqa: E402
from core.profile_parser import parse_onboarding_text  # noqa: E402
from core.insights import compute_profile_insights, make_document_checklist  # noqa: E402
from core.validation import safe_widget_bounds, validate_profile  # noqa: E402
from core.rag import retrieve  # noqa: E402
from core.report import make_markdown_report  # noqa: E402
from core.rule_engine import evaluate_all  # noqa: E402
from core.simulator import generate_timeline_events, simulate_income_cliff, simulate_timeline  # noqa: E402
from core.utils import normalize_profile, project_profile  # noqa: E402


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def test_catalog() -> None:
    benefits = load_benefits()
    assert_true(len(benefits) >= 20, "혜택 DB는 최소 20개 이상이어야 함")
    ids = [b["id"] for b in benefits]
    assert_true(len(ids) == len(set(ids)), "혜택 ID 중복 없음")
    for b in benefits:
        assert_true("rule" in b and isinstance(b["rule"], dict), f"{b['id']} rule 누락")


def test_parser() -> None:
    text = "만 27세 서울 1인가구, 실업급여 45일 남음. 3개월 뒤 알바 월소득 80만원 예정, 월세 55만원, 보증금 500만원, 신용점수 690점, 월상환 35만원"
    p = parse_onboarding_text(text)
    p = normalize_profile(p)
    assert_true(p.age == 27, "나이 파싱 실패")
    assert_true(p.region == "서울", "지역 파싱 실패")
    assert_true(p.household_size == 1, "가구 파싱 실패")
    assert_true(p.unemployment_benefit_receiving, "실업급여 상태 파싱 실패")
    assert_true(p.unemployment_benefit_days_left == 45, "잔여일 파싱 실패")
    assert_true(p.expected_monthly_income == 800000, "예상 월소득 파싱 실패")
    assert_true(p.rent == 550000, "월세 파싱 실패")
    assert_true(p.credit_score == 690, "신용점수 파싱 실패")
    assert_true(p.debt_monthly_payment == 350000, "월상환 파싱 실패")


def test_rule_engine_and_conflicts() -> None:
    benefits = load_benefits()
    sample = load_sample_profiles()[0]
    p = normalize_profile(parse_profile(sample))
    evaluations = evaluate_all(benefits, p)
    plan = optimize_benefits(evaluations)
    assert_true(plan.total_monthly_value > 0, "최적 조합 월 환산효과가 0보다 커야 함")
    assert_true(not has_conflict(plan.selected), "최적 조합에 충돌 혜택이 포함됨")
    selected_names = [b.name for b in plan.selected]
    housing_count = sum(1 for b in plan.selected if b.conflict_group == "housing_rent_support")
    assert_true(housing_count <= 1, "주거지원 중복 제거 실패")
    assert_true(any("실업급여" in name for name in selected_names), "수급 중 실업급여 상태가 선택되어야 함")
    assert_true(not any("국민취업지원제도 II" in name for name in selected_names), "실업급여 수급 중 KUA II가 선택되면 안 됨")


def parse_profile(sample_item):
    from core.models import UserProfile

    return UserProfile.from_dict(sample_item["profile"])


def test_future_transition() -> None:
    benefits = load_benefits()
    p = parse_profile(load_sample_profiles()[0])
    current = optimize_benefits(evaluate_all(benefits, project_profile(p, 0)))
    future = optimize_benefits(evaluate_all(benefits, project_profile(p, 3)))
    current_names = {b.name for b in current.selected}
    future_names = {b.name for b in future.selected}
    assert_true(any("실업급여" in name for name in current_names), "현재 실업급여 선택 필요")
    assert_true(not any("실업급여" in name for name in future_names), "3개월 후 실업급여는 종료되어야 함")
    assert_true(any(("국민취업지원" in name or "청년내일저축" in name or "근로장려" in name) for name in future_names), "3개월 후 전환/근로연계 혜택이 생겨야 함")


def test_timeline_and_cliff() -> None:
    benefits = load_benefits()
    for sample in load_sample_profiles():
        p = parse_profile(sample)
        timeline = simulate_timeline(p, benefits)
        assert_true(len(timeline) >= 4, f"{sample['name']} 타임라인 부족")
        assert_true(all(r.net_effect >= 0 for r in timeline), f"{sample['name']} 순효과 음수")
        cliff = simulate_income_cliff(p, benefits)
        assert_true(len(cliff) >= 5, f"{sample['name']} 소득 시나리오 부족")
        assert_true(all(r.net_effect >= 0 for r in cliff), f"{sample['name']} 절벽 시나리오 순효과 음수")
        events = generate_timeline_events(p, benefits)
        assert_true(len(events) >= 1, f"{sample['name']} 실행 이벤트 없음")


def test_admin_metrics() -> None:
    benefits = load_benefits()
    profiles = sample_profiles_as_models()
    metrics = build_admin_metrics(profiles, benefits)
    assert_true(metrics.total_profiles == len(profiles), "관리자 지표 사용자 수 불일치")
    assert_true(metrics.average_monthly_support >= 0, "평균 지원효과 오류")
    assert_true(len(metrics.region_summary) >= 3, "지역 요약 부족")
    assert_true(len(metrics.top_benefits) >= 1, "상위 혜택 지표 없음")


def test_rag_and_report() -> None:
    docs = retrieve("실업급여 종료 국민취업지원 복지절벽")
    assert_true(len(docs) >= 1, "근거 검색 실패")
    benefits = load_benefits()
    p = parse_profile(load_sample_profiles()[0])
    report = make_markdown_report(p, benefits)
    assert_true("LifePass AI 분석 리포트" in report, "리포트 제목 누락")
    assert_true("복지 절벽" in report, "리포트 복지절벽 섹션 누락")


def test_validation_and_insights() -> None:
    benefits = load_benefits()
    p = parse_onboarding_text("만 23세 서울 1인가구, 무직, 현재 월소득 0원, 예상 월소득 802만원, 3개월 뒤 소득 발생, 월세 500만원, 보증금 1000만원")
    p, warnings = validate_profile(p)
    assert_true(p.rent == 5000000, "고액 월세 파싱값 보존 실패")
    assert_true(any("월세" in w for w in warnings), "고액 월세 경고 누락")
    lo, hi, value = safe_widget_bounds(p.rent, 0, 3000000)
    assert_true(value == p.rent and hi >= p.rent, "Streamlit number_input 안전 범위 보정 실패")
    insights = compute_profile_insights(p, benefits)
    assert_true(0 <= insights["priority_score"] <= 100, "우선도 점수 범위 오류")
    assert_true(len(insights["recommended_actions"]) >= 1, "권장 액션 누락")
    evaluations = evaluate_all(benefits, p)
    plan = optimize_benefits(evaluations)
    checklist = make_document_checklist(plan.selected)
    assert_true(isinstance(checklist, list), "서류 체크리스트 생성 실패")


# v3 advanced integration checks. These are appended for direct importers; the main runner is patched below.
def test_v3_public_api_trust_search() -> None:
    from core.audit import build_trust_audit
    from core.public_api_clients import fetch_source_policies, source_status_rows
    from core.vector_search import search_policies
    from core.whatif import build_counterfactuals
    from core.tool_manifest import tool_manifest
    from core.privacy import consent_packet, mask_text, pseudonymize_identifier
    from core.policy_provenance import diff_catalogs

    benefits = load_benefits()
    p = parse_profile(load_sample_profiles()[0])

    statuses = source_status_rows()
    assert_true(len(statuses) >= 3, "공공 API 소스 레지스트리 부족")
    result = fetch_source_policies("local_city", query="청년", limit=5)
    assert_true(result.ok, "공공 API fallback 수집 실패")
    assert_true(len(result.benefits) >= 1, "공공 API 정책 변환 실패")
    assert_true("provenance" in result.benefits[0], "정책 provenance 누락")

    search_rows = search_policies("청년 월세 구직", benefits + result.benefits, top_k=5)
    assert_true(len(search_rows) >= 1, "정책 의미 검색 실패")

    cf_rows = build_counterfactuals(p, benefits)
    assert_true(len(cf_rows) >= 3, "counterfactual 시나리오 부족")
    assert_true("delta" in cf_rows[0], "counterfactual delta 누락")

    audit = build_trust_audit(p, benefits + result.benefits)
    assert_true(audit["audit_score"] >= 60, "신뢰성 감사 점수 비정상")
    assert_true(len(audit["controls"]) >= 6, "감사 통제 항목 부족")

    manifest = tool_manifest()
    assert_true(len(manifest["tools"]) >= 5, "MCP-style tool manifest 부족")
    assert_true("***@***" in mask_text("test@example.com"), "이메일 마스킹 실패")
    assert_true(pseudonymize_identifier("abc").startswith("lp_"), "가명 ID 생성 실패")
    assert_true("human_review_required" in consent_packet(p.to_dict()), "동의 패킷 누락")

    diff = diff_catalogs([], result.benefits)
    assert_true(diff["added_count"] == len(result.benefits), "정책 diff 계산 실패")


def run_all() -> None:
    tests = [
        test_catalog,
        test_parser,
        test_rule_engine_and_conflicts,
        test_future_transition,
        test_timeline_and_cliff,
        test_admin_metrics,
        test_rag_and_report,
        test_validation_and_insights,
        test_v2_agent_batch_policy_persistence,
        test_v3_public_api_trust_search,
        test_v4_operational_platform,
        test_v5_event_twin_security_causal_ops,
    ]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    print("\nALL CHECKS PASSED")



# Extra checks for v2 Agent/DB/CSV/policy-feed features.  These are defined
# after the original runner so they can also be called directly by importers.
def test_v2_agent_batch_policy_persistence() -> None:
    from core.agent import build_agent_plan
    from core.batch import analyze_profiles, template_dataframe
    from core.persistence import init_db, save_profile, list_profiles, create_tasks_from_benefits, list_tasks
    from core.policy_ingestion import benefits_from_dataframe, template_policy_dataframe
    from pathlib import Path
    import tempfile

    benefits = load_benefits()
    p = parse_profile(load_sample_profiles()[0])
    agent = build_agent_plan(p, benefits, "먼저 신청할 혜택과 서류를 알려줘")
    assert_true(len(agent["tool_trace"]) >= 5, "Agent tool trace 부족")
    assert_true(agent["monthly_support"] >= 0, "Agent 월 지원효과 오류")
    assert_true(len(agent["actions"]) >= 1, "Agent action queue 누락")

    batch_df, profiles = analyze_profiles(template_dataframe(), benefits)
    assert_true(len(batch_df) == len(profiles) >= 2, "CSV 일괄분석 실패")
    assert_true("priority_score" in batch_df.columns, "일괄분석 우선도 컬럼 누락")

    imported, warnings = benefits_from_dataframe(template_policy_dataframe())
    assert_true(len(imported) == 1, "정책 피드 변환 실패")
    assert_true("rule" in imported[0], "정책 룰 변환 누락")

    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "lifepass_test.sqlite3"
        init_db(db_path)
        profile_id = save_profile(p, "테스트", path=db_path)
        assert_true(profile_id >= 1, "프로필 저장 실패")
        rows = list_profiles(path=db_path)
        assert_true(len(rows) == 1, "프로필 목록 조회 실패")
        plan = optimize_benefits(evaluate_all(benefits, p))
        created = create_tasks_from_benefits(profile_id, plan.selected, path=db_path)
        assert_true(created == len(plan.selected), "신청 태스크 생성 실패")
        assert_true(len(list_tasks(path=db_path)) == created, "신청 태스크 조회 실패")




def test_v4_operational_platform() -> None:
    from core.agent_workflow import build_agent_workflow
    from core.constraint_solver import solve_benefit_portfolio
    from core.dbms import POSTGRES_PGVECTOR_DDL, dbms_capabilities, deployment_readiness
    from core.document_parser import draft_benefit_from_text, extract_policy_facts
    from core.durable_workflow import build_application_workflow
    from core.evaluation import run_benchmark
    from core.guardrails import validate_structured_payload
    from core.knowledge_graph import build_eligibility_graph
    from core.multitenancy import tenant_rows
    from core.notifications import plan_notifications
    from core.smart_mapper import infer_mapping, map_dataframe_to_profiles
    import pandas as pd

    benefits = load_benefits()
    p = parse_profile(load_sample_profiles()[0])
    evaluations = evaluate_all(benefits, p)
    workflow = build_agent_workflow(p, benefits, question="복지 절벽 대응")
    assert_true(len(workflow["steps"]) >= 7, "v4 Agent workflow steps 부족")
    assert_true("CREATE EXTENSION IF NOT EXISTS vector" in POSTGRES_PGVECTOR_DDL, "pgvector DDL 누락")
    assert_true(len(dbms_capabilities()) >= 4, "DBMS capability 부족")
    assert_true("recommended_env" in deployment_readiness(), "DBMS readiness 누락")

    portfolio = solve_benefit_portfolio(evaluations)
    assert_true(portfolio["conflict_free"], "Constraint optimizer 충돌 제거 실패")
    assert_true("objective_score" in portfolio["breakdown"], "Constraint optimizer objective 누락")

    app_wf = build_application_workflow(p, optimize_benefits(evaluations).selected)
    assert_true(len(app_wf["tasks"]) >= 3, "Durable workflow task 부족")
    assert_true(len(plan_notifications(p, app_wf)) >= 1, "Notification plan 부족")

    df = pd.DataFrame({"만나이": [27], "거주지역": ["서울"], "월소득": ["0원"], "월임대료": ["55만원"], "실업급여잔여일": [45]})
    mapping, suggestions = infer_mapping(df.columns)
    assert_true(mapping.get("age") == "만나이", "Smart mapper 나이 매핑 실패")
    profiles, mapped_df, warnings = map_dataframe_to_profiles(df, mapping)
    assert_true(len(profiles) == 1 and int(mapped_df.iloc[0]["rent"]) == 550000, "Smart mapper 프로필 변환 실패")

    doc = "정책명: 서울 청년 월세 지원\n대상: 만 19세~34세 서울 거주 청년\n지원: 매월 20만원\n서류: 주민등록등본, 임대차계약서"
    facts = extract_policy_facts(doc)
    draft = draft_benefit_from_text(doc)
    assert_true(facts["monthly_value"] == 200000, "문서 파서 금액 추출 실패")
    assert_true(draft["provenance"]["review_status"] == "draft_requires_human_review", "문서 파서 review status 누락")

    graph = build_eligibility_graph(p, evaluations)
    assert_true(len(graph["nodes"]) > 0 and len(graph["edges"]) > 0, "지식그래프 생성 실패")

    benchmark = run_benchmark(benefits)
    assert_true(benchmark["metrics"]["cases"] >= 3, "benchmark 케이스 부족")
    assert_true(benchmark["metrics"]["conflict_violation_rate"] == 0, "benchmark 충돌 위반")

    guard = validate_structured_payload({"age": 999, "region": "서울"})
    assert_true(guard["ok"], "guardrail 기본 검증 실패")
    assert_true(guard["clean_payload"]["age"] == 120, "guardrail 범위 clamp 실패")
    assert_true(len(tenant_rows()) >= 3, "multi-tenant rows 부족")



def test_v5_event_twin_security_causal_ops() -> None:
    from core.v5_event_mesh import event_ops_dashboard
    from core.v5_policy_digital_twin import simulate_policy_impact
    from core.v5_privacy_security import privacy_security_pack, check_access, dp_count
    from core.v5_causal_ops import estimate_intervention_effects, quality_ops_pack

    benefits = load_benefits()
    p = parse_profile(load_sample_profiles()[0])
    events = event_ops_dashboard(p)
    assert_true(events["metrics"]["events_generated"] >= 3, "v5 이벤트 생성 부족")
    assert_true(events["outbox"]["delivery_guarantee"] == "idempotent_at-least-once", "outbox 보장 설명 누락")
    assert_true(len(events["consumers"]) >= 3, "event consumer topology 부족")

    profiles = [parse_profile(item) for item in load_sample_profiles()]
    impact = simulate_policy_impact(profiles, benefits, age_upper=39, value_multiplier=1.1)
    assert_true(impact["metrics"]["profiles_simulated"] == len(profiles), "정책 디지털트윈 대상자 수 오류")
    assert_true("annualized_budget_delta" in impact["metrics"], "정책 디지털트윈 예산 지표 누락")

    sec = privacy_security_pack(p)
    assert_true(len(sec["privacy_budget"]) >= 3, "privacy budget ledger 부족")
    assert_true(len(sec["synthetic_profiles"]) >= 5, "synthetic profiles 부족")
    denied = check_access("auditor", "read:assigned", "audit", ["age", "deposit"])
    assert_true(not denied["ok"], "purpose scope 위반 차단 실패")
    assert_true(dp_count(10, epsilon=0.7) >= 0, "DP count 오류")

    causal = estimate_intervention_effects(p)
    assert_true(len(causal["recommended_interventions"]) >= 3, "causal intervention 후보 부족")
    assert_true(causal["recommended_interventions"][0]["expected_benefit_score"] >= causal["recommended_interventions"][-1]["expected_benefit_score"], "intervention ranking 정렬 실패")

    ops = quality_ops_pack()
    assert_true("data_contract" in ops and "model_card" in ops, "quality ops pack 누락")
    assert_true(len(ops["sla_playbook"]) >= 3, "incident playbook 부족")

if __name__ == "__main__":
    run_all()
