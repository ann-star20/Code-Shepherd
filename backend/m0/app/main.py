"""M0 KMS 인제스트 스텁 — /health + /ingest 계약 엔드포인트."""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from shared.contracts import M0IngestRequest, M0IngestResponse
from shared.logging import TraceIDMiddleware, configure_logging


@asynccontextmanager
async def lifespan(_app: FastAPI):
    configure_logging()
    yield


app = FastAPI(title="code-shepherd m0-kms-stub", version="0.1.0", lifespan=lifespan)
app.add_middleware(TraceIDMiddleware)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "m0-kms"}


@app.post("/ingest", response_model=M0IngestResponse)
async def ingest(payload: M0IngestRequest) -> M0IngestResponse:
    """KMS 인제스트 스텁 — 담당자가 실제 파이프라인으로 교체."""
    return M0IngestResponse(
        task_id=payload.task_id,
        status="accepted",
        message="Stub — KMS ingest pipeline not implemented yet",
    )
