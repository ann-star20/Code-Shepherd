"""M6 지식 그래프 엔드포인트 (스텁)."""

import uuid

from fastapi import APIRouter

from app.adapters.db.neo4j_repo import Neo4jConceptRepo
from app.core.neo4j_client import get_database, get_driver
from app.schemas.graph import GraphQueryRequest, GraphQueryResponse
from app.schemas.ingest import IngestRequest, IngestStatus

router = APIRouter(tags=["knowledge-graph"])


@router.get("/topology")
async def get_topology() -> dict[str, list[dict]]:
    """전체 Concept 토폴로지 - 노드/엣지 (force-graph 뷰어용)."""
    repo = Neo4jConceptRepo(get_driver(), get_database())
    return await repo.get_topology()


@router.post("/ingest", status_code=202)
async def ingest_document(payload: IngestRequest) -> IngestStatus:
    """외부 문서 수집 → 지식 그래프 변환 태스크 등록 (스텁)."""
    task_id = str(uuid.uuid4())
    # TODO: celery_app.send_task("app.services.pipeline.ingest_document", ...)
    return IngestStatus(task_id=task_id, status="pending", message="Stub — pipeline not implemented yet")


@router.get("/status/{task_id}")
async def get_task_status(task_id: str) -> IngestStatus:
    """태스크 진행 상태 조회 (스텁)."""
    return IngestStatus(task_id=task_id, status="pending", message="Stub — status check not implemented yet")


@router.post("/query")
async def query_graph(payload: GraphQueryRequest) -> GraphQueryResponse:
    """지식 그래프 쿼리 (스텁)."""
    return GraphQueryResponse(nodes=[], edges=[], total=0)
