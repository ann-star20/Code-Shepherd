"""P1-T10: POST /api/documents/{doc_id}/prescan — DB 주도형 자율 학습 프리스캔.

v3.2 — `framework_metadata` 테이블 기반 동적 패턴 매칭으로 하드코딩
`_FRAMEWORK_PATTERNS`를 완전히 대체한다. ETag는 대소문자 무관으로 포획해
`knowledge_documents.etag`에 영속화하고, 문서 원문 언어는 `knowledge_documents.doc_lang`에
별도 저장한다. `/metadata/learn`은 관리자가 HITL 모달에서 확정한 신규
프레임워크/패턴을 `framework_metadata`에 자율 학습시킨다.
"""

from __future__ import annotations

import logging
import re
from typing import Optional

import asyncpg
import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.interfaces.api._deps import get_conn

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/documents", tags=["prescan"])

_VERSION_PATTERN = re.compile(r"/(\d+\.\d+(?:\.\d+)?)/")
_LANG_PATTERN = re.compile(r'<html[^>]+lang=["\']([a-zA-Z-]+)["\']', re.IGNORECASE)
_TITLE_PATTERN = re.compile(r"<title>([^<]+)</title>", re.IGNORECASE)

CONFIDENCE_AUTO_THRESHOLD = 0.8

# NestJS 공식 문서는 URL 경로에 버전을 명시하지 않으므로(예: /security/authorization),
# 패턴 매칭으로 NestJS가 식별되면 최신 메이저 버전을 기본값으로 간주한다.
_NESTJS_DEFAULT_VERSION = "10.0"


# ── 스키마 ─────────────────────────────────────────────────────────────────


class PrescanResult(BaseModel):
    """프리스캔 추론 결과 + HITL 드롭다운 제안 페이로드."""

    doc_id: str
    original_url: str
    framework: Optional[str] = None
    version: Optional[str] = None
    lang: Optional[str] = None  # 프로그래밍/인프라 설정 언어
    doc_lang: Optional[str] = None  # 문서 원문 언어 (EN, KR ...)
    infer_confidence: float
    infer_status: str  # "auto" | "manual_required"
    suggested_frameworks: list[str] = []  # HITL 드롭다운용 등록 프레임워크 목록
    suggested_versions: list[str] = []  # HITL 드롭다운용 해당 프레임워크 버전 목록


class LearnMetadataRequest(BaseModel):
    """HITL 모달에서 관리자가 직접 입력한 신규 프레임워크/패턴 학습 요청."""

    framework: str
    pattern: str
    supported_langs: list[str] = Field(min_length=1)
    default_lang: Optional[str] = None


# ── 추출 헬퍼 ──────────────────────────────────────────────────────────────


def _extract_version(url: str) -> Optional[str]:
    """URL 경로에서 `/major.minor[.patch]/` 형태의 버전을 추출."""
    match = _VERSION_PATTERN.search(url)
    return match.group(1) if match else None


def _resolve_version(url: str, framework: Optional[str]) -> Optional[str]:
    """URL에서 버전을 추출하되, NestJS처럼 URL에 버전을 명시하지 않는
    프레임워크는 등록된 기본 버전으로 보정한다."""
    version = _extract_version(url)
    if version:
        return version
    if framework == "NestJS":
        return _NESTJS_DEFAULT_VERSION
    return None


def _extract_doc_lang(html: str) -> Optional[str]:
    """`<html lang="...">`에서 문서 원문 언어 코드를 추출 (대문자 2글자)."""
    match = _LANG_PATTERN.search(html)
    return match.group(1).split("-")[0].upper() if match else None


def _extract_title(html: str) -> Optional[str]:
    match = _TITLE_PATTERN.search(html)
    return match.group(1) if match else None


# ── DB 주도형 추론 로직 ────────────────────────────────────────────────────


async def _infer_via_db_patterns(
    conn: asyncpg.Connection, url: str
) -> tuple[Optional[str], float]:
    """`framework_metadata.url_patterns`를 런타임에 컴파일하여 URL 매칭.

    정규식 컴파일 실패는 전체 추론을 중단시키지 않고 다음 패턴으로 넘어간다.
    """
    rows = await conn.fetch("SELECT framework, url_patterns FROM framework_metadata")
    for row in rows:
        fw_name = row["framework"]
        for pattern_str in row["url_patterns"]:
            try:
                if re.search(pattern_str, url, re.IGNORECASE):
                    return fw_name, 0.5
            except re.error as exc:
                logger.error(
                    "[Regex Error] '%s'의 패턴 '%s' 컴파일 실패: %s",
                    fw_name,
                    pattern_str,
                    exc,
                )
                continue
    return None, 0.0


async def _infer_via_title(conn: asyncpg.Connection, html: str) -> Optional[str]:
    """URL 패턴 매칭 실패 시 `<title>` 텍스트에서 등록된 프레임워크명을 탐색."""
    title = _extract_title(html)
    if not title:
        return None

    rows = await conn.fetch("SELECT framework FROM framework_metadata")
    for row in rows:
        fw_name = row["framework"]
        if re.search(re.escape(fw_name), title, re.IGNORECASE):
            return fw_name
    return None


async def _resolve_default_lang(
    conn: asyncpg.Connection, framework: Optional[str]
) -> Optional[str]:
    """추론된 framework의 기본 프로그래밍/설정 언어를 `framework_metadata`에서 조회."""
    if not framework:
        return None
    row = await conn.fetchrow(
        "SELECT default_lang FROM framework_metadata WHERE framework = $1", framework
    )
    return row["default_lang"] if row else None


# ── 엔드포인트 ─────────────────────────────────────────────────────────────


@router.post("/{doc_id}/prescan", response_model=PrescanResult)
async def prescan_document(
    doc_id: str,
    conn=Depends(get_conn),
):
    """문서 URL을 경량 스캔하여 framework/version/lang/doc_lang 메타데이터를 자동 추론.

    추론 단계:
      1. `framework_metadata.url_patterns` 런타임 동적 매칭 (하드코딩 0%)
      2. 매칭 실패 시 `<title>` 텍스트에서 등록된 프레임워크명 탐색
      3. URL 버전 패턴 + `<html lang>` 문서 언어(doc_lang) 추출
      4. ETag 대소문자 무관 포획 (`ETag` | `etag`) 후 영속화
      5. confidence < 0.8 → manual_required, suggested_frameworks(HITL 드롭다운) 반환
    """
    row = await conn.fetchrow(
        "SELECT doc_id, original_url FROM knowledge_documents WHERE doc_id = $1",
        doc_id,
    )
    if row is None:
        raise HTTPException(status_code=404, detail=f"document '{doc_id}' not found")

    url = row["original_url"]
    framework: Optional[str] = None
    version: Optional[str] = None
    doc_lang: Optional[str] = None
    etag: Optional[str] = None
    confidence = 0.0

    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            resp = await client.get(url)
            etag = resp.headers.get("ETag") or resp.headers.get("etag")
            if etag:
                etag = etag.strip('"')
            if resp.status_code == 200:
                framework, confidence = await _infer_via_db_patterns(conn, url)

                doc_lang = _extract_doc_lang(resp.text)
                if doc_lang:
                    confidence = min(confidence + 0.1, 1.0)

                if not framework:
                    framework = await _infer_via_title(conn, resp.text)
                    if framework:
                        confidence = min(confidence + 0.3, 1.0)

                version = _resolve_version(url, framework)
                if version:
                    confidence = min(confidence + 0.3, 1.0)
            else:
                framework, confidence = await _infer_via_db_patterns(conn, url)
                version = _resolve_version(url, framework)
                if version:
                    confidence = min(confidence + 0.3, 1.0)
    except (httpx.HTTPError, OSError):
        framework, confidence = await _infer_via_db_patterns(conn, url)
        version = _resolve_version(url, framework)
        if version:
            confidence = min(confidence + 0.3, 1.0)

    lang = await _resolve_default_lang(conn, framework)

    infer_status = (
        "auto" if confidence >= CONFIDENCE_AUTO_THRESHOLD else "manual_required"
    )

    # manual_required 시 드롭다운 제안 목록 반환
    suggested_frameworks: list[str] = []
    if infer_status == "manual_required":
        fw_rows = await conn.fetch(
            "SELECT framework FROM framework_metadata ORDER BY framework"
        )
        suggested_frameworks = [r["framework"] for r in fw_rows]

    suggested_versions: list[str] = []
    if framework:
        ver_rows = await conn.fetch(
            "SELECT DISTINCT version FROM knowledge_documents "
            "WHERE framework = $1 AND version IS NOT NULL ORDER BY version",
            framework,
        )
        suggested_versions = [r["version"] for r in ver_rows]

    await conn.execute(
        """UPDATE knowledge_documents
           SET framework = $1, version = $2, lang = $3, doc_lang = $4,
               etag = $5, infer_confidence = $6, updated_at = now()
           WHERE doc_id = $7""",
        framework,
        version,
        lang,
        doc_lang,
        etag,
        confidence,
        doc_id,
    )

    return PrescanResult(
        doc_id=doc_id,
        original_url=url,
        framework=framework,
        version=version,
        lang=lang,
        doc_lang=doc_lang,
        infer_confidence=round(confidence, 3),
        infer_status=infer_status,
        suggested_frameworks=suggested_frameworks,
        suggested_versions=suggested_versions,
    )


@router.post("/metadata/learn")
async def learn_framework_metadata(
    req: LearnMetadataRequest,
    conn=Depends(get_conn),
):
    """관리자가 HITL 모달에서 입력한 신규 인프라/프레임워크 패턴을 자율 학습.

    `framework_metadata`에 upsert하여 코드 수정·재배포 없이 다음 프리스캔부터
    `_infer_via_db_patterns`가 즉시 새 패턴을 인식하도록 한다.
    """
    try:
        re.compile(req.pattern)
    except re.error as exc:
        raise HTTPException(
            status_code=422, detail=f"invalid regex pattern: {exc}"
        ) from exc

    default_lang = req.default_lang or req.supported_langs[0]

    await conn.execute(
        """INSERT INTO framework_metadata (framework, url_patterns, supported_langs, default_lang)
           VALUES ($1, ARRAY[$2::text], $3, $4)
           ON CONFLICT (framework) DO UPDATE
           SET url_patterns = CASE
                   WHEN framework_metadata.url_patterns @> ARRAY[$2::text]
                   THEN framework_metadata.url_patterns
                   ELSE array_append(framework_metadata.url_patterns, $2)
               END,
               supported_langs = $3,
               default_lang = $4""",
        req.framework,
        req.pattern,
        req.supported_langs,
        default_lang,
    )

    return {
        "status": "SUCCESS",
        "message": f"'{req.framework}' 생태계 학습 및 동기화 완료.",
    }
