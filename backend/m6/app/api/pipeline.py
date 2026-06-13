"""파이프라인 트리거 + SSE 스트림 엔드포인트."""

from __future__ import annotations

import json
import uuid
from typing import AsyncGenerator

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, HttpUrl

from app.core.redis_client import get_redis
from app.worker.tasks import trigger_pipeline

router = APIRouter(prefix="/pipeline", tags=["pipeline"])


class TriggerRequest(BaseModel):
    doc_id: HttpUrl


class TriggerResponse(BaseModel):
    session_id: str
    message: str = "triggered"


@router.post("/trigger", response_model=TriggerResponse, status_code=202)
async def trigger(payload: TriggerRequest) -> TriggerResponse:
    """파이프라인 비동기 시작 - session_id 반환."""
    session_id = str(uuid.uuid4())
    trigger_pipeline(session_id, str(payload.doc_id))
    return TriggerResponse(session_id=session_id)


@router.get("/stream/{session_id}")
async def stream(session_id: str) -> StreamingResponse:
    """SSE 단일 채널 - pipeline 이벤트 구독."""

    async def event_generator() -> AsyncGenerator[str, None]:
        r = get_redis()
        pubsub = r.pubsub()
        await pubsub.subscribe(f"pipeline:{session_id}")
        yield f"data: {json.dumps({'type': 'connected'})}\n\n"
        heartbeat_counter = 0
        try:
            async for msg in pubsub.listen():
                if msg["type"] == "message":
                    yield f"data: {msg['data']}\n\n"
                    try:
                        data = json.loads(msg["data"])
                        if data.get("type") == "finished":
                            break
                    except (json.JSONDecodeError, TypeError):
                        pass
                heartbeat_counter += 1
                if heartbeat_counter % 15 == 0:
                    yield f"data: {json.dumps({'type': 'heartbeat'})}\n\n"
        finally:
            await pubsub.unsubscribe(f"pipeline:{session_id}")

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "X-Accel-Buffering": "no",
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )
