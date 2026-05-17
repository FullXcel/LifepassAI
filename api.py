"""FastAPI backend for LifePass AI Agent Platform.

Run:
    uvicorn api:app --reload --port 8000
"""
from __future__ import annotations

from typing import Any, Dict

try:
    from fastapi import FastAPI, UploadFile, File
except Exception as exc:  # pragma: no cover
    raise RuntimeError("FastAPI 실행에는 `pip install fastapi uvicorn python-multipart`가 필요합니다.") from exc

import pandas as pd

from core.agent import build_agent_plan
from core.audit import build_trust_audit
from core.batch import analyze_profiles
from core.benefit_catalog import load_benefits
from core.models import UserProfile
from core.observability import recent_traces, trace_span
from core.policy_ingestion import benefits_from_dataframe, load_imported_benefits, save_imported_benefits
from core.public_api_clients import fetch_source_policies, load_source_specs, source_status_rows
from core.tool_manifest import tool_manifest
from core.utils import normalize_profile
from core.validation import validate_profile
from core.vector_search import search_policies
from core.whatif import build_counterfactuals
from core.agent_workflow import build_agent_workflow
from core.constraint_solver import solve_benefit_portfolio
from core.dbms import dbms_capabilities, deployment_readiness
from core.document_parser import draft_benefit_from_text
from core.durable_workflow import build_application_workflow
from core.evaluation import run_benchmark
from core.guardrails import validate_structured_payload
from core.knowledge_graph import build_eligibility_graph
from core.notifications import plan_notifications
from core.rule_engine import evaluate_all
from core.optimizer import optimize_benefits
from core.smart_mapper import infer_mapping, map_dataframe_to_profiles

from core.v5_event_mesh import event_ops_dashboard
from core.v5_policy_digital_twin import simulate_policy_impact
from core.v5_privacy_security import privacy_security_pack, check_access
from core.v5_causal_ops import estimate_intervention_effects, quality_ops_pack
from core.demo_data import load_sample_profiles

app = FastAPI(title="LifePass AI Agent API", version="5.0.0")


def active_benefits() -> list[dict[str, Any]]:
    benefits = load_benefits()
    try:
        imported = load_imported_benefits()
        existing = {b["id"] for b in benefits}
        benefits.extend([b for b in imported if b.get("id") not in existing])
    except Exception:
        pass
    return benefits


@app.get("/health")
def health() -> Dict[str, Any]:
    benefits = active_benefits()
    return {"status": "ok", "version": "5.0.0", "benefit_count": len(benefits), "source_count": len(load_source_specs())}


@app.get("/api/v1/mcp/tools")
def mcp_tools() -> Dict[str, Any]:
    return tool_manifest()


@app.post("/api/v1/analyze")
def analyze(payload: Dict[str, Any]) -> Dict[str, Any]:
    raw = payload.get("profile", payload)
    question = str(payload.get("question", ""))
    with trace_span("api.analyze", endpoint="/api/v1/analyze"):
        profile, warnings = validate_profile(UserProfile.from_dict(raw))
        plan = build_agent_plan(normalize_profile(profile), active_benefits(), question=question)
        plan["validation_warnings"] = warnings
        return plan


@app.post("/api/v1/batch/analyze")
async def batch_analyze(file: UploadFile = File(...)) -> Dict[str, Any]:
    with trace_span("api.batch_analyze", filename=file.filename or "uploaded.csv"):
        df = pd.read_csv(file.file)
        result_df, _ = analyze_profiles(df, active_benefits())
        return {"rows": result_df.to_dict(orient="records"), "count": len(result_df)}


@app.post("/api/v1/policies/preview")
async def policy_preview(file: UploadFile = File(...)) -> Dict[str, Any]:
    df = pd.read_csv(file.file)
    benefits, warnings = benefits_from_dataframe(df)
    return {"benefits": benefits, "warnings": warnings, "count": len(benefits)}


@app.get("/api/v1/sources")
def sources() -> Dict[str, Any]:
    return {"sources": source_status_rows()}


@app.post("/api/v1/sources/fetch")
def fetch_source(payload: Dict[str, Any]) -> Dict[str, Any]:
    source_id = str(payload.get("source_id", "local_city"))
    query = str(payload.get("query", ""))
    limit = int(payload.get("limit", 50))
    with trace_span("api.sources.fetch", source_id=source_id, query=query):
        result = fetch_source_policies(source_id, query=query, limit=limit)
        return result.to_dict()


@app.post("/api/v1/policies/sync")
def sync_policies(payload: Dict[str, Any]) -> Dict[str, Any]:
    source_id = str(payload.get("source_id", "local_city"))
    query = str(payload.get("query", ""))
    limit = int(payload.get("limit", 50))
    result = fetch_source_policies(source_id, query=query, limit=limit)
    if result.benefits:
        save_imported_benefits(result.benefits)
    return {"saved_count": len(result.benefits), "fetch": result.to_dict()}


@app.get("/api/v1/policies/search")
def policies_search(q: str, top_k: int = 8) -> Dict[str, Any]:
    rows = search_policies(q, active_benefits(), top_k=top_k)
    return {"query": q, "rows": rows, "count": len(rows)}


@app.post("/api/v1/audit")
def audit(payload: Dict[str, Any]) -> Dict[str, Any]:
    raw = payload.get("profile", payload)
    profile, _ = validate_profile(UserProfile.from_dict(raw))
    plan = build_agent_plan(normalize_profile(profile), active_benefits(), question="audit")
    return build_trust_audit(profile, active_benefits(), plan)


@app.post("/api/v1/whatif")
def whatif(payload: Dict[str, Any]) -> Dict[str, Any]:
    raw = payload.get("profile", payload)
    profile, _ = validate_profile(UserProfile.from_dict(raw))
    rows = build_counterfactuals(profile, active_benefits())
    return {"rows": rows, "count": len(rows)}


@app.get("/api/v1/observability/traces")
def traces() -> Dict[str, Any]:
    rows = recent_traces()
    return {"rows": rows, "count": len(rows)}


@app.post("/api/v1/agent/workflow")
def agent_workflow(payload: Dict[str, Any]) -> Dict[str, Any]:
    raw = payload.get("profile", payload)
    question = str(payload.get("question", ""))
    profile, _ = validate_profile(UserProfile.from_dict(raw))
    return build_agent_workflow(normalize_profile(profile), active_benefits(), question=question)


@app.get("/api/v1/dbms/readiness")
def dbms_readiness() -> Dict[str, Any]:
    ready = deployment_readiness()
    return {"capabilities": dbms_capabilities(), "database": ready["database"], "recommended_env": ready["recommended_env"]}


@app.post("/api/v1/portfolio/optimize")
def portfolio_optimize(payload: Dict[str, Any]) -> Dict[str, Any]:
    raw = payload.get("profile", payload)
    profile, _ = validate_profile(UserProfile.from_dict(raw))
    evaluations = evaluate_all(active_benefits(), normalize_profile(profile))
    return solve_benefit_portfolio(evaluations)


@app.post("/api/v1/application/workflow")
def application_workflow(payload: Dict[str, Any]) -> Dict[str, Any]:
    raw = payload.get("profile", payload)
    profile, _ = validate_profile(UserProfile.from_dict(raw))
    evaluations = evaluate_all(active_benefits(), normalize_profile(profile))
    selected = optimize_benefits(evaluations).selected
    wf = build_application_workflow(profile, selected)
    return {"workflow": wf, "notifications": plan_notifications(profile, wf)}


@app.post("/api/v1/policies/document/draft")
def policy_document_draft(payload: Dict[str, Any]) -> Dict[str, Any]:
    text = str(payload.get("text", ""))
    source_url = str(payload.get("source_url", "uploaded://api"))
    return {"benefit": draft_benefit_from_text(text, source_url=source_url)}


@app.post("/api/v1/knowledge-graph")
def knowledge_graph(payload: Dict[str, Any]) -> Dict[str, Any]:
    raw = payload.get("profile", payload)
    profile, _ = validate_profile(UserProfile.from_dict(raw))
    evaluations = evaluate_all(active_benefits(), normalize_profile(profile))
    return build_eligibility_graph(profile, evaluations)


@app.get("/api/v1/evaluation/benchmark")
def evaluation_benchmark() -> Dict[str, Any]:
    return run_benchmark(active_benefits())


@app.post("/api/v1/guardrails/validate")
def guardrails_validate(payload: Dict[str, Any]) -> Dict[str, Any]:
    schema = str(payload.get("schema", "UserProfile"))
    raw = payload.get("payload", payload.get("profile", payload))
    return validate_structured_payload(raw, schema_name=schema)


@app.post("/api/v1/events/simulate")
def events_simulate(payload: Dict[str, Any]) -> Dict[str, Any]:
    raw = payload.get("profile", payload)
    profile, _ = validate_profile(UserProfile.from_dict(raw))
    return event_ops_dashboard(normalize_profile(profile))


@app.post("/api/v1/policy/digital-twin")
def policy_digital_twin(payload: Dict[str, Any]) -> Dict[str, Any]:
    age_upper = int(payload.get("age_upper", 39))
    value_multiplier = float(payload.get("value_multiplier", 1.0))
    profiles_payload = payload.get("profiles")
    if isinstance(profiles_payload, list) and profiles_payload:
        profiles = [validate_profile(UserProfile.from_dict(p))[0] for p in profiles_payload]
    else:
        profiles = [UserProfile.from_dict(item["profile"]) for item in load_sample_profiles()]
    return simulate_policy_impact(profiles, active_benefits(), age_upper=age_upper, value_multiplier=value_multiplier)


@app.post("/api/v1/security/access-check")
def security_access_check(payload: Dict[str, Any]) -> Dict[str, Any]:
    return check_access(
        str(payload.get("role", "counselor")),
        str(payload.get("action", "read:assigned")),
        str(payload.get("purpose", "eligibility_screening")),
        payload.get("fields", ["age", "region", "monthly_income", "rent"]),
    )


@app.post("/api/v1/privacy/pack")
def privacy_pack(payload: Dict[str, Any]) -> Dict[str, Any]:
    raw = payload.get("profile", payload)
    profile, _ = validate_profile(UserProfile.from_dict(raw))
    return privacy_security_pack(normalize_profile(profile))


@app.post("/api/v1/causal/interventions")
def causal_interventions(payload: Dict[str, Any]) -> Dict[str, Any]:
    raw = payload.get("profile", payload)
    profile, _ = validate_profile(UserProfile.from_dict(raw))
    return estimate_intervention_effects(normalize_profile(profile))


@app.get("/api/v1/quality/ops")
def quality_ops() -> Dict[str, Any]:
    return quality_ops_pack()
