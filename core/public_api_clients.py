"""Public-policy source connectors for LifePass AI.

The module provides production-shaped connectors for public welfare/policy APIs.
Actual endpoint URLs and API keys vary by institution and deployment, so the
connector reads them from environment variables and falls back to bundled sample
payloads when credentials are not available.  This keeps the competition demo
fully runnable offline while proving the integration path for live systems.
"""
from __future__ import annotations

import csv
import hashlib
import json
import os
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

import pandas as pd

from .policy_ingestion import benefits_from_dataframe
from .policy_provenance import add_provenance, fingerprint_payload

ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = ROOT / "data" / "public_source_registry.json"
SAMPLE_PATH = ROOT / "data" / "live_policy_sample.json"
CACHE_DIR = ROOT / "data" / "api_cache"


@dataclass
class SourceSpec:
    source_id: str
    display_name: str
    institution: str
    description: str
    endpoint_env: str
    api_key_env: str
    default_query_param: str = "q"
    auth_header: str = "Authorization"
    response_format: str = "json"  # json or csv
    enabled_by_default: bool = False
    homepage: str = ""


@dataclass
class FetchResult:
    source_id: str
    ok: bool
    mode: str  # live, cached, bundled_sample, failed
    rows: List[Dict[str, Any]]
    benefits: List[Dict[str, Any]]
    warnings: List[str]
    fetched_at: str
    payload_hash: str
    endpoint_used: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def ensure_source_registry() -> None:
    if REGISTRY_PATH.exists():
        return
    REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
    specs = [
        {
            "source_id": "bokjiro",
            "display_name": "복지로/사회보장 정책 API",
            "institution": "보건복지·사회보장 영역",
            "description": "복지 서비스명, 대상, 신청조건, 서류, 신청 URL을 수집해 룰 카탈로그로 정규화하는 커넥터",
            "endpoint_env": "LIFEPASS_BOKJIRO_ENDPOINT",
            "api_key_env": "LIFEPASS_BOKJIRO_API_KEY",
            "default_query_param": "q",
            "auth_header": "Authorization",
            "response_format": "json",
            "enabled_by_default": False,
            "homepage": "https://www.bokjiro.go.kr",
        },
        {
            "source_id": "gov24",
            "display_name": "정부24 보조금/민원 정책 API",
            "institution": "행정안전·정부24 영역",
            "description": "정부24·보조금성 정책 데이터를 정책 룰 후보로 변환하는 커넥터",
            "endpoint_env": "LIFEPASS_GOV24_ENDPOINT",
            "api_key_env": "LIFEPASS_GOV24_API_KEY",
            "default_query_param": "q",
            "auth_header": "Authorization",
            "response_format": "json",
            "enabled_by_default": False,
            "homepage": "https://www.gov.kr",
        },
        {
            "source_id": "work24",
            "display_name": "고용24/직업훈련 정책 API",
            "institution": "고용노동·직업훈련 영역",
            "description": "구직·훈련·고용장려금 관련 공고를 수집해 일자리 혜택 룰로 변환하는 커넥터",
            "endpoint_env": "LIFEPASS_WORK24_ENDPOINT",
            "api_key_env": "LIFEPASS_WORK24_API_KEY",
            "default_query_param": "q",
            "auth_header": "Authorization",
            "response_format": "json",
            "enabled_by_default": False,
            "homepage": "https://www.work24.go.kr",
        },
        {
            "source_id": "local_city",
            "display_name": "지자체 공고 CSV/JSON Gateway",
            "institution": "광역·기초 지자체",
            "description": "지자체 공고 크롤러·오픈데이터·수작업 CSV를 동일 스키마로 수집하는 범용 커넥터",
            "endpoint_env": "LIFEPASS_LOCAL_CITY_ENDPOINT",
            "api_key_env": "LIFEPASS_LOCAL_CITY_API_KEY",
            "default_query_param": "keyword",
            "auth_header": "Authorization",
            "response_format": "json",
            "enabled_by_default": True,
            "homepage": "",
        },
    ]
    REGISTRY_PATH.write_text(json.dumps(specs, ensure_ascii=False, indent=2), encoding="utf-8")


def load_source_specs() -> List[SourceSpec]:
    ensure_source_registry()
    raw = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    return [SourceSpec(**item) for item in raw]


def get_source_spec(source_id: str) -> SourceSpec:
    for spec in load_source_specs():
        if spec.source_id == source_id:
            return spec
    raise ValueError(f"Unknown source_id: {source_id}")


def source_status_rows() -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for spec in load_source_specs():
        endpoint = os.getenv(spec.endpoint_env, "")
        api_key = os.getenv(spec.api_key_env, "")
        rows.append({
            "source_id": spec.source_id,
            "display_name": spec.display_name,
            "institution": spec.institution,
            "endpoint_configured": bool(endpoint),
            "api_key_configured": bool(api_key),
            "mode": "live-ready" if endpoint else "offline-sample",
            "endpoint_env": spec.endpoint_env,
            "api_key_env": spec.api_key_env,
            "homepage": spec.homepage,
        })
    return rows


def _ensure_sample_payload() -> None:
    if SAMPLE_PATH.exists():
        return
    SAMPLE_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "items": [
            {
                "id": "live_youth_interview_allowance",
                "name": "청년 면접수당 API 샘플",
                "domain": "일자리",
                "estimated_monthly_value": 50000,
                "priority": 71,
                "description": "구직 청년의 면접 비용을 지원하는 외부 API 수집 예시",
                "target": "만 18~39세 구직 청년",
                "min_age": 18,
                "max_age": 39,
                "region": "서울|경기|인천",
                "employment_status": "unemployed|job_seeker",
                "required_docs": "신분증, 면접확인서, 통장사본",
                "apply_url": "https://example.go.kr/youth-interview",
                "source_system": "bundled_sample",
            },
            {
                "id": "live_energy_voucher_sample",
                "name": "취약계층 에너지바우처 API 샘플",
                "domain": "생활안정",
                "estimated_monthly_value": 35000,
                "priority": 67,
                "description": "취약계층 생활비 부담 완화를 위한 외부 API 수집 예시",
                "target": "차상위 또는 위기 사유 가구",
                "min_age": 0,
                "max_age": 120,
                "max_income_percent": 100,
                "required_docs": "주민등록등본, 소득자료, 위기사유 증빙",
                "apply_url": "https://example.go.kr/energy-voucher",
                "source_system": "bundled_sample",
            },
        ]
    }
    SAMPLE_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _flatten_payload(payload: Any) -> List[Dict[str, Any]]:
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]
    if isinstance(payload, dict):
        for key in ["items", "data", "rows", "results", "policies", "benefits", "response"]:
            value = payload.get(key)
            if isinstance(value, list):
                return [x for x in value if isinstance(x, dict)]
            if isinstance(value, dict):
                nested = _flatten_payload(value)
                if nested:
                    return nested
        return [payload]
    return []


def _read_csv_text(text: str) -> List[Dict[str, Any]]:
    reader = csv.DictReader(text.splitlines())
    return [dict(row) for row in reader]


def _normalize_rows(rows: Iterable[Dict[str, Any]], source_id: str) -> List[Dict[str, Any]]:
    normalized: List[Dict[str, Any]] = []
    for idx, row in enumerate(rows, start=1):
        record = dict(row)
        # Common public API field aliases
        aliases = {
            "servNm": "name",
            "서비스명": "name",
            "서비스ID": "id",
            "bizId": "id",
            "jurMnofNm": "domain",
            "서비스목적": "description",
            "서비스대상": "target",
            "지원내용": "description",
            "신청URL": "apply_url",
            "url": "apply_url",
            "지원금액": "estimated_monthly_value",
            "나이시작": "min_age",
            "나이종료": "max_age",
            "시도": "region",
            "소관기관": "domain",
        }
        for src, dst in aliases.items():
            if src in record and dst not in record:
                record[dst] = record[src]
        record.setdefault("id", f"{source_id}_{idx}_{hashlib.sha1(json.dumps(row, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:10]}")
        record.setdefault("name", record.get("policy_name") or record.get("title") or f"{source_id} 수집 정책 {idx}")
        record.setdefault("domain", record.get("category") or record.get("분야") or "외부공공API")
        record.setdefault("priority", 60)
        record.setdefault("source_system", source_id)
        normalized.append(record)
    return normalized


def _cache_path(source_id: str, query: str) -> Path:
    digest = hashlib.md5(f"{source_id}:{query}".encode("utf-8")).hexdigest()[:16]
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return CACHE_DIR / f"{source_id}_{digest}.json"


def _request_live(spec: SourceSpec, query: str = "", limit: int = 50, timeout: int = 8) -> Tuple[List[Dict[str, Any]], str, str]:
    endpoint = os.getenv(spec.endpoint_env, "").strip()
    if not endpoint:
        raise RuntimeError(f"{spec.endpoint_env} 환경변수가 설정되지 않아 live call을 생략합니다.")
    params = {spec.default_query_param: query, "limit": str(limit)} if query else {"limit": str(limit)}
    separator = "&" if "?" in endpoint else "?"
    url = endpoint + separator + urllib.parse.urlencode(params, doseq=True)
    headers = {"User-Agent": "LifePassAI/3.0 policy-ingestion"}
    api_key = os.getenv(spec.api_key_env, "").strip()
    if api_key:
        if spec.auth_header.lower() == "authorization":
            headers[spec.auth_header] = f"Bearer {api_key}"
        else:
            headers[spec.auth_header] = api_key
    req = urllib.request.Request(url, headers=headers, method="GET")
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 - explicit external integration path
        raw = resp.read().decode("utf-8", errors="replace")
    if spec.response_format == "csv" or raw.lstrip().startswith(("id,", "name,")):
        rows = _read_csv_text(raw)
    else:
        rows = _flatten_payload(json.loads(raw))
    return _normalize_rows(rows[:limit], spec.source_id), url, raw


def fetch_source_policies(source_id: str, query: str = "", limit: int = 50, use_cache: bool = True, use_sample_on_fail: bool = True) -> FetchResult:
    spec = get_source_spec(source_id)
    warnings: List[str] = []
    fetched_at = _now_iso()
    endpoint_used = ""
    mode = "live"
    rows: List[Dict[str, Any]] = []
    raw_payload = ""
    cache_path = _cache_path(source_id, query)

    try:
        rows, endpoint_used, raw_payload = _request_live(spec, query=query, limit=limit)
        cache_path.write_text(json.dumps({"rows": rows, "fetched_at": fetched_at, "endpoint": endpoint_used}, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as live_exc:  # noqa: BLE001
        warnings.append(str(live_exc))
        if use_cache and cache_path.exists():
            cached = json.loads(cache_path.read_text(encoding="utf-8"))
            rows = cached.get("rows", [])[:limit]
            endpoint_used = cached.get("endpoint", "cache")
            mode = "cached"
            raw_payload = json.dumps(cached, ensure_ascii=False)
        elif use_sample_on_fail:
            _ensure_sample_payload()
            payload = json.loads(SAMPLE_PATH.read_text(encoding="utf-8"))
            rows = _normalize_rows(_flatten_payload(payload)[:limit], source_id)
            endpoint_used = "bundled sample"
            mode = "bundled_sample"
            raw_payload = json.dumps(payload, ensure_ascii=False)
        else:
            return FetchResult(source_id, False, "failed", [], [], warnings, fetched_at, "", endpoint_used)

    payload_hash = fingerprint_payload(raw_payload or rows)
    df = pd.DataFrame(rows)
    benefits, transform_warnings = benefits_from_dataframe(df)
    warnings.extend(transform_warnings)
    benefits = add_provenance(benefits, source_system=source_id, source_url=endpoint_used, raw_hash=payload_hash, collected_at=fetched_at)
    return FetchResult(source_id, True, mode, rows, benefits, warnings, fetched_at, payload_hash, endpoint_used)


def fetch_all_enabled_sources(query: str = "", limit: int = 50) -> List[FetchResult]:
    results: List[FetchResult] = []
    for spec in load_source_specs():
        if spec.enabled_by_default or os.getenv(spec.endpoint_env):
            results.append(fetch_source_policies(spec.source_id, query=query, limit=limit))
    return results
