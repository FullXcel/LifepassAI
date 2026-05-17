"""Policy feed ingestion and normalization.

The ingestion layer converts public/open-data policy feeds into the same JSON
rule format used by LifePass' deterministic rule engine.  The production update
adds explicit source/provenance fields, demo/live flags and better aliases for
Korean public-service payloads.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

import pandas as pd

from .benefit_catalog import validate_benefits

DEFAULT_IMPORTED_PATH = Path(__file__).resolve().parents[1] / "data" / "imported_benefits.json"


def _slug(text: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9가-힣]+", "_", str(text).strip()).strip("_")
    return cleaned[:64] or "policy"


def _is_blank(value: Any) -> bool:
    return value is None or (isinstance(value, float) and pd.isna(value)) or str(value).strip() == ""


def _as_int(value: Any, default: int = 0) -> int:
    if _is_blank(value):
        return default
    try:
        text = str(value).replace(",", "").replace("원", "").strip()
        text = re.sub(r"[^0-9.\-만만원]", "", text)
        if text.endswith("만원"):
            return int(float(text[:-2]) * 10_000)
        if text.endswith("만"):
            return int(float(text[:-1]) * 10_000)
        return int(float(text))
    except (TypeError, ValueError):
        return default


def _split_docs(value: Any) -> List[str]:
    if _is_blank(value):
        return []
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    text = str(value)
    parts = re.split(r"[,;/|\n·]+", text)
    return [p.strip() for p in parts if p.strip()]


def _row_get(row: Dict[str, Any], *keys: str, default: Any = None) -> Any:
    for key in keys:
        if key in row and not _is_blank(row[key]):
            return row[key]
    return default


def _parse_bool(value: Any, default: bool = False) -> bool:
    if _is_blank(value):
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "y", "예", "필수", "demo", "sample"}


def _normalize_date(value: Any) -> str:
    if _is_blank(value):
        return ""
    text = str(value).strip()
    # Keep public API date values human-readable while normalizing common forms.
    m = re.search(r"(20\d{2})[.\-/년 ]{1,3}(\d{1,2})[.\-/월 ]{1,3}(\d{1,2})", text)
    if m:
        y, mo, d = m.groups()
        return f"{int(y):04d}-{int(mo):02d}-{int(d):02d}"
    return text[:32]


def _rule_from_income(row: Dict[str, Any]) -> List[Dict[str, Any]]:
    max_income_percent = _row_get(row, "max_income_percent", "income_ceiling_percent", "중위소득상한", "소득기준", default=None)
    if max_income_percent in (None, ""):
        return []
    value = _as_int(max_income_percent)
    if value <= 0:
        return []
    return [{"field": "income_percent_median", "op": "<=", "value": value, "label": f"중위소득 {value}% 이하"}]


def benefit_from_policy_row(row: Dict[str, Any], idx: int = 0) -> Dict[str, Any]:
    name = str(_row_get(row, "name", "policy_name", "service_name", "title", "정책명", "사업명", "서비스명", default=f"외부정책 {idx}"))
    policy_id = str(_row_get(row, "id", "policy_id", "service_id", "정책ID", "서비스ID", default=f"imported_{_slug(name)}_{idx}"))
    min_age = _row_get(row, "min_age", "age_min", "최소나이", "나이시작", default=None)
    max_age = _row_get(row, "max_age", "age_max", "최대나이", "나이종료", default=None)
    region = _row_get(row, "region", "sido", "지역", "시도", "관할지역", default=None)
    employment = _row_get(row, "employment_status", "employment", "고용상태", "취업상태", default=None)
    rent_required = _row_get(row, "rent_required", "월세필수", default=None)

    rules: List[Dict[str, Any]] = []
    if min_age not in (None, "") and max_age not in (None, ""):
        rules.append({"field": "age", "op": "between", "value": [_as_int(min_age), _as_int(max_age)], "label": f"만 {_as_int(min_age)}~{_as_int(max_age)}세"})
    elif min_age not in (None, ""):
        rules.append({"field": "age", "op": ">=", "value": _as_int(min_age), "label": f"만 {_as_int(min_age)}세 이상"})
    elif max_age not in (None, ""):
        rules.append({"field": "age", "op": "<=", "value": _as_int(max_age), "label": f"만 {_as_int(max_age)}세 이하"})
    if region:
        rules.append({"field": "region", "op": "in", "value": [r.strip() for r in re.split(r"[|,/ ]+", str(region)) if r.strip()], "label": f"지역: {region}"})
    rules.extend(_rule_from_income(row))
    if employment:
        values = [v.strip() for v in str(employment).split("|") if v.strip()]
        if values:
            rules.append({"field": "employment_status", "op": "in", "value": values, "label": f"고용상태: {employment}"})
    if _parse_bool(rent_required):
        rules.append({"field": "rent", "op": ">", "value": 0, "label": "월세 거주"})
    if not rules:
        # Public feeds often provide unstructured eligibility text only.  Keep the
        # policy searchable but mark it for human review instead of silently making
        # it universally eligible.
        rules.append({"field": "age", "op": ">=", "value": 0, "label": "상세 자격조건 원문 확인 필요"})

    source_url = str(_row_get(row, "source_document_url", "source_url", "detail_url", "원문URL", "공고URL", "url", "apply_url", "신청URL", default=""))
    apply_url = str(_row_get(row, "apply_url", "신청URL", "application_url", default=source_url))
    announcement_date = _normalize_date(_row_get(row, "announcement_date", "source_date", "등록일", "공고일", "수정일", default=""))
    effective_start = _normalize_date(_row_get(row, "effective_start_date", "start_date", "접수시작일", "시작일", default=""))
    effective_end = _normalize_date(_row_get(row, "effective_end_date", "end_date", "접수종료일", "종료일", default=""))

    benefit = {
        "id": policy_id,
        "name": name,
        "domain": str(_row_get(row, "domain", "category", "jurisdiction", "분야", "소관기관", default="외부공고")),
        "estimated_monthly_value": _as_int(_row_get(row, "estimated_monthly_value", "monthly_value", "월환산효과", "지원금액", "support_amount", default=0)),
        "priority": _as_int(_row_get(row, "priority", "우선순위", default=50), 50),
        "description": str(_row_get(row, "description", "summary", "설명", "개요", "지원내용", "서비스목적", default="외부 정책 피드에서 수집된 정책입니다.")),
        "target": str(_row_get(row, "target", "target_text", "대상", "서비스대상", "지원대상", default="외부 정책 피드 기준")),
        "required_docs": _split_docs(_row_get(row, "required_docs", "documents", "필요서류", "구비서류", default="본인확인, 소득자료")),
        "apply_url": apply_url,
        "source_document_url": source_url,
        "announcement_date": announcement_date,
        "effective_start_date": effective_start,
        "effective_end_date": effective_end,
        "source_name": str(_row_get(row, "source_name", "source_system", "제공기관", "소관기관", default="external_public_source")),
        "is_demo": _parse_bool(_row_get(row, "is_demo", "demo", "sample", default=False)),
        "human_review_required": bool("상세 자격조건 원문 확인 필요" in rules[0].get("label", "")),
        "exclusive_group": _row_get(row, "exclusive_group", "중복그룹", default=None),
        "conflicts_with": _split_docs(_row_get(row, "conflicts_with", "충돌혜택", default="")),
        "rule": {"all": rules},
    }
    return benefit


def benefits_from_dataframe(df: pd.DataFrame) -> Tuple[List[Dict[str, Any]], List[str]]:
    warnings: List[str] = []
    benefits: List[Dict[str, Any]] = []
    if df is None or df.empty:
        return [], ["업로드된 정책 데이터가 비어 있습니다."]
    for idx, (_, row) in enumerate(df.iterrows(), start=1):
        try:
            benefits.append(benefit_from_policy_row(row.to_dict(), idx))
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"{idx}행 변환 실패: {exc}")
    try:
        validate_benefits(benefits)
    except Exception as exc:  # noqa: BLE001
        warnings.append(f"정책 카탈로그 검증 경고: {exc}")
    return benefits, warnings


def load_imported_benefits(path: str | Path = DEFAULT_IMPORTED_PATH) -> List[Dict[str, Any]]:
    path = Path(path)
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, dict):
        data = data.get("benefits", [])
    validate_benefits(data)
    return data


def save_imported_benefits(benefits: Iterable[Dict[str, Any]], path: str | Path = DEFAULT_IMPORTED_PATH) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = list(benefits)
    validate_benefits(data)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return path


def template_policy_dataframe() -> pd.DataFrame:
    return pd.DataFrame([
        {
            "id": "city_youth_transport_demo",
            "name": "청년 교통비 지원(외부피드 예시)",
            "domain": "교통",
            "estimated_monthly_value": 60000,
            "priority": 72,
            "min_age": 19,
            "max_age": 34,
            "region": "서울|경기|인천",
            "max_income_percent": 150,
            "employment_status": "unemployed|job_seeker|part_time|student",
            "rent_required": "no",
            "required_docs": "주민등록등본, 소득확인자료, 교통카드 사용내역",
            "apply_url": "https://example.go.kr",
            "source_document_url": "https://example.go.kr/notice/transport",
            "announcement_date": "2026-01-01",
            "is_demo": True,
            "description": "외부 CSV/API 피드에서 변환되는 정책 예시입니다.",
        }
    ])


def template_policy_csv_bytes() -> bytes:
    return template_policy_dataframe().to_csv(index=False).encode("utf-8-sig")
