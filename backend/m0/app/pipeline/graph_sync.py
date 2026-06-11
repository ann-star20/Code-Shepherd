"""
Graph Sync Agent — 교체(replace) 시 이전 문서 버전 4개 저장소에서 정리

PG:      chunks, chunk_embeddings, agent_traces, documents 삭제
Neo4j:   Document 노드 + 연결 관계 삭제
GCS:     images/{old_doc_id}/ 경로 아래 모든 파일 삭제
"""
from __future__ import annotations

import logging
import os

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


async def sync_old_document_version(
    old_doc_id: str,
    session: AsyncSession,
    delete_gcs: bool = True,
    delete_neo4j: bool = True,
) -> None:
    """
    이전 버전 문서 데이터를 4개 저장소에서 일괄 삭제한다.

    순서:
      1. PG — chunks, chunk_embeddings는 FK cascade, agent_traces, documents
      2. Neo4j — Document 노드 + 연결된 엔티티 관계
      3. GCS — images/{old_doc_id}/ 이미지
    """
    # PG: FK cascade 덕분에 documents 삭제 시 chunks, chunk_embeddings도 자동 삭제.
    # agent_traces는 별도 FK 구조에 따라 직접 삭제.
    await session.execute(
        text("DELETE FROM agent_traces WHERE doc_id = :doc_id"),
        {"doc_id": old_doc_id},
    )
    await session.execute(
        text("DELETE FROM documents WHERE doc_id = :doc_id"),
        {"doc_id": old_doc_id},
    )
    await session.commit()
    logger.info(f"[GraphSync] PG 삭제 완료: doc_id={old_doc_id}")

    if delete_neo4j:
        await _delete_neo4j_document(old_doc_id)

    if delete_gcs:
        await _delete_gcs_images(old_doc_id)


async def _delete_neo4j_document(doc_id: str) -> None:
    """Neo4j에서 Document 노드와 연결된 모든 관계를 삭제한다."""
    neo4j_uri = os.getenv("NEO4J_URI", "bolt://host.docker.internal:7687")
    neo4j_user = os.getenv("NEO4J_USER", "neo4j")
    neo4j_password = os.getenv("NEO4J_PASSWORD", "password")

    try:
        from neo4j import AsyncGraphDatabase
    except ImportError:
        logger.warning("[GraphSync] neo4j 패키지 미설치 — Neo4j 삭제 건너뜁니다.")
        return

    driver = AsyncGraphDatabase.driver(neo4j_uri, auth=(neo4j_user, neo4j_password))
    try:
        async with driver.session() as neo_session:
            await neo_session.run(
                """
                MATCH (d:Document {doc_id: $doc_id})
                OPTIONAL MATCH (d)-[r]-()
                DELETE r, d
                """,
                doc_id=doc_id,
            )
        logger.info(f"[GraphSync] Neo4j 삭제 완료: doc_id={doc_id}")
    except Exception as e:
        logger.error(f"[GraphSync] Neo4j 삭제 실패 doc_id={doc_id}: {e}")
    finally:
        await driver.close()


async def _delete_gcs_images(doc_id: str) -> None:
    """GCS images/{doc_id}/ 하위 모든 이미지를 삭제한다."""
    from app.routes.kms_routes import _get_storage

    try:
        storage = _get_storage()
        prefix = f"images/{doc_id}/"
        paths = await storage.list_prefix(prefix)
        for path in paths:
            try:
                await storage.delete(path)
            except Exception as e:
                logger.warning(f"[GraphSync] GCS 파일 삭제 실패 {path}: {e}")
        logger.info(f"[GraphSync] GCS 삭제 완료: {len(paths)}개 파일, prefix={prefix}")
    except Exception as e:
        logger.error(f"[GraphSync] GCS 삭제 실패 doc_id={doc_id}: {e}")
