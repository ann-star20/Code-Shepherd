"""M5 GraphDB + YouTube 추천 서비스."""

from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from neo4j.exceptions import (
    ConfigurationError,
    Neo4jError,
    ServiceUnavailable,
    SessionExpired,
)
from shared.contracts import M5ExtractRequest, M5ExtractResponse
from shared.logging import TraceIDMiddleware, configure_logging

from app.graph_query import (
    ConceptGraphResponse,
    GraphOverviewResponse,
    MechanismGraphResponse,
    fetch_concept,
    fetch_mechanism,
    fetch_overview,
)
from app.keyword_builder import build_queries
from app.neo4j_client import close_driver
from app.schemas import RankedRecommendRequest, RankedRecommendResponse, VideoResult
from app.video_store import fetch_candidates

log = structlog.get_logger()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    configure_logging()
    yield
    await close_driver()


app = FastAPI(
    title="code-shepherd m5-graph-youtube", version="0.2.0", lifespan=lifespan
)
app.add_middleware(TraceIDMiddleware)


async def database_unavailable(_request: Request, exc: Exception) -> JSONResponse:
    log.warning("neo4j_unavailable", error=type(exc).__name__)
    return JSONResponse(
        status_code=503,
        content={
            "detail": "Neo4j를 사용할 수 없습니다. 연결 설정과 DB 실행 상태를 확인해 주세요."
        },
    )


for database_error in (
    Neo4jError,
    ServiceUnavailable,
    SessionExpired,
    ConfigurationError,
):
    app.add_exception_handler(database_error, database_unavailable)


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

    videos: list[VideoResult] = []
    seen: set[str] = set()
    for idx, query in enumerate(queries):
        for result in await fetch_candidates(concept.concept_name, query):
            if result["video_id"] in seen:
                continue
            seen.add(result["video_id"])
            videos.append(
                VideoResult(
                    is_mock=result.get("is_mock", False),
                    rank=idx + 1,
                    recommendation_type=labels.get(idx + 1, "관련 영상"),
                    query_used=query,
                    title=result["title"],
                    url=result["url"],
                    thumbnail=result.get("thumbnail"),
                    channel_title=result.get("channel_title"),
                )
            )
            break
    return RankedRecommendResponse(concept_name=concept.concept_name, videos=videos)
