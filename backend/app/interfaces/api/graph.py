"""GET /api/graph/topology — 4-레이어 지식 그래프 토폴로지 조회."""

from typing import Optional

from fastapi import APIRouter, Query, Request

from app.adapters.db.neo4j_repo import Neo4jConceptRepo

router = APIRouter(prefix="/api/graph", tags=["graph"])


@router.get("/topology")
async def get_topology(
    request: Request,
    domains: Optional[list[str]] = Query(default=None),
    limit: int = Query(default=200, ge=1, le=1000),
):
    """4-레이어 전체 토폴로지를 nodes/edges 형태로 반환."""
    driver = request.app.state.neo4j_driver
    repo = Neo4jConceptRepo(driver)
    return await repo.get_topology(domains=domains, limit=limit)
