"""M6 지식 그래프 엔드포인트 (스텁)."""

import json
import uuid
from typing import Any, Optional

import asyncpg
from fastapi import APIRouter, Query

from app.adapters.db.neo4j_repo import Neo4jConceptRepo
from app.core.config import pg_dsn
from app.core.neo4j_client import get_database, get_driver
from app.schemas.graph import GraphQueryRequest, GraphQueryResponse
from app.schemas.ingest import IngestRequest, IngestStatus

router = APIRouter(tags=["knowledge-graph"])


@router.get("/topology")
async def get_topology(session_id: Optional[str] = Query(default=None)) -> dict[str, list[dict]]:
    """전체 Concept 토폴로지 - 노드/엣지 (force-graph 뷰어용).

    session_id가 주어지면 staging_concepts의 DRAFT 항목을
    is_staging/is_new 플래그를 가진 노드로 함께 반환한다 (extract_advanced.md §2A).
    """
    repo = Neo4jConceptRepo(get_driver(), get_database())
    topology = await repo.get_topology()
    if session_id:
        draft_nodes = await _get_draft_staging_nodes(session_id)
        topology = {
            "nodes": [*topology["nodes"], *draft_nodes],
            "edges": topology["edges"],
        }
    return topology


async def _get_draft_staging_nodes(session_id: str) -> list[dict[str, Any]]:
    """staging_concepts state='DRAFT' 항목 → GraphNode (is_staging/is_new=true)."""
    conn = await asyncpg.connect(pg_dsn())
    try:
        rows = await conn.fetch(
            "SELECT id::text AS staging_id, concept_json, infer_action, "
            "       infer_confidence, target_concept_name "
            "FROM staging_concepts "
            "WHERE session_id = $1 AND state = 'DRAFT' "
            "ORDER BY created_at",
            uuid.UUID(session_id),
        )
    finally:
        await conn.close()
    return [_draft_to_graph_node(row) for row in rows]


def _draft_to_graph_node(row: Any) -> dict[str, Any]:
    concept_json = row["concept_json"]
    concept = json.loads(concept_json) if isinstance(concept_json, str) else concept_json
    return {
        "id": f"draft:{row['staging_id']}",
        "name": concept.get("concept_name"),
        "node_type": "Concept",
        "layer": "L2",
        "status": "DRAFT",
        "is_staging": True,
        "is_new": True,
        "domains": concept.get("domains", []),
        "infer_action": row["infer_action"],
        "infer_confidence": row["infer_confidence"],
        "target_concept_name": row["target_concept_name"],
        "cwe_id": concept.get("cwe_id"),
        "owasp_id": concept.get("owasp_id"),
        "severity": concept.get("severity"),
        "description_ko": concept.get("description_ko"),
        "aliases": concept.get("aliases", []),
        "mechanisms": concept.get("mechanism", []),
        "staging_id": row["staging_id"],
    }


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
