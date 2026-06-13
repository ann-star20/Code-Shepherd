"""문서 중복 검사 + 프레임워크 메타데이터 학습 엔드포인트."""

from __future__ import annotations

import asyncpg
from fastapi import APIRouter
from pydantic import BaseModel, HttpUrl

from app.core.config import pg_dsn

router = APIRouter(prefix="/documents", tags=["documents"])

_PG_DSN = pg_dsn()


class CheckDuplicateRequest(BaseModel):
    url: HttpUrl


class CheckDuplicateResponse(BaseModel):
    is_duplicate: bool
    doc_id: str | None = None


@router.post("/check-duplicate", response_model=CheckDuplicateResponse)
async def check_duplicate(payload: CheckDuplicateRequest) -> CheckDuplicateResponse:
    """동일 원본 URL의 미배제 문서 존재 여부 확인."""
    conn = await asyncpg.connect(_PG_DSN)
    try:
        row = await conn.fetchrow(
            "SELECT doc_id FROM knowledge_documents "
            "WHERE original_url = $1 AND is_deprecated = false "
            "ORDER BY created_at DESC LIMIT 1",
            str(payload.url),
        )
        if row is None:
            return CheckDuplicateResponse(is_duplicate=False)
        return CheckDuplicateResponse(is_duplicate=True, doc_id=row["doc_id"])
    finally:
        await conn.close()


class MetadataLearnRequest(BaseModel):
    framework: str
    pattern: str
    supported_langs: list[str]
    default_lang: str | None = None


@router.post("/metadata/learn", status_code=200)
async def learn_metadata(payload: MetadataLearnRequest) -> dict[str, str]:
    """프레임워크 URL 패턴/지원 언어 학습 - HITL 메타데이터 보정."""
    conn = await asyncpg.connect(_PG_DSN)
    try:
        await conn.execute(
            "INSERT INTO framework_metadata (framework, url_patterns, supported_langs, default_lang) "
            "VALUES ($1, ARRAY[$2::text], $3, COALESCE($4, $3[1])) "
            "ON CONFLICT (framework) DO UPDATE SET "
            "    url_patterns = CASE WHEN $2 = ANY(framework_metadata.url_patterns) "
            "                         THEN framework_metadata.url_patterns "
            "                         ELSE array_append(framework_metadata.url_patterns, $2::text) END, "
            "    supported_langs = $3, "
            "    default_lang = COALESCE($4, framework_metadata.default_lang)",
            payload.framework,
            payload.pattern,
            payload.supported_langs,
            payload.default_lang,
        )
        return {"framework": payload.framework, "status": "learned"}
    finally:
        await conn.close()
