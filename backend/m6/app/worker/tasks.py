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
import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Coroutine

import asyncpg
import httpx
import redis as sync_redis
from celery_app import celery_app
from pydantic import ValidationError

from app.core.config import (
    GEMINI_API_KEY,
    GEMINI_MODEL,
    REDIS_URL,
    USE_REAL_LLM,
    pg_dsn,
)
from app.domain.models import ConceptExtractionSchema

_PG_DSN = pg_dsn()
logger = logging.getLogger(__name__)

# crawling-chunking-guide-v2.md §3 — Gemini가 ConceptExtractionSchema 구조를 벗어나지 않도록 강제하는 포맷 지시문
_FORMAT_INSTRUCTIONS = (
    "다음 JSON 스키마를 반드시 준수하여 JSON 배열로만 응답하라 (설명 텍스트 금지):\n"
    + json.dumps(ConceptExtractionSchema.model_json_schema(), ensure_ascii=False)
)


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
    _emit(session_id, {"type": "step_update", "step": "Input", "status": "RUNNING"})
    try:
        ctx = _run_async(_prescan_async(session_id, url))
        if ctx.get("skip"):
            _emit(session_id, {
                "type": "step_update", "step": "Input", "status": "SKIPPED",
                "reason": ctx.get("skip_reason", "중복 문서로 파이프라인을 건너뜁니다."),
            })
            _emit(session_id, {"type": "finished"})
        elif ctx.get("awaiting_metadata"):
            _emit(session_id, {
                "type": "metadata_required", "step": "Input",
                "doc_id": ctx["doc_id"], "url": ctx["url"],
                "suggestions": ctx.get("suggestions", []),
            })
        else:
            _emit(session_id, {"type": "step_update", "step": "Input", "status": "DONE"})
        return ctx
    except Exception as exc:
        _set_failed_sync(session_id)
        raise self.retry(exc=exc, countdown=5) from exc


def _make_doc_id(url: str, content_hash: str) -> str:
    """doc_id 생성 - EXT_<URL 슬러그>_<content_hash> 형식.

    URL의 fragment(#...)는 제거하고, 영숫자가 아닌 모든 문자를 '-'로 치환한다.
    예) https://react.dev/reference/react-dom/preloadModule#parameters
        -> EXT_https---react-dev-reference-react-dom-preloadModule_<hash>
    """
    slug = re.sub(r"[^A-Za-z0-9]", "-", url.split("#", 1)[0])
    return f"EXT_{slug}_{content_hash}"


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
        if existing and existing["state"] == "COMMITTED":
            reason = (
                f"이미 처리된 문서입니다 (doc_id={existing['doc_id']}, "
                f"state={existing['state']}) - 파이프라인을 건너뜁니다."
            )
            _log(session_id, "Prescan", f"중복 문서 감지 - doc_id={existing['doc_id']}, 건너뜀")
            return {
                "skip": True, "doc_id": existing["doc_id"], "session_id": session_id,
                "skip_reason": reason,
            }
        meta = await _match_framework(conn, url)
        doc_id = _make_doc_id(url, content_hash)
        await conn.execute(
            "INSERT INTO knowledge_documents "
            "    (doc_id, source_prefix, original_url, content_hash, etag, doc_lang,"
            "     lang, framework, version, state, session_id) "
            "VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, 'PENDING', $10) "
            "ON CONFLICT (doc_id) DO UPDATE "
            "SET state = 'PENDING', session_id = EXCLUDED.session_id, updated_at = now()",
            doc_id, "external", url, content_hash, etag, content_lang,
            meta.get("lang"), meta.get("framework"), meta.get("version"),
            session_id,
        )
        _log(session_id, "Prescan", f"knowledge_documents 등록 완료: {doc_id}")
        if meta.get("framework") is None:
            suggestions = await _list_frameworks(conn)
            _log(session_id, "Prescan", "프레임워크 자동 인식 실패 - HITL 메타데이터 입력 대기")
            return {
                "skip": False, "awaiting_metadata": True,
                "doc_id": doc_id, "url": url, "session_id": session_id,
                "suggestions": suggestions, **meta,
            }
        logger.debug("[Prescan] etag:%s, 문서언어:%s, 프레임워크: %s, 언어: %s", etag, content_lang, meta.get("framework"), meta.get("lang"))   
        return {"skip": False, "doc_id": doc_id, "url": url, "session_id": session_id, **meta}
    finally:
        await conn.close()


async def _list_frameworks(conn: asyncpg.Connection) -> list[str]:
    rows = await conn.fetch("SELECT framework FROM framework_metadata ORDER BY framework")
    return [row["framework"] for row in rows]


def _normalize_etag(raw: str | None) -> str | None:
    """ETag 헤더 값을 정규화한다 (W/ 약한 검증 접두사 및 둘러싼 따옴표 제거)."""
    if not isinstance(raw, str) or not raw:
        return None
    if raw.startswith("W/"):
        raw = raw[2:]
    return raw.strip('"')


async def _fetch_meta(url: str) -> tuple[str | None, str, str]:
    etag: str | None = None
    content_lang = ""  # 기본값은 한국어로 간주 - HEAD 실패 시에도 정의되어야 함
    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        try:
            head = await client.head(url)
            etag = _normalize_etag(head.headers.get("etag"))
            header_lang = head.headers.get("Content-Language", "").lower()

            # 헤더에 언어 설정이 있다면 1차 획득
            if "en" in header_lang:
                content_lang = "en"
            elif "ko" in header_lang:
                content_lang = "ko"
        except Exception:
            etag = None
        try:
            resp = await client.get(url)
            content = resp.content
            # HEAD가 etag를 제공하지 않는 서버/CDN을 위한 GET 응답 폴백
            if etag is None:
                etag = _normalize_etag(resp.headers.get("etag"))
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
    if ctx.get("skip") or ctx.get("awaiting_metadata"):
        return ctx
    session_id = ctx["session_id"]
    _emit(session_id, {"type": "step_update", "step": "Crawler", "status": "RUNNING"})
    try:
        result = _run_async(_crawl_async(ctx))
        _emit(session_id, {"type": "step_update", "step": "Crawler", "status": "DONE"})
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
    
    _log(url, "Crawler", "HTML에서 텍스트 추출 완료 (노이즈 제거 및 헤더 마킹 포함)")
    chunks = _chunk_text(text)
    
    
    logger.debug("%s crawling page START %s", "=" * 10, "=" * 10)
    logger.debug("[%s 자]원문: %s", len(text), text)
    logger.debug("%s crawling page CONVERT %s", "=" * 10, "=" * 10)
    logger.debug("[%s 자]구조적 청크: %s", len(chunks), chunks)
    logger.debug("%s crawling page END %s", "=" * 10, "=" * 10)
    _log(session_id, "Crawler", f"구조적 청크 {len(chunks)}개 생성 (헤더/문단 경계 스냅)")
    return {**ctx, "chunks": chunks}


_NOISE_CLASS_PATTERN = re.compile(r"banner|announcement|promo|menu|toolbar|cookie", re.I)


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
        for tag in soup(["script", "style", "nav", "footer", "header", "button", "aside"]):
            tag.decompose()
        for tag in soup.find_all(attrs={"aria-hidden": "true"}):
            tag.decompose()
        for tag in soup.find_all(class_=_NOISE_CLASS_PATTERN):
            tag.decompose()
        # <main>/role=main/<article> 우선 - 사이트 배너/메뉴/버전 알림 등
        # 본문 외 영역(nextjs.org 등)이 nav/header 태그 밖에 있을 때 본문만 추출
        content = soup.find("main") or soup.find(attrs={"role": "main"}) or soup.find("article") or soup
        # h1~h3을 마크다운 헤더로 변환 - _chunk_text의 헤더 스냅 경계 탐지용
        for level in (1, 2, 3):
            for heading in content.find_all(f"h{level}"):
                heading.string = "#" * level + " " + heading.get_text(strip=True)
        return content.get_text(separator="\n", strip=True)
    except ImportError:
        return re.sub(r"<[^>]+>", " ", html)


_HEADER_PATTERN = re.compile(r"(?m)^#{1,3} ")

# 정책 2: RELATED_TO 판정 시 방어책/해결책 명칭 감지 → transplant_as_mechanism 트리거
_DEFENSE_NAME_PATTERN = re.compile(r"(Protection|Defense|Mitigation|Guard|Filter|Handler)$")


def _chunk_text(
    text: str,
    min_len: int = 30000,
    max_len: int = 40000,
    overlap: int = 2500,
) -> list[str]:
    """구조적 청킹 - 헤더/문단 경계 스냅 + 컨텍스트 오버랩 보존.

    1. len(text) <= max_len: 단일 청크 반환
    2. [start+min_len, start+max_len] 윈도우 내에서 가장 가까운 마크다운 헤더
       (#, ##, ###) 직전, 없으면 빈 줄(문단 경계) 직후에서 컷
    3. 적절한 경계가 없으면 max_len에서 강제 컷
    4. 다음 청크 상단에 이전 청크의 마지막 overlap자를 중복 적재
    """
    if not text:
        return [""]
    if len(text) <= max_len:
        return [text]

    chunks: list[str] = []
    start = 0
    n = len(text)
    while start < n:
        if n - start <= max_len:
            chunks.append(text[start:].strip())
            break

        window_start = min(start + min_len, n)
        window_end = min(start + max_len, n)
        window = text[window_start:window_end]

        boundary: int | None = None
        header_match = _HEADER_PATTERN.search(window)
        if header_match:
            boundary = window_start + header_match.start()
        else:
            para_idx = window.find("\n\n")
            if para_idx != -1:
                boundary = window_start + para_idx

        if boundary is None or boundary <= start:
            boundary = window_end

        chunks.append(text[start:boundary].strip())

        next_start = boundary - overlap
        start = next_start if next_start > start else boundary

    return [c for c in chunks if c]


# crawling-chunking-guide §2 — 본문 전체가 노이즈로 판정되어 적재 가능한 개념이
# 하나도 없을 때 프론트엔드 팝업/단계 표시에 사용하는 안내 메시지
_NO_CONCEPTS_FOUND_MESSAGE = "해당 페이지의 본문에서 분석 가능한 핵심 개념(안티패턴/약점)을 찾지 못했습니다."


def _classify_error(exc: Exception) -> str:
    """Celery 태스크 예외를 사용자 친화적 메시지로 변환."""
    if isinstance(exc, httpx.HTTPStatusError):
        code = exc.response.status_code
        if code == 503:
            return f"Gemini API 일시 과부하 ({code}) — 잠시 후 자동 재시도합니다."
        if code == 429:
            return f"Gemini API 요청 한도 초과 ({code}) — 잠시 후 자동 재시도합니다."
        return f"Gemini API 오류 ({code}) — 자동 재시도합니다."
    if isinstance(exc, httpx.TimeoutException):
        return "Gemini API 응답 시간 초과 — 자동 재시도합니다."
    if isinstance(exc, httpx.HTTPError):
        return "Gemini API 통신 오류 — 자동 재시도합니다."
    return f"LLM 추출 단계 오류 ({type(exc).__name__}) — 재시도 버튼으로 다시 시도해 주세요."


@celery_app.task(name="m6.extract", bind=True, max_retries=3, queue="m6_graph")
def extract_task(self, ctx: dict) -> dict:
    """LLM 개념 추출 + 벡터 임베딩 + staging DRAFT 적재."""
    if ctx.get("skip") or ctx.get("awaiting_metadata"):
        return ctx
    session_id = ctx["session_id"]
    _emit(session_id, {"type": "step_update", "step": "Extractor", "status": "RUNNING"})
    try:
        result = _run_async(_extract_async(ctx))
        if result.get("no_concepts_found"):
            _emit(session_id, {
                "type": "step_update", "step": "Extractor", "status": "FAILED",
                "reason": _NO_CONCEPTS_FOUND_MESSAGE,
            })
        else:
            _emit(session_id, {"type": "step_update", "step": "Extractor", "status": "DONE"})
        _emit(session_id, {"type": "finished"})
        return result
    except Exception as exc:
        is_final = self.request.retries >= self.max_retries
        reason = _classify_error(exc)
        _emit(session_id, {
            "type": "step_update", "step": "Extractor", "status": "FAILED", "reason": reason,
        })
        _set_failed_sync(session_id)
        if is_final:
            _emit(session_id, {"type": "finished"})
        raise self.retry(exc=exc, countdown=60) from exc


async def _extract_async(ctx: dict) -> dict:
    from app.infrastructure.graph.hybrid_resolver import HybridResolver, _embed_async

    session_id = ctx["session_id"]
    doc_id = ctx["doc_id"]
    chunks = ctx.get("chunks", [""])
    _log(session_id, "Extractor", "LLM 개념 추출 시작 (4-Layer 온톨로지 컨텍스트 주입)")
    await _update_doc_state(doc_id, "EXTRACTING")

    conn = await asyncpg.connect(_PG_DSN)
    try:
        allowed_domains = await _list_allowed_domains(conn)
        _log(session_id, "Extractor", f"활성 도메인 레지스트리 조회 완료: {allowed_domains}")
        metadata = {
            "framework": ctx.get("framework"),
            "language": ctx.get("lang"),
            "allowed_domains": allowed_domains,
        }

        concepts: list[dict] = []
        for idx, chunk in enumerate(chunks):
            if USE_REAL_LLM and idx > 0:
                _log(session_id, "Extractor", "Gemini 무료 티어 20RPM 제한 회피 - 4초 대기")
                await asyncio.sleep(4)
            if not USE_REAL_LLM and idx > 0:
                _log(session_id, "Extractor", "MOCK 모드: 잔여 청크 건너뜀 (중복 적재 방지)")
                break
            extracted = await _llm_extract(chunk, ctx, metadata)
            concepts.extend(extracted)

        for concept in concepts:
            _ensure_domains(concept, ctx, allowed_domains)

        concepts = _validate_concepts(concepts, session_id, doc_id)

        if not concepts:
            _log(session_id, "Extractor", "본문에서 분석 가능한 핵심 개념(안티패턴/약점)을 찾지 못함 - staging 적재 건너뜀")
            await _update_doc_state_conn(conn, doc_id, "EXTRACTED")
            return {**ctx, "staged": 0, "no_concepts_found": True}

        _log(session_id, "Extractor", f"{len(concepts)}개 개념 추출 완료({[concept['concept_name'] for concept in concepts]})")

        _emit(session_id, {"type": "step_update", "step": "Resolver", "status": "RUNNING"})
        resolver = HybridResolver()
        staged = 0
        for idx, concept in enumerate(concepts):
            _log(session_id, "Resolver", f"[{idx + 1}/{len(concepts)}] '{concept['concept_name']}' 벡터 임베딩 중... (CPU, 30초~2분 소요)")
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

        _emit(session_id, {"type": "step_update", "step": "Resolver", "status": "DONE"})
        await _update_doc_state_conn(conn, doc_id, "EXTRACTED")
        _log(session_id, "Extractor", f"staging DRAFT {staged}건 - HITL 검토 대기")
    finally:
        await conn.close()

    return {**ctx, "staged": staged}


async def _list_allowed_domains(conn: asyncpg.Connection) -> list[str]:
    """Layer 0 - 활성 도메인 레지스트리 조회 (LLM 추출 시 domains 분류 컨텍스트로 주입)."""
    rows = await conn.fetch(
        "SELECT name FROM domain_registry WHERE is_active = true ORDER BY name"
    )
    return [row["name"] for row in rows]


def _ensure_domains(concept: dict, ctx: dict, allowed_domains: list[str]) -> None:
    """[Checkpoint] 도메인 배지 누락 검증 - Layer 0 allowed_domains 기준으로 정규화한다."""
    raw = concept.get("domains") or []
    if allowed_domains:
        domains = [d for d in raw if d in allowed_domains]
        if not domains:
            domains = [allowed_domains[0]]
    else:
        domains = raw or [ctx.get("source_prefix", "external")]
    concept["domains"] = domains


def _validate_concepts(concepts: list[dict], session_id: str, doc_id: str) -> list[dict]:
    """[Checkpoint] Pydantic 강제 파싱 + 논리 무결성 검증 (crawling-chunking-guide-v2.md §1, §2).

    description_ko 노이즈 위반은 "이 청크에는 분석 가능한 본문이 없다"는 신호로 보고
    해당 개념만 건너뛴다 (취약점/안티패턴과 무관한 페이지일 수 있음). 그 외 스키마/온톨로지
    위반은 ValidationError를 그대로 전파하여 extract_task의 except 블록이 staging 적재를
    차단하고 세션을 FAILED로 전이시키도록 한다.
    """
    validated: list[dict] = []
    for concept in concepts:
        try:
            schema = ConceptExtractionSchema(**concept)
        except ValidationError as exc:
            if "노이즈" in str(exc):
                logger.debug(
                    "concept_skipped_noise session_id=%s doc_id=%s concept=%s",
                    session_id, doc_id, concept,
                )
                continue
            logger.debug(
                "concept_validation_failed session_id=%s doc_id=%s concept=%s error=%s",
                session_id, doc_id, concept, exc,
            )
            raise
        normalized = schema.model_dump()
        logger.debug(
            "concept_validated session_id=%s doc_id=%s concept_name=%s description_ko=%s",
            session_id, doc_id, normalized["concept_name"], normalized["description_ko"],
        )
        validated.append(normalized)
    return validated


async def _llm_extract(chunk: str, ctx: dict, metadata: dict | None = None) -> list[dict]:
    if USE_REAL_LLM and GEMINI_API_KEY:
        return await _gemini_extract(chunk, ctx, metadata)
    return _mock_extract(chunk, ctx, metadata)


def _mock_extract(chunk: str, ctx: dict, metadata: dict | None = None) -> list[dict]:
    short_hash = hashlib.md5(chunk[:50].encode()).hexdigest()[:6]
    fw = ctx.get("framework") or "unknown"
    # crawling-chunking-guide-v3.md §2 — concept_name은 ^[A-Z][a-zA-Z0-9]+$ PascalCase 강제
    # (concept_ 접두사/해시 접미사/프레임워크 원형(예: "Next.js") 금지)
    fw_pascal = re.sub(r"[^A-Za-z0-9+-]", "", fw) or "Unknown"
    fw_pascal = fw_pascal[0].upper() + fw_pascal[1:]
    allowed_domains = (metadata or {}).get("allowed_domains") or []
    domains = [allowed_domains[0]] if allowed_domains else [ctx.get("source_prefix", "external")]
    return [{
        "concept_name": f"{fw_pascal}Concept{short_hash.capitalize()}",
        "concept_type": "antipattern",  # ◄ 형님의 결정 반영 (antipattern 고정)
        "cwe_id": "CWE-000",
        "owasp_id": None,
        "severity": "medium",
        "domains": domains,
        "description_ko": chunk[:200] if chunk else "모크 데이터 설명 본문입니다.",
        "aliases": [f"{fw_pascal} Antipattern"],
        "root_cause": "mock_root_cause",
        "affected_components": ["mock_component"],
        "mechanism": [
            {
                "mechanism_name": "mock_defense_mechanism",
                "code_examples": [
                    {
                        "lang": ctx.get("lang", "python"),
                        "lang_version": "*",
                        "framework": fw.lower(),
                        "framework_version": "*",
                        "code": "# Mock Code Example\npass",
                        "description": "모크 구현 코드 설명입니다."
                    }
                ]
            }
        ],
        "config_properties": []  # ◄ 스키마 구조 싱크용 추가
    }]

async def _gemini_extract(chunk: str, ctx: dict, metadata: dict | None = None) -> list[dict]:
    metadata = metadata or {}
    allowed_domains = metadata.get("allowed_domains") or []
    domain_hint = ", ".join(allowed_domains) if allowed_domains else "general"
    prompt = (
        "다음 문서 텍스트를 4-Layer 온톨로지 구조"
        "(Layer0 Domain - Layer1 Concept[문제/취약점 중심] - Layer2 Mechanism/Property/RootCause/Component[종속 속성] - "
        "Layer3 CodeExample)에 맞춰 JSON 배열로 추출하라.\n"
        f"- framework: {metadata.get('framework') or ctx.get('framework')}\n"
        f"- language: {metadata.get('language') or ctx.get('lang')}\n"
        f"- allowed_domains (Layer0, 이 중에서만 분류): [{domain_hint}]\n"
        "각 항목은 하나의 최상위 Concept(Layer2)을 기준으로 하며, 하위 필드로 명시된 명사들을 추출한다"
        "필드 구성: concept_name, concept_type, domains(allowed_domains 중에서 선택), description_ko, "
        "aliases, root_cause, affected_components, "
        "mechanism(mechanism_name, code_examples[{lang, framework, code, description}]).\n\n"
        "## [절대 엄수 제약 조건 - 위반 시 검증 실패로 적재가 차단된다]\n"
        "1. 노이즈 차단: 'This page is also available as Markdown', 'Was this helpful?', "
        "'Last updated', 'llms.txt', 메뉴/내비게이션/배너 등 기술 본문과 무관한 웹사이트 "
        "레이아웃 텍스트는 description_ko에서 절대 인용하지 말고 철저히 무시하라.\n"
        "2. 명명 규칙 강제: concept_name은 'concept_' 접두사나 해시 접미사, 프레임워크 이름을 절대 포함하지 않는 순수 파스칼케이스(PascalCase) 명사여야 한다"
        "또한, 방어/해결책 명칭(예: CsrfProtection, XssDefense)을 최상위 concept_name으로 삼는 것을 절대 금지하며, "
        "반드시 문제 본질이나 안티패턴 명칭을 써야 한다. 올바른 예: CsrfAttack, MemoryLeak. 잘못된 예: CsrfProtection.\nn"
        "3.타입 제한: 최상위 객체의 concept_type은 'concept'(보안 취약점 등 일반 개념) 또는 'antipattern' 중 하나로만 분류하라."
        "4. 4. 문제 중심 역산 추출: 입력 문서가 'CsrfProtection'이나 'csrf-csrf 미들웨어 설정'처럼 오직 방어 기법/해결책만 설명하고 있더라도, "
"해당 방어 기술이 막고자 하는 '본질적인 취약점/안티패턴 이름'(예: CSRF)을 역산하여 최상위 concept_name(Layer1)으로 반드시 추출하라. "
"그리고 문서에 나온 패키지 설정이나 미들웨어 코드는 그 아래의 mechanism(mechanism_name: 'double_csrf_protection' 등) 배열로 밀어 넣어라."
        "5. Null 처리: 해당 정보가 본문에 없는 메타 필드는 키를 누락시키지 말고 null 또는 빈 배열([])로 명시하라.\n\n"
        "## 모범 출력 예시 (Few-Shot)\n"
        "입력된 텍스트가 메모리 누수에 관한 것이라면 아래와 같이 출력해야 한다:\n"
        "[\n"
        "  {\n"
        '    "concept_name": "MemoryLeak",\n'
        '    "concept_type": "antipattern",\n'
        '    "domains": ["performance"],\n'
        '    "description_ko": "메모리 누수는 더 이상 사용하지 않는 메모리를 해제하지 않아 힙이 지속 증가하는 안티패턴이다.",\n'
        '    "aliases": ["Memory Leak", "OOM"],\n'
        '    "root_cause": "object_reference_retained_preventing_gc",\n'
        '    "affected_components": ["long_running_worker"],\n'
        '    "mechanism": [{"mechanism_name": "bounded_cache_eviction", "code_examples": []}]\n'
        "  }\n"
        "]\n\n"
        "마크다운 래핑 기호 외에 어떠한 부연 설명 텍스트도 출력하지 마라.\n\n"
        + _FORMAT_INSTRUCTIONS
        + "\n\n"
        + chunk[:30000]
    )
    
    logger.debug("%s gemini_raw_request START %s", "=" * 10, "=" * 10)
    logger.debug("[%s 자] %s", len(prompt), prompt)
    logger.debug("%s gemini_raw_request END %s", "=" * 10, "=" * 10)
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}"
            f":generateContent?key={GEMINI_API_KEY}",
            json={"contents": [{"parts": [{"text": prompt}]}]},
        )
        resp.raise_for_status()
        text = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
    logger.debug("%s gemini_raw_response START %s", "=" * 10, "=" * 10)
    logger.debug("[%s 자] %s", len(text), text)
    logger.debug("%s gemini_raw_response END %s", "=" * 10, "=" * 10)
    logger.debug("gemini_raw_response chunk_len=%d response=%s", len(chunk), text)
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
    _emit(session_id, {"type": "step_update", "step": "Writer", "status": "RUNNING"})
    try:
        result = _run_async(_write_graph_async(session_id))
        _emit(session_id, {"type": "step_update", "step": "Writer", "status": "DONE"})
        _emit(session_id, {"type": "finished"})
        return result
    except Exception as exc:
        _set_failed_sync(session_id)
        raise self.retry(exc=exc, countdown=15) from exc


async def _write_graph_async(session_id: str) -> dict:
    from app.adapters.db.neo4j_repo import Neo4jConceptRepo, merge_related_to
    from app.core.neo4j_client import get_database, get_driver
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

                if action == "MERGE" and row["target_concept_name"]:
                    await repo.absorb_into_target(concept, row["target_concept_name"])
                    await resolver.do_centroid_shift(
                        row["target_concept_name"], concept.aliases
                    )
                else:
                    if (
                        action == "RELATED_TO"
                        and row["target_concept_name"]
                        and _DEFENSE_NAME_PATTERN.search(concept.concept_name)
                    ):
                        # 정책 2: 방어책 오기출 → target의 L3 Mechanism으로 격하 이식
                        await repo.transplant_as_mechanism(concept, row["target_concept_name"])
                    else:
                        await repo.merge_concept(concept)
                        if action == "RELATED_TO" and row["target_concept_name"]:
                            await merge_related_to(
                                driver, concept.concept_name,
                                row["target_concept_name"], get_database()
                            )

                summary[action] = summary.get(action, 0) + 1

            await conn.execute(
                "UPDATE knowledge_documents SET state = 'COMMITTED', updated_at = now() "
                "WHERE session_id = $1",
                session_id,
            )
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


def resume_pipeline(ctx: dict) -> None:
    """HITL 메타데이터 입력(또는 skip) 완료 후 crawl -> extract 체인 재개."""
    chain = crawl_task.s(ctx) | extract_task.s()
    chain.apply_async()
