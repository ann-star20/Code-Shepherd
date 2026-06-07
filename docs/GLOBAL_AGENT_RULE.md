# GLOBAL_AGENT_RULE.md — 팀 전원 공통 강제 규칙

**버전**: v1.0 | **적용 범위**: Module 0~5 전원 | **작성일**: 2026-06-04  
**이 문서의 모든 규칙은 선택이 아니라 강제다. 예외는 없다.**

---

## §1. Agent 설계 원칙

### 1-1. Agent / Tool / Workflow 구분

| 구분 | 정의 | 예시 |
|------|------|------|
| **Tool** | 결정론적 단일 함수. LLM 없음. 입력 → 출력 고정. | `_chunk_text()`, `_validate_schema()`, `pgvector_search()` |
| **LLM Node** | LLM 단독 호출. 반복 없음. 출력 검증 후 다음 단계로 전달. | `_extract_metadata()`, `_classify_intent()` |
| **Agent** | Tool + LLM + 반복(Retry/Loop) + 분기(Conditional). | `stage2_validate_agent`, `orchestrator` |
| **Workflow** | Agent 여러 개를 LangGraph StateGraph로 연결한 파이프라인. | KMS 문서 파이프라인 (Stage 1~6) |

### 1-2. Agent가 되기 위한 조건 (2개 이상 충족 시 Agent)

```
□ Tool을 2개 이상 선택적으로 호출하는가?
□ 출력 품질을 평가하고 재시도(Retry)하는가?
□ 조건에 따라 다른 경로로 분기(Conditional Edge)하는가?
□ HITL 여부를 판단하는가?
```

조건 0~1개: **Tool 또는 LLM Node**로 구현.
조건 2개 이상: **Agent** (LangGraph StateGraph로 구현).

### 1-3. LLM 단독 호출과 Agent의 차이

```python
# ❌ 잘못된 패턴 — LLM 호출을 "Agent"라 부르며 StateGraph 없이 구현
async def my_agent(state):
    result = await llm.invoke(prompt)
    return {"output": result}

# ✅ 올바른 패턴 — Tool + 반복 + 분기가 있을 때 StateGraph
graph = StateGraph(MyState)
graph.add_node("evaluate", evaluate_node)
graph.add_node("fix",      fix_node)
graph.add_conditional_edges("evaluate", route_fn, {"pass": END, "retry": "fix"})
```

---

## §2. Clean Architecture 규칙

### 2-1. 레이어 정의

```
[Presentation Layer]    FastAPI 라우터, Webhook 핸들러
[Application Layer]     Agent 로직, LangGraph 그래프, Use Case
[Domain Layer]          Pydantic 모델, 비즈니스 규칙, 엔티티 정의
[Infrastructure Layer]  DB 접근, 외부 API 클라이언트, 저장소 구현체
```

### 2-2. 의존성 방향 (이 방향만 허용)

```
Presentation → Application → Domain ← Infrastructure
                                 ↑
                         (인터페이스로만 참조)
```

### 2-3. 레이어별 책임

| 레이어 | 해도 되는 것 | 하면 안 되는 것 |
|--------|-------------|----------------|
| Presentation | Webhook 수신, HTTP 응답 직렬화 | 비즈니스 로직, DB 직접 접근 |
| Application | Agent 로직, 모듈 라우팅, 상태 관리 | SQL 직접 작성, 외부 API 직접 호출 |
| Domain | Pydantic 모델 정의, 검증 규칙 | 외부 의존성 import |
| Infrastructure | DB 쿼리, API 클라이언트 | 비즈니스 판단 |

### 2-4. 금지사항

```python
# ❌ FastAPI 라우터에 비즈니스 로직
@app.post("/webhook")
async def webhook(payload: dict):
    if payload["critical"] >= 1:        # ← 비즈니스 로직이 라우터에 있음
        await slack_notify(...)

# ❌ Agent 코드에 SQL 직접 노출
async def analyze(state):
    rows = await conn.fetch("SELECT * FROM users WHERE ...")  # ← Repository 없이 직접

# ❌ 도메인 모델에 외부 의존성
from anthropic import Anthropic          # ← Domain 레이어에 인프라 import
class Document(BaseModel):
    client: Anthropic                   # ← 절대 금지
```

---

## §3. LangGraph StateGraph 규칙

### 3-1. 공통 State 사용 의무

**모든 모듈은 `src/common/state.py`의 `PlatformState`를 기반으로 동작한다.**  
모듈 전용 추가 필드는 허용하되, 공통 필드는 절대 재정의하지 않는다.

```python
# ✅ 올바른 패턴
from common.state import PlatformState

class Module2State(PlatformState):   # PlatformState 상속
    static_analysis_raw: str         # 모듈 2 전용 추가 필드

# ❌ 잘못된 패턴 — 공통 필드 재정의
class Module2State(TypedDict):
    task_id: str                     # PlatformState와 충돌 위험
```

### 3-2. 오케스트레이터 라우팅 기준

```python
# Module 1이 State.request_type으로 라우팅
def route_by_request_type(state: PlatformState) -> str:
    if state["request_type"] == RequestType.PR_REVIEW:
        return "parallel_analysis"     # Module 2 + 3 asyncio.gather
    elif state["request_type"] == RequestType.KMS_QUERY:
        return "kms_search"            # Module 0 pgVector 검색
    return "end"
```

### 3-3. Conditional Edge 사용 기준

| 상황 | Edge 방식 |
|------|-----------|
| 항상 다음 노드로 이동 | `graph.add_edge(A, B)` |
| 조건에 따라 다른 노드 | `graph.add_conditional_edges(A, route_fn, {…})` |
| 판정에 따라 종료/계속 | Conditional Edge로 `END` 분기 |

### 3-4. Retry / HITL 분기 기준

```python
def route_after_validate(state) -> str:
    if state["validation_result"] == "pass":
        return "next_stage"
    if state["retry_count"] >= MAX_RETRY:
        return "hitl"               # HITL 큐 등록
    return "fix_and_retry"          # retry_count 증가 후 재시도
```

---

## §4. Agent Input / Output Contract

**모든 Agent의 출력은 반드시 아래 필드를 포함해야 한다. 필드 삭제 불가.**

```python
# src/common/contracts.py의 AgentResult 사용 의무
{
    "task_id":          "uuid",               # 작업 단위 고유 ID (Module 1이 생성)
    "trace_id":         "trc_0001_3a9f1c2b",  # LangSmith + DB 추적 ID
    "agent_name":       "StaticAnalysisAgent",
    "module_id":        "module_2",
    "status":           "success | fail | hitl_pending | escalated",
    "issues":           [...],                # IssueItem 목록
    "summary":          {"critical": 0, "major": 2, "minor": 5},
    "validation_result":"pass | fail | skip",
    "execution_ms":     1200,
    "next_agent":       "module_4 | null"
}
```

**필드 추가는 가능하나 이 10개 필드는 항상 존재해야 한다.**

---

## §5. Validation 3단계 규칙

**모든 Agent는 출력을 다음 단계로 전달하기 전에 3단계 검증을 수행한다.**

### 1차: Pydantic Schema Validation

```python
from common.contracts import AgentResult

try:
    validated = AgentResult(**raw_output)
except ValidationError as e:
    # 1차 실패 → 즉시 fail 처리, 재시도 없음
    return {"status": "fail", "error_message": f"schema_error: {e}"}
```

**목적**: 필드 존재 여부, 타입 일치, 필수값 누락 확인.  
**실패 처리**: 재시도 없이 즉시 `status: fail` → `agent_traces`에 기록.

### 2차: Business Rule Validation

```python
def validate_business_rules(result: AgentResult) -> bool:
    # 예시: Critical 이슈가 있으면 verdict는 반드시 escalate여야 함
    if result.summary.critical >= 1 and result.next_agent != "escalate":
        return False
    # 예시: execution_ms가 0이면 비정상
    if result.execution_ms <= 0:
        return False
    return True
```

**목적**: 도메인 규칙 위반 여부 확인.  
**실패 처리**: `retry_count` 증가 → 최대 횟수 초과 시 HITL.

### 3차: Validation Agent / 검증 함수

```python
# Stage 5b처럼 별도 검증 Agent가 있는 경우
async def metadata_validate(state):
    score = await _evaluate_metadata_quality(state["metadata"])
    if score < THRESHOLD:
        return {"validation_result": "fail", "hitl_required": True}
    return {"validation_result": "pass"}
```

**목적**: LLM 출력 품질 평가, 구조적 완결성 확인.  
**실패 처리**: quality_score 기준 미달 → HITL 큐 등록.

---

## §6. Pydantic 사용 규칙

### 6-1. 모든 Input / Output은 Pydantic BaseModel 필수

```python
# ❌ dict 직접 반환
return {"task_id": task_id, "issues": []}

# ✅ Pydantic 모델 사용
from common.contracts import AgentResult
return AgentResult(task_id=task_id, issues=[]).model_dump()
```

### 6-2. Optional 남용 금지

```python
# ❌ 모든 필드를 Optional로 선언
class MyOutput(BaseModel):
    task_id: Optional[str] = None
    issues: Optional[list] = None

# ✅ 실제로 없을 수 있는 필드만 Optional
class MyOutput(BaseModel):
    task_id: str                        # 항상 존재
    issues: List[IssueItem]             # 항상 존재 (빈 리스트도 OK)
    error_message: Optional[str] = None # 실패 시에만 존재
```

### 6-3. Enum 사용 의무

```python
# ❌ 문자열 리터럴 직접 사용
status = "success"

# ✅ Enum 사용
from common.state import AgentStatus
status = AgentStatus.SUCCESS
```

### 6-4. 타입 불일치 시 실패 처리

```python
model_config = ConfigDict(strict=True)  # 암묵적 타입 변환 금지
```

---

## §7. LangSmith Trace 규칙

### 7-1. 환경변수 설정 의무

```bash
LANGCHAIN_TRACING_V2=true
LANGCHAIN_API_KEY=ls__xxxx
# ⚠️ 반드시 모듈명 + GitHub ID 포함. 없으면 팀원 trace가 섞인다.
# 예: module1-alice, module2-bob
LANGCHAIN_PROJECT=module{N}-{yourGitHubId}
```

### 7-2. 모든 Agent 호출은 AgentHarness로 래핑

```python
from common.harness import AgentHarness
from common.trace import new_pipeline_trace, DocPipelineStage

# ❌ 직접 ainvoke
result = await my_graph.ainvoke(state)

# ✅ AgentHarness 래핑
trace_id = new_pipeline_trace(DocPipelineStage.MARKDOWN_CONVERT, doc_id=doc_id)
async with AgentHarness(trace_id=trace_id, agent_name="MyAgent", db_pool=pool) as h:
    result = await h.run(my_graph.ainvoke, state)
```

### 7-3. 기록 필수 항목

모든 trace는 다음 4개 필드를 포함해야 한다.

```python
# LangGraph config metadata에 자동 주입됨 (AgentHarness가 처리)
{
    "trace_id":   "trc_0001_3a9f1c2b",
    "task_id":    "uuid | null",
    "module_id":  "module_2",
    "agent_name": "StaticAnalysisAgent"
}
```

### 7-4. Timeout 처리 — try/except 위치 규칙

```python
# ✅ 올바른 패턴 — with 블록 바깥에서 TimeoutError 처리
try:
    async with AgentHarness(...) as harness:
        return await harness.run(fn, *args)
except asyncio.TimeoutError:
    return make_timeout_result(agent_name)  # status='fail' 자동 기록됨

# ❌ 잘못된 패턴 — with 블록 안에서 잡으면 status='success'로 기록됨
async with AgentHarness(...) as harness:
    try:
        return await harness.run(fn, *args)
    except asyncio.TimeoutError:            # __aexit__이 성공으로 판단
        return make_timeout_result(agent_name)
```

---

## §8. Harness 평가 규칙

### 8-1. 모듈별 최소 테스트 케이스

모든 모듈은 다음 케이스를 반드시 단위 테스트로 커버한다.

| 케이스 | 설명 |
|--------|------|
| **정상 케이스** | 유효한 입력 → 정상 Output Contract 반환 |
| **실패 케이스** | 잘못된 입력 → `status: fail` + `error_message` 기록 |
| **경계 케이스** | 빈 리스트, 최대 길이, null 값 등 |
| **타임아웃 케이스** | 30초 초과 → `make_timeout_result()` 반환 |
| **HITL 케이스** | 품질/점수 기준 미달 → `status: hitl_pending` 반환 |

### 8-2. 단위 테스트는 Mock 기반 (DB/LLM 없이 통과)

```python
@pytest.fixture
def mock_db_pool():
    with patch("module_2.static_analysis.get_pool") as m:
        yield AsyncMock()

async def test_static_analysis_normal_case(mock_db_pool):
    result = await static_analysis(state=make_test_state(), db_pool=mock_db_pool)
    assert result["status"] == "success"
    assert "task_id" in result
```

### 8-3. 평가 지표

| 지표 | 기준 |
|------|------|
| 단위 테스트 커버리지 | >= 80% (모듈별) |
| 정상/실패/경계 케이스 | 각 최소 1개 이상 |
| Mock 없이 통과 | 실제 DB/LLM 연결 없이 pytest 통과 |

---

## §9. HITL 규칙

### 9-1. Human Review 전환 조건

| 조건 | 임계값 | 처리 |
|------|--------|------|
| Markdown 품질 점수 | < 0.8 | HITL 큐 등록, 자동 진행 중단 |
| 표/이미지 구조 손실 | 발생 시 | HITL 큐 등록 |
| Chunk 길이 기준 초과/미달 | 발생 시 | HITL 큐 등록 |
| Critical 보안 이슈 | >= 1건 | 즉시 Slack 에스컬레이션 |
| 재작업 요청 횟수 | > 3회 | 시니어 직접 개입 요청 |
| Agent retry 소진 | 발생 시 | HITL 큐 등록 |

### 9-2. HITL 처리 코드 패턴

```python
if hitl_required:
    await hitl_queue.enqueue({
        "doc_id": doc_id,
        "reason": issues,
        "quality_score": score,
        "agent_name": agent_name,
        "status": "hitl_pending"
    })
    return {"status": "hitl_pending", "validated_markdown": None}
```

### 9-3. 자동 머지 절대 금지

**시니어의 최종 승인은 항상 사람이 한다.**  
코드 어디에도 PR을 자동으로 머지하는 로직을 작성하지 않는다.

---

## §10. Retry 규칙

### 10-1. 최대 재시도 횟수

```python
# 환경변수로 조정 가능 (기본값 준수)
MAX_RETRY_KMS_STAGE2   = int(os.getenv("STAGE2_MAX_FIX_ATTEMPTS", "2"))
MAX_RETRY_AGENT_DEFAULT = int(os.getenv("AGENT_MAX_RETRY", "3"))
```

### 10-2. 재시도 가능한 오류

```python
RETRYABLE_ERRORS = (
    asyncio.TimeoutError,           # 일시적 타임아웃
    json.JSONDecodeError,           # LLM 응답 파싱 실패 (1회만 재시도)
    asyncpg.TooManyConnectionsError, # DB 연결 과부하
    # HTTP 5xx (외부 API 일시 오류)
)
```

### 10-3. 재시도 불가능한 오류

```python
NON_RETRYABLE_ERRORS = (
    ValidationError,       # Pydantic 스키마 오류 — 코드 버그
    PermissionError,       # 권한 오류 — 재시도해도 동일
    # HTTP 4xx (클라이언트 오류 — 입력값 문제)
)
```

### 10-4. 재시도 후 실패 처리

```python
if retry_count >= MAX_RETRY:
    await agent_traces.record(status="fail", error_message=str(e))
    if is_hitl_eligible:
        return {"status": "hitl_pending"}
    return {"status": "fail", "error_message": "max_retry_exceeded"}
```

---

## §11. Logging 규칙

**모든 Agent 시작/종료 시 `agent_traces` 테이블에 아래 11개 필드를 기록한다.**

```python
# AgentHarness가 자동 처리 — 별도 구현 불필요
{
    "task_id":          "uuid | null",
    "trace_id":         "trc_0001_3a9f1c2b",
    "module_id":        "module_2",
    "agent_name":       "StaticAnalysisAgent",
    "status":           "running | success | fail | hitl_pending",
    "input_summary":    "PR #42, diff 1200 chars",      # 500자 이내 요약
    "output_summary":   "critical:0, major:2, minor:5",  # 500자 이내 요약
    "validation_result":"pass | fail | skip",
    "error_message":    "null | 오류 메시지",
    "execution_ms":     1200,
    "started_at":       "ISO8601",
    "ended_at":         "ISO8601"
}
```

**추가 규칙:**
- `input_summary` / `output_summary`는 민감 데이터(PII) 제외 후 기록
- LLM 원본 응답은 로그에 저장하지 않는다 (토큰 낭비 + 보안)
- DB 로그 실패는 경고만 남기고 에이전트 실행을 막지 않는다

---

## §12. Error Handling 규칙

### 오류 유형별 처리

| 오류 유형 | 처리 방식 | 예시 |
|-----------|-----------|------|
| **Recoverable** | 재시도 (최대 MAX_RETRY) | 타임아웃, LLM JSON 파싱 실패 |
| **Non-recoverable** | 즉시 fail + 상위 전파 | ValidationError, 권한 오류 |
| **Validation error** | 재시도 없이 fail | Pydantic 스키마 불일치 |
| **Tool error** | 재시도 1회 후 빈 결과 | 외부 CLI 도구 실패 |
| **External API error** | 429 → 60초 대기 후 1회 재시도 / 4xx → 즉시 fail | GitHub, Slack API |
| **DB error** | 로그만 남기고 계속 (agent_traces 기록 실패 시) | PostgreSQL 연결 오류 |

### 에러는 삼키지 않는다

```python
# ❌ 예외 삼키기
try:
    result = await agent.run(state)
except Exception:
    pass  # 절대 금지

# ✅ 기록 후 상위 전파
try:
    result = await agent.run(state)
except Exception as e:
    await agent_traces.record(status="fail", error_message=str(e))
    raise   # 상위 레이어에서 처리 결정
```

### GitHub API Rate Limit 처리

```python
# 429: 60초 대기 후 1회 재시도
# 401/403: 즉시 fail + Slack 에스컬레이션
async def handle_github_error(e: GitHubError):
    if e.status == 429:
        await asyncio.sleep(60)
        return await retry_once()
    if e.status in (401, 403):
        await slack_notify(f"GitHub API 인증 실패: {e}")
        raise
```

### Slack API 실패 처리

```python
# Slack 알림 실패는 무시 — 알림 실패가 전체 파이프라인을 막으면 안 됨
try:
    await slack_client.notify(message)
except Exception as e:
    logger.warning(f"Slack 알림 실패 (무시): {e}")
```

---

## 적용 체크리스트 (PR 머지 전 확인)

```
□ Agent 분류가 §1 기준에 맞는가? (Tool/LLM/Agent 구분)
□ Clean Architecture 의존성 방향이 맞는가?
□ PlatformState의 공통 필드를 재정의하지 않았는가?
□ Output Contract 10개 필드가 모두 존재하는가?
□ Validation 3단계가 구현되었는가?
□ 모든 모델이 Pydantic BaseModel인가?
□ LangSmith LANGCHAIN_PROJECT에 GitHub ID가 포함되었는가?
□ AgentHarness 없이 ainvoke를 직접 호출하지 않았는가?
□ TimeoutError를 with 블록 바깥에서 처리하는가?
□ 단위 테스트가 Mock 기반으로 DB/LLM 없이 통과하는가?
□ HITL 조건이 구현되었는가?
□ 자동 머지 코드가 없는가?
□ 에러를 삼키지 않는가?
```
