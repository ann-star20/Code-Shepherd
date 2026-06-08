"""M0 KMS — FastAPI 진입점."""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from shared.contracts import M0IngestRequest, M0IngestResponse
from shared.db import _AsyncSessionFactory
from shared.logging import TraceIDMiddleware, configure_logging

import app.routes.kms_routes as kms_routes
import app.routes.hitl_routes as hitl_routes
import app.routes.chat_routes as chat_routes


@asynccontextmanager
async def lifespan(_app: FastAPI):
    configure_logging()

    from app.storage import get_storage
    from app.pipeline.graph import build_pipeline
    from app.categories_db import get_valid_categories
    import app.pipeline._category_definitions as _cat_defs

    session_factory = _AsyncSessionFactory
    storage = get_storage()
    pipeline = build_pipeline(db_session_factory=session_factory, storage=storage)

    # DB 카테고리를 로드해 VALID_CATEGORIES 갱신 (KB Evolution으로 추가된 카테고리 반영)
    try:
        db_categories = await get_valid_categories(session_factory)
        if db_categories:
            _cat_defs.VALID_CATEGORIES = db_categories
    except Exception:
        pass  # DB 연결 실패 시 하드코딩 frozenset 유지

    # 라우터 모듈에 싱글턴 주입
    kms_routes._db_session_factory = session_factory
    kms_routes._pipeline = pipeline
    kms_routes._storage = storage

    hitl_routes._db_session_factory = session_factory
    hitl_routes._storage = storage

    chat_routes._db_session_factory = session_factory
    chat_routes._storage = storage

    yield


app = FastAPI(title="code-shepherd m0-kms", version="0.1.0", lifespan=lifespan)
app.add_middleware(TraceIDMiddleware)

app.include_router(kms_routes.router)
app.include_router(hitl_routes.router)
app.include_router(chat_routes.router)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "m0-kms"}


@app.post("/ingest", response_model=M0IngestResponse)
async def ingest(payload: M0IngestRequest) -> M0IngestResponse:
    """M1 오케스트레이터용 계약 엔드포인트 — 문서 업로드는 /kms/upload 사용."""
    return M0IngestResponse(
        task_id=payload.task_id,
        status="accepted",
        message="KMS pipeline started. Use /kms/status/{doc_id} to poll.",
    )
