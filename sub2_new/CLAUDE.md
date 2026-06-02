# CLAUDE.md — 조직 지식 관리 + 개발자 온보딩 멀티 에이전트 플랫폼

**PRD 버전**: v1.1 | **팀**: 6명 (FE 1 + 서비스 5) | **MVP**: 개발자 직군 신입사원 온보딩

이 파일은 AI 에이전트(Claude)가 이 프로젝트에서 코드를 작성하거나 설계할 때
따라야 할 전역 규칙이다. 모든 규칙은 PRD와 DB_데이터_요구사항.md에서 도출됐다.

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
[Entities / Domain]           Developer, Document, Chunk, PRReview, MistakePattern, AgentTrace
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
문서 파이프라인 (단계 접두사 + doc_id):
  trc_0001_{doc_id_8hex}  Markdown 변환 Agent
  trc_0002_{doc_id_8hex}  Markdown 검증 Agent
  trc_0003_{doc_id_8hex}  청킹 Agent
  trc_0004_{doc_id_8hex}  Chunk 검증 Agent
  trc_0005_{doc_id_8hex}  메타데이터 추출 Agent
  trc_0006_{doc_id_8hex}  저장 & 라우팅

  예시: trc_0001_3a9f1c2b

  ⚠️ doc_id 없이 new_pipeline_trace(stage)를 호출하면 trc_0001 고정값이 반환된다.
     agent_traces.trace_id는 PRIMARY KEY이므로 두 번째 문서 처리 시 첫 번째 기록이
     덮어써진다. 운영 환경에서는 반드시 doc_id를 전달할 것:
     trace_id = new_pipeline_trace(DocPipelineStage.MARKDOWN_CONVERT, doc_id=doc_id)

PR 리뷰 파이프라인 (동적 UUID):
  pr_{12자리 hex}  — 각 PR 처리마다 새로 생성
  예시: pr_3a9f1c2b44e0

병렬 에이전트 서브 trace:
  {parent_trace_id}_{agent_name}_{4자리 hex}
  예시: pr_3a9f1c2b44e0_static_analysis_a1b2
```

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
| Week 2~3 (개발 중) | `dev1-{github_id}`, `dev2-{github_id}`, ... (개인별 분리 필수) |
| Week 5 (통합) | `onboarding-platform-integrated` |
| 데모 | `onboarding-platform-demo` |

> ⚠️ **개인 네이밍 필수** — `dev1-orchestrator` 처럼 역할명만 쓰면
> 팀원 여러 명의 trace가 같은 LangSmith 프로젝트에 섞인다.
> 반드시 `dev1-alice`, `dev1-bob` 처럼 본인 GitHub ID를 붙인다.
>
> ```bash
> # .env 예시 (본인 ID로 교체)
> LANGCHAIN_PROJECT=dev1-alice
> ```

---

## 4. MAS 패턴 & DEV별 책임

### 시스템 흐름

```
GitHub Webhook → [Dev1 Orchestrator] → asyncio.gather([Dev2, Dev3]) → [Dev4 Evaluator]
                         ↓                                                      ↓
                   KMS 컨텍스트 검색                              GitHub 코멘트 + Slack 알림
                   (pgVector)                                              ↓
                                                               [Dev5 Curriculum & Feedback]
```

### Dev1: Orchestrator + KMS Search

- **MAS 패턴**: Supervisor (LangGraph StateGraph)
- **책임**: Webhook 수신 → 의도 분류 → 에이전트 라우팅 → 결과 취합
- **필수 구현**:
  - GitHub Webhook HMAC-SHA256 서명 검증 (F-ORC-01)
  - 의도 분류: PR 리뷰 / KMS 질의 / 온보딩 / 아키텍처 질문 (F-ORC-02)
  - pgVector 코사인 유사도 검색 (F-KMS-01, F-KMS-02)
  - PostgreSQL `pr_reviews` 이전 이력 조회 (F-KMS-03)
- **의존 데이터**: `chunk_embeddings`(pgVector), `developers`, `pr_reviews`

### Dev2: 정적 분석 + 보안 스캔

- **MAS 패턴**: Parallel Independent Agent (asyncio.gather)
- **책임**: ESLint/Pylint 실행, 순환복잡도, SQL 인젝션/XSS/CSRF 탐지, CVE 스캔
- **타임아웃**: 30초 (초과 시 해당 에이전트 결과 제외하고 진행)
- **출력**: Output Contract JSON (섹션 5-A 참고)
- **의존 데이터**: 없음 (PR diff 직접 분석)

### Dev3: 테스트 검증 + 성능 분석

- **MAS 패턴**: Parallel Independent Agent (asyncio.gather)
- **책임**: 커버리지 측정(80% 미달 시 Major), N+1 쿼리 감지, 시간복잡도 추정
- **타임아웃**: 30초
- **출력**: Output Contract JSON (섹션 5-A 참고)
- **의존 데이터**: 없음 (PR diff 직접 분석)

### Dev4: 개발 평가 + 개인화

- **MAS 패턴**: Aggregator + Conditional Router (LangGraph conditional_edges)
- **책임**: Dev2/3 결과 취합 → 3-Way 판정 → 개인화 피드백 → GitHub 코멘트
- **3-Way 판정 로직**:
  ```
  Critical ≥ 1  → escalate  (Slack 즉시 알림)
  Major ≥ 3     → rework    (힌트 포함, 최대 3회 리트라이)
  나머지         → lgtm      (시니어 최종 승인 요청)
  ```
- **의존 데이터**: `developers`(skill_level), Dev2/3 Output Contract

### Dev5: 커리큘럼 + 온보딩 이력 + 피드백 루프

- **MAS 패턴**: Cyclical Feedback Loop + HITL (LangGraph cyclical graph)
- **책임**: 주차별 로드맵 생성, PR 이력 저장, 반복 실수 패턴 감지, KMS 갱신 제안
- **의존 데이터**: `developers`, `pr_reviews`, `mistake_patterns`, `chunk_embeddings`

---

## 5. API 출력 계약 (Output Contracts)

에이전트 간 통신은 이 계약을 정확히 따른다. 필드 추가는 가능하지만 삭제 불가.

### A. Dev2/3 → Dev4 (분석 에이전트 출력)

```json
{
  "task_id": "uuid",
  "agent": "static_analysis | security_scan | test_verification | performance",
  "issues": [
    {
      "severity": "Critical | Major | Minor",
      "line": 42,
      "file": "src/auth.py",
      "message": "string",
      "rule_id": "string",
      "suggestion": "string"
    }
  ],
  "summary": { "critical": 0, "major": 2, "minor": 5 },
  "execution_ms": 1200
}
```

### B. Dev1 → Dev2/3 (오케스트레이터 입력 계약)

```json
{
  "task_id": "uuid",
  "pr_id": "github-pr-number",
  "pr_diff": "string (unified diff format)",
  "context": {
    "architecture_docs": ["chunk_id_1", "chunk_id_2"],
    "coding_conventions": "string",
    "previous_pr_issues": ["N+1 쿼리", "SQL 인젝션"]
  },
  "developer": {
    "id": "string",
    "skill_level": "junior | mid | senior",
    "tech_stack": ["python", "fastapi", "postgresql"]
  }
}
```

### C. Dev4 → 프론트엔드 / GitHub / Slack (평가 에이전트 출력)

```json
{
  "task_id": "uuid",
  "pr_id": "string",
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

### pgVector (chunk_embeddings) — 파이프라인이 자동 채움

> ⚠️ **차원 통일 필수** — 임베딩 옵션 선택 후 아래 3곳을 동시에 맞춘다.
> 하나라도 다르면 첫 번째 임베딩 INSERT에서 차원 불일치 오류가 발생한다.
>
> | 수정 위치 | 옵션 A (Upstage) | 옵션 B (Ollama) |
> |---|---|---|
> | `.env` `PGVECTOR_DIMENSION` | `4096` | `768` |
> | `DB_데이터_요구사항.md` DDL | `vector(4096)` | `vector(768)` |
> | 아래 seed INSERT | `::vector(4096)` | `::vector(768)` |

```sql
-- 수동 임베딩 INSERT (Week 2~3 개발용 seed)
-- {차원} 자리에 4096 (Upstage) 또는 768 (Ollama) 입력 — .env와 동일해야 함
INSERT INTO chunk_embeddings (chunk_id, embedding, content, metadata)
VALUES (
  gen_random_uuid(),
  '[0.1, 0.2, ...]'::vector(4096),  -- ← 팀 결정값으로 교체
  'N+1 쿼리 방지: for 루프 안에서 DB 쿼리 반복 호출 금지...',
  '{"category": "코딩컨벤션", "doc_title": "N+1 쿼리 방지 가이드"}'::jsonb
);
```

### MVP P0 필수 seed 데이터

```
문서 (→ pgVector):
  □ N+1 쿼리 방지 가이드        (Dev1 KMS + Dev5 학습 추천에 필수)
  □ SQL 인젝션 방지 패턴         (Critical 에스컬레이션 데모에 필수)
  □ 서비스 아키텍처 개요         (Dev1 KMS에 필수)
  □ 신입 1주차 온보딩 가이드     (Dev5 커리큘럼에 필수)

개발자 프로파일 (→ PostgreSQL developers):
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
| Vector DB | pgVector (PostgreSQL 확장) | HNSW 인덱스, vector(4096 또는 768) — 팀 결정값 통일 |
| 메타 DB | PostgreSQL | 라우터, 메타데이터, trace 로그 |
| 원본 저장소 | S3 / MinIO | 이미지, Markdown, Docx 원본 |
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

## 11. LangGraph State 구조 (공통 TypedDict)

모든 DEV가 같은 State 구조를 사용해야 통합 시 충돌이 없다.

```python
from typing import TypedDict, Literal, Optional
from uuid import UUID

class IssueItem(TypedDict):
    severity: Literal["Critical", "Major", "Minor"]
    line: int
    file: str
    message: str
    rule_id: str
    suggestion: str

class IssueSummary(TypedDict):
    critical: int
    major: int
    minor: int

class AgentResult(TypedDict):
    task_id: str
    agent: str
    issues: list[IssueItem]
    summary: IssueSummary
    execution_ms: int

class PRReviewState(TypedDict):
    # Dev1이 채움 (입력)
    task_id: str
    pr_id: str
    pr_diff: str
    developer_id: str
    skill_level: Literal["junior", "mid", "senior"]
    tech_stack: list[str]
    architecture_docs: list[str]       # chunk_id 목록
    coding_conventions: str
    previous_pr_issues: list[str]

    # Dev2/3가 채움 (분석 결과)
    analysis_results: list[AgentResult]

    # Dev4가 채움 (최종 판정)
    verdict: Optional[Literal["lgtm", "rework", "escalate"]]
    comment_body: Optional[str]
    learning_resources: Optional[list[dict]]

    # Dev5가 채움 (이력/커리큘럼)
    issue_patterns: Optional[list[str]]
    curriculum_update: Optional[dict]
```

---

## 12. 오류 처리 공백 (GAP 정의)

에이전트 코드 작성 시 반드시 아래 케이스를 처리한다.

| 상황 | 처리 방법 |
|------|-----------|
| **pgVector 검색 결과 0건** | 빈 리스트 반환, `context.architecture_docs = []`로 Dev2/3 전달, 로그 기록 |
| **LLM 응답이 잘못된 JSON** | `json.JSONDecodeError` 캐치 → `agent_traces`에 원본 응답 저장 → 재시도 1회 → 실패 시 `{"issues": [], "error": "parse_failed"}` 반환 |
| **GitHub API 429 (Rate Limit)** | `time.sleep(60)` 후 1회 재시도, 2회 실패 시 `escalate` 판정으로 강제 처리 |
| **GitHub API 401/403** | 즉시 실패, Slack 에스컬레이션, `agent_traces`에 기록 |
| **Slack API 실패** | 로그만 남기고 무시 (알림 실패가 전체 파이프라인을 막으면 안 됨) |
| **Developer ID DB 미존재** | `developers` 테이블 조회 실패 → `skill_level: "junior"` 기본값으로 진행, 경고 로그 |

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

```bash
# ===== LangSmith (Harness) =====
LANGCHAIN_TRACING_V2=true
LANGCHAIN_API_KEY=ls__xxxx
LANGCHAIN_PROJECT=dev1-orchestrator   # 개발 중: devN-name / 통합: onboarding-platform-integrated

# ===== LLM =====
ANTHROPIC_API_KEY=sk-ant-xxxx
USE_MOCK_LLM=true                     # 개발 중 true, 통합 테스트/데모 시 false

# ===== Database =====
POSTGRES_URL=postgresql://user:pass@localhost:5432/onboarding_db
PGVECTOR_DIMENSION=4096               # 옵션 A(Upstage)=4096 / 옵션 B(Ollama)=768 — .env.example 참고

# ===== Graph DB =====
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=password

# ===== Storage =====
MINIO_ENDPOINT=localhost:9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin
MINIO_BUCKET=onboarding-docs

# ===== GitHub =====
GITHUB_WEBHOOK_SECRET=your-hmac-secret
GITHUB_TOKEN=ghp_xxxx                 # PR 코멘트 작성용

# ===== Slack =====
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/xxx
SLACK_CHANNEL_SECURITY=#team-security
SLACK_CHANNEL_REVIEW=#team-backend

# ===== Agent Service URLs (Mock 기반 개발) =====
ANALYSIS_AGENT_URL=http://mock-server:8001/analysis
KMS_AGENT_URL=http://mock-server:8001/kms
EVAL_AGENT_URL=http://mock-server:8001/eval
CURRICULUM_AGENT_URL=http://mock-server:8001/curriculum

# ===== 임베딩 =====
EMBEDDING_MODEL=text-embedding-3-small  # OpenAI 또는 Claude 임베딩
OPENAI_API_KEY=sk-xxxx                  # pgVector 검색용 임베딩 생성 시
```

---

## 15. Git 브랜치 전략

6인 병렬 개발 — 브랜치 규칙 없으면 main이 깨진다.

### 브랜치 명명 규칙

```
feature/dev1-orchestrator-webhook       # Dev1 새 기능
feature/dev2-sql-injection-scan         # Dev2 새 기능
feature/dev3-coverage-threshold         # Dev3 새 기능
feature/dev4-eval-3way-verdict          # Dev4 새 기능
feature/dev5-curriculum-autogen         # Dev5 새 기능
feature/fe-pr-review-dashboard          # 프론트엔드
fix/dev1-kms-empty-result               # 버그 수정
```

### PR 머지 규칙

```
dev ← feature/* (PR 통해서만)

PR 요건:
  □ 단위 테스트 통과 (Mock 기반, DB 없이)
  □ Output Contract 변경 시 → 영향받는 DEV에게 반드시 알림
  □ CLAUDE.md 섹션 5 API 계약 변경 시 → PR description에 명시
  □ 최소 1명 코드 리뷰 후 머지

금지:
  ✗ dev 직접 push
  ✗ 다른 DEV 담당 파일 임의 수정
  ✗ --force push
```

### 통합 주간 (Week 5) 브랜치 전략

```
dev
  └── integration/week5          # Week 5 통합 브랜치
        ├── feature/dev1-real-connect
        ├── feature/dev2-real-connect
        └── feature/dev3-real-connect
```

Week 5에는 `integration/week5`에서 Mock → 실제 연결 작업 후 E2E 확인, 통과 시 dev 머지.
