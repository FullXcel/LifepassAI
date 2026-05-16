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
    ]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    print("\nALL CHECKS PASSED")


if __name__ == "__main__":
    run_all()
