CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS tenants (
    tenant_id TEXT PRIMARY KEY,
    display_name TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS profile_snapshots (
    profile_id BIGSERIAL PRIMARY KEY,
    tenant_id TEXT DEFAULT 'seoul-demo',
    profile_hash TEXT NOT NULL,
    profile_json JSONB NOT NULL,
    consent_json JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS policy_catalog (
    policy_id TEXT PRIMARY KEY,
    tenant_id TEXT DEFAULT 'seoul-demo',
    policy_json JSONB NOT NULL,
    provenance_json JSONB DEFAULT '{}'::jsonb,
    version_hash TEXT,
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS policy_chunks (
    chunk_id BIGSERIAL PRIMARY KEY,
    policy_id TEXT REFERENCES policy_catalog(policy_id) ON DELETE CASCADE,
    chunk_text TEXT NOT NULL,
    embedding vector(384),
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS agent_runs (
    run_id BIGSERIAL PRIMARY KEY,
    tenant_id TEXT DEFAULT 'seoul-demo',
    profile_hash TEXT,
    question TEXT,
    audit_score NUMERIC,
    human_review_required BOOLEAN DEFAULT false,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS agent_steps (
    step_id BIGSERIAL PRIMARY KEY,
    run_id BIGINT REFERENCES agent_runs(run_id) ON DELETE CASCADE,
    step_name TEXT NOT NULL,
    tool_name TEXT,
    status TEXT DEFAULT 'completed',
    latency_ms INTEGER DEFAULT 0,
    step_payload JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS event_outbox (
    event_id TEXT PRIMARY KEY,
    tenant_id TEXT DEFAULT 'seoul-demo',
    routing_key TEXT NOT NULL,
    event_type TEXT NOT NULL,
    idempotency_key TEXT UNIQUE NOT NULL,
    payload JSONB NOT NULL,
    status TEXT DEFAULT 'ready_to_publish',
    retry_count INTEGER DEFAULT 0,
    next_attempt_at TIMESTAMPTZ DEFAULT now(),
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS application_workflows (
    workflow_id BIGSERIAL PRIMARY KEY,
    tenant_id TEXT DEFAULT 'seoul-demo',
    profile_hash TEXT,
    current_state TEXT DEFAULT 'created',
    workflow_json JSONB NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS audit_logs (
    audit_id BIGSERIAL PRIMARY KEY,
    tenant_id TEXT DEFAULT 'seoul-demo',
    actor_role TEXT,
    purpose TEXT,
    action TEXT,
    decision TEXT,
    fields JSONB DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_profile_snapshots_tenant ON profile_snapshots(tenant_id);
CREATE INDEX IF NOT EXISTS idx_event_outbox_status ON event_outbox(status, next_attempt_at);
CREATE INDEX IF NOT EXISTS idx_policy_catalog_tenant ON policy_catalog(tenant_id);
-- In a production environment, choose ivfflat/hnsw index parameters after embedding volume is known.
-- CREATE INDEX IF NOT EXISTS idx_policy_chunks_embedding ON policy_chunks USING hnsw (embedding vector_cosine_ops);
