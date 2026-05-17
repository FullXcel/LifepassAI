"""DBMS and pgvector-ready metadata layer.

SQLite remains the local default for zero-ops demos.  The DDL preview below is
what should be applied in PostgreSQL/pgvector production deployments so the app
can persist users, policies, policy chunks, agent runs, cases, notifications and
privacy audits.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Dict, List

from .persistence import database_url, db_status

POSTGRES_PGVECTOR_DDL = """
CREATE EXTENSION IF NOT EXISTS vector;
CREATE TABLE IF NOT EXISTS tenants (
    id BIGSERIAL PRIMARY KEY,
    tenant_key TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    region_scope TEXT DEFAULT 'national',
    created_at TIMESTAMPTZ DEFAULT now()
);
CREATE TABLE IF NOT EXISTS user_accounts (
    user_id BIGSERIAL PRIMARY KEY,
    tenant_id BIGINT REFERENCES tenants(id),
    email TEXT UNIQUE NOT NULL,
    display_name TEXT NOT NULL,
    role TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    salt TEXT NOT NULL,
    disabled BOOLEAN DEFAULT false,
    created_at TIMESTAMPTZ DEFAULT now(),
    last_login_at TIMESTAMPTZ
);
CREATE TABLE IF NOT EXISTS profile_snapshots (
    profile_id BIGSERIAL PRIMARY KEY,
    tenant_id BIGINT REFERENCES tenants(id),
    profile_hash TEXT NOT NULL,
    profile_json JSONB NOT NULL,
    consent_json JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT now()
);
CREATE TABLE IF NOT EXISTS policy_catalog_live (
    policy_id TEXT PRIMARY KEY,
    tenant_id BIGINT REFERENCES tenants(id),
    benefit_json JSONB NOT NULL,
    provenance_json JSONB DEFAULT '{}'::jsonb,
    version_hash TEXT NOT NULL,
    source_system TEXT NOT NULL,
    source_url TEXT DEFAULT '',
    source_document_url TEXT DEFAULT '',
    source_date TEXT DEFAULT '',
    is_demo BOOLEAN DEFAULT false,
    human_review_required BOOLEAN DEFAULT false,
    active BOOLEAN DEFAULT true,
    first_seen_at TIMESTAMPTZ DEFAULT now(),
    last_seen_at TIMESTAMPTZ DEFAULT now()
);
CREATE TABLE IF NOT EXISTS policy_sync_runs (
    run_id BIGSERIAL PRIMARY KEY,
    tenant_id BIGINT REFERENCES tenants(id),
    source_id TEXT NOT NULL,
    mode TEXT NOT NULL,
    status TEXT NOT NULL,
    query TEXT DEFAULT '',
    limit_count INT DEFAULT 0,
    payload_hash TEXT DEFAULT '',
    endpoint_used TEXT DEFAULT '',
    live_required BOOLEAN DEFAULT false,
    diff_json JSONB NOT NULL,
    warnings_json JSONB DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ DEFAULT now()
);
CREATE TABLE IF NOT EXISTS policy_documents (
    id BIGSERIAL PRIMARY KEY,
    tenant_id BIGINT REFERENCES tenants(id),
    benefit_id TEXT REFERENCES policy_catalog_live(policy_id),
    source_url TEXT,
    title TEXT NOT NULL,
    body TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    version_tag TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now()
);
CREATE TABLE IF NOT EXISTS policy_chunks (
    id BIGSERIAL PRIMARY KEY,
    document_id BIGINT REFERENCES policy_documents(id),
    chunk_index INT NOT NULL,
    chunk_text TEXT NOT NULL,
    embedding vector(384),
    created_at TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS policy_chunks_embedding_hnsw
    ON policy_chunks USING hnsw (embedding vector_cosine_ops);
CREATE TABLE IF NOT EXISTS agent_runs (
    id BIGSERIAL PRIMARY KEY,
    tenant_id BIGINT REFERENCES tenants(id),
    profile_id BIGINT,
    run_type TEXT NOT NULL,
    status TEXT NOT NULL,
    input_json JSONB NOT NULL,
    output_json JSONB,
    human_review_required BOOLEAN DEFAULT false,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);
CREATE TABLE IF NOT EXISTS agent_steps (
    id BIGSERIAL PRIMARY KEY,
    run_id BIGINT REFERENCES agent_runs(id),
    step_name TEXT NOT NULL,
    tool_name TEXT NOT NULL,
    status TEXT NOT NULL,
    latency_ms INT DEFAULT 0,
    input_json JSONB,
    output_json JSONB,
    created_at TIMESTAMPTZ DEFAULT now()
);
CREATE TABLE IF NOT EXISTS application_cases (
    case_id BIGSERIAL PRIMARY KEY,
    tenant_id BIGINT REFERENCES tenants(id),
    profile_hash TEXT NOT NULL,
    profile_json JSONB NOT NULL,
    selected_benefits_json JSONB NOT NULL,
    status TEXT NOT NULL,
    risk_level TEXT NOT NULL DEFAULT 'normal',
    assigned_role TEXT DEFAULT 'counselor',
    reviewer_email TEXT DEFAULT '',
    decision_reason TEXT DEFAULT '',
    created_by TEXT DEFAULT '',
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);
CREATE TABLE IF NOT EXISTS notification_outbox (
    notification_id BIGSERIAL PRIMARY KEY,
    tenant_id BIGINT REFERENCES tenants(id),
    idempotency_key TEXT UNIQUE NOT NULL,
    channel TEXT NOT NULL,
    destination TEXT NOT NULL,
    template TEXT NOT NULL,
    payload_json JSONB NOT NULL,
    severity TEXT DEFAULT 'medium',
    status TEXT DEFAULT 'queued',
    attempts INT DEFAULT 0,
    last_error TEXT DEFAULT '',
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);
CREATE TABLE IF NOT EXISTS audit_logs (
    id BIGSERIAL PRIMARY KEY,
    tenant_id BIGINT REFERENCES tenants(id),
    actor_id TEXT,
    event_type TEXT NOT NULL,
    subject_type TEXT NOT NULL,
    subject_id TEXT,
    payload_json JSONB,
    created_at TIMESTAMPTZ DEFAULT now()
);
CREATE TABLE IF NOT EXISTS consent_records (
    consent_id BIGSERIAL PRIMARY KEY,
    tenant_id BIGINT REFERENCES tenants(id),
    subject_hash TEXT NOT NULL,
    purpose TEXT NOT NULL,
    granted BOOLEAN NOT NULL,
    scope_json JSONB NOT NULL,
    expires_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT now()
);
CREATE TABLE IF NOT EXISTS privacy_access_logs (
    access_id BIGSERIAL PRIMARY KEY,
    tenant_id BIGINT REFERENCES tenants(id),
    actor_id TEXT NOT NULL,
    role TEXT NOT NULL,
    action TEXT NOT NULL,
    purpose TEXT NOT NULL,
    subject_hash TEXT NOT NULL,
    fields_json JSONB NOT NULL,
    decision TEXT NOT NULL,
    reason TEXT DEFAULT '',
    created_at TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_policy_catalog_live_source ON policy_catalog_live(source_system, active);
CREATE INDEX IF NOT EXISTS idx_policy_sync_runs_source ON policy_sync_runs(source_id, created_at);
CREATE INDEX IF NOT EXISTS idx_application_cases_status ON application_cases(status, updated_at);
CREATE INDEX IF NOT EXISTS idx_notification_outbox_status ON notification_outbox(status, updated_at);
CREATE INDEX IF NOT EXISTS idx_privacy_access_subject ON privacy_access_logs(subject_hash, created_at);
""".strip()


@dataclass
class DbmsCapability:
    name: str
    status: str
    value: str
    why_it_matters: str


def dbms_capabilities() -> List[Dict[str, Any]]:
    url = database_url()
    mode = "postgresql+pgvector" if url.startswith(("postgresql://", "postgres://")) else "sqlite-local / postgres-ready"
    rows = [
        DbmsCapability("Operational DBMS", mode, url, "사용자·정책·판정·상담 이력을 영속 저장"),
        DbmsCapability("Policy sync history", "DDL-ready", "policy_catalog_live, policy_sync_runs", "정책 원문·버전·데모 여부·업데이트 diff를 재현"),
        DbmsCapability("pgvector RAG", "DDL-ready", "policy_chunks.embedding vector(384)", "정책 문서 의미검색과 근거 검색을 DB 내부에서 처리"),
        DbmsCapability("Agent audit tables", "DDL-ready", "agent_runs, agent_steps, audit_logs", "AI Agent 실행과 도구 호출을 감사 가능하게 기록"),
        DbmsCapability("Human review workflow", "DDL-ready", "application_cases", "고위험·데모 데이터·불확실 판정을 상담사가 승인"),
        DbmsCapability("Notification outbox", "DDL-ready", "notification_outbox", "신청 마감·자격 변화 알림을 idempotent하게 발송"),
        DbmsCapability("Privacy audit", "DDL-ready", "consent_records, privacy_access_logs", "동의와 개인정보 접근을 목적 기반으로 추적"),
        DbmsCapability("Multi-tenant schema", "DDL-ready", "tenants.tenant_key", "중앙정부·지자체·대학·복지기관별 독립 운영"),
    ]
    return [r.__dict__ for r in rows]


def deployment_readiness() -> Dict[str, Any]:
    status = db_status()
    return {
        "database": status,
        "pgvector_enabled_by_env": bool(os.getenv("LIFEPASS_ENABLE_PGVECTOR", "0") in {"1", "true", "TRUE"}),
        "ddl_preview": POSTGRES_PGVECTOR_DDL,
        "recommended_env": {
            "LIFEPASS_DATABASE_URL": "postgresql://lifepass:lifepass@postgres:5432/lifepass",
            "LIFEPASS_ENABLE_PGVECTOR": "1",
            "LIFEPASS_TENANT_KEY": "seoul-production",
            "LIFEPASS_AUTH_SECRET": "replace-with-strong-secret",
            "LIFEPASS_STRICT_LIVE_SOURCES": "1",
        },
    }
