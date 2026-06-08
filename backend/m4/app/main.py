"""M4 커리큘럼·판정 스텁."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router as learning_router
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
# 프론트(Vite, localhost:5173)가 m4(localhost:8005)를 별도 포트로 직접 호출한다 (FRONTEND_SPEC Section 0
# m4Api) — api-core 프록시를 거치지 않는 cross-origin 호출이라 CORS 미들웨어가 없으면 preflight에서 막힌다.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(TraceIDMiddleware)
app.include_router(learning_router)


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
