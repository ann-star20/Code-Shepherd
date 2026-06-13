"""5단계 Celery 파이프라인 체인.

실행 순서: Prescan -> Crawling -> Extract -> (HITL via API) -> WriteGraph
PG -> Neo4j 쓰기 순서 고정 (데드락 방지)
FAILED 클린업: staging DRAFT 삭제 + knowledge_documents state=FAILED
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import hashlib
import json
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Coroutine

import asyncpg
import httpx
import redis as sync_redis
from celery_app import celery_app

from app.core.config import (
    GEMINI_API_KEY,
    GEMINI_MODEL,
    REDIS_URL,
    USE_REAL_LLM,
    pg_dsn,
)

_PG_DSN = pg_dsn()


def _run_async(coro: Coroutine[Any, Any, Any]) -> Any:
    """코루틴 실행 - LOCAL_DEBUG(task_always_eager) 모드에서 FastAPI 이벤트 루프 내부 호출 대응.

    이미 실행 중인 이벤트 루프가 있으면(asyncio.run 호출 불가) 별도 스레드에서
    새 루프를 만들어 실행한다.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result()


def _emit(session_id: str, event: dict[str, Any]) -> None:
    r = sync_redis.from_url(REDIS_URL)
    try:
        r.publish(f"pipeline:{session_id}", json.dumps(event))
    finally:
        r.close()


def _log(session_id: str, agent: str, message: str) -> None:
    _emit(session_id, {
        "type": "log",
        "agent": agent,
        "message": message,
        "ts": datetime.now(timezone.utc).isoformat(),
    })


@celery_app.task(name="m6.prescan", bind=True, max_retries=3, queue="m6_graph")
def prescan_task(self, session_id: str, url: str) -> dict:
    """URL 메타 분석 + ETag/hash 중복 검증 + knowledge_documents PENDING 생성."""
    try:
        ctx = _run_async(_prescan_async(session_id, url))
        _emit(session_id, {"type": "step_update", "agent": "Prescan", "status": "SUCCESS"})
        return ctx
    except Exception as exc:
        _set_failed_sync(session_id)
        raise self.retry(exc=exc, countdown=5) from exc


async def _prescan_async(session_id: str, url: str) -> dict:
    _log(session_id, "Prescan", f"URL 사전 탐색 시작: {url}")
    etag, content_hash, content_lang = await _fetch_meta(url)
    conn = await asyncpg.connect(_PG_DSN)
    try:
        existing = await conn.fetchrow(
            "SELECT doc_id, state FROM knowledge_documents "
            "WHERE content_hash = $1 OR (original_url = $2 AND etag = $3 AND etag IS NOT NULL)",
            content_hash, url, etag,
        )
        if existing and existing["state"] not in ("FAILED",):
            _log(session_id, "Prescan", f"중복 문서 감지 - doc_id={existing['doc_id']}, 건너뜀")
            return {"skip": True, "doc_id": existing["doc_id"], "session_id": session_id}
        meta = await _match_framework(conn, url)
        doc_id = f"doc_{content_hash}"
        await conn.execute(
            "INSERT INTO knowledge_documents "
            "    (doc_id, source_prefix, original_url, content_hash, etag, doc_lang,"
            "     lang, framework, version, state, session_id) "
            "VALUES ($1, $2, $3, $4, $5, $6, $7, $8, 'PENDING', $9) "
            "ON CONFLICT (doc_id) DO UPDATE "
            "SET state = 'PENDING', session_id = EXCLUDED.session_id, updated_at = now()",
            # doc_id, meta.get("source_prefix", "external"),
            doc_id, "external", url, content_hash, etag, content_lang,
            meta.get("lang"), meta.get("framework"), meta.get("version"),
            session_id,
        )
        _log(session_id, "Prescan", f"knowledge_documents 등록 완료: {doc_id}")
        return {"skip": False, "doc_id": doc_id, "url": url, "session_id": session_id, **meta}
    finally:
        await conn.close()


async def _fetch_meta(url: str) -> tuple[str | None, str]:
    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        try:
            head = await client.head(url)
            etag = head.headers.get("etag")
            content_lang = head.headers.get("Content-Language", "").lower()
            if etag:
                # Weak ETag 접두사(W/) 제거 후 앞뒤 따옴표 정제
                if etag.startswith('W/'):
                    etag = etag[2:]
                etag = etag.strip('"')
                
            # 헤더에 언어 설정이 있다면 1차 획득
            if "en" in content_lang:
                content_lang = "en"
            else:
                content_lang = "ko"  # 기본값은 한국어로 간주 
        except Exception:
            etag = None
        try:
            resp = await client.get(url)
            content = resp.content
        except Exception:
            content = url.encode()
    return etag, hashlib.md5(content).hexdigest()[:8], content_lang


async def _match_framework(conn: asyncpg.Connection, url: str) -> dict:
    rows = await conn.fetch("SELECT framework, url_patterns, default_lang FROM framework_metadata")
    for row in rows:
        for pattern in row["url_patterns"]:
            if re.search(pattern, url, re.IGNORECASE):
                return {
                    "source_prefix": row["framework"].lower(),
                    "framework": row["framework"],
                    "lang": row["default_lang"],
                    "version": None,
                }
    return {"source_prefix": "external", "framework": None, "lang": None, "version": None}


@celery_app.task(name="m6.crawl", bind=True, max_retries=3, queue="m6_graph")
def crawl_task(self, ctx: dict) -> dict:
    """DOM 정제 텍스트 추출 스마트 청킹."""
    if ctx.get("skip"):
        return ctx
    session_id = ctx["session_id"]
    try:
        result = _run_async(_crawl_async(ctx))
        _emit(session_id, {"type": "step_update", "agent": "Crawler", "status": "SUCCESS"})
        return result
    except Exception as exc:
        _set_failed_sync(session_id)
        raise self.retry(exc=exc, countdown=10) from exc


async def _crawl_async(ctx: dict) -> dict:
    session_id = ctx["session_id"]
    doc_id = ctx["doc_id"]
    url = ctx["url"]
    _log(session_id, "Crawler", f"페이지 수집 시작: {url}")
    await _update_doc_state(doc_id, "CRAWLING")
    text = await _extract_text(url)
    chunks = _chunk_text(text, max_len=4000)
    _log(session_id, "Crawler", f"텍스트 청크 {len(chunks)}개 생성")
    return {**ctx, "chunks": chunks}


async def _extract_text(url: str) -> str:
    try:
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            html = resp.text
    except Exception:
        return ""
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "header"]):
            tag.decompose()
        return soup.get_text(separator="\n", strip=True)
    except ImportError:
        return re.sub(r"<[^>]+>", " ", html)


def _chunk_text(text: str, max_len: int = 4000) -> list[str]:
    if len(text) <= max_len:
        return [text] if text else [""]
    paragraphs = text.split("\n\n")
    chunks: list[str] = []
    current = ""
    for para in paragraphs:
        if len(current) + len(para) > max_len and current:
            chunks.append(current.strip())
            current = para
        else:
            current += "\n\n" + para
    if current.strip():
        chunks.append(current.strip())
    return chunks or [text[:max_len]]


@celery_app.task(name="m6.extract", bind=True, max_retries=3, queue="m6_graph")
def extract_task(self, ctx: dict) -> dict:
    """LLM 개념 추출 + 벡터 임베딩 + staging DRAFT 적재."""
    if ctx.get("skip"):
        return ctx
    session_id = ctx["session_id"]
    try:
        result = _run_async(_extract_async(ctx))
        _emit(session_id, {"type": "step_update", "agent": "Extractor", "status": "SUCCESS"})
        _emit(session_id, {"type": "finished"})
        return result
    except Exception as exc:
        _set_failed_sync(session_id)
        raise self.retry(exc=exc, countdown=15) from exc


async def _extract_async(ctx: dict) -> dict:
    from app.infrastructure.graph.hybrid_resolver import HybridResolver, _embed_async

    session_id = ctx["session_id"]
    doc_id = ctx["doc_id"]
    chunks = ctx.get("chunks", [""])
    _log(session_id, "Extractor", "LLM 개념 추출 시작")
    await _update_doc_state(doc_id, "EXTRACTING")

    concepts: list[dict] = []
    for chunk in chunks[:5]:
        extracted = await _llm_extract(chunk, ctx)
        concepts.extend(extracted)

    _log(session_id, "Extractor", f"{len(concepts)}개 개념 추출 완료({[concept['concept_name'] for concept in concepts]})")

    resolver = HybridResolver()
    conn = await asyncpg.connect(_PG_DSN)
    try:
        staged = 0
        for concept in concepts:
            name_vec = await _embed_async(
                " ".join([concept["concept_name"]] + concept.get("aliases", []))
            )
            desc_vec = (
                await _embed_async(concept["description_ko"])
                if concept.get("description_ko")
                else None
            )
            concept["name_vector"] = name_vec
            concept["desc_vector"] = desc_vec

            resolve = await resolver.resolve(
                name=concept["concept_name"],
                aliases=concept.get("aliases", []),
                name_vector=name_vec or [],
                desc_vector=desc_vec,
            )

            await conn.execute(
                "INSERT INTO staging_concepts "
                "    (session_id, doc_id, concept_json, state, "
                "     infer_action, infer_confidence, target_concept_name, "
                "     score_jaro_winkler, score_name_vector, score_desc_vector) "
                "VALUES ($1, $2, $3, 'DRAFT', $4, $5, $6, $7, $8, $9)",
                uuid.UUID(session_id), doc_id, json.dumps(concept),
                resolve.action.value, resolve.score,
                resolve.target_concept_name,
                resolve.score_jaro_winkler,
                resolve.score_name_vector,
                resolve.score_desc_vector,
            )
            staged += 1

        await _update_doc_state_conn(conn, doc_id, "EXTRACTED")
        _log(session_id, "Extractor", f"staging DRAFT {staged}건 - HITL 검토 대기")
    finally:
        await conn.close()

    return {**ctx, "staged": staged}


async def _llm_extract(chunk: str, ctx: dict) -> list[dict]:
    if USE_REAL_LLM and GEMINI_API_KEY:
        return await _gemini_extract(chunk, ctx)
    return _mock_extract(chunk, ctx)


def _mock_extract(chunk: str, ctx: dict) -> list[dict]:
    short_hash = hashlib.md5(chunk[:50].encode()).hexdigest()[:6]
    fw = ctx.get("framework") or "unknown"
    return [{
        "concept_name": f"concept_{fw}_{short_hash}",
        "concept_type": "mechanism",
        "domains": [ctx.get("source_prefix", "external")],
        "description_ko": chunk[:200],
        "aliases": [],
        "severity": None,
        "cwe_id": None,
        "owasp_id": None,
        "root_cause": "",
        "mechanism": [],
        "affected_components": [],
    }]


async def _gemini_extract(chunk: str, ctx: dict) -> list[dict]:
    prompt = (
        "다음 문서 텍스트에서 기술 개념을 JSON 배열로 추출하라. "
        "각 항목: concept_name, domains, description_ko, aliases, mechanism.\n\n"
        + chunk[:3000]
    )
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}"
            f":generateContent?key={GEMINI_API_KEY}",
            json={"contents": [{"parts": [{"text": prompt}]}]},
        )
        resp.raise_for_status()
        text = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
    try:
        m = re.search(r"\[.*\]", text, re.DOTALL)
        if m:
            return json.loads(m.group())
    except Exception:
        pass
    return []


@celery_app.task(name="m6.write_graph", bind=True, max_retries=3, queue="m6_graph")
def write_graph_task(self, session_id: str) -> dict:
    """APPROVED staging_concepts -> Neo4j 쓰기 -> COMMITTED."""
    try:
        result = _run_async(_write_graph_async(session_id))
        _emit(session_id, {"type": "step_update", "agent": "GraphWriter", "status": "SUCCESS"})
        _emit(session_id, {"type": "finished"})
        return result
    except Exception as exc:
        _set_failed_sync(session_id)
        raise self.retry(exc=exc, countdown=15) from exc


async def _write_graph_async(session_id: str) -> dict:
    from app.adapters.db.neo4j_repo import Neo4jConceptRepo, merge_related_to
    from app.core.neo4j_client import get_database, get_driver
    from app.domain.models import ConceptExtractionSchema
    from app.infrastructure.graph.hybrid_resolver import HybridResolver

    _log(session_id, "GraphWriter", "승인된 개념 Neo4j 영속화 시작")

    driver = get_driver()
    repo = Neo4jConceptRepo(driver, get_database())
    resolver = HybridResolver()
    summary: dict[str, int] = {"MERGE": 0, "RELATED_TO": 0, "NEW": 0}

    conn = await asyncpg.connect(_PG_DSN)
    try:
        async with conn.transaction():
            rows = await conn.fetch(
                "SELECT id, concept_json, infer_action, target_concept_name "
                "FROM staging_concepts "
                "WHERE session_id = $1 AND state = 'APPROVED' "
                "FOR UPDATE SKIP LOCKED",
                uuid.UUID(session_id),
            )
            for row in rows:
                concept = ConceptExtractionSchema(**json.loads(row["concept_json"]))
                action = row["infer_action"] or "NEW"

                await conn.execute(
                    "UPDATE staging_concepts SET state = 'COMMITTED', committed_at = now() WHERE id = $1",
                    row["id"],
                )

                await repo.merge_concept(concept)

                if action == "RELATED_TO" and row["target_concept_name"]:
                    await merge_related_to(
                        driver, concept.concept_name,
                        row["target_concept_name"], get_database()
                    )

                if action == "MERGE" and row["target_concept_name"]:
                    await resolver.do_centroid_shift(
                        row["target_concept_name"], concept.aliases
                    )

                summary[action] = summary.get(action, 0) + 1
    finally:
        await conn.close()

    _log(session_id, "GraphWriter", f"영속화 완료: {summary}")
    return {"session_id": session_id, "summary": summary}


def _set_failed_sync(session_id: str) -> None:
    try:
        _run_async(_set_failed_async(session_id))
    except Exception:
        pass


async def _set_failed_async(session_id: str) -> None:
    conn = await asyncpg.connect(_PG_DSN)
    try:
        sid = uuid.UUID(session_id)
        await conn.execute(
            "DELETE FROM staging_concepts WHERE session_id = $1 AND state = 'DRAFT'", sid
        )
        await conn.execute(
            "UPDATE knowledge_documents SET state = 'FAILED', updated_at = now() WHERE session_id = $1",
            session_id,
        )
    finally:
        await conn.close()


async def _update_doc_state(doc_id: str, state: str) -> None:
    conn = await asyncpg.connect(_PG_DSN)
    try:
        await _update_doc_state_conn(conn, doc_id, state)
    finally:
        await conn.close()


async def _update_doc_state_conn(conn: asyncpg.Connection, doc_id: str, state: str) -> None:
    await conn.execute(
        "UPDATE knowledge_documents SET state = $1, updated_at = now() WHERE doc_id = $2",
        state, doc_id,
    )


def trigger_pipeline(session_id: str, url: str) -> None:
    """prescan -> crawl -> extract 체인 비동기 실행."""
    chain = prescan_task.s(session_id, url) | crawl_task.s() | extract_task.s()
    chain.apply_async()
