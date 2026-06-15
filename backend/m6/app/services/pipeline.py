"""Celery 태스크 — 외부 문서 → 지식 그래프 파이프라인 스텁."""

import uuid

from celery_app import celery_app


@celery_app.task(name="app.services.pipeline.ingest_document", queue="m6_graph")
def ingest_document(payload: dict) -> dict:
    """
    외부 문서 수집 → 엔티티 추출 → Neo4j 저장 파이프라인.

    payload: {"url": str, "title": str|None, "tags": list[str]}

    TODO:
      1. doc_crawler.fetch_text(url) — 본문 추출
      2. LLM 엔티티 추출 (Gemini Flash)
      3. graph_store.upsert_document_node / upsert_entity_node / create_relation
    """
    task_id = celery_app.current_task.request.id or str(uuid.uuid4())
    return {
        "task_id": task_id,
        "status": "pending",
        "message": "Stub — pipeline not implemented yet",
    }
