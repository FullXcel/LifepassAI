"""DBMS and pgvector-ready metadata layer.

This module keeps the demo zero-ops while making the production architecture
explicit. SQLite remains the local default; PostgreSQL + pgvector can be enabled
with LIFEPASS_DATABASE_URL and the DDL exported here.
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
CREATE TABLE IF NOT EXISTS policy_documents (
    id BIGSERIAL PRIMARY KEY,
    tenant_id BIGINT REFERENCES tenants(id),
    benefit_id TEXT,
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
        DbmsCapability("pgvector RAG", "DDL-ready", "policy_chunks.embedding vector(384)", "정책 문서 의미검색과 근거 검색을 DB 내부에서 처리"),
        DbmsCapability("Agent audit tables", "DDL-ready", "agent_runs, agent_steps, audit_logs", "AI Agent 실행과 도구 호출을 감사 가능하게 기록"),
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
            "LIFEPASS_TENANT_KEY": "seoul-demo",
        },
    }
