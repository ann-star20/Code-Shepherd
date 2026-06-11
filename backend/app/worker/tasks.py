"""Celery 파이프라인 태스크 — Phase 2 + 3-Factor 하이브리드 수렴 연동.

각 단계는 asyncio.run()으로 async 구현체를 호출한다.
psycopg2: 상태/로그 기록 (동기), asyncpg: 데이터 적재 (비동기).

환경 플래그:
  USE_REAL_LLM=true         Gemini API 호출. false(기본) → llm_response.json MockClient
  USE_REAL_EMBEDDING=true   실 임베딩 API. false(기본) → MockEmbeddingService (1024/768-dim BoW)
"""

import asyncio
import json
import logging
import os
from unittest import mock

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
            "UPDATE knowledge_document SET state=%s, updated_at=now() WHERE doc_id=%s",
            (state, doc_id),
        )
    conn.commit()


# ── 1단계: Crawler ────────────────────────────────────────────────────────────

@celery_app.task(name="pipeline.crawler", bind=True, max_retries=3)
def crawl_task(self, session_id: str, doc_id: str):
    """knowledge_document.original_url 조회 → HTTP 크롤링 → 텍스트 청크 분리."""
    conn = _pg_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT state, original_url FROM knowledge_document WHERE doc_id=%s", (doc_id,))
            row = cur.fetchone()
            if row and row[0] == 'FAILED':
                _log(conn, doc_id, session_id, "System", "WARNING", f"[RESET] 과거 실패 문서({doc_id}) 감지 ➔ 스테이징 세척 및 1단계 클린 리부팅 단행.")
                with conn.cursor() as cur:
                    cur.execute("DELETE FROM staging_concepts WHERE doc_id=%s", (doc_id,))
                    cur.execute("DELETE FROM pipeline_logs WHERE doc_id=%s", (doc_id,))
                conn.commit()
                _set_state(conn, doc_id, "PENDING")
        if not row:
            raise ValueError(f"doc_id '{doc_id}' not found in knowledge_document")
        url = row[1]

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
# 수정된 데코레이터 예시
@celery_app.task(
    name="pipeline.extractor", 
    bind=True, 
    max_retries=2,
    autoretry_for=(Exception,), # 또는 특정 에러 클래스 (ServerError 등)
    retry_backoff=True,         # 재시도 간격을 점점 늘림 (60초 -> 120초 -> ...)
    retry_backoff_max=600       # 최대 10분까지만 증가
)
@celery_app.task(name="pipeline.extractor", bind=True, max_retries=3)
def extract_task(self, session_id: str, doc_id: str, chunks: list[str]):
    """LLM 추출 → staging_concepts DRAFT / DOMAIN_PENDING 적재.

    USE_REAL_LLM=false (기본): MockClient → llm_response.json (또는 내장 _MOCK_CONCEPTS)
    USE_REAL_LLM=true:         GeminiClient 실 API 호출
    """
    conn = _pg_conn()
    try:
        _set_state(conn, doc_id, "EXTRACTING")
        _log(conn, doc_id, session_id, "Extractor", "INFO",
             f"LLM 추출 시작 — {len(chunks)} 청크 (real_llm={_USE_REAL_LLM})")
        n = asyncio.run(_do_extract(session_id, doc_id, chunks))
        if n == 0:
            _log(conn, doc_id, session_id, "Extractor", "ERROR",
                 "추출된 개념 0건 — Gemini가 빈 배열을 반환했습니다. 문서 내용을 확인 후 재시도하세요.")
            _set_state(conn, doc_id, "FAILED")
            return
        _set_state(conn, doc_id, "EXTRACTED")
        _log(conn, doc_id, session_id, "Extractor", "INFO", f"추출 완료 — staging {n}건 적재 완료")
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
    """
    staging_concepts에 infer_action/infer_confidence/target_concept_name 업데이트.
    3-Factor 하이브리드 중복 판정 역추적 전용 세부 지표 영속화.
    최종 결합 신뢰도(infer_confidence)뿐만 아니라 Jaro, Name_Vec, Desc_Vec 점수를 RDB에 개별 컬럼으로 분리 적재함.
    mock/production 모드 모두 동일 로직. 환경 플래그에 무관하다.
    """
    for concept, result in zip(concepts, results):
        await db_pool.execute(
"""UPDATE staging_concepts
               SET infer_action = $1, 
                   infer_confidence = $2, 
                   target_concept_name = $3,
                   score_jaro_winkler = $4,
                   score_name_vector = $5,
                   score_desc_vector = $6
               WHERE session_id = $7::uuid
               AND concept_json->>'concept_name' = $8""",
            result.action.value,         # MERGE / RELATED_TO / NEW
            result.score,                # 최종 결합 Hybrid Score
            result.target,               # 병합/연관 타겟 마스터 개념명
            result.score_metrics["jaro"],     # 1) 어휘 구조 유사도 (40%)
            result.score_metrics["name_vec"], # 2) 키워드 풀 1024차원 코사인 유사도 (30%)
            result.score_metrics["desc_vec"], # 3) 요약 설명문 1024차원 코사인 유사도 (30%)
            session_id,
            concept.concept_name,
        )


async def _do_extract(session_id: str, doc_id: str, chunks: list[str]) -> int:
    from app.infrastructure.llm.factory import create_llm_client, create_embedding_client, create_embedding_client
    from app.infrastructure.database.domain_repo import get_registered_domains
    from app.usecases.write_staging_draft import write_staging_draft
    from app.infrastructure.graph.hybrid_resolver import compute_resolve_score

    # USE_REAL_LLM=true → GeminiClient, false(기본) → MockClient (llm_response.json)
    llm_mode = "production" if _USE_REAL_LLM else "development"
    client = create_llm_client(
        llm_mode,
        api_key=os.getenv("GEMINI_API_KEY", ""),
        model=os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
    )
    
    # USE_REAL_EMBEDDING=true → GeminiEmbeddingService, false(기본) → MockEmbeddingService
    embedding_mode = "production" if _USE_REAL_EMBEDDING else "development"
    # embedding_svc = create_embedding_client(
    #     embedding_mode,
    #     api_key=os.getenv("GEMINI_API_KEY", ""),
    #     model=os.getenv("EMBEDDING_MODEL", "text-embedding-004"),
    # )
    # 🎯 1024차원 고성능 BGE-M3 로컬 임베딩 클라이언트 빌드 및 의존성 인젝션
    embedding_svc = create_embedding_client(
        embedding_mode,
        model=os.getenv("EMBEDDING_MODEL", "BAAI/bge-m3"),
    )
    pool = await asyncpg.create_pool(_pg_async_dsn(), min_size=1, max_size=2, ssl=False)
    try:
        async with pool.acquire() as db_conn:
            registered = await get_registered_domains(db_conn)
            doc_meta_row = await db_conn.fetchrow(
                "SELECT framework, lang FROM knowledge_document WHERE doc_id=$1", doc_id
            )
            metadata = {
                "framework": (doc_meta_row["framework"] if doc_meta_row else None) or "Unknown",
                "lang": (doc_meta_row["lang"] if doc_meta_row else None) or "EN",
                "allowed_domains": sorted(registered) if registered else None,
            }
            if _USE_REAL_LLM:
                all_concepts = []
                for i, chunk in enumerate(chunks):
                    if i > 0:
                        await asyncio.sleep(4)  # 무료 티어 20 req/min → 청크 간 4초 간격
                    concepts = await client.extract_concepts(chunk, doc_id, metadata)
                    all_concepts.extend(concepts)
            else:
                # MockClient는 청크 내용과 무관하게 llm_response.json(또는 내장 _MOCK_CONCEPTS)을
                # 그대로 반환하므로, 청크 수만큼 반복하면 동일 컨셉이 중복 적재된다 → 1회만 호출.
                all_concepts = await client.extract_concepts(chunks[0] if chunks else "", doc_id, metadata)
            await write_staging_draft(session_id, doc_id, all_concepts, db_conn, registered)

        # 3-Factor 하이브리드 점수 선행 계산 → staging 영속화
        # compute_resolve_score는 PG/Neo4j 사이드이펙트 없이 점수만 반환한다.
        resolve_results = []
        for concept in all_concepts:
            result = await compute_resolve_score(concept, pool, embedding_svc)
            resolve_results.append(result)
        await _save_infer_scores(session_id, all_concepts, resolve_results, pool)
        return len(all_concepts)
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
    from app.infrastructure.llm.factory import create_embedding_client

    # USE_REAL_EMBEDDING=true → GeminiEmbeddingService, false(기본) → MockEmbeddingService
    embedding_mode = "production" if _USE_REAL_EMBEDDING else "development"
    embedding_svc = create_embedding_client(
        embedding_mode,
        model=os.getenv("EMBEDDING_MODEL", "BAAI/bge-m3"),
    )

    neo4j_uri  = os.getenv("NEO4J_URI", "bolt://127.0.0.1:7688")
    neo4j_auth = (os.getenv("NEO4J_USER", "neo4j"), os.getenv("NEO4J_PASSWORD", "pass1234!"))
    driver = AsyncGraphDatabase.driver(neo4j_uri, auth=neo4j_auth)

    pool = await asyncpg.create_pool(_pg_async_dsn(), min_size=1, max_size=2, ssl=False)
    summary: dict[str, int] = {a.value: 0 for a in MergeAction}
    try:
        repo   = Neo4jConceptRepo(driver)
        writer = GraphWriterService(pool, driver, repo, embedding_svc)

        rows = await pool.fetch(
            "SELECT id, concept_json, infer_action, infer_confidence, target_concept_name "
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
                        score=float(row["infer_confidence"] or 0.0),
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
