# CLAUDE.md — 사내 지식 관리 + 신입 개발자 온보딩 플랫폼 (팀 전역 지침)

**PRD 버전**: v2.0 | **기준**: Module 0~5 | **팀**: 6명 (FE 1 + 서비스 5)

이 파일은 AI 에이전트(Claude)가 이 프로젝트에서 코드를 작성하거나 설계할 때
따라야 할 **팀 전역 규칙**이다. Module 0~5 모두에 적용된다.

> **Module 0 (KMS 파이프라인) 세부 구현 규칙**은 `src/module_0_kms/CLAUDE.md`를 참조한다.  
> **세부 Agent/Contract/State 규칙**은 `docs/` 폴더 문서를 참조한다 (섹션 16).

---

## 1. 제품 한 줄 정의

> 사내 지식을 AI가 자동 구조화하고, 신입 개발자의 코드 리뷰·학습 경로를 자동화하는 멀티 에이전트 플랫폼.

두 가지 목표:
- **KMS**: PDF·DOCX·PPTX·TXT → Markdown 정규화 → 구조화 저장 → 자연어 검색
- **온보딩**: KMS 지식 활용 → PR 자동 코드 리뷰 → 맞춤형 학습 추천 → 성장 추적

---

## 2. Clean Architecture 레이어

이 프로젝트의 의존성 방향은 항상 안쪽(도메인)을 향한다.

```
[Frameworks & Drivers]        LangGraph, FastAPI, PostgreSQL, pgVector, Neo4j, GitHub API, Slack
        ↑ depends on
[Interface Adapters]          API 계약 JSON, Repository 구현체, Webhook 핸들러
        ↑ depends on
[Use Cases / Application]     각 에이전트 로직 (Orchestrator, KMS, Static Analysis, Eval, Curriculum)
        ↑ depends on
[Entities / Domain]           User, Document, Chunk, PRReview, MistakePattern, AgentTrace
```

### 레이어 규칙

- **상위 레이어가 하위 레이어를 직접 import하지 않는다.** 의존성은 인터페이스(추상)를 통해서만.
- **각 에이전트는 Output Contract JSON을 준수해야 한다.** (섹션 5 참고)
- **DB 접근은 Repository 패턴으로 래핑한다.** 에이전트 코드에 SQL/ORM이 직접 노출되지 않는다.
- **비즈니스 로직은 LangGraph 노드 함수 안에 위치한다.** FastAPI 라우터는 Webhook 수신과 응답 직렬화만 담당.

### 도메인 엔티티 (Entities)

```python
# 모든 DB 엔티티는 이 공통 키 구조를 포함해야 한다
class CommonKey:
    doc_id: UUID          # 문서 단위 공통 키
    chunk_id: UUID        # 청크 단위 공통 키
    parent_chunk_id: UUID | None
    trace_id: str         # "trc_0001" ~ "trc_0006" (문서 파이프라인)
    source: str           # "notion | confluence | slack | upload"
    created_at: datetime
    status: str           # "processing | validated | stored | failed"
```

---

## 3. Harness Engineering (LangSmith)

모든 에이전트 실행은 LangSmith로 추적한다. 예외 없음.

### 필수 환경변수

```bash
LANGCHAIN_TRACING_V2=true
LANGCHAIN_API_KEY=ls__xxxx          # 팀 공용 키 또는 개인 키
LANGCHAIN_PROJECT=onboarding-dev1   # DEV별로 분리 (통합 시 onboarding-platform으로 교체)
```

### Trace ID 체계

```
PR 리뷰 파이프라인 (Module 1~4):
  pr_{12자리 hex}                             각 PR 처리마다 새로 생성
  예시: pr_3a9f1c2b44e0

병렬 에이전트 서브 trace (Module 2/3):
  {parent_trace_id}_{agent_name}_{4자리 hex}
  예시: pr_3a9f1c2b44e0_static_analysis_a1b2

Module 5 (독립 GraphDB):
  graph_{12자리 hex}                          문서 처리마다 새로 생성
```

> Module 0 (KMS 문서 파이프라인) trace ID 체계 (trc_0001~0006)는
> `src/module_0_kms/CLAUDE.md`를 참조한다.

### LangSmith 연동 패턴

```python
# LangGraph + LangSmith 자동 추적 (코드 변경 없음, 환경변수만 설정)
from langchain_core.callbacks import LangChainTracer

tracer = LangChainTracer(project_name=os.getenv("LANGCHAIN_PROJECT"))

# StateGraph 실행 시 config에 callbacks 추가
result = graph.invoke(state, config={"callbacks": [tracer]})
```

### PostgreSQL agent_traces 로깅 (LangSmith와 별개로 필수)

```python
# 모든 에이전트 시작/종료 시 동기적으로 기록
# task_id: PR 리뷰 파이프라인 → PRReviewState.task_id (UUID)
#          문서 파이프라인     → None
{
    "trace_id": "trc_0001",
    "task_id": "uuid | null",
    "agent_name": "MarkdownConverterAgent",
    "doc_id": "uuid | null",
    "status": "success | fail | review",
    "started_at": "ISO8601",
    "ended_at": "ISO8601",
    "execution_ms": 1200,
    "error_message": "if any, else null"
}
```

### 프로젝트별 LangSmith 네이밍

| 개발 단계 | LANGCHAIN_PROJECT 값 |
|-----------|----------------------|
| Week 2~3 (개발 중) | `module{N}-{yourGitHubId}` (개인별 분리 필수) |
| Week 5 (통합) | `onboarding-platform-integrated` |
| 데모 | `onboarding-platform-demo` |

> ⚠️ **모듈명 + GitHub ID 필수** — `module2-orchestrator` 처럼 역할명만 쓰면
> 팀원 trace가 같은 LangSmith 프로젝트에 섞인다.
> 반드시 `module2-alice`, `module3-bob` 처럼 본인 GitHub ID를 붙인다.
>
> ```bash
> # .env 예시 (본인 모듈 번호 + GitHub ID로 교체)
> LANGCHAIN_PROJECT=module2-yourGitHubId
> ```

---

## 4. MAS 패턴 & 모듈별 책임

> 세부 입출력 계약은 `docs/MODULE_CONTRACT.md`를 참조한다.

### 시스템 흐름

```
GitHub Webhook
    │
    ▼
[Module 1: Orchestrator]  ──── KMS 컨텍스트 검색 (Module 0 pgVector)
    │
    ├── asyncio.gather([
    │       Module 2: 정적분석 + 보안,
    │       Module 3: 테스트 + 성능
    │   ])
    │
    ▼
[Module 4: 커리큘럼 에이전트]
    ├── 3-Way 판정 (lgtm / rework / escalate)
    ├── GitHub 코멘트 작성
    └── Slack 에스컬레이션 (Critical 시)

[Module 5: GraphDB + YouTube]  ← 독립 실행 (Module 1~4와 현재 분리)
```

### Module 0: KMS 사내 지식 파이프라인

- **MAS 패턴**: Sequential Pipeline (Stage 1~6)
- **책임**: 사내 문서 → Markdown 변환 → 검증 → 청킹 → 메타데이터 → pgVector/PostgreSQL/Neo4j 저장
- **역할**: 전체 서비스의 지식 저장소 — 다른 모듈이 KMS 검색 결과를 사용
- **세부 규칙**: `src/module_0_kms/CLAUDE.md` 참조
- **의존 데이터**: `documents`, `chunks`, `chunk_embeddings`, `agent_traces`

### Module 1: 오케스트레이터

- **MAS 패턴**: Supervisor (LangGraph StateGraph)
- **책임**: Webhook 수신 → 의도 분류 → Module 2/3 병렬 호출 → 결과 취합 → Module 4 전달
- **필수 구현**:
  - GitHub Webhook HMAC-SHA256 서명 검증 (X-Hub-Signature-256 없으면 403)
  - 의도 분류: PR 리뷰 / KMS 질의 / 온보딩 / 아키텍처 질문
  - pgVector 코사인 유사도 검색 (KMS 컨텍스트 조회)
  - `users` 테이블에서 개발자 프로파일 조회 (없으면 skill_level="junior" 기본값)
- **의존 데이터**: `chunk_embeddings`(pgVector), `users`, `pr_reviews`

### Module 2: 정적 분석 + 보안 분석

- **MAS 패턴**: Parallel Independent Agent (asyncio.gather, 타임아웃 30초)
- **책임**: ESLint/Pylint 실행, 순환복잡도, SQL 인젝션/XSS/CSRF 탐지, CVE 스캔
- **타임아웃**: 30초 (초과 시 빈 결과로 대체, 파이프라인 중단 없음)
- **출력**: `AgentResult` Output Contract (섹션 5-A 참고)
- **KMS 활용**: 코딩 컨벤션, 보안 가이드 chunk 조회

### Module 3: 테스트 검증 + 성능 분석

- **MAS 패턴**: Parallel Independent Agent (asyncio.gather, 타임아웃 30초)
- **책임**: 커버리지 측정(80% 미달 시 Major), N+1 쿼리 감지, 시간복잡도 추정
- **타임아웃**: 30초
- **출력**: `AgentResult` Output Contract (섹션 5-A 참고)
- **KMS 활용**: 테스트 가이드, 성능 패턴 chunk 조회

### Module 4: 커리큘럼 에이전트 (Evaluator + Feedback Loop)

- **MAS 패턴**: Aggregator + Conditional Router (LangGraph conditional_edges)
- **책임**: Module 2/3 결과 취합 → 3-Way 판정 → 개인화 피드백 → GitHub 코멘트 + Slack
- **3-Way 판정 로직 (고정 규칙, LLM 임의 변경 금지)**:
  ```
  Critical ≥ 1  → escalate  (Slack 즉시 알림)
  Major ≥ 3     → rework    (힌트 포함, 최대 3회 리트라이)
  나머지         → lgtm      (시니어 최종 승인 요청)
  ```
- **의존 데이터**: `users`(skill_level), Module 2/3 AgentResult, `pr_reviews`
- **자동 머지 절대 금지**: 시니어 최종 승인은 항상 사람이 한다

### Module 5: 독립 GraphDB + YouTube 추천

- **MAS 패턴**: 독립 Pipeline (Module 1~4와 현재 분리)
- **책임**: 별도 웹 UI에서 문서 업로드 → 엔티티/관계 추출 → Neo4j Aura → YouTube 추천
- **독립성**: Module 0~4와 직접 연결 없음. doc_id/file_hash 공통 키로 향후 KMS 연결 가능
- **세부 규칙**: `docs/MODULE_5_GRAPH_YOUTUBE_RULE.md` 참조

---

## 5. API 출력 계약 (Output Contracts)

> 전체 모듈별 계약은 `docs/MODULE_CONTRACT.md`를 참조한다.  
> 공통 Pydantic 모델은 `src/common/state.py`의 `AgentResult`를 사용한다.  
> **필드 추가는 가능하지만 삭제 불가. 변경 시 docs/MODULE_CONTRACT.md 동기화 필수.**

### A. Module 2/3 → Module 4 (분석 에이전트 출력 — AgentResult)

```json
{
  "task_id": "uuid",
  "trace_id": "pr_3a9f1c2b44e0_static_analysis_a1b2",
  "agent_name": "StaticAnalysisAgent | SecurityScanAgent | TestVerificationAgent | PerformanceAgent",
  "module_id": "module_2 | module_3",
  "status": "success | fail | hitl_pending",
  "issues": [
    {
      "severity": "Critical | Major | Minor",
      "line": 42,
      "file": "src/auth.py",
      "message": "string",
      "rule_id": "SEC-001 | PERF-001 | TEST-001",
      "suggestion": "string"
    }
  ],
  "summary": { "critical": 0, "major": 2, "minor": 5 },
  "validation_result": "pass | fail | skip",
  "execution_ms": 1200,
  "next_agent": "module_4 | null"
}
```

### B. Module 1 → Module 2/3 (오케스트레이터 입력 — PlatformState)

```json
{
  "task_id": "uuid",
  "trace_id": "pr_3a9f1c2b44e0",
  "pr_context": {
    "pr_id": "42",
    "pr_diff": "unified diff string",
    "repo": "org/backend-service",
    "author_github_id": "junior_dev_01"
  },
  "kms_context": {
    "architecture_docs": ["chunk_id_1", "chunk_id_2"],
    "coding_conventions": "string",
    "previous_pr_issues": ["N+1 쿼리", "SQL 인젝션"]
  },
  "developer": {
    "user_id": "usr_001",
    "skill_level": "junior | mid | senior",
    "tech_stack": ["python", "fastapi", "postgresql"]
  }
}
```

### C. Module 4 → 프론트엔드 / GitHub / Slack (평가 에이전트 출력)

```json
{
  "task_id": "uuid",
  "pr_id": "42",
  "verdict": "lgtm | rework | escalate",
  "comment_body": "string (마크다운 형식)",
  "learning_resources": [
    { "title": "사내 N+1 쿼리 가이드", "url": "notion://..." }
  ],
  "escalation": {
    "required": true,
    "slack_channel": "#team-security",
    "message": "string"
  },
  "onboarding_update": {
    "issue_pattern": "N+1 쿼리",
    "occurrence_count": 3
  }
}
```

---

## 6. 위험 방지 규칙

### HITL (Human-in-the-Loop) 개입 기준

| 상황 | 임계값 | 처리 |
|------|--------|------|
| Markdown 품질 점수 | < 0.8 | 인간 검토 큐 등록, 자동 진행 중단 |
| 표/이미지 구조 손실 감지 | 발생 시 | 인간 검토 큐 등록 |
| Chunk 길이 기준 초과/미달 | 발생 시 | 인간 검토 큐 등록 |
| Parent-Child 연결 실패 | 발생 시 | 인간 검토 큐 등록 |
| Critical 보안 이슈 | ≥ 1건 | 즉시 Slack 에스컬레이션 |
| 재작업 요청 횟수 | > 3회 | 시니어 직접 개입 요청 |

> **자동 머지 없음.** 시니어의 최종 승인은 항상 사람이 한다.

### 에이전트 타임아웃

모든 분석 에이전트는 30초 타임아웃을 적용한다. `run_parallel_agents()`가 이를 자동 처리한다.

```python
# common/harness.py의 run_parallel_agents 사용 — 직접 구현 금지
# 타임아웃 발생 시 agent_traces에 status='fail'로 기록되고
# 해당 에이전트 결과는 make_timeout_result()로 대체된다

results = await run_parallel_agents(
    agents=[
        ("static_analysis", sa_graph.ainvoke, (state,), {}),
        ("security_scan",   ss_graph.ainvoke, (state,), {}),
    ],
    db_pool=pool,
    pr_trace_id=pr_trace,
    task_id=state["task_id"],  # agent_traces.task_id — PR 작업 단위 연결
)
```

> ⚠️ **타임아웃 처리 주의사항**
>
> `asyncio.TimeoutError`를 `async with AgentHarness()` **블록 안에서** 잡으면
> `__aexit__`이 예외를 보지 못해 `agent_traces.status`가 `'success'`로 기록된다.
> 반드시 `try/except`를 `async with` **바깥에** 위치시킨다.
>
> ```python
> # 올바른 패턴 (harness.py _run_one 참고)
> try:
>     async with AgentHarness(...) as harness:
>         return await harness.run(fn, *args, **kwargs)  # TimeoutError 전파됨
> except asyncio.TimeoutError:
>     return make_timeout_result(agent_name)  # with 블록 바깥에서 처리
>
> # 잘못된 패턴 — __aexit__이 성공으로 판단함
> async with AgentHarness(...) as harness:
>     try:
>         return await harness.run(fn, *args, **kwargs)
>     except asyncio.TimeoutError:          # ← 여기서 잡으면 안 됨
>         return make_timeout_result(agent_name)
> ```

### 보안 규칙

- GitHub Webhook은 반드시 HMAC-SHA256으로 서명 검증 후 처리한다.
- `X-Hub-Signature-256` 헤더 없는 요청은 403 반환.
- SQL 쿼리는 파라미터 바인딩만 사용한다. f-string으로 SQL 조합 금지.
- LLM 응답을 직접 DB에 저장 시 반드시 파싱/검증 후 저장한다.

### LLM 비용 통제

```python
# 개발 중: Mock LLM 사용
# 실제 LLM API는 통합 테스트(Week 5)와 데모 시에만 사용

USE_MOCK_LLM = os.getenv("USE_MOCK_LLM", "true").lower() == "true"
```

---

## 7. 개발 워크플로우 (Mock/실제 전환)

### Mock 기반 병렬 개발 (Week 2~3)

각 DEV는 다른 DEV의 실제 구현 없이 개발할 수 있다.

```python
# 환경변수로 Mock/실제 전환 — 코드 변경 없음
ANALYSIS_AGENT_URL = os.getenv("ANALYSIS_AGENT_URL", "http://mock-server:8001/analysis")
KMS_AGENT_URL      = os.getenv("KMS_AGENT_URL",      "http://mock-server:8001/kms")
EVAL_AGENT_URL     = os.getenv("EVAL_AGENT_URL",      "http://mock-server:8001/eval")
```

### 통합 전환 (Week 5)

`.env` 파일에서 URL을 실제 서비스 주소로 교체. 코드 변경 없음.

### 마일스톤 기준

| 주차 | 목표 | 완료 기준 |
|------|------|-----------|
| Week 1 | DB 스키마 합의 + API 계약 + Mock 서버 세팅 | 계약 문서 완성, seed 데이터 INSERT |
| Week 2~3 | 각자 P0 구현 (Mock 기반) | 독립 실행 + 단위 테스트 통과 |
| Week 4 | 문서 파이프라인 5단계 완성 (공동) | 실제 문서 → pgVector 저장 확인 |
| Week 5 | Mock → 실제 에이전트 연결 | PR 제출 → 코멘트 등록 E2E 확인 |
| Week 6 | P1 기능 + 버그 수정 + 발표 준비 | 전체 데모 시나리오 동작 |

---

## 8. DB 적재 기준

> ⚠️ **실제 DB 테이블 주의** — 코드와 쿼리에서 반드시 아래 이름을 사용한다.
> - 개발자 프로파일: `developers` ❌ → **`users`** ✅
> - 외래 키: `dev_id` ❌ → **`user_id`** ✅
> - `users.skill_level`, `users.github_id` 등 컬럼명은 그대로 유지.

### pgVector (chunk_embeddings) — 파이프라인이 자동 채움

> **임베딩 모델 확정: Ollama `bge-m3` (1024차원)**
> `.env` `PGVECTOR_DIMENSION=1024`, DDL `vector(1024)`, 아래 seed INSERT `::vector(1024)` — 세 곳이 반드시 일치해야 한다.

```sql
-- 수동 임베딩 INSERT (Week 2~3 개발용 seed)
-- 모델: ollama pull bge-m3
INSERT INTO chunk_embeddings (chunk_id, embedding, content, metadata)
VALUES (
  gen_random_uuid(),
  '[0.1, 0.2, ...]'::vector(1024),
  'N+1 쿼리 방지: for 루프 안에서 DB 쿼리 반복 호출 금지...',
  '{"category": "코딩컨벤션", "doc_title": "N+1 쿼리 방지 가이드"}'::jsonb
);
```

### MVP P0 필수 seed 데이터

```
문서 (→ pgVector, Module 0이 파이프라인으로 자동 채움):
  □ N+1 쿼리 방지 가이드        (Module 1 KMS 검색 + Module 4 학습 추천에 필수)
  □ SQL 인젝션 방지 패턴         (Critical 에스컬레이션 데모에 필수)
  □ 서비스 아키텍처 개요         (Module 1 KMS 검색에 필수)
  □ 신입 1주차 온보딩 가이드     (Module 4 커리큘럼에 필수)

개발자 프로파일 (→ PostgreSQL users):
  □ junior_dev_01 (skill_level: junior, tech_stack: ["python","fastapi","postgresql"])
  □ senior_dev_01 (skill_level: senior, 에스컬레이션 수신용)

PR 이력 (→ PostgreSQL pr_reviews):
  □ PR-001: verdict=rework, major=1 (N+1 쿼리 시나리오)
  □ PR-002: verdict=escalate, critical=1 (SQL 인젝션 시나리오)
```

---

## 9. 기술 스택 & 버전

| 레이어 | 기술 | 비고 |
|--------|------|------|
| 언어 | Python 3.11+ | `asyncio`, `type hints` 필수 |
| 에이전트 프레임워크 | LangGraph | StateGraph, conditional_edges, cyclical |
| LLM | claude-sonnet-4-6 | LangSmith 추적 포함 |
| 문서 변환 | UnStructured.io + Gemini Multimodal | PDF/DOCX → Markdown |
| Vector DB | pgVector (PostgreSQL 확장) | HNSW 인덱스, vector(1024) — Ollama bge-m3 |
| 메타 DB | PostgreSQL | 라우터, 메타데이터, trace 로그 |
| 원본 저장소 | GCS (Google Cloud Storage) | 이미지, Markdown, Docx 원본 |
| Graph DB | Neo4j | 관계 맵, 엔티티 관계 |
| GitHub 연동 | PyGitHub | Webhook + PR 코멘트 |
| 알림 | Slack Webhook API | 에스컬레이션, 갱신 알림 |
| Observability | LangSmith | 에이전트 추적, 품질 대시보드 |
| 프론트엔드 | React + TypeScript | 단일 UI |
| 로컬 통합 | Docker Compose | 전체 스택 단일 실행 |

---

## 10. 코드 작성 원칙

1. **타입 힌트 필수** — 모든 함수 시그니처에 `TypedDict` 또는 Pydantic 모델 사용.
2. **에이전트 출력은 Output Contract를 Pydantic으로 검증** 후 다음 에이전트로 전달.
3. **환경변수로 Mock/실제 전환** — `os.getenv("KEY", "default")` 패턴 사용.
4. **에러는 삼키지 않는다** — 에이전트 실패 시 `agent_traces`에 에러 기록 후 상위에 전파.
5. **단위 테스트는 Mock 기반으로 작성** — 실제 DB/LLM 없이 통과해야 함.
6. **LangSmith 콜백은 config로 주입** — 에이전트 함수 내부에 하드코딩 금지.
7. **자동 머지 코드 작성 금지** — PR 최종 결정은 항상 사람(시니어)이 한다.

---

## 11. LangGraph State 구조 (공통 State Schema)

**모든 모듈은 동일한 State 구조를 사용해야 통합 시 충돌이 없다.**

- **구현 파일**: `src/common/state.py` (단일 진실의 원천)
- **상세 문서**: `docs/AGENT_STATE_SCHEMA.md` (필드별 타입·설명·예시·사용 모듈)

```python
# 사용 방법 — 임의 재정의 금지
from common.state import (
    PlatformState,      # 공통 State (모든 모듈이 사용)
    AgentResult,        # Output Contract Pydantic 모델
    IssueItem,          # 이슈 항목
    DeveloperInfo,      # 개발자 프로파일
    PRContext,          # PR 컨텍스트
    KMSContext,         # KMS 검색 결과
    AgentStatus,        # 상태 Enum
    RequestType,        # 요청 유형 Enum
)

# 모듈 전용 필드가 필요하면 PlatformState를 상속
class Module2State(PlatformState, total=False):
    static_analysis_raw: str    # Module 2 전용 추가 필드 (공통 필드 재정의 금지)
```

**모듈별 State 필드 책임:**

| 필드 | 채우는 모듈 |
|------|------------|
| `task_id`, `trace_id`, `request_type` | Module 1 (초기화) |
| `developer`, `pr_context`, `kms_context` | Module 1 (요청 파싱 후) |
| `analysis_results`, `issues` | Module 2/3 (병렬 분석 결과 추가) |
| `verdict`, `comment_body` | Module 4 (판정 후) |
| `status`, `retry_count`, `error_message` | 각 모듈 자신 |
| Module 5 | 독립 `Module5State` 사용 (PlatformState와 분리) |

---

## 12. 오류 처리 공백 (GAP 정의)

에이전트 코드 작성 시 반드시 아래 케이스를 처리한다.

| 상황 | 처리 방법 |
|------|-----------|
| **pgVector 검색 결과 0건** | 빈 리스트 반환, `kms_context.architecture_docs = []`로 Module 2/3 전달, 로그 기록 |
| **LLM 응답이 잘못된 JSON** | `json.JSONDecodeError` 캐치 → `agent_traces`에 원본 응답 저장 → 재시도 1회 → 실패 시 `{"issues": [], "error": "parse_failed"}` 반환 |
| **GitHub API 429 (Rate Limit)** | `time.sleep(60)` 후 1회 재시도, 2회 실패 시 `escalate` 판정으로 강제 처리 |
| **GitHub API 401/403** | 즉시 실패, Slack 에스컬레이션, `agent_traces`에 기록 |
| **Slack API 실패** | 로그만 남기고 무시 (알림 실패가 전체 파이프라인을 막으면 안 됨) |
| **User ID DB 미존재** | `users` 테이블 조회 실패 → `skill_level: "junior"` 기본값으로 진행, 경고 로그 |

```python
# pgVector 0결과 처리 예시
async def search_kms(query: str) -> list[str]:
    results = await pgvector_search(query, limit=3)
    if not results:
        logger.warning(f"KMS search returned 0 results for: {query[:50]}")
        return []  # 빈 리스트로 진행, 예외 던지지 않음
    return [r.chunk_id for r in results]
```

---

## 13. 테스트 작성 패턴

에이전트 단위 테스트는 실제 DB/LLM 없이 Mock으로 작성한다.

```python
# pytest + unittest.mock 패턴
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

class TestDev1KMSSearch:
    @pytest.fixture
    def mock_pgvector(self):
        """pgVector를 Mock — 실제 DB 연결 없음"""
        with patch("agents.dev1.kms.pgvector_search") as mock:
            mock.return_value = [
                MagicMock(chunk_id="chunk-001", content="N+1 쿼리 방지..."),
            ]
            yield mock

    @pytest.fixture
    def mock_llm(self):
        """LLM을 Mock — 실제 API 호출 없음"""
        with patch("agents.dev1.orchestrator.claude_client") as mock:
            mock.messages.create = AsyncMock(return_value=MagicMock(
                content=[MagicMock(text='{"intent": "pr_review"}')]
            ))
            yield mock

    async def test_kms_search_returns_empty_on_no_results(self, mock_pgvector):
        mock_pgvector.return_value = []
        result = await search_kms("없는 주제")
        assert result == []  # 예외 던지지 않아야 함

    async def test_intent_classification_pr_review(self, mock_llm):
        result = await classify_intent("PR #42에서 N+1 쿼리 발견")
        assert result == "pr_review"

# Mock 서버 테스트 (Dev4가 Dev2/3 Mock으로 개발할 때)
class TestDev4WithMockDev2:
    @pytest.fixture
    def mock_analysis_result(self):
        return {
            "task_id": "test-uuid",
            "agent": "static_analysis",
            "issues": [{"severity": "Major", "line": 42, "file": "auth.py",
                        "message": "N+1 쿼리", "rule_id": "PERF-001", "suggestion": "joinedload 사용"}],
            "summary": {"critical": 0, "major": 1, "minor": 0},
            "execution_ms": 500
        }

    async def test_verdict_rework_on_major_3plus(self, mock_analysis_result):
        mock_analysis_result["summary"]["major"] = 3
        verdict = await evaluate([mock_analysis_result, mock_analysis_result, mock_analysis_result])
        assert verdict == "rework"
```

---

## 14. 환경변수 전체 목록 (.env.example)

> **.env.example** 파일이 단일 진실의 원천이다. 이 섹션은 그 요약이다.  
> 실제 값은 `.env`에만 저장하고 절대 git에 커밋하지 않는다.

```bash
# ===== LangSmith (Harness) =====
LANGCHAIN_TRACING_V2=true
LANGCHAIN_API_KEY=ls__xxxx
# ⚠️ 반드시 모듈번호 + GitHub ID 포함. 없으면 팀원 trace가 섞인다.
# 개발 중: module{N}-yourGitHubId / 통합(Week 5): onboarding-platform-integrated
LANGCHAIN_PROJECT=module1-yourGitHubId

# ===== LLM — Gemini 2.5 Flash (팀 전체 통일) =====
# 멀티모달 지원 (이미지·표 포함 문서 + 피드백 생성 모두 사용)
GOOGLE_API_KEY=AIzaxxxx
GEMINI_MODEL=gemini-2.5-flash
USE_MOCK_LLM=true                     # 개발 중 true, 통합 테스트·데모 시 false

# ===== Database (PostgreSQL + pgVector) =====
POSTGRES_URL=postgresql://user:password@host:5432/dbname
PGVECTOR_DIMENSION=1024               # Ollama bge-m3 (1024차원) — schema.sql과 반드시 일치

# ===== Graph DB (Neo4j — Module 5) =====
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=password

# ===== Storage — GCS (Google Cloud Storage) =====
STORAGE_BACKEND=gcs                   # gcs: Google Cloud Storage / local: 로컬 파일
GCS_BUCKET=your-gcs-bucket-name
# 인증: Application Default Credentials
#   로컬: gcloud auth application-default login 실행 필요
#   Cloud Run: 자동 (Compute Engine 기본 서비스 계정)

# ===== GitHub =====
GITHUB_WEBHOOK_SECRET=your-hmac-secret
GITHUB_TOKEN=ghp_xxxx                 # PR 코멘트 작성용 (Module 1/4)

# ===== Slack =====
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/xxx/yyy/zzz
SLACK_CHANNEL_SECURITY=#team-security
SLACK_CHANNEL_REVIEW=#team-backend

# ===== Agent Service URLs (Mock 기반 개발 — Week 2~3) =====
# Week 5 통합 시 실제 서비스 주소로 교체. 코드 변경 없음.
ANALYSIS_AGENT_URL=http://mock-server:8001/analysis
KMS_AGENT_URL=http://mock-server:8001/kms
EVAL_AGENT_URL=http://mock-server:8001/eval
CURRICULUM_AGENT_URL=http://mock-server:8001/curriculum

# ===== 임베딩 — Ollama bge-m3 (팀 확정 모델) =====
EMBEDDING_PROVIDER=ollama
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_EMBEDDING_MODEL=bge-m3         # 1024차원, 한국어 포함 다국어
OLLAMA_VISION_MODEL=gemma3            # 문서 파싱 보조용 (멀티모달)
# 설치: ollama pull bge-m3 && ollama pull gemma3

# ===== CORS =====
CORS_ORIGINS=http://localhost:3000,http://localhost:5173
# Cloud Run 배포 시: 프론트엔드 URL로 반드시 교체

# ===== 에이전트 실행 =====
AGENT_TIMEOUT_SECONDS=30              # 모든 분석 에이전트 타임아웃 (Module 2/3)

# ===== KMS 파이프라인 (Module 0 전용) =====
ANTHROPIC_API_KEY=sk-ant-xxxx        # Stage 2 검증, Stage 5 메타데이터 추출
ANTHROPIC_MODEL=claude-sonnet-4-6
UPSTAGE_API_KEY=up_xxxx              # HIGH complexity PDF 파싱
MARKDOWN_QUALITY_THRESHOLD=0.8       # 이 값 미만이면 HITL 등록
GEMINI_FALLBACK_IMAGE_RATIO=0.3      # 이 값 이상이면 Gemini Multimodal 폴백
STAGE2_MAX_FIX_ATTEMPTS=2            # Stage 2 retry 최대 횟수
```

---

## 15. Git 브랜치 전략

6인 병렬 개발 — 브랜치 규칙 없으면 main이 깨진다.

### 브랜치 명명 규칙

```
feature/module0-kms-stage2-retry        # Module 0 새 기능
feature/module1-webhook-intent-classify # Module 1 새 기능
feature/module2-sql-injection-scan      # Module 2 새 기능
feature/module3-coverage-threshold      # Module 3 새 기능
feature/module4-eval-3way-verdict       # Module 4 새 기능
feature/module5-neo4j-entity-extract    # Module 5 새 기능
feature/fe-pr-review-dashboard          # 프론트엔드
fix/module1-kms-empty-result            # 버그 수정
```

### PR 머지 규칙

```
main ← feature/* (PR 통해서만)

PR 요건:
  □ 단위 테스트 통과 (Mock 기반, DB 없이)
  □ Output Contract 변경 시 → docs/MODULE_CONTRACT.md 업데이트 + 영향받는 모듈 담당자 공지
  □ src/common/state.py 변경 시 → PR description에 명시 + 전 모듈에 알림
  □ 최소 1명 코드 리뷰 후 머지

금지:
  ✗ main 직접 push
  ✗ 다른 모듈 담당 파일 임의 수정
  ✗ --force push
  ✗ src/common/state.py PlatformState 공통 필드 재정의
```

### 통합 주간 (Week 5) 브랜치 전략

```
main
  └── integration/week5          # Week 5 통합 브랜치
        ├── feature/dev1-real-connect
        ├── feature/dev2-real-connect
        └── feature/dev3-real-connect
```

Week 5에는 `integration/week5`에서 Mock → 실제 연결 작업 후 E2E 확인, 통과 시 main 머지.

---

## 16. 팀 전역 규칙 문서 (docs/ 폴더)

> **Claude에게 — 강제 지침**: 아래 트리거 조건에 해당하는 코드를 작성하기 전에
> 반드시 Read 도구로 해당 문서를 읽고 규칙을 따른다. 읽지 않고 작성하는 것은 금지다.

### 문서 목록 및 읽기 트리거

| 문서 | 경로 | 이 상황에서 반드시 읽어라 |
|------|------|--------------------------|
| `GLOBAL_AGENT_RULE.md` | `docs/GLOBAL_AGENT_RULE.md` | Agent/Tool/Workflow 코드 작성, Validation 구현, HITL/Retry/Error 처리 작성 |
| `AGENT_STATE_SCHEMA.md` | `docs/AGENT_STATE_SCHEMA.md` | LangGraph StateGraph 작성, State 정의, 모듈 간 State 공유 코드 작성 |
| `MODULE_CONTRACT.md` | `docs/MODULE_CONTRACT.md` | 모듈 간 통신 코드 작성, Output Contract 구현, 다른 모듈 호출 코드 작성 |
| `MODULE_5_GRAPH_YOUTUBE_RULE.md` | `docs/MODULE_5_GRAPH_YOUTUBE_RULE.md` | Module 5(GraphDB + YouTube) 관련 코드 일체 |

### 트리거 조건 요약

```
Agent / Tool / Workflow 설계 또는 구현
    → docs/GLOBAL_AGENT_RULE.md 읽기

LangGraph StateGraph, TypedDict, PlatformState 작성
    → docs/AGENT_STATE_SCHEMA.md 읽기

모듈 간 호출, AgentResult, Output Contract 구현
    → docs/MODULE_CONTRACT.md 읽기

module_5_graph_youtube/ 폴더 내 코드 작성
    → docs/MODULE_5_GRAPH_YOUTUBE_RULE.md 읽기
```

### 팀원 공통 준수 사항

- `src/common/state.py` — LangGraph State 단일 진실의 원천. 이 파일을 재정의하지 않는다.
- 모든 Agent 출력은 `AgentResult` Pydantic 모델을 사용한다 (`src/common/state.py` 내).
- 모든 Agent 실행은 `common/harness.py`의 `AgentHarness`로 래핑한다.
- Output Contract 변경 시 `docs/MODULE_CONTRACT.md` 업데이트 후 영향받는 모듈 담당자에게 공지.

## Skill routing

When the user's request matches an available skill, ALWAYS invoke it using the Skill
tool as your FIRST action. Do NOT answer directly, do NOT use other tools first.
The skill has specialized workflows that produce better results than ad-hoc answers.

Key routing rules:
- Product ideas, "is this worth building", brainstorming → invoke office-hours
- Bugs, errors, "why is this broken", 500 errors → invoke investigate
- Ship, deploy, push, create PR → invoke ship
- QA, test the site, find bugs → invoke qa
- Code review, check my diff → invoke review
- Update docs after shipping → invoke document-release
- Weekly retro → invoke retro
- Design system, brand → invoke design-consultation
- Visual audit, design polish → invoke design-review
- Architecture review → invoke plan-eng-review
- Save progress, save state, save my work → invoke context-save
- Resume, where was I, pick up where I left off → invoke context-restore
- Code quality, health check → invoke health
