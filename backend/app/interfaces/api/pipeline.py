"""P1-T11: POST /api/pipeline/trigger — 파이프라인 트리거."""

import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.interfaces.api._deps import get_conn

router = APIRouter(prefix="/api/pipeline", tags=["pipeline"])

# Celery 태스크는 worker 모듈에서 import — 순환 방지를 위해 지연 import
def run_pipeline_task(session_id: str, doc_id: str):  # noqa: F811
    """Celery 태스크 지연 import 래퍼 (테스트에서 patch 대상)."""
    from app.worker.tasks import run_pipeline_task as _task
    return _task.delay(session_id=session_id, doc_id=doc_id)


# ── 스키마 ─────────────────────────────────────────────────────────────────

class TriggerRequest(BaseModel):
    doc_id: str


class TriggerResponse(BaseModel):
    session_id: str
    doc_id: str
    message: str


# ── 엔드포인트 ─────────────────────────────────────────────────────────────

@router.post("/trigger", status_code=202, response_model=TriggerResponse)
async def trigger_pipeline(
    body: TriggerRequest,
    conn=Depends(get_conn),
):
    """PENDING 문서에 대해 파이프라인을 트리거하고 Celery 큐에 태스크를 적재."""
    row = await conn.fetchrow(
        "SELECT doc_id, state, original_url FROM documents WHERE doc_id = $1",
        body.doc_id,
    )
    if row is None:
        raise HTTPException(status_code=404, detail=f"document '{body.doc_id}' not found")

    if row["state"] not in ("PENDING", "FAILED"):
        raise HTTPException(
            status_code=409,
            detail=f"document is in state '{row['state']}'; only PENDING/FAILED can be triggered",
        )

    session_id = str(uuid.uuid4())

    # pipeline_logs 기록
    await conn.execute(
        """INSERT INTO pipeline_logs (doc_id, session_id, agent, level, message)
           VALUES ($1, $2, 'Input', 'INFO', '파이프라인 트리거됨')""",
        body.doc_id, session_id,
    )

    # CRAWLING 상태로 전이
    await conn.execute(
        "UPDATE documents SET state='CRAWLING', updated_at=now() WHERE doc_id=$1",
        body.doc_id,
    )

    # Celery 큐 적재 (import 실패해도 202 반환 — worker가 미기동일 수 있음)
    try:
        run_pipeline_task(session_id=session_id, doc_id=body.doc_id)
    except Exception:
        pass

    return TriggerResponse(
        session_id=session_id,
        doc_id=body.doc_id,
        message="파이프라인이 시작되었습니다.",
    )
