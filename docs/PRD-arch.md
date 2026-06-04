
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
│   │       ├── mock_client.py         # DEV 모드: PRD §3.3.3 고정 스펙 Mock JSON 반환
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

### 14.4. 프론트엔드 — 아토믹 디자인 패턴 기반 폴더 레이아웃

**설계 원칙**: Vite 빌드의 빠른 HMR을 살리면서, UI 컴포넌트는 원자 단위로 분리하고 비즈니스 로직과 API 통신은 `hooks` 레이어로 격리한다.

```
frontend/
├── src/
│   ├── assets/
│   │   ├── styles/
│   │   │   └── globals.css            # Tailwind 기본 설정 (@tailwind base/components/utilities)
│   │   └── fonts/
│   │
│   ├── components/                    # 아토믹 디자인 격리 레이어
│   │   ├── atoms/                     # [원자] 최소 단위 — 상태·로직 없음
│   │   │   ├── Badge.tsx              #   도메인 라벨 배지 (Security · Performance · 교차)
│   │   │   ├── Button.tsx             #   범용 버튼 (승인·거부·제출)
│   │   │   ├── Spinner.tsx            #   로딩 인디케이터
│   │   │   └── StatusDot.tsx          #   파이프라인 단계 상태 점 (PENDING/RUNNING/DONE)
│   │   │
│   │   ├── molecules/                 # [분자] 원자 2개 이상 조합 — 단일 책임
│   │   │   ├── PipelineStepIndicator.tsx   # StatusDot + 단계명 텍스트 조합
│   │   │   ├── MetadataForm.tsx            # 입력 필드 + 추론 신뢰도 배지 조합
│   │   │   └── DiffSummaryCard.tsx         # 승인 전 diff 요약 (신규 N개·업데이트 M개)
│   │   │
│   │   ├── organisms/                 # [유기체] 독립 가동 UI 블록 — 훅 결합 허용
│   │   │   ├── TopologyViewer.tsx     #   react-force-graph 래퍼
│   │   │   │                          #   가상 노드 미리보기: DRAFT=점선, COMMITTED=실선
│   │   │   ├── ConceptInspector.tsx   #   우측 사이드 패널 — 노드 상세·승인/거부 토글
│   │   │   ├── LogConsole.tsx         #   SSE 실시간 로그 스트림 출력 콘솔
│   │   │   └── ApprovalPanel.tsx      #   전체 승인·거부·diff 요약 패널
│   │   │
│   │   └── templates/                 # [템플릿] 레이아웃 골격 — 빈 슬롯 구조
│   │       └── DashboardLayout.tsx    #   사이드바 + 메인뷰 + 인스펙터 3-panel 레이아웃
│   │
│   ├── pages/                         # 라우팅 페이지 — 훅·유기체 결합점
│   │   └── MainPage.tsx               #   단일 SPA 페이지 (파이프라인 대시보드)
│   │
│   ├── hooks/                         # 비즈니스 로직·전역 상태 격리
│   │   ├── usePipelineSSE.ts          #   SSE 스트림 구독 → 파이프라인 단계 상태 업데이트
│   │   ├── useGraphMerge.ts           #   기존 Neo4j 노드 + DRAFT 노드 클라이언트 병합
│   │   │                              #   가상 토폴로지 데이터 생성 (DB 미접촉)
│   │   ├── useStagingApproval.ts      #   DRAFT 노드 목록 조회·개별 승인/거부·최종 승인 API
│   │   └── useDocumentInput.ts        #   URL 입력·메타데이터 Pre-scan 자동 추론 연동
│   │
│   ├── services/                      # Axios 기반 API 통신 추상화
│   │   ├── api.ts                     #   Axios 인스턴스·baseURL·인터셉터 설정
│   │   ├── pipelineService.ts         #   파이프라인 트리거·상태 조회 API
│   │   ├── stagingService.ts          #   스테이징 CRUD·승인·diff API
│   │   └── graphService.ts            #   토폴로지 조회 API
│   │
│   ├── types/                         # TypeScript 인터페이스·도메인 타입
│   │   ├── concept.ts                 #   ConceptNode, ConceptDomain, NodeLabel
│   │   ├── pipeline.ts                #   PipelineState, AgentStep, StagingRecord
│   │   └── graph.ts                   #   GraphNode, GraphEdge, VirtualNodeStyle
│   │
│   └── utils/                         # 순수 함수·데이터 파싱
│       ├── docId.ts                   #   build_doc_id 클라이언트 사이드 구현 (표시용)
│       └── nodeStyler.ts             #   노드 상태별 시각 스타일 결정 함수
│                                      #   (DRAFT=점선, COMMITTED=실선, REJECTED=빨간 테두리)
│
├── nginx.conf                         # 프로덕션 Nginx 설정 (SPA fallback, gzip, cache)
├── Dockerfile                         # Multi-stage: node build → nginx serve
├── package.json
└── vite.config.ts                     # 빌드 도구 설정 (path alias, proxy dev server)
```

**아토믹 레이어별 책임 구분**:

| 레이어 | 상태 보유 | 훅 사용 | API 호출 | 범위 |
|--------|-----------|---------|----------|------|
| atoms | 불가 | 불가 | 불가 | 스타일·렌더링만 |
| molecules | 로컬 UI 상태만 | 불가 | 불가 | 원자 조합 |
| organisms | 가능 | 가능 | hooks 통해서만 | 독립 UI 블록 |
| templates | 불가 | 불가 | 불가 | 레이아웃 슬롯 |
| pages | 가능 | 가능 | services 통해서만 | 라우팅 조합점 |

**`useGraphMerge.ts` 핵심 동작** (SDD 스펙):

```typescript
// Arrange: 두 데이터 소스 로드
const confirmedNodes = await graphService.getTopology()     // GET /api/graph/topology
const draftNodes = await stagingService.getDraft(sessionId) // GET /api/staging/{id}

// Act: 클라이언트 사이드 가상 병합 (DB 미접촉)
const merged = mergeVirtualGraph(confirmedNodes, draftNodes)
// merged 내 DRAFT 노드: strokeDasharray=true, opacity=0.65
// merged 내 SAME_AS 후보: badge="병합 예정"

// Assert (렌더 결과 테스트): 
// - DRAFT 노드 count === draftNodes.length
// - COMMITTED 노드 style.opacity === 1
```

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