"""Celery 파이프라인 태스크 — Phase 2 실제 구현 연결.

각 단계는 asyncio.run()으로 async 구현체를 호출한다.
psycopg2: 상태/로그 기록 (동기), asyncpg: 데이터 적재 (비동기).
"""

import asyncio
import json
import logging
import os

import asyncpg
import psycopg2

from app.worker.celery_app import celery_app

logger = logging.getLogger(__name__)


# ── DB 헬퍼 ───────────────────────────────────────────────────────────────────

def _pg_conn():
    return psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", "5433")),
        user=os.getenv("DB_USER", "postgres"),
        password=os.getenv("DB_PASSWORD", "postgres"),
        dbname=os.getenv("DB_NAME", "postgres"),
    )


def _pg_async_dsn() -> str:
    return (
        f"postgresql://{os.getenv('DB_USER','postgres')}:{os.getenv('DB_PASSWORD','postgres')}"
        f"@{os.getenv('DB_HOST','localhost')}:{os.getenv('DB_PORT','5433')}"
        f"/{os.getenv('DB_NAME','postgres')}"
    )


def _log(conn, doc_id: str, session_id: str, agent: str, level: str, message: str):
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO pipeline_logs (doc_id, session_id, agent, level, message) "
            "VALUES (%s, %s, %s, %s, %s)",
            (doc_id, session_id, agent, level, message),
        )
    conn.commit()


def _set_state(conn, doc_id: str, state: str):
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE documents SET state=%s, updated_at=now() WHERE doc_id=%s",
            (state, doc_id),
        )
    conn.commit()


# ── 1단계: Crawler ────────────────────────────────────────────────────────────

@celery_app.task(name="pipeline.crawler", bind=True, max_retries=3)
def crawl_task(self, session_id: str, doc_id: str):
    """documents.original_url 조회 → HTTP 크롤링 → 텍스트 청크 분리."""
    conn = _pg_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT original_url FROM documents WHERE doc_id=%s", (doc_id,))
            row = cur.fetchone()
        if not row:
            raise ValueError(f"doc_id '{doc_id}' not found in documents")
        url = row[0]

        _log(conn, doc_id, session_id, "Crawler", "INFO", f"크롤링 시작: {url}")
        _set_state(conn, doc_id, "CRAWLING")

        result, chunks = asyncio.run(_do_crawl(url))
        _log(conn, doc_id, session_id, "Crawler", "INFO", f"크롤링 완료 — {len(chunks)} 청크")
        extract_task.delay(session_id=session_id, doc_id=doc_id, chunks=chunks)
    except Exception as exc:
        _log(conn, doc_id, session_id, "Crawler", "ERROR", str(exc))
        _set_state(conn, doc_id, "FAILED")
        raise self.retry(exc=exc, countdown=30)
    finally:
        conn.close()


async def _do_crawl(url: str) -> tuple:
    import aiohttp
    from app.infrastructure.crawler import http_crawler
    async with aiohttp.ClientSession() as session:
        result = await http_crawler.fetch(url, session)
    return result, http_crawler.smart_chunk(result)


# ── 2단계: Extractor ──────────────────────────────────────────────────────────

@celery_app.task(name="pipeline.extractor", bind=True, max_retries=3)
def extract_task(self, session_id: str, doc_id: str, chunks: list[str]):
    """LLM 추출 → staging_concepts DRAFT / DOMAIN_PENDING 적재."""
    conn = _pg_conn()
    try:
        _log(conn, doc_id, session_id, "Extractor", "INFO", f"LLM 추출 시작 — {len(chunks)} 청크")
        _set_state(conn, doc_id, "EXTRACTED")

        asyncio.run(_do_extract(session_id, doc_id, chunks))
        _log(conn, doc_id, session_id, "Extractor", "INFO", "추출 완료 — staging 적재 완료")
    except Exception as exc:
        _log(conn, doc_id, session_id, "Extractor", "ERROR", str(exc))
        _set_state(conn, doc_id, "FAILED")
        raise self.retry(exc=exc, countdown=60)
    finally:
        conn.close()


async def _do_extract(session_id: str, doc_id: str, chunks: list[str]) -> None:
    from app.infrastructure.llm.factory import create_llm_client
    from app.infrastructure.database.domain_repo import get_registered_domains
    from app.usecases.write_staging_draft import write_staging_draft

    app_mode = os.getenv("APP_MODE", "development")
    client = create_llm_client(
        app_mode,
        api_key=os.getenv("GEMINI_API_KEY", ""),
        model=os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
    )

    pool = await asyncpg.create_pool(_pg_async_dsn(), min_size=1, max_size=2, ssl=False)
    try:
        async with pool.acquire() as db_conn:
            registered = await get_registered_domains(db_conn)
            all_concepts = []
            for i, chunk in enumerate(chunks):
                if i > 0:
                    await asyncio.sleep(4)  # 무료 티어 20 req/min → 청크 간 4초 간격
                concepts = await client.extract_concepts(chunk, doc_id, {})
                all_concepts.extend(concepts)
            await write_staging_draft(session_id, doc_id, all_concepts, db_conn, registered)
    finally:
        await pool.close()


# ── 3단계: Graph Writer ───────────────────────────────────────────────────────

@celery_app.task(name="pipeline.graph_writer", bind=True, max_retries=3)
def write_graph_task(self, session_id: str, doc_id: str):
    """APPROVED staging → Neo4j MERGE + APOC addLabels → COMMITTED."""
    conn = _pg_conn()
    try:
        _log(conn, doc_id, session_id, "Writer", "INFO", "그래프 적재 시작")
        asyncio.run(_do_write_graph(session_id))
        _log(conn, doc_id, session_id, "Writer", "INFO", "그래프 적재 완료")
        resolve_links_task.delay(session_id=session_id, doc_id=doc_id)
    except Exception as exc:
        _log(conn, doc_id, session_id, "Writer", "ERROR", str(exc))
        _set_state(conn, doc_id, "FAILED")
        raise self.retry(exc=exc, countdown=60)
    finally:
        conn.close()


async def _do_write_graph(session_id: str) -> None:
    from neo4j import AsyncGraphDatabase
    from app.domain.models import ConceptExtractionSchema
    from app.infrastructure.graph.graph_writer import write_concept_node

    neo4j_uri = os.getenv("NEO4J_URI", "bolt://127.0.0.1:7688")
    neo4j_auth = (os.getenv("NEO4J_USER", "neo4j"), os.getenv("NEO4J_PASSWORD", "pass1234!"))
    driver = AsyncGraphDatabase.driver(neo4j_uri, auth=neo4j_auth)

    pool = await asyncpg.create_pool(_pg_async_dsn(), min_size=1, max_size=2, ssl=False)
    try:
        async with pool.acquire() as db_conn:
            rows = await db_conn.fetch(
                "SELECT id, concept_json FROM staging_concepts "
                "WHERE session_id=$1::uuid AND state='APPROVED'",
                session_id,
            )
            for row in rows:
                raw = row["concept_json"]
                data = json.loads(raw) if isinstance(raw, str) else dict(raw)
                concept = ConceptExtractionSchema(**data)
                await write_concept_node(concept, driver)
                await db_conn.execute(
                    "UPDATE staging_concepts SET state='COMMITTED', committed_at=now() "
                    "WHERE id=$1",
                    row["id"],
                )
    finally:
        await pool.close()
        await driver.close()


# ── 4단계: Link Resolver ──────────────────────────────────────────────────────

@celery_app.task(name="pipeline.link_resolver", bind=True, max_retries=3)
def resolve_links_task(self, session_id: str, doc_id: str):
    """session의 COMMITTED concepts에 대해 aliases 기반 SAME_AS 관계 탐색."""
    conn = _pg_conn()
    try:
        _log(conn, doc_id, session_id, "Resolver", "INFO", "링크 리졸버 시작")
        same_as_total, _ = asyncio.run(_do_resolve_links(session_id))
        _set_state(conn, doc_id, "COMMITTED")
        _log(conn, doc_id, session_id, "Resolver", "INFO",
             f"파이프라인 완료 — COMMITTED, SAME_AS 관계 {same_as_total}건")
    except Exception as exc:
        _log(conn, doc_id, session_id, "Resolver", "ERROR", str(exc))
        raise self.retry(exc=exc, countdown=120)
    finally:
        conn.close()


async def _do_resolve_links(session_id: str) -> tuple[int, int]:
    """session_id의 COMMITTED staging rows에서 concept_name 추출 → resolve_links 호출."""
    from neo4j import AsyncGraphDatabase
    from app.infrastructure.graph.link_resolver import resolve_links

    neo4j_uri = os.getenv("NEO4J_URI", "bolt://127.0.0.1:7688")
    neo4j_auth = (os.getenv("NEO4J_USER", "neo4j"), os.getenv("NEO4J_PASSWORD", "pass1234!"))
    driver = AsyncGraphDatabase.driver(neo4j_uri, auth=neo4j_auth)

    pool = await asyncpg.create_pool(_pg_async_dsn(), min_size=1, max_size=2, ssl=False)
    same_as_total = 0
    try:
        async with pool.acquire() as db_conn:
            rows = await db_conn.fetch(
                "SELECT concept_json FROM staging_concepts "
                "WHERE session_id=$1::uuid AND state='COMMITTED'",
                session_id,
            )
        for row in rows:
            raw = row["concept_json"]
            data = json.loads(raw) if isinstance(raw, str) else dict(raw)
            concept_name = data.get("concept_name", "")
            if concept_name:
                cnt, _ = await resolve_links(concept_name, driver)
                same_as_total += cnt
    finally:
        await pool.close()
        await driver.close()

    return same_as_total, 0


# ── 통합 엔트리포인트 ─────────────────────────────────────────────────────────

@celery_app.task(name="pipeline.run", bind=True)
def run_pipeline_task(self, session_id: str, doc_id: str):
    crawl_task.delay(session_id=session_id, doc_id=doc_id)
