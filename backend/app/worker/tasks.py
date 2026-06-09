"""Celery 파이프라인 태스크 — Phase 2 + 3-Factor 하이브리드 수렴 연동.

각 단계는 asyncio.run()으로 async 구현체를 호출한다.
psycopg2: 상태/로그 기록 (동기), asyncpg: 데이터 적재 (비동기).

환경 플래그:
  USE_REAL_LLM=true         Gemini API 호출. false(기본) → llm_response.json MockClient
  USE_REAL_EMBEDDING=true   실 임베딩 API. false(기본) → MockEmbeddingService (768-dim BoW)
"""

import asyncio
import json
import logging
import os

import asyncpg
import psycopg2

from app.worker.celery_app import celery_app

logger = logging.getLogger(__name__)

# ── 환경 플래그 ───────────────────────────────────────────────────────────────
_USE_REAL_LLM       = os.getenv("USE_REAL_LLM", "false").lower() == "true"
_USE_REAL_EMBEDDING = os.getenv("USE_REAL_EMBEDDING", "false").lower() == "true"


# ── DB 헬퍼 ───────────────────────────────────────────────────────────────────

def _pg_conn():
    return psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", "5432")),
        user=os.getenv("DB_USER", "postgres"),
        password=os.getenv("DB_PASSWORD", "postgres"),
        dbname=os.getenv("DB_NAME", "postgres"),
    )


def _pg_async_dsn() -> str:
    return (
        f"postgresql://{os.getenv('DB_USER','postgres')}:{os.getenv('DB_PASSWORD','postgres')}"
        f"@{os.getenv('DB_HOST','localhost')}:{os.getenv('DB_PORT','5432')}"
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
    """LLM 추출 → staging_concepts DRAFT / DOMAIN_PENDING 적재.

    USE_REAL_LLM=false (기본): MockClient → llm_response.json (또는 내장 _MOCK_CONCEPTS)
    USE_REAL_LLM=true:         GeminiClient 실 API 호출
    """
    conn = _pg_conn()
    try:
        _log(conn, doc_id, session_id, "Extractor", "INFO",
             f"LLM 추출 시작 — {len(chunks)} 청크 (real_llm={_USE_REAL_LLM})")
        asyncio.run(_do_extract(session_id, doc_id, chunks))
        _set_state(conn, doc_id, "EXTRACTED")
        _log(conn, doc_id, session_id, "Extractor", "INFO", "추출 완료 — staging 적재 완료")
    except Exception as exc:
        _log(conn, doc_id, session_id, "Extractor", "ERROR", str(exc))
        _set_state(conn, doc_id, "FAILED")
        raise self.retry(exc=exc, countdown=60)
    finally:
        conn.close()


async def _save_infer_scores(
    session_id: str,
    concepts: list,
    results: list,
    db_pool: object,
) -> None:
    """staging_concepts에 infer_action/infer_score/target_concept_name 업데이트.

    mock/production 모드 모두 동일 로직. 환경 플래그에 무관하다.
    """
    for concept, result in zip(concepts, results):
        await db_pool.execute(
            """UPDATE staging_concepts
               SET infer_action = $1, infer_score = $2, target_concept_name = $3
               WHERE session_id = $4::uuid
               AND concept_json->>'concept_name' = $5""",
            result.action.value,
            result.score,
            result.target,
            session_id,
            concept.concept_name,
        )


async def _do_extract(session_id: str, doc_id: str, chunks: list[str]) -> None:
    from app.infrastructure.llm.factory import create_llm_client
    from app.infrastructure.database.domain_repo import get_registered_domains
    from app.usecases.write_staging_draft import write_staging_draft
    from app.infrastructure.graph.hybrid_resolver import compute_resolve_score
    from app.infrastructure.llm.mock_embedding import MockEmbeddingService

    # USE_REAL_LLM=true → GeminiClient, false(기본) → MockClient (llm_response.json)
    llm_mode = "production" if _USE_REAL_LLM else "development"
    client = create_llm_client(
        llm_mode,
        api_key=os.getenv("GEMINI_API_KEY", ""),
        model=os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
    )
    embedding_svc = MockEmbeddingService()

    pool = await asyncpg.create_pool(_pg_async_dsn(), min_size=1, max_size=2, ssl=False)
    try:
        async with pool.acquire() as db_conn:
            registered = await get_registered_domains(db_conn)
            all_concepts = []
            for i, chunk in enumerate(chunks):
                if i > 0 and _USE_REAL_LLM:
                    await asyncio.sleep(4)  # 무료 티어 20 req/min → 청크 간 4초 간격
                concepts = await client.extract_concepts(chunk, doc_id, {})
                all_concepts.extend(concepts)
            await write_staging_draft(session_id, doc_id, all_concepts, db_conn, registered)

        # 3-Factor 하이브리드 점수 선행 계산 → staging 영속화
        # compute_resolve_score는 PG/Neo4j 사이드이펙트 없이 점수만 반환한다.
        resolve_results = []
        for concept in all_concepts:
            result = await compute_resolve_score(concept, pool, embedding_svc)
            resolve_results.append(result)
        await _save_infer_scores(session_id, all_concepts, resolve_results, pool)
    finally:
        await pool.close()


# ── 3단계: Graph Writer + 3-Factor 하이브리드 수렴 통합 ───────────────────────
#
# 구형 write_concept_node() + resolve_links_task(SAME_AS) 완전 폐기.
# GraphWriterService.write() 가 hybrid_resolve → 분기 처리를 원자적으로 수행한다.
#
#   MERGE      (score ≥ 0.88)      : Centroid Shifting + PG name_vector UPDATE + Neo4j aliases 갱신
#   RELATED_TO (0.72 ≤ score < 0.88): 신규 4-레이어 노드 생성 + [:RELATED_TO] 엣지 가교
#   NEW        (score < 0.72)       : 완전 독립 4-레이어 노드 신규 생성
# ---------------------------------------------------------------------------

@celery_app.task(name="pipeline.graph_writer", bind=True, max_retries=3)
def write_graph_task(self, session_id: str, doc_id: str):
    """APPROVED staging → GraphWriterService(hybrid_resolve) → COMMITTED.

    USE_REAL_EMBEDDING=false(기본): MockEmbeddingService (768-dim BoW)
    USE_REAL_EMBEDDING=true:        실 임베딩 API
    """
    conn = _pg_conn()
    try:
        _log(conn, doc_id, session_id, "Writer", "INFO",
             f"3-Factor 하이브리드 수렴 적재 시작 (real_emb={_USE_REAL_EMBEDDING})")
        summary = asyncio.run(_do_write_graph(session_id))
        _set_state(conn, doc_id, "COMMITTED")
        _log(conn, doc_id, session_id, "Writer", "INFO",
             f"파이프라인 완료 — COMMITTED {summary}")
    except Exception as exc:
        _log(conn, doc_id, session_id, "Writer", "ERROR", str(exc))
        _set_state(conn, doc_id, "FAILED")
        raise self.retry(exc=exc, countdown=60)
    finally:
        conn.close()


async def _do_write_graph(session_id: str) -> dict[str, int]:
    """APPROVED staging_concepts → GraphWriterService.write() → hybrid_resolve 분기 처리.

    모든 APPROVED 개념을 처리 후 staging_concepts.state → COMMITTED 전이.
    Returns: {"MERGE": n, "RELATED_TO": n, "NEW": n}
    """
    from neo4j import AsyncGraphDatabase
    from app.domain.models import ConceptExtractionSchema
    from app.infrastructure.graph.neo4j_service import GraphWriterService
    from app.adapters.db.neo4j_repo import Neo4jConceptRepo
    from app.infrastructure.graph.hybrid_resolver import MergeAction, ResolveResult

    if _USE_REAL_EMBEDDING:
        from app.infrastructure.llm.factory import create_llm_client
        # 실 임베딩 클라이언트가 별도 팩토리로 분리되면 교체 가능
        # 현재는 MockEmbeddingService를 폴백으로 사용
        logger.warning("[gw] USE_REAL_EMBEDDING=true이지만 실 임베딩 팩토리 미구현 — MockEmbeddingService 폴백")
        from app.infrastructure.llm.mock_embedding import MockEmbeddingService
        embedding_svc = MockEmbeddingService()
    else:
        from app.infrastructure.llm.mock_embedding import MockEmbeddingService
        embedding_svc = MockEmbeddingService()

    neo4j_uri  = os.getenv("NEO4J_URI", "bolt://127.0.0.1:7688")
    neo4j_auth = (os.getenv("NEO4J_USER", "neo4j"), os.getenv("NEO4J_PASSWORD", "pass1234!"))
    driver = AsyncGraphDatabase.driver(neo4j_uri, auth=neo4j_auth)

    pool = await asyncpg.create_pool(_pg_async_dsn(), min_size=1, max_size=2, ssl=False)
    summary: dict[str, int] = {a.value: 0 for a in MergeAction}
    try:
        repo   = Neo4jConceptRepo(driver)
        writer = GraphWriterService(pool, driver, repo, embedding_svc)

        rows = await pool.fetch(
            "SELECT id, concept_json, infer_action, infer_score, target_concept_name "
            "FROM staging_concepts "
            "WHERE session_id=$1::uuid AND state='APPROVED'",
            session_id,
        )

        for row in rows:
            raw  = row["concept_json"]
            data = json.loads(raw) if isinstance(raw, str) else dict(raw)
            concept = ConceptExtractionSchema(**data)

            try:
                infer_action_str = row["infer_action"]
                if infer_action_str:
                    # staging에 사전 계산된 점수 존재 → 재스코어링 생략
                    precomputed = ResolveResult(
                        action=MergeAction(infer_action_str),
                        target=row["target_concept_name"],
                        score=float(row["infer_score"] or 0.0),
                        incoming_name=concept.concept_name,
                    )
                    write_result = await writer.write_with_precomputed(concept, precomputed)
                else:
                    # fallback: 점수 없으면 재계산 (하위 호환)
                    write_result = await writer.write(concept)
                summary[write_result.resolve.action.value] += 1
            except Exception as exc:
                logger.warning("[gw] '%s' 처리 실패 (skip+continue): %s",
                               concept.concept_name, exc)
                continue

            await pool.execute(
                "UPDATE staging_concepts SET state='COMMITTED', committed_at=now() "
                "WHERE id=$1",
                row["id"],
            )
    finally:
        await pool.close()
        await driver.close()

    return summary


# ── 통합 엔트리포인트 ─────────────────────────────────────────────────────────

@celery_app.task(name="pipeline.run", bind=True)
def run_pipeline_task(self, session_id: str, doc_id: str):
    crawl_task.delay(session_id=session_id, doc_id=doc_id)
