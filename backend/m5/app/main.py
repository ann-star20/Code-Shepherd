"""M5 GraphDB + YouTube 스텁 — Module 1과 독립."""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from shared.contracts import (
    M5ExtractRequest,
    M5ExtractResponse,
    M5YoutubeRecommendRequest,
    M5YoutubeRecommendResponse,
)
from shared.logging import TraceIDMiddleware, configure_logging


@asynccontextmanager
async def lifespan(_app: FastAPI):
    configure_logging()
    yield


app = FastAPI(title="code-shepherd m5-graph-youtube-stub", version="0.1.0", lifespan=lifespan)
app.add_middleware(TraceIDMiddleware)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "m5-graph-youtube"}


@app.post("/extract", response_model=M5ExtractResponse)
async def extract(payload: M5ExtractRequest) -> M5ExtractResponse:
    """엔티티/관계 추출 → Neo4j 스텁."""
    return M5ExtractResponse(
        task_id=payload.task_id,
        doc_id=payload.doc_id,
        status="accepted",
        message="Stub — entity extraction and Neo4j write not implemented yet",
    )


@app.post("/youtube/recommend", response_model=M5YoutubeRecommendResponse)
async def youtube_recommend(
    payload: M5YoutubeRecommendRequest,
) -> M5YoutubeRecommendResponse:
    """YouTube 학습 자료 추천 스텁."""
    return M5YoutubeRecommendResponse(
        task_id=payload.task_id,
        videos=[],
        message="Stub — YouTube recommendation not implemented yet",
    )
