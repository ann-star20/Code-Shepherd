"""
KMS 파이프라인 서버 — FastAPI 앱 진입점

실행:
    cd src && uvicorn main:app --host 0.0.0.0 --port 8001 --reload

환경변수: .env 파일 또는 시스템 환경변수
    POSTGRES_URL, GOOGLE_API_KEY, ANTHROPIC_API_KEY 등 (.env.example 참고)
"""
import logging
from pathlib import Path

from dotenv import load_dotenv

# src/ 안에서 실행할 때 한 단계 위 루트의 .env를 자동 로드
load_dotenv(Path(__file__).parent.parent / ".env")
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import module_0_kms.api as kms_api_module
import module_0_kms.chat_api as chat_api_module
import module_0_kms.hitl_api as hitl_api_module
from common.harness import create_db_pool
from module_0_kms.api import router as kms_router
from module_0_kms.chat_api import router as chat_router
from module_0_kms.hitl_api import router as hitl_router
from module_0_kms.pipeline.graph import build_pipeline
from module_0_kms.storage import get_storage

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """앱 시작 시 DB 풀 + Storage 초기화, 종료 시 정리."""
    pool = await create_db_pool()
    storage = get_storage()
    pipeline = build_pipeline(db_pool=pool, storage=storage)

    # 각 라우터 모듈에 풀/스토리지/파이프라인 공유
    kms_api_module._db_pool = pool
    kms_api_module._pipeline = pipeline
    kms_api_module._storage = storage
    hitl_api_module._db_pool = pool
    hitl_api_module._storage = storage
    chat_api_module._db_pool = pool

    logger.info("KMS 파이프라인 서버 시작 — DB 풀 + 파이프라인 준비 완료")
    yield

    await pool.close()
    logger.info("KMS 파이프라인 서버 종료")


app = FastAPI(
    title="KMS 문서 처리 파이프라인",
    version="1.0.0",
    description="사내 지식을 AI가 자동 구조화하고 저장하는 KMS 파이프라인 서버",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "*").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(kms_router)
app.include_router(hitl_router)
app.include_router(chat_router)


@app.get("/health", tags=["System"])
async def health() -> dict:
    """서버 상태 확인."""
    return {"status": "ok", "version": "1.0.0"}
