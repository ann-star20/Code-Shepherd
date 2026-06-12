"""M6 지식 그래프 엔드포인트 (스텁)."""

import uuid

from fastapi import APIRouter

from app.schemas.graph import GraphQueryRequest, GraphQueryResponse
from app.schemas.ingest import IngestRequest, IngestStatus

router = APIRouter(tags=["knowledge-graph"])


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
