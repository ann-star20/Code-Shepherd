"""M3 테스트 검증·성능 분석 스텁."""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from shared.contracts import M3VerifyRequest, M3VerifyResponse
from shared.logging import TraceIDMiddleware, configure_logging


@asynccontextmanager
async def lifespan(_app: FastAPI):
    configure_logging()
    yield


app = FastAPI(title="code-shepherd m3-verify-stub", version="0.1.0", lifespan=lifespan)
app.add_middleware(TraceIDMiddleware)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "m3-verify"}


@app.post("/verify/tests", response_model=M3VerifyResponse)
async def verify_tests(payload: M3VerifyRequest) -> M3VerifyResponse:
    """테스트 검증 스텁."""
    return M3VerifyResponse(
        task_id=payload.task_id,
        agent="test_verification",
        issues=[],
        execution_ms=0,
    )


@app.post("/analyze/performance", response_model=M3VerifyResponse)
async def analyze_performance(payload: M3VerifyRequest) -> M3VerifyResponse:
    """성능 분석 스텁."""
    return M3VerifyResponse(
        task_id=payload.task_id,
        agent="performance",
        issues=[],
        execution_ms=0,
    )
