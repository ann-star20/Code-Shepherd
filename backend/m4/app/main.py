"""M4 커리큘럼·판정 스텁."""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from shared.contracts import (
    M4CurriculumRequest,
    M4CurriculumResponse,
    M4EvaluateRequest,
    M4EvaluateResponse,
)
from shared.logging import TraceIDMiddleware, configure_logging


@asynccontextmanager
async def lifespan(_app: FastAPI):
    configure_logging()
    yield


app = FastAPI(title="code-shepherd m4-curriculum-stub", version="0.1.0", lifespan=lifespan)
app.add_middleware(TraceIDMiddleware)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "m4-curriculum"}


@app.post("/evaluate", response_model=M4EvaluateResponse)
async def evaluate(payload: M4EvaluateRequest) -> M4EvaluateResponse:
    """평가·판정 스텁."""
    return M4EvaluateResponse(
        task_id=payload.task_id,
        pr_id=payload.pr_id,
        verdict="lgtm",
        comment_body="Stub — evaluation pipeline not implemented yet",
        execution_ms=0,
    )


@app.post("/curriculum", response_model=M4CurriculumResponse)
async def curriculum(payload: M4CurriculumRequest) -> M4CurriculumResponse:
    """커리큘럼 생성 스텁."""
    return M4CurriculumResponse(
        task_id=payload.task_id,
        developer_id=payload.developer.id,
        roadmap=[],
        message="Stub — curriculum generation not implemented yet",
    )
