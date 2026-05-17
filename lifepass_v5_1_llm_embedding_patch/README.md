# LifePass AI Agent v5

## Policy Intelligence & Welfare Operations Platform

LifePass AI Agent v5는 복지 혜택을 단순 추천하는 데모 앱이 아니라, **정책 데이터 수집, 시민 프로필 구조화, 자격 판정, 최적 혜택 조합, 신청 워크플로우, 정책 변경 영향 시뮬레이션, 감사 로그, 개인정보 보호 운영**까지 하나의 흐름으로 연결하는 AI Agent 기반 복지 운영 플랫폼이다.

본 프로젝트의 핵심 방향은 명확하다. 복지 사각지대는 혜택이 존재하지 않아서만 발생하지 않는다. 사용자가 자신의 상황에 맞는 제도를 알지 못하고, 정책 조건이 복잡하며, 신청 시점과 서류 준비를 놓치고, 생애전환 시점에 기존 혜택 상실과 신규 혜택 발생을 동시에 관리하지 못하기 때문에 발생한다. LifePass는 이 문제를 **AI Agent + deterministic rule engine + 운영형 DBMS + 정책 Digital Twin**으로 해결한다.

---

## 1. 실행 방법

### 1.1 운영형 DBMS 포함 실행 권장

대회 시연 및 심사 환경에서는 PostgreSQL, pgvector, Redis, FastAPI, Streamlit을 함께 실행하는 Docker Compose 모드를 권장한다.

```bash
cd lifepass_agent_v5
docker compose up -d --build
```

실행 후 접속 주소는 다음과 같다.

```text
Streamlit Dashboard: http://localhost:8501
FastAPI OpenAPI Docs: http://localhost:8000/docs
PostgreSQL + pgvector: localhost:5432
Redis Event Queue: localhost:6379
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

### 1.2 빠른 로컬 실행

로컬 화면 검증만 필요한 경우 다음 명령으로 실행할 수 있다.

```bash
pip install -r requirements.txt
streamlit run app.py
```

단, 이 방식은 빠른 MVP 실행용이며 PostgreSQL/pgvector/Redis 기반 운영 구조를 함께 보여주기에는 Docker Compose 모드가 더 적합하다.

### 1.3 검증

```bash
python -m py_compile app.py api.py core/*.py cli_demo.py tests/verify_mvp.py
python tests/verify_mvp.py
```

검증 스크립트는 룰엔진, 자연어 파싱, 최적화, 정책 수집, 신뢰성 감사, v4 운영 기능, v5 이벤트/정책트윈/보안/인과/품질 운영 기능을 확인한다.

---

## 2. 심사 포인트 요약

LifePass v5는 다음 다섯 가지 차별점을 중심으로 평가될 수 있다.

### 2.1 입력 장벽을 낮춘 AI 상담형 온보딩

사용자는 긴 행정 입력폼을 처음부터 작성하지 않아도 된다. 자연어 문장 입력을 통해 나이, 지역, 가구원 수, 소득, 주거비, 실업급여 잔여일, 예상 소득 변화 같은 정보를 구조화된 `UserProfile`로 변환한다. 자연어 파싱 결과는 구조화 입력폼에서 다시 수정할 수 있으며, JSON 업로드와 CSV 일괄 업로드도 지원한다.

### 2.2 LLM-only 판정을 배제한 deterministic eligibility engine

복지 자격 판정은 환각 가능성이 있는 LLM에 맡기지 않는다. 정책 조건은 JSON rule schema로 관리되며, 실제 자격 판정은 deterministic rule engine이 수행한다. LLM 또는 Agent는 설명, 요약, 상담 흐름 보조, 신청 전략 생성에 사용되는 구조로 설계했다.

### 2.3 추천에서 신청 완료까지 이어지는 운영형 플랫폼

단순히 받을 수 있는 혜택 목록을 보여주는 데서 끝나지 않는다. 상호배타 혜택 충돌을 제거하고, 월 환산 효과와 긴급도, 마감일, 신청 난이도를 고려한 최적 조합을 산출하며, 신청 태스크와 서류 체크리스트, 마감 리마인더를 생성한다.

### 2.4 PostgreSQL + pgvector + Redis 기반 운영 구조

v5는 Docker Compose로 Streamlit UI, FastAPI API 서버, PostgreSQL + pgvector DBMS, Redis event queue를 함께 실행할 수 있다. PostgreSQL은 사용자 프로필, 정책 카탈로그, agent run, application workflow, audit log, event outbox 저장소로 설계되며, pgvector는 정책 문서 chunk embedding 검색에 대응한다.

### 2.5 정책 Digital Twin과 Responsible AI 운영

정책 변경이 실제로 시행되기 전, 연령 기준이나 지원액 변화가 사용자군과 예산에 미치는 영향을 사전 시뮬레이션한다. 또한 purpose-based access control, differential privacy 집계, synthetic data, audit log, model card, data contract, incident playbook을 포함하여 공공·복지 영역에서 필요한 신뢰성 운영 체계를 갖췄다.

---

## 3. v5에서 추가된 고급 기술

### 3.1 Event Mesh + Transactional Outbox

사용자 프로필 변경, 주거 계약 검증, 혜택 판정 요청, 마감 위험 감지, 생애전환 신호를 event envelope로 생성한다. 각 event는 idempotency key, routing key, schema version, trace id를 포함한다. Outbox table 설계를 통해 API 요청과 이벤트 발행 사이의 불일치를 줄이는 구조를 제시한다.

시연 위치:

```text
v5 실시간·정책트윈 → 이벤트 envelope → Transactional outbox → Event consumer topology
```

### 3.2 Policy Digital Twin

정책 변경이 시행되기 전 영향받는 사용자 수, 신규 지원 가능자, 월/연 예산 변화, 개인별 지원 변화량을 계산한다. 예를 들어 청년 정책 연령 상한을 34세에서 39세로 확장하거나 지원액을 1.2배로 조정했을 때 사용자군과 예산에 미치는 영향을 즉시 확인할 수 있다.

시연 위치:

```text
v5 실시간·정책트윈 → 정책 Digital Twin
```

### 3.3 Zero-Trust Access Control

역할 기반 접근통제(RBAC)와 목적 기반 필드 접근통제(ABAC)를 함께 적용한다. 예를 들어 상담사는 자격 판정 목적에 필요한 최소 필드만 조회할 수 있고, 감사자는 개별 민감정보가 아니라 마스킹된 감사용 정보만 접근하도록 설계된다.

시연 위치:

```text
v5 보안·인과·품질 → Access-control interactive check
```

### 3.4 Differential Privacy Aggregate Release

지역별 통계나 정책 영향 통계처럼 외부 공개 가능성이 있는 집계에는 privacy budget ledger와 DP count demo를 적용한다. 개별 상담 큐나 고위험 개인 목록은 DP 공개 대상이 아니라 차단 대상으로 구분한다.

시연 위치:

```text
v5 보안·인과·품질 → Privacy budget ledger
```

### 3.5 Synthetic Data for Demo and Testing

실제 개인정보 없이도 테스트와 시연이 가능하도록 seed profile 주변의 비식별 synthetic profile을 생성한다. 이 데이터는 데모와 품질 검증에 사용되며 실제 개인을 재식별하지 않는 운영 원칙을 따른다.

### 3.6 Causal Intervention Ranking

혜택 추천만으로는 신청 완료율을 높이기 어렵다. v5는 상담사 1:1 동행, 서류 체크리스트 발송, 마감 리마인더, 근로·훈련 연계 안내 같은 개입 액션을 uplift·비용·ROI proxy 기준으로 정렬한다. 실제 운영 데이터가 축적되면 이 구조는 uplift model, A/B test, doubly robust estimator로 확장될 수 있다.

### 3.7 Data Contract + Model Card + Incident Playbook

외부 CSV 업로드와 API 연동에서 필요한 데이터 계약을 정의하고, 모델/룰엔진의 사용 가능 범위와 금지 범위를 model card로 명시한다. 또한 정책 API 실패, human review rate 급증, 충돌 위반 발생, DB latency 증가 같은 운영 신호에 대한 incident playbook을 제공한다.

---

## 4. 시스템 아키텍처

```text
[Streamlit Dashboard]
    ├─ 자연어 온보딩 / 구조화 프로필 입력 / JSON 업로드
    ├─ CSV 일괄분석 / Smart Data Mapper
    ├─ Agent Workflow Trace / Human Review Queue
    ├─ Policy Digital Twin / Impact Simulation
    ├─ Security·Privacy·Causal Ops / Quality Ops
    ↓
[FastAPI Backend]
    ├─ /api/v1/analyze
    ├─ /api/v1/batch/analyze
    ├─ /api/v1/policies/search
    ├─ /api/v1/agent/workflow
    ├─ /api/v1/events/simulate
    ├─ /api/v1/policy/digital-twin
    ├─ /api/v1/security/access-check
    ├─ /api/v1/privacy/pack
    ├─ /api/v1/causal/interventions
    └─ /api/v1/quality/ops
    ↓
[Core Intelligence Layer]
    ├─ Rule Engine
    ├─ Conflict-aware Optimizer
    ├─ Smart Mapper
    ├─ Policy Ingestion
    ├─ Document Parser
    ├─ Vector Search-ready RAG
    ├─ Event Mesh / Outbox
    ├─ Policy Digital Twin
    ├─ Privacy/Security Pack
    └─ Causal Ops / Quality Ops
    ↓
[Operational Storage]
    ├─ PostgreSQL
    ├─ pgvector
    ├─ Redis
    └─ Local fallback artifacts
```

---

## 5. 주요 화면 구성

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

시연에서는 모든 화면을 길게 보여줄 필요가 없다. 시연은 다음 순서가 가장 효과적이다.

```text
자연어 온보딩
→ 현재 자격 판정
→ 최적 혜택 조합·신청 서류
→ 생애전환/복지절벽
→ Agent Workflow Trace
→ v5 Event Mesh
→ v5 Policy Digital Twin
→ v5 보안·인과·품질 운영
→ FastAPI /docs와 Docker Compose 운영 구조
```

---

## 6. REST API

Docker Compose 실행 후 다음 주소에서 OpenAPI 문서를 확인할 수 있다.

```text
http://localhost:8000/docs
```

대표 엔드포인트:

```text
GET  /health
POST /api/v1/analyze
POST /api/v1/batch/analyze
POST /api/v1/policies/preview
GET  /api/v1/policies/search
POST /api/v1/agent/workflow
POST /api/v1/portfolio/optimize
POST /api/v1/application/workflow
POST /api/v1/knowledge-graph
GET  /api/v1/evaluation/benchmark
POST /api/v1/events/simulate
POST /api/v1/policy/digital-twin
POST /api/v1/security/access-check
POST /api/v1/privacy/pack
POST /api/v1/causal/interventions
GET  /api/v1/quality/ops
```

예시:

```bash
curl -X POST http://localhost:8000/api/v1/analyze \
  -H "Content-Type: application/json" \
  -d '{"profile":{"age":27,"region":"서울","household_size":1,"monthly_income":0,"rent":550000,"unemployment_benefit_receiving":true,"unemployment_benefit_days_left":45}}'
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
audit_logs purpose/action/decision 저장
```

이 구조는 심사 환경에서 단순 파일 기반 데모가 아니라, 실제 지자체·복지기관·대학·공공서비스에 확장 가능한 운영형 저장소를 제시한다.

---

## 8. 기술 스택

```text
Frontend: Streamlit
API: FastAPI
DBMS: PostgreSQL
Vector Search Ready: pgvector
Event Queue: Redis-ready event mesh
Data Layer: pandas, JSON policy catalog
Agent: deterministic tool trace + human-in-the-loop workflow
Optimization: conflict-aware benefit optimizer + constraint-style portfolio solver
Policy Intelligence: public API gateway, document parser, policy version diff, policy digital twin
Security: RBAC/ABAC, purpose-based field access, audit log
Privacy: masking, synthetic data, differential privacy aggregate demo
Quality: benchmark suite, guardrails, data contract, model card, incident playbook
Deployment: Docker Compose
```

---

## 9. 한계와 확장 계획

본 버전은 실제 공공기관의 운영 API key 없이도 심사 환경에서 전체 파이프라인을 검증할 수 있도록 fallback sample과 local policy catalog를 포함한다. 실제 서비스화 단계에서는 다음 확장이 필요하다.

```text
복지로·정부24·고용24·지자체 공고 API의 실제 운영 키 연결
정책 문서 embedding 생성 및 pgvector 검색 인덱스 활성화
상담사 계정/권한/배정 로직 고도화
실제 신청 결과 데이터를 통한 uplift model 학습
기관별 멀티테넌트 배포와 SSO 연동
감사 로그 보존 정책 및 개인정보 파기 정책 적용
```

이 한계는 핵심 아이디어의 결함이 아니라, 공공 API 접근권한과 운영 데이터 확보 이후의 서비스화 과제에 해당한다. v5는 대회 심사에서 기술적 가능성과 실제 운영 구조를 동시에 보여주는 competition-ready prototype을 목표로 한다.

## v5.1 Embedding RAG + Bounded LLM 설명 계층

LifePass v5.1은 정책 검색과 상담 설명 계층을 분리해 AI 활용 위치를 명확히 제한한다. 자격 판정은 여전히 `core/rule_engine.py`의 deterministic rule engine이 수행하며, 임베딩 모델은 정책 카탈로그·근거 문서 검색에만 사용된다. LLM은 검색된 근거와 룰엔진 판정 결과를 기반으로 쉬운 상담 문장, 서류 안내, 정책 요약을 생성하는 보조 계층으로만 배치된다. 이 설계는 복지·공공 행정 도메인에서 생성형 AI가 자격 여부를 임의로 만들어내는 위험을 줄이고, 설명 가능성과 감사 가능성을 유지하기 위한 구조이다.

기본 실행은 API 키가 없어도 동작한다. 기본값은 `LIFEPASS_EMBEDDING_PROVIDER=local_hash`, `LIFEPASS_LLM_PROVIDER=template`이며, 이 모드에서는 네트워크 호출 없이 로컬 벡터 fallback과 deterministic template 설명을 사용한다. 실제 임베딩·LLM 모델을 연결하려면 `.env` 또는 Docker Compose 환경변수에 `OPENAI_API_KEY`, `LIFEPASS_EMBEDDING_PROVIDER=openai`, `LIFEPASS_EMBEDDING_MODEL=text-embedding-3-small`, `LIFEPASS_LLM_PROVIDER=openai`, `LIFEPASS_LLM_MODEL=gpt-4o-mini`를 설정한다. 이 설정을 넣으면 `/api/v1/rag/search`는 embedding retrieval을 수행하고, `/api/v1/rag/ask`는 검색 근거와 rule engine 결과를 조합해 LLM 기반 상담 답변을 생성한다.

추가된 API는 다음과 같다. `GET /api/v1/rag/status`는 현재 임베딩·LLM provider 상태와 안전 경계를 반환한다. `GET /api/v1/rag/search?q=...`는 정책 카탈로그, 로컬 근거 문서, 정책 문서 chunk에서 의미 기반 검색 결과를 반환한다. `POST /api/v1/rag/ask`는 사용자 프로필과 질문을 받아 rule engine 판정, 최적화 결과, embedding RAG 근거, bounded LLM 설명을 하나의 패키지로 반환한다. Streamlit 대시보드의 `고급 AI/신뢰성` 탭에서도 같은 흐름을 시연할 수 있다.
