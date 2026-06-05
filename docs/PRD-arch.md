## 14. 시스템 아키텍처 및 표준 폴더 레이아웃

### 14.1. 아키텍처 설계 원칙 — PRD에 포함하는 3가지 이유

| 이유 | 설명 |
|------|------|
| 테스트 경계 시각화 | 어떤 레이어가 어느 테스트 파일로 커버되는지 레이어-테스트 매핑이 명확해야 TDD가 가능하다 |
| SDD 스펙 도출 근거 | 폴더 구조는 곧 유즈케이스 목록이다. `usecases/run_pipeline.py`, `usecases/approve_staging.py`가 PRD 요구사항과 1:1 대응됨을 보장한다 |
| 비동기 흐름 복잡성 통제 | FastAPI → BackgroundTask(PipelineTask) → dual-DB commit까지 이어지는 흐름에서 "어떤 레이어가 어느 경계를 넘는가"를 구조로 강제하면 레이스 컨디션 원인 파악이 즉각 가능하다 |

### 14.2. 고수준 컴포넌트 통신 흐름

> **v1 아키텍처**: Celery/Redis 미사용. `FastAPI BackgroundTasks` + `PipelineTask` 프로토콜로 비동기 처리.
> v2에서 처리량이 10개/세션을 초과하면 Celery+Redis로 교체 가능하도록 `PipelineTask` 인터페이스로 추상화.

```
[React :3000] ──REST/SSE──▶ [FastAPI :8000]
                                    │
                          BackgroundTasks.add_task()
                          (PipelineTask 프로토콜 구현체)
                                    │
                    ┌───────────────┼────────────────┐
                    ▼               ▼                 ▼
             HITL 승인 게이트  [pipeline_jobs]   asyncio.gather()
             (SELECT FOR        PostgreSQL        Semaphore(RPM)
              UPDATE SKIP       상태 기록              │
              LOCKED)                          ──LLM API──▶ [Gemini 2.5 Flash]
                    │                          ──@traceable─▶ [LangSmith]
                    ▼
           [PostgreSQL UPSERT]
                    │  커밋 성공 후
                    ▼
            [Neo4j MERGE]       ← 실패 시 startup reconciliation 재처리
```

**컴포넌트별 통신 방식** (v1):

| 송신 | 수신 | 방식 | 방향 |
|------|------|------|------|
| React | FastAPI | REST (JSON) + SSE (실시간 로그) | 양방향 |
| FastAPI | PipelineTask | `BackgroundTasks.add_task()` | 단방향 |
| PipelineTask | PostgreSQL | SQLAlchemy AsyncSession | 양방향 |
| PipelineTask | Neo4j | Neo4j Driver (MERGE Cypher) | 양방향 |
| PipelineTask | Gemini API | `asyncio.gather()` + Semaphore(RPM) | 단방향 |
| PipelineTask | LangSmith | `@traceable` SDK 래핑 | 단방향 (트레이싱) |
| FastAPI | LangSmith | `client.create_feedback()` (HITL 수정 시) | 단방향 |
| FastAPI (startup) | PostgreSQL | RUNNING 고아 잡 → FAILED 전환 (10분 초과) | 양방향 |

> **v2 마이그레이션 경로**: `PipelineTask` 프로토콜 구현체를 `CeleryPipelineTask`로 교환하면 Celery+Redis 전환 완료.
> `FastAPI → task.delay() → Celery Worker → Redis pub/sub → SSE` 패턴은 v2 스펙.

### 14.3. 백엔드 — 클린 아키텍처 기반 폴더 레이아웃

**의존성 규칙**: 의존성은 외부(`infrastructure`)에서 내부(`domain`)로만 향한다. 비즈니스 로직(에이전트 파이프라인 흐름, 승인 상태 전이)은 특정 DB 기술이나 프레임워크에 종속되지 않는다.

```
backend/
├── app/
│   ├── domain/                        # 레이어 1: 핵심 비즈니스 엔티티 (프레임워크 무관)
│   │   ├── models.py                  # 도메인 개념 모델 (순수 Python/Pydantic)
│   │   │                              #   Concept, Document, StagingRecord, PipelineState
│   │   └── pipeline.py                # 파이프라인 상태 전이 규칙
│   │                                  #   PENDING→CRAWLING→EXTRACTED→COMMITTED
│   │
│   ├── usecases/                      # 레이어 2: 애플리케이션 흐름 (도메인↔인프라 중계)
│   │   ├── run_pipeline.py            # 에이전트 5단계 파이프라인 구동 유즈케이스
│   │   ├── approve_staging.py         # 스테이징 DRAFT→APPROVED→COMMITTED 유즈케이스
│   │   │                              #   4대 커밋 규칙 (§11) 실행 주체
│   │   └── interfaces/                # 의존성 역전 추상 인터페이스 (DIP)
│   │       ├── repository.py          #   PostgreSQL 접근 추상 (구현은 infra에서)
│   │       └── graph_service.py       #   Neo4j 접근 추상 (구현은 infra에서)
│   │
│   ├── infrastructure/                # 레이어 3: 외부 저수준 인프라 구현체
│   │   ├── database/
│   │   │   ├── pg_repository.py       # SQLAlchemy AsyncSession 구현체
│   │   │   └── migrations/            # Alembic 마이그레이션 파일
│   │   ├── graph/
│   │   │   ├── neo4j_service.py       # Neo4j Driver + Cypher 쿼리 구현체
│   │   │   └── cypher/                # .cypher 쿼리 파일 (MERGE 템플릿)
│   │   ├── queue/
│   │   │   ├── celery_app.py          # Celery 앱 인스턴스 및 설정
│   │   │   └── tasks/                 # 에이전트별 비동기 태스크
│   │   │       ├── crawler_task.py
│   │   │       ├── extractor_task.py
│   │   │       ├── writer_task.py
│   │   │       └── resolver_task.py
│   │   └── llm/
│   │       ├── interface.py           # LLM 추상 인터페이스 (ILLMClient) — DIP 기반
│   │       ├── gemini_client.py       # PROD 모드: Gemini 2.5 Flash + LangSmith 활성화
│   │       ├── mock_client.py         # DEV 모드: PRD-domain §3.3.3 고정 스펙 Mock JSON 반환
│   │       └── factory.py             # APP_MODE 플래그 기반 클라이언트 선택 팩토리
│   │
│   └── interfaces/                    # 레이어 4: HTTP 진입점 (컨트롤러)
│       ├── api/
│       │   ├── pipeline.py            # POST /api/pipeline/trigger
│       │   ├── staging.py             # GET·PATCH·POST /api/staging/{session_id}
│       │   └── graph.py               # GET /api/graph/topology
│       └── schemas/
│           ├── request.py             # HTTP Request DTO (Pydantic)
│           └── response.py            # HTTP Response DTO (Pydantic)
│
├── config/
│   ├── settings.py                    # pydantic-settings 환경변수 바인딩
│   └── logging.py                     # 구조화 로깅 설정
│
├── scripts/
│   └── seed/                          # § 9 형상 관리 정책 대상 스크립트 디렉토리
│       ├── security/
│       │   ├── schema.sql
│       │   ├── seed_data.sql
│       │   └── seed_data.cypher
│       ├── performance/
│       │   ├── perf_antipattern_schema.sql
│       │   ├── perf_seed_data.sql
│       │   └── perf_seed_data.cypher
│       └── verify_seed.py
│
├── tests/
│   └── harness/                       # § 10 QA 테스트 하네스 (레이어 A~D)
│       ├── conftest.py                #   픽스처: db_session · neo4j_session · celery_app
│       ├── test_utils.py              #   레이어 A: T01·T02 (doc_id 멱등성)
│       ├── test_db_migration.py       #   레이어 B: T03·T04 (DB 멱등성)
│       ├── test_pipeline_gate.py      #   레이어 C: T05·T06 (비동기 격리)
│       └── test_llm_eval.py           #   레이어 D: T07·T08 (LLM 품질)
│
├── langsmith_datasets/
│   ├── extractor_schema_eval/         # Pre-Eval 골든 데이터셋
│   │   ├── golden_inputs/
│   │   └── expected_outputs/
│   └── translation_eval/
│       └── en_ko_pairs/
│
├── Dockerfile
├── requirements.txt
└── .env.example
```

**레이어-테스트 경계 매핑**:

| 레이어 | 테스트 파일 | 검증 방식 | 인프라 의존 |
|--------|------------|-----------|-------------|
| `domain` | `test_utils.py` (레이어 A) | 순수 함수 단위 테스트 | 없음 |
| `usecases` + `infrastructure` (DB) | `test_db_migration.py` (레이어 B) | 격리 컨테이너 실물 DB | PostgreSQL, Neo4j |
| `usecases` + `infrastructure` (queue) | `test_pipeline_gate.py` (레이어 C) | `ALWAYS_EAGER` 동기화 | PostgreSQL, Neo4j, Redis |
| `infrastructure/llm` | `test_llm_eval.py` (레이어 D) | Pydantic 검증 + SDK Mock | LangSmith Mock |
### 14.5. 루트 모노레포 레이아웃

```
project-root/
├── backend/                   # §14.3 백엔드 클린 아키텍처 루트
├── frontend/                  # §14.4 프론트엔드 아토믹 디자인 루트
├── infra/
│   ├── docker-compose.yml     # §5.2 애플리케이션 3-서비스 컴포즈
│   ├── .env.local             # 로컬 외부 컨테이너 환경변수
│   └── .env.prod              # GCP Cloud SQL Auth Proxy 환경변수
├── docs/
│   └── PRD_Knowledge_Graph_Agent.md   # 본 문서
└── .github/
    └── workflows/             # CI: pytest → LangSmith Pre-Eval → Docker build
```

---

## 15. 시스템 다이어그램 명세 (Diagram Specifications)

### 15.1. 고수준 시스템 아키텍처 — 레이어 경계 요약

```
┌─────────────────────────────────────────────────────────────┐
│  프론트엔드 레이어 (React · Vite · Atomic Design)            │
│  atoms/molecules → organisms → hooks/services → pages       │
└────────────────────────┬────────────────────────────────────┘
                         │ REST / SSE
┌────────────────────────▼────────────────────────────────────┐
│  백엔드 레이어 (FastAPI · Clean Architecture)                │
│  interfaces → usecases → domain  ◀── 의존성 역전(DIP)       │
│  └── infrastructure (database · graph · queue · llm)        │
└──────────────────┬──────────────────────────────────────────┘
                   │ task.delay()
┌──────────────────▼──────────────────────────────────────────┐
│  Celery Worker 레이어 — 5단계 파이프라인                      │
│  Input → Crawler → Extractor → Graph Writer → Link Resolver │
│                    ↓ 최종 승인 게이트 (HITL)                  │
│                    4대 커밋 규칙 (①②③④) 원자 실행             │
└──────────┬──────────────────────┬───────────────────────────┘
           │                      │
  ┌────────▼──────────┐  ┌────────▼──────────────────────────┐
  │  외부 인프라       │  │  외부 서비스                       │
  │  PostgreSQL       │  │  Gemini 2.5 Flash (LLM API)       │
  │  Neo4j            │  │  LangSmith (@traceable · Pre-Eval) │
  │  Redis            │  └───────────────────────────────────┘
  └───────────────────┘
  env 교체만으로 로컬↔GCP 전환
```