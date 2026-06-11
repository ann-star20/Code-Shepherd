# 파이프라인 단계 재시도 — `POST /api/pipeline/{session_id}/resume` 구현

## Context

프론트엔드 `handleRetryStep`(`frontend/src/pages/MainPage.tsx:944-954`)은 이미 구현되어
있다 — `PipelineStepList`에서 FAILED 상태 스텝에 호버하면 나타나는 RETRY 버튼을 누르면
`POST /api/pipeline/{sessionId}/resume`을 `{ resume_step: step }` 바디로 호출한다.

문제: 백엔드 `backend/app/interfaces/api/pipeline.py`의 `/api/pipeline` 라우터에는
`/trigger`, `/stream/{session_id}`, `/logs/{session_id}`만 존재하고 `/resume`이 없어
**`POST /api/pipeline/{session_id}/resume` → 404**가 발생한다. 또한 응답을 받은 뒤에도
프론트가 SSE를 재연결하지 않으므로(실패 시 `closeSSE()`로 이미 닫혀있음), 엔드포인트가
생겨도 진행 상황이 갱신되지 않는다.

목표: 실패한 파이프라인을 해당 단계부터 재개하는 백엔드 엔드포인트를 구현하고, 프론트엔드가
재개 후 SSE를 재연결해 스피너→✓ 전환이 정상적으로 보이도록 한다.

## Critical Files

- `backend/app/interfaces/api/pipeline.py` — 신규 `POST /{session_id}/resume` 라우트 추가
- `backend/app/worker/tasks.py`
  - L70-100 `crawl_task`: FAILED 상태 감지 버그 수정 (재시도 시 클린 리부팅이 실제로
    동작하려면 필요)
- `frontend/src/pages/MainPage.tsx`
  - L944-954 `handleRetryStep`: 응답 처리 + SSE 재연결 + 에러 핸들링
- `backend/tests/harness/test_pipeline_resume_api.py` (신규) — `test_pipeline_logs_api.py`
  패턴(`_make_test_app`, `asyncpg_pool` fixture, httpx ASGITransport) 재사용

## Changes

### 1. `crawl_task`의 FAILED 감지 버그 수정 (`tasks.py` L75-87)

현재 코드:
```python
cur.execute("SELECT original_url FROM documents WHERE doc_id=%s", (doc_id,))
row = cur.fetchone()
if row and row[0] == 'FAILED':   # row[0]은 original_url — 항상 False
    ...클린 리부팅(스테이징/로그 삭제 + state→PENDING)...
if not row:
    raise ValueError(...)
url = row[0]
```

`state`를 함께 조회하도록 수정:
```python
cur.execute("SELECT state, original_url FROM documents WHERE doc_id=%s", (doc_id,))
row = cur.fetchone()
if row and row[0] == 'FAILED':
    ...(클린 리부팅 로직 동일)...
if not row:
    raise ValueError(...)
url = row[1]
```

이 수정이 없으면 1~3단계 재시도 시 이전 실패 런의 `staging_concepts`/`pipeline_logs`가
남아 중복 적재된다.

### 2. `POST /api/pipeline/{session_id}/resume` 신규 라우트 (`pipeline.py`)

`/trigger`와 `/logs/{session_id}` 사이에 추가. `get_pipeline_logs`와 동일한 패턴으로
`pipeline_logs`에서 `doc_id`를 역조회한다.

```python
class ResumeRequest(BaseModel):
    resume_step: int


class ResumeResponse(BaseModel):
    session_id: str
    doc_id: str
    resumed_step: int
    message: str


@router.post("/{session_id}/resume", response_model=ResumeResponse)
async def resume_pipeline(session_id: str, body: ResumeRequest, conn=Depends(get_conn)):
    doc_row = await conn.fetchrow(
        "SELECT doc_id FROM pipeline_logs WHERE session_id=$1::uuid LIMIT 1", session_id,
    )
    if doc_row is None:
        raise HTTPException(status_code=404, detail=f"session '{session_id}' not found")
    doc_id = doc_row["doc_id"]

    state_row = await conn.fetchrow("SELECT state FROM documents WHERE doc_id=$1", doc_id)
    if state_row is None or state_row["state"] != "FAILED":
        current = state_row["state"] if state_row else "unknown"
        raise HTTPException(status_code=409, detail=f"document state must be FAILED to resume (current: {current})")

    if body.resume_step in (1, 2, 3):
        target_agent = "Crawler"
    elif body.resume_step in (4, 5):
        approved = await conn.fetchval(
            "SELECT count(*) FROM staging_concepts WHERE session_id=$1::uuid AND state='APPROVED'",
            session_id,
        )
        if not approved:
            raise HTTPException(status_code=409, detail="재시도할 APPROVED 스테이징 항목이 없습니다. 먼저 승인하세요.")
        target_agent = "Writer"
    else:
        raise HTTPException(status_code=400, detail=f"invalid resume_step: {body.resume_step}")

    await conn.execute(
        """INSERT INTO pipeline_logs (doc_id, session_id, agent, level, message)
           VALUES ($1, $2::uuid, 'System', 'INFO', $3)""",
        doc_id, session_id, f"[RESUME] {body.resume_step}단계 재시도 트리거",
    )

    if target_agent == "Crawler":
        from app.worker.tasks import crawl_task
        crawl_task.delay(session_id=session_id, doc_id=doc_id)
    else:
        await conn.execute("UPDATE documents SET state='APPROVED', updated_at=now() WHERE doc_id=$1", doc_id)
        from app.worker.tasks import write_graph_task
        write_graph_task.delay(session_id=session_id, doc_id=doc_id)

    return ResumeResponse(session_id=session_id, doc_id=doc_id, resumed_step=body.resume_step, message="재시도가 시작되었습니다.")
```

동작 매핑:
- `resume_step` 1~3 (Prescan/Crawler/Extractor) → `crawl_task.delay()` 재호출. 수정된
  FAILED 감지 로직이 스테이징/로그를 정리하고 `PENDING`→`CRAWLING`부터 전체 파이프라인을
  다시 진행한다.
- `resume_step` 4~5 (Graph Writer/Link Resolve) → `staging_concepts`에 `APPROVED` 행이
  있어야 하며, `documents.state`를 `APPROVED`로 되돌린 뒤 `write_graph_task.delay()`만
  재호출 (재추출 없이 그래프 적재/하이브리드 수렴만 재시도).

### 3. 프론트엔드 `handleRetryStep` 수정 (`MainPage.tsx` L944-954)

```tsx
const handleRetryStep = useCallback((step: number) => {
  addLog("SYSTEM", `[RETRY] ${step}단계 재시도 요청`);
  setStepStatuses(s => ({ ...s, [step]: "LOADING" as StepStatus }));
  setPipelineState("RUNNING");
  const sid = sessionIdRef.current;
  if (!sid) return;
  fetch(`/api/pipeline/${sid}/resume`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ resume_step: step }),
  })
    .then((res) => {
      if (!res.ok) throw new Error(`resume failed: ${res.status}`);
      startSSE(sid);
    })
    .catch(() => {
      setStepStatuses(s => ({ ...s, [step]: "FAILED" as StepStatus }));
      setPipelineState("ERROR");
      addToast("error", `${step}단계 재시도 요청 실패`);
    });
}, [addLog, addToast, startSSE]);
```

- 성공 시 `startSSE(sid)`로 SSE를 재연결 — FAILED 도달 시 `closeSSE()`로 닫혔던 채널을
  복구해 재개된 파이프라인의 `step_update`/`log` 이벤트를 다시 수신.
- 실패(404/409/네트워크 오류) 시 스텝 상태를 다시 FAILED로 되돌리고 토스트로 알림 —
  기존의 `.catch(() => {})` 무응답 처리 제거.
- `useCallback` 의존성 배열에 `addToast`, `startSSE` 추가 (`startSSE`는 L600에서 이미
  `useCallback`으로 정의되어 있어 안정적인 참조).

## Out of Scope

- `AGENT_STEP_MAP`(L190-196)의 `Writer`/`Resolver` → step 5 단일 매핑 재설계 — step 4
  ("Graph Writer")는 현재 SSE에서 FAILED를 받을 수 없어 RETRY 버튼이 노출되지 않는
  기존 동작 그대로 유지. resume 엔드포인트는 대칭성을 위해 4도 처리하지만 실사용 경로는
  주로 2/3/5.
- `write_staging_draft`의 멱등성/중복 적재 로직 자체 — 1~3단계 재시도 시 클린 리부팅
  (스테이징 삭제)으로 우회.
- Celery 태스크의 `max_retries`/backoff 설정 변경.

## Verification

1. `cd backend && pytest tests/harness/test_pipeline_resume_api.py -v` — 신규 테스트:
   - FAILED 문서 + resume_step=2 → 200, `pipeline_logs`에 `[RESUME]` 행 삽입, `crawl_task.delay`
     호출 확인 (monkeypatch)
   - documents.state != FAILED → 409
   - resume_step=5 + APPROVED staging 없음 → 409
   - resume_step=5 + APPROVED staging 존재 → 200, `documents.state` → APPROVED,
     `write_graph_task.delay` 호출 확인
   - 알 수 없는 session_id → 404
2. `cd backend && pytest tests/harness/test_pipeline_task_impl.py tests/harness/test_pipeline.py -v`
   — `crawl_task` FAILED 감지 수정으로 인한 회귀 없는지 확인
3. `cd frontend && npx tsc --noEmit --pretty false`
4. `cd frontend && npx vitest run src/pages/__tests__/MainPage.test.tsx` — 기존 베이스라인
   (3 failed / 24 passed, 이번 세션 이전과 동일) 유지 확인
5. 수동 확인: 개발 서버에서 파이프라인 트리거 → Extractor 강제 실패(예: 빈 응답) →
   FAILED 스텝 RETRY 클릭 → `POST /resume` 200 응답(404 아님) → 스피너 표시 →
   재실행된 파이프라인 진행에 따라 ✓ 전환되는지 확인
