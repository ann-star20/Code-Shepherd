"""GET /api/graph/* — 지식 그래프 토폴로지 및 코드 예제 조회."""

from typing import Optional

from fastapi import APIRouter, Query, Request

from app.adapters.db.neo4j_repo import Neo4jConceptRepo

router = APIRouter(prefix="/api/graph", tags=["graph"])


@router.get("/topology")
async def get_topology(
    request: Request,
    domains: Optional[list[str]] = Query(default=None),
    search: Optional[str] = Query(default=None),
    limit: int = Query(default=200, ge=1, le=1000),
):
    """3-레이어 토폴로지(Domain→Concept→Mechanism)를 nodes/edges 형태로 반환."""
    driver = request.app.state.neo4j_driver
    repo = Neo4jConceptRepo(driver)
    return await repo.get_topology(domains=domains, search=search, limit=limit)


@router.get("/concept/{name}/code")
async def get_concept_code(
    name: str,
    request: Request,
    lang: Optional[str] = Query(default=None),
    framework: Optional[str] = Query(default=None),
):
    """Concept → Mechanism → CodeExample 경로 조회.

    lang / framework 쿼리 파라미터로 좁힌다. 생략 시 모든 예제를 반환한다.
    """
    driver = request.app.state.neo4j_driver
    repo = Neo4jConceptRepo(driver)
    return await repo.get_concept_code(name=name, lang=lang, framework=framework)
