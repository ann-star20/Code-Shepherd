"""M5 GraphDB + YouTube 추천 서비스."""

import os
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, HTTPException, Query

from shared.contracts import M5ExtractRequest, M5ExtractResponse
from shared.logging import TraceIDMiddleware, configure_logging
from app.neo4j_client import close_driver
from app.graph_query import (
    fetch_concept,
    fetch_mechanism,
    fetch_overview,
    ConceptGraphResponse,
    MechanismGraphResponse,
    GraphOverviewResponse,
)
from app.schemas import RankedRecommendRequest, RankedRecommendResponse, VideoResult
from app.keyword_builder import build_queries
from app.youtube_client import search_one

log = structlog.get_logger()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    configure_logging()
    yield
    await close_driver()


app = FastAPI(title="code-shepherd m5-graph-youtube", version="0.2.0", lifespan=lifespan)
app.add_middleware(TraceIDMiddleware)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "m5-graph-youtube"}


@app.post("/extract", response_model=M5ExtractResponse)
async def extract(payload: M5ExtractRequest) -> M5ExtractResponse:
    return M5ExtractResponse(
        task_id=payload.task_id,
        doc_id=payload.doc_id,
        status="accepted",
        message="Stub — entity extraction not implemented yet",
    )


# ── Graph 조회 API ────────────────────────────────────────────────────────────

@app.get("/graph/overview", response_model=GraphOverviewResponse)
async def get_graph_overview() -> GraphOverviewResponse:
    """전체 Concept·Mechanism 노드 목록 반환 — 프론트 초기 그래프 렌더용."""
    return await fetch_overview()


@app.get("/graph/concept", response_model=ConceptGraphResponse)
async def get_concept(
    keyword: str = Query(..., description="조회할 Concept 이름 (대소문자 무관)"),
) -> ConceptGraphResponse:
    result = await fetch_concept(keyword)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Concept '{keyword}' not found")
    return result


@app.get("/graph/mechanism/{mechanism_name}", response_model=MechanismGraphResponse)
async def get_mechanism(mechanism_name: str) -> MechanismGraphResponse:
    result = await fetch_mechanism(mechanism_name)
    if result is None:
        raise HTTPException(
            status_code=404, detail=f"Mechanism '{mechanism_name}' not found"
        )
    return result


# ── YouTube 랭킹 추천 API ─────────────────────────────────────────────────────

@app.post("/youtube/ranked", response_model=RankedRecommendResponse)
async def youtube_ranked(payload: RankedRecommendRequest) -> RankedRecommendResponse:
    """컨셉·매커니즘·코드 선택 상태에 따라 5개 YouTube 영상을 랭킹 순으로 추천한다."""
    if not os.getenv("YOUTUBE_API_KEY"):
        raise HTTPException(
            status_code=503,
            detail="YOUTUBE_API_KEY가 설정되지 않았습니다. .env에 키를 추가해 주세요.",
        )

    concept = await fetch_concept(payload.concept_name)
    if concept is None:
        raise HTTPException(
            status_code=404, detail=f"Concept '{payload.concept_name}' not found"
        )

    queries, labels = build_queries(
        concept_name=concept.concept_name,
        mechanism_name=payload.mechanism_name,
        code_lang=payload.code_lang,
        code_framework=payload.code_framework,
        cwe_id=concept.cwe_id,
        owasp_id=concept.owasp_id,
        affected_components=concept.affected_components,
    )

    # 각 쿼리당 YouTube API 1회 호출 — 순차 처리로 API quota 안전하게 관리
    videos: list[VideoResult] = []
    for idx, query in enumerate(queries):
        rank = idx + 1
        try:
            result = await search_one(query)
        except Exception as exc:
            # URL에 API 키가 포함되므로 exc 메시지 전체를 로그에 남기지 않는다
            safe_error = type(exc).__name__
            if hasattr(exc, "response") and exc.response is not None:  # type: ignore[union-attr]
                safe_error += f" {exc.response.status_code}"  # type: ignore[union-attr]
            log.warning("youtube_search_failed", rank=rank, query=query, error=safe_error)
            result = None

        if result:
            videos.append(
                VideoResult(
                    rank=rank,
                    recommendation_type=labels.get(rank, "관련 영상"),
                    query_used=query,
                    title=result["title"],
                    url=result["url"],
                    thumbnail=result.get("thumbnail"),
                    channel_title=result.get("channel_title"),
                )
            )

    return RankedRecommendResponse(concept_name=concept.concept_name, videos=videos)
