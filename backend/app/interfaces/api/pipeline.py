"""파이프라인 트리거 + 로그 조회 + SSE 실시간 스트림."""

import asyncio
import json
import uuid
from typing import AsyncIterator, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.interfaces.api._deps import get_conn

router = APIRouter(prefix="/api/pipeline", tags=["pipeline"])


def run_pipeline_task(session_id: str, doc_id: str):
    from app.worker.tasks import run_pipeline_task as _task

    return _task.delay(session_id=session_id, doc_id=doc_id)


# ── SSE 순수 헬퍼 ──────────────────────────────────────────────────────────────


def _format_sse(payload: dict) -> str:
    """RFC 8895 단일채널 SSE: data: JSON + 빈 줄."""
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


_STATE_STEP_MAP: dict[str, list[dict]] = {
    "CRAWLING": [
        {"agent": "Input", "status": "DONE"},
        {"agent": "Crawler", "status": "RUNNING"},
    ],
    "EXTRACTING": [
        {"agent": "Crawler", "status": "DONE"},
        {"agent": "Extractor", "status": "RUNNING"},
    ],
    "EXTRACTED": [
        {"agent": "Extractor", "status": "DONE"},
    ],
    "COMMITTED": [
        {"agent": "Writer", "status": "DONE"},
    ],
    "FAILED": [],
}


def _state_to_step_updates(state: str) -> list[dict]:
    """문서 DB 상태 → 프론트엔드 step_update 이벤트 목록."""
    return _STATE_STEP_MAP.get(state, [])


# ── GET /stream/{session_id} ───────────────────────────────────────────────────

_POLL_INTERVAL = 1.0  # seconds
_HEARTBEAT_INTERVAL = 15  # poll 횟수 단위


async def _event_stream(
    session_id: str,
    pool,
    request: Request,
) -> AsyncIterator[str]:
    """파이프라인 로그 + 상태 변이를 SSE로 푸시하는 비동기 제너레이터.

    - pipeline_logs: 신규 행마다 event: log 발행
    - knowledge_document.state: 변이 감지 시 event: step_update 발행
    - COMMITTED/FAILED 상태 도달 시 스트림 종료
    """
    last_ts: Optional[object] = None
    last_state: Optional[str] = None
    first_poll = True
    heartbeat_tick = 0

    while True:
        if await request.is_disconnected():
            break

        async with pool.acquire() as conn:
            # ── 신규 로그 수집 ─────────────────────────────────────────────
            if last_ts:
                rows = await conn.fetch(
                    "SELECT agent, level, message, created_at "
                    "FROM pipeline_logs "
                    "WHERE session_id = $1::uuid AND created_at > $2 "
                    "ORDER BY created_at",
                    session_id,
                    last_ts,
                )
            else:
                rows = await conn.fetch(
                    "SELECT agent, level, message, created_at "
                    "FROM pipeline_logs "
                    "WHERE session_id = $1::uuid "
                    "ORDER BY created_at",
                    session_id,
                )

            for row in rows:
                msg = f"[{row['agent']}] {row['message']}"
                yield _format_sse({"type": "log", "message": msg})
                last_ts = row["created_at"]

            # ── 문서 상태 변이 감지 ────────────────────────────────────────
            doc_row = await conn.fetchrow(
                "SELECT state FROM knowledge_document WHERE doc_id = "
                "(SELECT doc_id FROM pipeline_logs WHERE session_id=$1::uuid LIMIT 1)",
                session_id,
            )

            if doc_row:
                new_state: str = doc_row["state"]
                # 재연결 직후 첫 폴링에서 FAILED를 관측한 경우, 이는 재시도 이전의
                # 잔류 상태일 수 있으므로 즉시 종료하지 않고 한 번의 유예를 둔다.
                stale_failed_on_reconnect = first_poll and new_state == "FAILED"
                first_poll = False

                if stale_failed_on_reconnect:
                    # last_state를 갱신하지 않아, 다음 폴링에서 잔류 FAILED가
                    # 지속되든(genuine FAILED) EXTRACTED/COMMITTED로 바뀌든
                    # new_state != last_state 비교가 정상적으로 트리거되도록 한다.
                    pass
                elif new_state != last_state:
                    last_state = new_state
                    if new_state == "FAILED":
                        err_row = await conn.fetchrow(
                            "SELECT agent FROM pipeline_logs "
                            "WHERE session_id = $1::uuid AND level = 'ERROR' "
                            "ORDER BY created_at DESC LIMIT 1",
                            session_id,
                        )
                        if err_row:
                            yield _format_sse(
                                {
                                    "type": "step_update",
                                    "agent": err_row["agent"],
                                    "status": "FAILED",
                                }
                            )
                    else:
                        for update in _state_to_step_updates(new_state):
                            yield _format_sse({"type": "step_update", **update})

                if not stale_failed_on_reconnect and new_state in (
                    "COMMITTED",
                    "FAILED",
                ):
                    break

        # ── 주기적 하트비트 ────────────────────────────────────────────────
        heartbeat_tick += 1
        if heartbeat_tick % _HEARTBEAT_INTERVAL == 0:
            yield _format_sse({"type": "heartbeat"})

        await asyncio.sleep(_POLL_INTERVAL)


@router.get("/stream/{session_id}")
async def stream_pipeline(session_id: str, request: Request):
    """SSE 실시간 파이프라인 로그 스트림.

    Celery 워커가 pipeline_logs에 적재하거나 knowledge_document.state가 변이할 때마다
    이벤트를 푸시한다. COMMITTED/FAILED 도달 시 스트림 자동 종료.
    """
    pool = request.app.state.pool
    return StreamingResponse(
        _event_stream(session_id, pool, request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ── 스키마 ─────────────────────────────────────────────────────────────────────


class TriggerRequest(BaseModel):
    doc_id: str


class TriggerResponse(BaseModel):
    session_id: str
    doc_id: str
    message: str


# ── POST /trigger ──────────────────────────────────────────────────────────────


@router.post("/trigger", status_code=202, response_model=TriggerResponse)
async def trigger_pipeline(
    body: TriggerRequest,
    conn=Depends(get_conn),
):
    """PENDING 문서에 대해 파이프라인을 트리거하고 Celery 큐에 태스크를 적재."""
    row = await conn.fetchrow(
        "SELECT doc_id, state, original_url FROM knowledge_document WHERE doc_id = $1",
        body.doc_id,
    )
    if row is None:
        raise HTTPException(
            status_code=404, detail=f"document '{body.doc_id}' not found"
        )

    if row["state"] not in ("PENDING", "FAILED"):
        raise HTTPException(
            status_code=409,
            detail=f"document is in state '{row['state']}'; only PENDING/FAILED can be triggered",
        )

    session_id = str(uuid.uuid4())

    await conn.execute(
        """INSERT INTO pipeline_logs (doc_id, session_id, agent, level, message)
           VALUES ($1, $2, 'Input', 'INFO', '파이프라인 트리거됨')""",
        body.doc_id,
        session_id,
    )
    await conn.execute(
        "UPDATE knowledge_document SET state='CRAWLING', updated_at=now() WHERE doc_id=$1",
        body.doc_id,
    )

    try:
        run_pipeline_task(session_id=session_id, doc_id=body.doc_id)
    except Exception:
        pass

    return TriggerResponse(
        session_id=session_id,
        doc_id=body.doc_id,
        message="파이프라인이 시작되었습니다.",
    )


# ── 스키마 ─────────────────────────────────────────────────────────────────────


class ResumeRequest(BaseModel):
    resume_step: int


class ResumeResponse(BaseModel):
    session_id: str
    doc_id: str
    resumed_step: int
    message: str


# ── POST /{session_id}/resume ──────────────────────────────────────────────────


@router.post("/{session_id}/resume", response_model=ResumeResponse)
async def resume_pipeline(
    session_id: str,
    body: ResumeRequest,
    conn=Depends(get_conn),
):
    """FAILED 상태 파이프라인을 지정된 단계부터 재개."""
    doc_row = await conn.fetchrow(
        "SELECT doc_id FROM pipeline_logs WHERE session_id=$1::uuid LIMIT 1",
        session_id,
    )
    if doc_row is None:
        raise HTTPException(status_code=404, detail=f"session '{session_id}' not found")
    doc_id = doc_row["doc_id"]

    state_row = await conn.fetchrow(
        "SELECT state FROM knowledge_document WHERE doc_id=$1", doc_id
    )
    if state_row is None or state_row["state"] != "FAILED":
        current = state_row["state"] if state_row else "unknown"
        raise HTTPException(
            status_code=409,
            detail=f"document state must be FAILED to resume (current: {current})",
        )

    if body.resume_step in (1, 2, 3):
        target_agent = "Crawler"
    elif body.resume_step in (4, 5):
        approved = await conn.fetchval(
            "SELECT count(*) FROM staging_concepts WHERE session_id=$1::uuid AND state='APPROVED'",
            session_id,
        )
        if not approved:
            raise HTTPException(
                status_code=409,
                detail="재시도할 APPROVED 스테이징 항목이 없습니다. 먼저 승인하세요.",
            )
        target_agent = "Writer"
    else:
        raise HTTPException(
            status_code=400, detail=f"invalid resume_step: {body.resume_step}"
        )

    await conn.execute(
        """INSERT INTO pipeline_logs (doc_id, session_id, agent, level, message)
           VALUES ($1, $2::uuid, 'System', 'INFO', $3)""",
        doc_id,
        session_id,
        f"[RESUME] {body.resume_step}단계 재시도 트리거",
    )

    if target_agent == "Crawler":
        from app.worker.tasks import crawl_task

        crawl_task.delay(session_id=session_id, doc_id=doc_id)
    else:
        # write_graph_task는 완료/실패 시까지 knowledge_document.state를 변경하지 않으므로,
        # SSE 재연결 시 잔류 FAILED 상태로 즉시 종료되지 않도록 EXTRACTED로 되돌린다.
        await conn.execute(
            "UPDATE knowledge_document SET state='EXTRACTED', updated_at=now() WHERE doc_id=$1",
            doc_id,
        )
        from app.worker.tasks import write_graph_task

        write_graph_task.delay(session_id=session_id, doc_id=doc_id)

    return ResumeResponse(
        session_id=session_id,
        doc_id=doc_id,
        resumed_step=body.resume_step,
        message="재시도가 시작되었습니다.",
    )


# ── 스키마 ─────────────────────────────────────────────────────────────────────


class LogEntry(BaseModel):
    ts: str
    agent: str
    level: str
    message: str


class LogsResponse(BaseModel):
    session_id: str
    doc_state: Optional[str]
    logs: list[LogEntry]


# ── GET /logs/{session_id} ─────────────────────────────────────────────────────


@router.get("/logs/{session_id}", response_model=LogsResponse)
async def get_pipeline_logs(
    session_id: str,
    conn=Depends(get_conn),
):
    """session_id 기준 pipeline_logs 조회 + knowledge_document.state 반환."""
    rows = await conn.fetch(
        """SELECT l.agent, l.level, l.message, l.created_at
           FROM pipeline_logs l
           WHERE l.session_id = $1::uuid
           ORDER BY l.created_at""",
        session_id,
    )

    doc_state: Optional[str] = None
    if rows:
        doc_row = await conn.fetchrow(
            "SELECT state FROM knowledge_document WHERE doc_id = "
            "(SELECT doc_id FROM pipeline_logs WHERE session_id=$1::uuid LIMIT 1)",
            session_id,
        )
        if doc_row:
            doc_state = doc_row["state"]

    logs = [
        LogEntry(
            ts=str(r["created_at"]),
            agent=r["agent"],
            level=r["level"],
            message=r["message"],
        )
        for r in rows
    ]

    return LogsResponse(session_id=session_id, doc_state=doc_state, logs=logs)
