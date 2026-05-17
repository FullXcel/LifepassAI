# LifePass AI Agent v5.1

## Policy Intelligence & Welfare Operations Platform for Youth Welfare Transitions

LifePass AI Agent v5.1은 단순 복지 혜택 추천 챗봇이 아니라, **정책 데이터 수집, 시민 프로필 구조화, deterministic 자격 판정, 최적 혜택 조합, 신청 워크플로우, 생애전환/복지절벽 시뮬레이션, 정책 Digital Twin, 보안·프라이버시·감사 운영, Embedding RAG + bounded LLM 상담 설명**을 하나의 흐름으로 연결하는 AI Agent 기반 복지 운영 플랫폼이다.

복지 사각지대는 혜택이 없어서만 발생하지 않는다. 사용자가 자신의 상황에 맞는 제도를 알지 못하거나, 정책 조건이 복잡하거나, 신청 시점과 서류 준비를 놓치거나, 실업급여 종료·소득 발생·이사·가구 변화 같은 생애전환 시점에서 기존 혜택 상실과 신규 혜택 발생을 동시에 관리하지 못할 때 발생한다. LifePass는 이 문제를 **AI Agent + deterministic rule engine + conflict-aware optimizer + operational DBMS + policy digital twin + responsible AI operations**로 해결한다.

핵심 원칙은 명확하다. **LLM은 자격 여부를 임의로 판정하지 않는다.** 실제 자격 판정은 `core/rule_engine.py`의 deterministic rule engine이 수행하고, LLM은 검색된 근거와 룰엔진 결과를 바탕으로 상담 문장, 서류 안내, 정책 요약을 생성하는 bounded explanation layer로만 사용된다.

---

## 1. 빠른 실행

### 1.1 Docker Compose 실행 권장

대회 시연 및 심사 환경에서는 Streamlit, FastAPI, PostgreSQL + pgvector, Redis를 함께 실행하는 Docker Compose 모드를 권장한다.

```bash
cd lifepass
docker compose up -d --build
```

현재 `docker-compose.yml` 기준 접속 주소는 다음과 같다.

```text
Streamlit Dashboard: http://localhost:8503
FastAPI OpenAPI Docs: http://localhost:8002/docs
PostgreSQL + pgvector: localhost:5433
Redis Event Queue: localhost:6380
```

상태 확인:

```bash
docker compose ps
```

로그 확인:

```bash
docker compose logs -f lifepass-ui
docker compose logs -f lifepass-api
docker compose logs -f postgres
docker compose logs -f redis
```

종료:

```bash
docker compose down
```

DB 볼륨까지 삭제:

```bash
docker compose down -v
```

### 1.2 `.env` 설정

두 서비스(`lifepass-ui`, `lifepass-api`) 모두 `env_file: .env`를 사용한다. 프로젝트 루트에 `.env`를 만들고 다음 값을 넣는다.

```env
LIFEPASS_DATABASE_URL=postgresql://lifepass:lifepass@postgres:5432/lifepass
LIFEPASS_REDIS_URL=redis://redis:6379/0
LIFEPASS_ENABLE_PGVECTOR=1
LIFEPASS_TENANT_KEY=seoul-demo
LIFEPASS_RUN_MODE=competition

PUBLIC_POLICY_API_TIMEOUT=8
PUBLIC_POLICY_API_USE_CACHE=1

LIFEPASS_EMBEDDING_PROVIDER=local_hash
LIFEPASS_EMBEDDING_MODEL=local-hash-ko-384

LIFEPASS_LLM_PROVIDER=template
LIFEPASS_LLM_MODEL=gpt-4o-mini
LIFEPASS_OPENAI_TIMEOUT=30
LIFEPASS_LLM_MAX_TOKENS=900
# OPENAI_API_KEY=your_openai_api_key_here
```

기본 모드는 API 키 없이 동작하는 `local_hash + template` 모드다. 실제 OpenAI 기반 embedding/LLM을 사용할 때만 아래처럼 바꾼다.

```env
LIFEPASS_EMBEDDING_PROVIDER=openai
LIFEPASS_EMBEDDING_MODEL=text-embedding-3-small
LIFEPASS_LLM_PROVIDER=openai
LIFEPASS_LLM_MODEL=gpt-4o-mini
OPENAI_API_KEY=your_openai_api_key_here
```

> 보안 주의: 실제 API 키가 들어간 `.env`는 GitHub, 대회 제출 zip, 채팅창에 올리지 않는다.

### 1.3 빠른 로컬 실행

화면만 빠르게 확인할 때는 다음 방식도 가능하다.

```bash
pip install -r requirements.txt
streamlit run app.py
```

이 경우 기본 Streamlit 주소는 `http://localhost:8501`이다. 단, PostgreSQL/pgvector/Redis 기반 운영 구조까지 함께 보여주려면 Docker Compose 모드가 더 적합하다.

### 1.4 검증

```bash
python -m py_compile app.py api.py core/*.py cli_demo.py tests/verify_mvp.py
python tests/verify_mvp.py
```

검증 스크립트는 정책 카탈로그, 자연어 프로필 파싱, 룰엔진, 혜택 충돌 제거, 생애전환 시뮬레이션, RAG/리포트, 신뢰성 감사, v4 운영 기능, v5 이벤트/정책트윈/보안/인과/품질 기능을 확인한다.

---

## 2. 프로젝트가 해결하는 문제

LifePass는 청년 1인가구, 실직 청년, 저소득 근로자, 프리랜서처럼 복지·고용·정책금융 제도의 영향을 크게 받지만 제도 이해와 신청 타이밍 관리가 어려운 사용자를 1차 타깃으로 한다.

기존 복지 추천 서비스가 “현재 조건에서 받을 수 있는 혜택 목록”을 보여주는 데 그쳤다면, LifePass는 다음 질문에 답한다.

```text
지금 받을 수 있는 제도는 무엇인가?
실업급여가 끝나는 시점에 어떤 제도가 새로 열리는가?
월소득이 생기면 어떤 혜택이 사라지고 어떤 제도가 가능해지는가?
혜택끼리 중복 제한이나 충돌이 있는가?
어떤 순서로 신청해야 총 월 환산효과가 커지는가?
신청 마감과 서류 준비는 언제 해야 하는가?
정책 조건이 바뀌면 사용자군과 예산에 어떤 영향이 생기는가?
```

---

## 3. 핵심 기능

### 3.1 AI 상담형 온보딩

사용자는 긴 행정 입력폼을 처음부터 작성하지 않아도 된다. 카카오톡 스타일의 자연어 입력으로 나이, 지역, 가구원 수, 월소득, 월세, 실업급여 잔여일, 고용 상태, 예상 소득 변화 등을 입력한다. `core/profile_parser.py`가 자연어를 `UserProfile` 구조로 변환하고, 화면의 구조화 입력폼에서 다시 수정할 수 있다.

### 3.2 Deterministic Eligibility Rule Engine

정책 조건은 `data/benefits.json`의 JSON rule schema로 관리된다. 실제 자격 판정은 `core/rule_engine.py`가 수행하며, 각 조건은 `RuleTrace`로 남는다. 이 구조는 LLM-only 판정보다 감사 가능하고 재현 가능하다.

### 3.3 Conflict-aware Benefit Optimizer

`core/optimizer.py`와 `core/constraint_solver.py`는 eligible benefit 중 상호배타 조건이 있는 혜택을 제거하고, 월 환산효과와 긴급도, 신청 난이도를 고려한 최적 조합을 만든다. 단순 추천 목록이 아니라 실제 신청 가능한 조합을 제시하는 점이 차별점이다.

### 3.4 생애전환 및 복지절벽 시뮬레이션

`core/simulator.py`와 `core/whatif.py`는 3개월·6개월·12개월 시점의 사용자 상태를 재계산하고, 소득 변화에 따른 혜택 상실/획득을 비교한다. 실업급여 종료, 아르바이트 시작, 정규직 전환, 주거비 변화 같은 전환 이벤트를 기반으로 복지절벽 위험을 시각화한다.

### 3.5 신청 워크플로우와 서류 체크리스트

`core/durable_workflow.py`, `core/notifications.py`, `core/persistence.py`는 신청 태스크, 서류 체크리스트, 마감 리마인더, 신청 상태 추적을 지원한다. 추천에서 끝나지 않고 신청 완료까지 이어지는 운영형 플랫폼을 지향한다.

### 3.6 정책 수집·정제·동기화

`core/public_api_clients.py`, `core/policy_ingestion.py`, `core/policy_provenance.py`, `scripts/ingest_policy_feed.py`는 공공 정책 소스 registry, CSV 정책 피드, 샘플 fallback, provenance, version diff를 처리한다. 실제 공공 API 키가 없어도 심사 환경에서 정책 동기화 흐름을 재현할 수 있다.

### 3.7 Embedding RAG + Bounded LLM 상담 설명

`core/embedding_rag.py`, `core/rag.py`, `core/llm_assistant.py`는 정책 문서와 카탈로그에서 근거를 검색하고, 룰엔진 판정 결과와 함께 상담 답변을 만든다. 기본값은 API 키 없이 동작하는 `local_hash` embedding과 `template` LLM이며, OpenAI 설정을 추가하면 실제 embedding retrieval과 LLM 기반 설명을 사용할 수 있다.

### 3.8 Event Mesh + Transactional Outbox

`core/v5_event_mesh.py`는 사용자 프로필 변경, 혜택 판정 요청, 마감 위험 감지, 생애전환 신호를 event envelope로 만들고 outbox 구조를 시뮬레이션한다. 이벤트에는 routing key, schema version, trace id, idempotency key가 포함된다.

### 3.9 Policy Digital Twin

`core/v5_policy_digital_twin.py`는 정책 연령 기준이나 지원액이 바뀌었을 때 영향받는 사용자 수, 신규 지원 가능자, 월/연 예산 변화, 개인별 지원 변화량을 사전에 계산한다.

### 3.10 Zero-Trust Security, Privacy, Causal Ops, Quality Ops

`core/v5_privacy_security.py`는 purpose-based RBAC/ABAC, differential privacy aggregate release, synthetic profile generation을 제공한다. `core/v5_causal_ops.py`는 상담사 동행, 서류 체크리스트, 마감 리마인더 같은 intervention을 uplift·비용·ROI proxy 기준으로 정렬하고, data contract, model card, incident playbook을 포함한 품질 운영 패키지를 제공한다.

---

## 4. 주요 화면 구성

Streamlit 대시보드는 다음 탭으로 구성된다.

```text
AI Agent
온보딩/프로필
현재 판정
생애전환/절벽
CSV 일괄분석
정책 수집
DB/신청관리
전략·API
운영자
공공 API Gateway
고급 AI/신뢰성
v4 운영플랫폼
v4 데이터지능
v4 품질/API
v5 실시간·정책트윈
v5 보안·인과·품질
```

권장 시연 순서:

```text
자연어 온보딩
→ 현재 자격 판정·최적 조합
→ 신청 서류 체크리스트
→ 생애전환/복지절벽 시뮬레이션
→ Agent Workflow Trace
→ Embedding RAG + bounded LLM 상담 답변
→ Event Mesh / Transactional Outbox
→ Policy Digital Twin
→ Zero-Trust / Privacy / Causal Ops / Quality Ops
→ FastAPI /docs와 Docker Compose 운영 구조
```

---

## 5. 시스템 아키텍처

```text
[Streamlit Dashboard]
    ├─ 자연어 온보딩 / 구조화 프로필 입력 / JSON 업로드
    ├─ CSV 일괄분석 / Smart Data Mapper
    ├─ Agent Workflow Trace / Human Review Queue
    ├─ 생애전환·복지절벽 시뮬레이터
    ├─ Embedding RAG + bounded LLM 상담 설명
    ├─ Policy Digital Twin / Impact Simulation
    └─ Security·Privacy·Causal Ops / Quality Ops
        ↓
[FastAPI Backend]
    ├─ /api/v1/analyze
    ├─ /api/v1/batch/analyze
    ├─ /api/v1/rag/status, /rag/search, /rag/ask
    ├─ /api/v1/agent/workflow
    ├─ /api/v1/portfolio/optimize
    ├─ /api/v1/application/workflow
    ├─ /api/v1/events/simulate
    ├─ /api/v1/policy/digital-twin
    ├─ /api/v1/security/access-check
    ├─ /api/v1/privacy/pack
    ├─ /api/v1/causal/interventions
    └─ /api/v1/quality/ops
        ↓
[Core Intelligence Layer]
    ├─ profile parser / smart mapper
    ├─ deterministic rule engine
    ├─ conflict-aware optimizer
    ├─ timeline and cliff simulator
    ├─ policy ingestion / provenance / document parser
    ├─ RAG / embedding / bounded LLM assistant
    ├─ event mesh / transactional outbox
    ├─ policy digital twin
    ├─ privacy/security pack
    └─ causal ops / quality ops
        ↓
[Operational Storage]
    ├─ PostgreSQL
    ├─ pgvector-ready policy chunks
    ├─ Redis-ready event queue
    └─ local fallback artifacts
```

---

## 6. REST API

Docker Compose 실행 후 OpenAPI 문서는 다음 주소에서 확인한다.

```text
http://localhost:8002/docs
```

대표 엔드포인트:

```text
GET  /health
GET  /api/v1/mcp/tools
POST /api/v1/analyze
POST /api/v1/batch/analyze
POST /api/v1/policies/preview
GET  /api/v1/sources
POST /api/v1/sources/fetch
POST /api/v1/policies/sync
GET  /api/v1/policies/search
GET  /api/v1/rag/status
GET  /api/v1/rag/search
POST /api/v1/rag/ask
POST /api/v1/audit
POST /api/v1/whatif
GET  /api/v1/observability/traces
POST /api/v1/agent/workflow
GET  /api/v1/dbms/readiness
POST /api/v1/portfolio/optimize
POST /api/v1/application/workflow
POST /api/v1/policies/document/draft
POST /api/v1/knowledge-graph
GET  /api/v1/evaluation/benchmark
POST /api/v1/guardrails/validate
POST /api/v1/events/simulate
POST /api/v1/policy/digital-twin
POST /api/v1/security/access-check
POST /api/v1/privacy/pack
POST /api/v1/causal/interventions
GET  /api/v1/quality/ops
```

분석 API 예시:

```bash
curl -X POST http://localhost:8002/api/v1/analyze \
  -H "Content-Type: application/json" \
  -d '{"profile":{"age":27,"region":"서울","household_size":1,"monthly_income":0,"rent":550000,"unemployment_benefit_receiving":true,"unemployment_benefit_days_left":45}}'
```

RAG 상담 API 예시:

```bash
curl -X POST http://localhost:8002/api/v1/rag/ask \
  -H "Content-Type: application/json" \
  -d '{"question":"실업급여가 45일 뒤 끝나면 무엇을 준비해야 하나요?","profile":{"age":27,"region":"서울","household_size":1,"monthly_income":0,"rent":550000,"unemployment_benefit_receiving":true,"unemployment_benefit_days_left":45}}'
```

---

## 7. DBMS 설계

`infra/postgres/init.sql`은 PostgreSQL + pgvector 기반 운영 테이블을 정의한다.

```text
tenants
profile_snapshots
policy_catalog
policy_chunks
agent_runs
agent_steps
event_outbox
application_workflows
audit_logs
```

핵심 설계 포인트:

```text
policy_chunks.embedding vector(384)
event_outbox.idempotency_key unique
agent_steps.run_id foreign key
application_workflows.workflow_json jsonb
audit_logs purpose/action/decision/fields 저장
```

이 구조는 단순 파일 기반 데모가 아니라, 실제 지자체·복지기관·대학·공공서비스로 확장 가능한 운영형 저장소를 제시한다.

---

## 8. 기술 스택

```text
Frontend: Streamlit
API: FastAPI
DBMS: PostgreSQL
Vector Search Ready: pgvector
Event Queue: Redis-ready event mesh
Data Layer: pandas, JSON policy catalog, local fallback artifacts
Agent: deterministic tool trace + human-in-the-loop workflow
Optimization: conflict-aware optimizer + constraint-style portfolio solver
Policy Intelligence: public API gateway, document parser, policy version diff, policy digital twin
RAG/LLM: local_hash embedding fallback, optional OpenAI embedding/LLM, bounded explanation layer
Security: RBAC/ABAC, purpose-based field access, audit log
Privacy: masking, synthetic data, differential privacy aggregate demo
Quality: benchmark suite, guardrails, data contract, model card, incident playbook
Deployment: Docker Compose
```

---

## 9. 디렉토리 구조

```text
app.py                         Streamlit dashboard
api.py                         FastAPI backend
cli_demo.py                    CLI demo entry point
core/models.py                 UserProfile, evaluation, scenario models
core/profile_parser.py          Natural language onboarding parser
core/rule_engine.py             Deterministic eligibility engine
core/optimizer.py               Conflict-aware benefit optimizer
core/simulator.py               Timeline and welfare cliff simulator
core/whatif.py                  Counterfactual what-if engine
core/embedding_rag.py           Embedding retrieval and bounded RAG package
core/llm_assistant.py           Template/OpenAI grounded counseling answer
core/v5_event_mesh.py           Event envelope and outbox simulation
core/v5_policy_digital_twin.py  Policy change impact simulator
core/v5_privacy_security.py     RBAC/ABAC, DP, synthetic data
core/v5_causal_ops.py           Intervention ranking and quality ops
infra/postgres/init.sql         PostgreSQL + pgvector schema
scripts/ingest_policy_feed.py   Policy feed ingestion script
tests/verify_mvp.py             End-to-end MVP verification
```

---

## 10. 한계와 확장 계획

본 버전은 실제 공공기관 API key 없이도 심사 환경에서 전체 파이프라인을 검증할 수 있도록 fallback sample과 local policy catalog를 포함한다. 실제 서비스화 단계에서는 다음 확장이 필요하다.

```text
복지로·정부24·고용24·지자체 공고 API의 실제 운영 키 연결
정책 문서 embedding 생성 및 pgvector 검색 인덱스 활성화
상담사 계정/권한/배정 로직 고도화
실제 신청 결과 데이터를 통한 uplift model 학습
기관별 멀티테넌트 배포와 SSO 연동
감사 로그 보존 정책 및 개인정보 파기 정책 적용
```

이 한계는 핵심 아이디어의 결함이 아니라, 공공 API 접근권한과 운영 데이터 확보 이후의 서비스화 과제다. LifePass v5.1은 대회 심사에서 기술적 가능성과 실제 운영 구조를 동시에 보여주는 competition-ready prototype을 목표로 한다.
