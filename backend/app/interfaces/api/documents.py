"""P1-T9: POST /api/documents — URL 입력, doc_id 생성, PENDING 적재."""

import hashlib
import re
from typing import Annotated
from urllib.parse import urlparse, urlunparse

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, HttpUrl, field_validator

from app.interfaces.api._deps import get_conn

router = APIRouter(prefix="/api/documents", tags=["documents"])


# ── 스키마 ─────────────────────────────────────────────────────────────────

class DocumentsRequest(BaseModel):
    urls: list[HttpUrl]

    @field_validator("urls")
    @classmethod
    def validate_url_count(cls, v):
        if len(v) == 0:
            raise ValueError("최소 1개 URL 필요")
        if len(v) > 5:
            raise ValueError("최대 5개 URL까지 입력 가능")
        return v


class DocumentItem(BaseModel):
    doc_id: str
    state: str
    original_url: str


class DocumentsResponse(BaseModel):
    documents: list[DocumentItem]


# ── doc_id 생성 ────────────────────────────────────────────────────────────

def _build_doc_id(prefix: str, url: str, content: str = "") -> str:
    """PREFIX_urlpart_sha8 형식 마스터 키 생성."""
    parsed = urlparse(url)
    normalized = urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", "", ""))
    url_part = re.sub(r"[:/.]", "-", normalized).strip("-")[:80]
    hash8 = hashlib.sha256((content or url).encode()).hexdigest()[:8]
    return f"{prefix}_{url_part}_{hash8}"


# ── 엔드포인트 ─────────────────────────────────────────────────────────────

@router.post("", status_code=201, response_model=DocumentsResponse)
async def submit_documents(
    body: DocumentsRequest,
    conn=Depends(get_conn),
):
    """외부 문서 URL을 최대 5개 입력받아 PENDING 상태로 등록."""
    results: list[DocumentItem] = []

    for url_obj in body.urls:
        url = str(url_obj)
        doc_id = _build_doc_id("EXT", url)

        await conn.execute(
            """
            INSERT INTO documents (doc_id, source_prefix, original_url, content_hash, state)
            VALUES ($1, 'EXT', $2, $3, 'PENDING')
            ON CONFLICT (doc_id) DO UPDATE SET updated_at = now()
            """,
            doc_id, url, doc_id[-8:],
        )

        row = await conn.fetchrow(
            "SELECT doc_id, state, original_url FROM documents WHERE doc_id = $1",
            doc_id,
        )
        results.append(DocumentItem(
            doc_id=row["doc_id"],
            state=row["state"],
            original_url=row["original_url"],
        ))

    return DocumentsResponse(documents=results)
