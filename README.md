# LifePass AI Agent v5.1

## 청년 복지 절벽 방지·생애전환 의사결정 플랫폼

LifePass는 사용자의 현재 상황과 앞으로의 변화를 함께 보고, 받을 수 있는 복지·고용·정책금융 제도를 찾아주는 프로젝트입니다.  
단순히 “지금 받을 수 있는 혜택 목록”만 보여주는 것이 아니라, 실업급여 종료, 소득 발생, 이사, 가구 변화처럼 시간이 지나며 달라지는 상황까지 계산합니다.

이 프로젝트의 핵심은 다음과 같습니다.

- 사용자의 말을 구조화된 프로필로 바꿉니다.
- 정책 조건을 코드로 판정합니다.
- 중복되거나 같이 받을 수 없는 혜택을 정리합니다.
- 3개월, 6개월, 12개월 뒤 자격 변화를 예측합니다.
- 신청 순서, 준비 서류, 마감 알림까지 이어지게 만듭니다.
- 정책 원문, 수집 시각, 변경 이력을 남길 수 있는 구조를 갖춥니다.

> 중요한 원칙: LLM은 자격 여부를 마음대로 결정하지 않습니다.  
> 실제 판정은 `core/rule_engine.py`의 규칙 기반 판정 코드가 맡고, LLM은 결과를 쉽게 설명하는 보조 역할만 합니다.

---

## 1. 이 프로젝트가 해결하려는 문제

복지 사각지대는 혜택이 없어서만 생기지 않습니다. 실제로는 아래 이유 때문에 자주 발생합니다.

- 어떤 제도가 있는지 모름
- 정책 조건이 복잡해서 내 상황에 맞는지 판단하기 어려움
- 신청 마감일과 준비 서류를 놓침
- 실업급여 종료, 취업, 소득 증가, 이사 같은 변화 이후에 받을 수 있는 제도가 달라짐
- 어떤 혜택은 동시에 받을 수 없는데, 그 관계를 사용자가 직접 알기 어려움

LifePass는 이 문제를 “상담 → 판정 → 조합 선택 → 미래 변화 예측 → 신청 관리” 흐름으로 해결하려는 프로젝트입니다.

---

## 2. 대상 사용자

1차 대상은 복지·고용·정책금융 제도의 영향을 크게 받지만, 제도 이해와 신청 타이밍 관리가 어려운 사람들입니다.

- 청년 1인가구
- 실직 청년
- 프리랜서
- 저소득 근로자
- 월세 부담이 큰 청년
- 실업급여 종료를 앞둔 사용자

---

## 3. 실행 방법

### 3.1 Docker Compose 실행

대회 시연이나 전체 구조 확인에는 Docker Compose 실행을 권장합니다.

```bash
cd lifepass
docker compose up -d --build
```

기본 접속 주소는 다음과 같습니다.

```text
Streamlit 화면: http://localhost:8503
FastAPI 문서:  http://localhost:8002/docs
PostgreSQL:    localhost:5433
Redis:         localhost:6380
```

상태 확인:

```bash
docker compose ps
```

로그 확인:

```bash
docker compose logs -f lifepass-ui
docker compose logs -f lifepass-api
```

종료:

```bash
docker compose down
```

### 3.2 빠른 로컬 실행

화면만 빠르게 보고 싶다면 다음 방식도 가능합니다.

```bash
pip install -r requirements.txt
streamlit run app.py
```

이 경우 기본 주소는 보통 다음과 같습니다.

```text
http://localhost:8501
```

---

## 4. `.env` 설정

프로젝트 루트에 `.env` 파일을 만들고 아래처럼 설정합니다.

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

기본 설정은 API 키가 없어도 동작하는 로컬 모드입니다. 실제 OpenAI API를 사용할 때만 아래 값을 바꿉니다.

```env
LIFEPASS_EMBEDDING_PROVIDER=openai
LIFEPASS_EMBEDDING_MODEL=text-embedding-3-small
LIFEPASS_LLM_PROVIDER=openai
LIFEPASS_LLM_MODEL=gpt-4o-mini
OPENAI_API_KEY=your_openai_api_key_here
```

보안 주의:

- 실제 API 키가 들어간 `.env`는 GitHub에 올리면 안 됩니다.
- 대회 제출 zip에도 `.env`를 넣지 않는 것이 안전합니다.
- 팀원에게 공유할 때는 `.env.example`만 공유하고, 실제 키는 각자 따로 설정하게 하는 것이 좋습니다.

---

## 5. 주요 기능

### 5.1 자연어 온보딩

사용자가 긴 입력폼을 처음부터 다 채우지 않아도 됩니다. 예를 들어 다음처럼 입력할 수 있습니다.

```text
저는 서울에 사는 27세 1인가구이고, 월소득은 없고, 월세는 55만 원입니다. 실업급여는 45일 남았습니다.
```

`core/profile_parser.py`가 이 문장을 나이, 지역, 소득, 월세, 실업급여 잔여일 같은 값으로 정리합니다.

### 5.2 규칙 기반 자격 판정

복지 자격은 LLM이 임의로 판단하지 않습니다.  
정책 조건은 `data/benefits.json`에 정리되어 있고, `core/rule_engine.py`가 조건을 하나씩 검사합니다.

예를 들어 다음 조건을 확인합니다.

- 나이가 조건에 맞는가?
- 지역이 조건에 맞는가?
- 월소득이 기준 이하인가?
- 1인가구인지 아닌지?
- 실업급여를 받고 있는지?

이 방식은 같은 입력이면 항상 같은 결과가 나오기 때문에, 심사와 설명에 유리합니다.

### 5.3 혜택 조합 최적화

받을 수 있는 혜택이 여러 개라도 모두 동시에 받을 수 있는 것은 아닙니다.  
`core/optimizer.py`와 `core/constraint_solver.py`는 같이 받을 수 없는 혜택을 정리하고, 실제로 신청 가능한 조합을 고릅니다.

### 5.4 생애전환·복지절벽 시뮬레이션

LifePass의 가장 큰 차별점입니다. 현재만 보는 것이 아니라, 앞으로의 변화까지 계산합니다.

예시:

- 실업급여가 45일 뒤 끝나는 경우
- 3개월 뒤 아르바이트를 시작하는 경우
- 월소득이 0원에서 80만 원, 140만 원으로 바뀌는 경우
- 월세가 오르거나 이사하는 경우

이때 어떤 혜택이 사라지고, 어떤 혜택이 새로 가능해지는지 보여줍니다.

### 5.5 정책 수집과 변경 이력 관리

실서비스화를 위해 정책 데이터의 출처와 변경 이력을 남길 수 있는 구조를 추가했습니다.

- 정책 원문 링크
- 데이터 수집 시각
- 정책 출처
- demo 데이터와 live 데이터 구분
- 정책 변경 전후 diff
- 사용자에게 보여줄 근거 문서 링크

관련 파일은 다음과 같습니다.

```text
core/public_api_clients.py
core/policy_ingestion.py
core/policy_provenance.py
core/policy_store.py
```

### 5.6 신청 관리와 운영자 검토

추천에서 끝나는 것이 아니라, 실제 신청 흐름으로 이어지도록 설계했습니다.

- 신청 case 생성
- 제출 상태 관리
- 운영자 검토 필요 표시
- 승인/반려 기록
- 검토 사유 저장

관련 파일:

```text
core/application_review.py
```

### 5.7 알림 outbox

마감 알림이나 상태 변경 알림을 바로 보내지 않고, 먼저 outbox에 쌓습니다.  
실서비스에서는 이 구조에 카카오 알림톡, 이메일, SMS 등을 붙일 수 있습니다.

관련 파일:

```text
core/notification_delivery.py
```

### 5.8 개인정보 동의와 접근 기록

사용자의 개인정보를 누가, 어떤 목적으로, 어떤 항목까지 보았는지 기록할 수 있게 했습니다.

관련 파일:

```text
core/privacy_audit.py
core/v5_privacy_security.py
```

---

## 6. 화면 구성

Streamlit 화면은 여러 탭으로 구성됩니다.

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
실서비스화
```

권장 시연 순서:

```text
자연어 온보딩
→ 현재 자격 판정
→ 최적 혜택 조합
→ 신청 서류 체크리스트
→ 생애전환/복지절벽 시뮬레이션
→ 정책 근거 검색
→ 정책 변경 영향 시뮬레이션
→ 운영자 검토/알림/개인정보 감사 구조
→ FastAPI 문서와 Docker Compose 구조
```

---

## 7. 주요 소스파일 설명

| 파일 | 쉽게 말하면 |
|---|---|
| `app.py` | 사용자가 보는 Streamlit 화면입니다. 입력, 결과, 시뮬레이션, 운영 기능을 탭으로 보여줍니다. |
| `api.py` | 외부 프로그램이나 화면이 LifePass 기능을 요청할 수 있게 해주는 FastAPI 서버입니다. |
| `cli_demo.py` | 웹 화면 없이 터미널에서 간단히 기능을 확인하는 실행 파일입니다. |
| `core/models.py` | 사용자 정보, 혜택 판정 결과, 시나리오 결과 같은 기본 데이터 형태를 정의합니다. |
| `core/profile_parser.py` | 사용자의 자연어 설명을 나이, 지역, 소득 같은 구조화된 값으로 바꿉니다. |
| `core/rule_engine.py` | 정책 조건을 하나씩 검사해서 사용자가 받을 수 있는지 판단합니다. |
| `core/optimizer.py` | 받을 수 있는 혜택 중 실제로 같이 신청하면 좋은 조합을 고릅니다. |
| `core/constraint_solver.py` | 동시에 받을 수 없는 혜택을 걸러내는 보조 계산 파일입니다. |
| `core/simulator.py` | 3개월, 6개월, 12개월 뒤 상황 변화를 계산합니다. |
| `core/whatif.py` | “소득이 바뀌면?”, “실업급여가 끝나면?” 같은 가정 실험을 합니다. |
| `core/public_api_clients.py` | 공공 정책 데이터를 가져오는 통로입니다. 실제 API가 없으면 샘플로도 실행됩니다. |
| `core/policy_ingestion.py` | 외부에서 가져온 정책 데이터를 프로젝트가 쓰기 좋은 형태로 정리합니다. |
| `core/policy_provenance.py` | 정책 데이터의 출처, 수집 시각, 원문 링크를 기록합니다. |
| `core/policy_store.py` | 정책 목록과 변경 이력을 저장하고, 업데이트 전후 차이를 계산합니다. |
| `core/embedding_rag.py` | 문서에서 질문과 관련 있는 근거를 찾는 기능입니다. |
| `core/llm_assistant.py` | 판정 결과를 사용자가 이해하기 쉬운 상담 문장으로 바꿉니다. |
| `core/auth_accounts.py` | 회원가입, 로그인, 권한 역할을 다루는 기본 인증 파일입니다. |
| `core/application_review.py` | 신청 case를 만들고 운영자가 승인/반려할 수 있게 관리합니다. |
| `core/notification_delivery.py` | 알림을 바로 보내지 않고 보낼 목록에 쌓아두는 파일입니다. |
| `core/privacy_audit.py` | 개인정보 동의와 접근 기록을 남깁니다. |
| `core/v5_event_mesh.py` | 사용자 상태 변화나 신청 이벤트를 일정한 형식으로 기록합니다. |
| `core/v5_policy_digital_twin.py` | 정책 기준이 바뀌었을 때 영향받는 사용자와 예산 변화를 미리 계산합니다. |
| `core/v5_privacy_security.py` | 권한, 마스킹, 가명 데이터 같은 보안·개인정보 보호 기능을 제공합니다. |
| `core/v5_causal_ops.py` | 어떤 개입이 효과적일지 비교하고, 운영 품질 문서를 제공합니다. |
| `infra/postgres/init.sql` | PostgreSQL 데이터베이스 테이블을 처음 만들 때 쓰는 SQL 파일입니다. |
| `scripts/ingest_policy_feed.py` | CSV 정책 파일을 읽어서 정책 카탈로그로 넣는 스크립트입니다. |
| `tests/verify_mvp.py` | 핵심 기능이 정상 동작하는지 확인하는 테스트 파일입니다. |
| `tests/verify_production_extensions.py` | 실서비스화 추가 기능이 정상 동작하는지 확인하는 테스트 파일입니다. |

---

## 8. FastAPI 주요 주소

Docker Compose 실행 후 아래 주소에서 API 문서를 볼 수 있습니다.

```text
http://localhost:8002/docs
```

대표 API:

| API | 역할 |
|---|---|
| `POST /api/v1/analyze` | 한 명의 사용자에 대해 자격 판정과 혜택 조합을 계산합니다. |
| `POST /api/v1/batch/analyze` | CSV로 여러 사용자를 한 번에 분석합니다. |
| `POST /api/v1/rag/ask` | 정책 근거를 찾아 상담 답변을 만듭니다. |
| `POST /api/v1/policy/digital-twin` | 정책이 바뀌었을 때 영향을 미리 계산합니다. |
| `POST /api/v1/policies/sync-all` | 정책 데이터를 가져오고 저장합니다. |
| `GET /api/v1/policies/sync-runs` | 정책 동기화 이력을 확인합니다. |
| `POST /api/v1/auth/login` | 로그인 토큰을 발급합니다. |
| `POST /api/v1/applications/cases` | 신청 case를 생성합니다. |
| `POST /api/v1/notifications/enqueue` | 알림을 보낼 목록에 추가합니다. |
| `POST /api/v1/privacy/consent` | 개인정보 동의 기록을 저장합니다. |

---

## 9. 검증 방법

아래 명령어로 기본 문법과 핵심 기능을 확인합니다.

```bash
python -m py_compile app.py api.py core/*.py cli_demo.py tests/verify_mvp.py
python tests/verify_mvp.py
python tests/verify_production_extensions.py
```

검증 범위:

- 정책 카탈로그 로딩
- 자연어 프로필 파싱
- 룰엔진 자격 판정
- 혜택 충돌 제거
- 생애전환 시뮬레이션
- RAG/상담 답변
- 정책 수집·출처·변경 이력
- 인증/신청 관리/알림/개인정보 감사

---

## 10. 기술 용어를 쉽게 풀어쓴 설명

| 용어 | 쉬운 설명 |
|---|---|
| LLM | ChatGPT 같은 큰 언어 모델입니다. 이 프로젝트에서는 설명문을 만드는 보조 역할입니다. |
| RAG | 답을 그냥 지어내지 않고, 문서에서 근거를 찾아 답하게 하는 방식입니다. |
| deterministic rule engine | 같은 입력이면 항상 같은 결과를 내는 규칙 기반 판정 코드입니다. |
| optimizer | 여러 선택지 중 더 좋은 조합을 고르는 계산 로직입니다. |
| policy digital twin | 실제 정책을 바꾸기 전에 가상으로 바꿔 보고 영향을 미리 계산하는 기능입니다. |
| provenance | 데이터가 어디서 왔는지, 언제 가져왔는지 남기는 기록입니다. |
| diff | 바뀌기 전과 바뀐 후의 차이입니다. |
| outbox | 바로 보내지 않고, 나중에 처리할 작업을 쌓아두는 목록입니다. |
| pgvector | PostgreSQL에서 문서 의미 검색을 하기 위한 확장 기능입니다. |
| Redis | 빠른 작업 큐나 임시 저장소로 쓰는 프로그램입니다. |

---

## 11. 현재 한계와 앞으로 보완할 점

현재 버전은 대회 시연과 MVP 검증을 위한 구조가 잘 갖춰져 있습니다. 다만 실제 서비스로 운영하려면 아래 보완이 필요합니다.

- 실제 복지로·정부24·고용24·지자체 API 키 연결
- 정책 원문 문서 수집 자동화
- PostgreSQL/Redis를 모든 기능에 더 깊게 연결
- 기관별 사용자 계정과 권한 관리 고도화
- 카카오 알림톡, 이메일, SMS 실제 발송 연결
- 실제 신청 결과 데이터를 기반으로 추천 효과 검증
- 운영 환경의 HTTPS, 비밀키 관리, 접근 제한 설정

---

## 12. 발표용 한 줄 설명

LifePass는 청년의 현재 조건과 앞으로의 생애 변화를 함께 분석해, 받을 수 있는 복지 제도와 신청 순서를 근거 기반으로 안내하는 AI Agent형 복지 운영 플랫폼입니다.
