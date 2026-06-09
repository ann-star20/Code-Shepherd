"""P1-T9: POST /api/documents — URL 입력, doc_id 생성, PENDING 적재."""

import hashlib
import re
from urllib.parse import urlparse, urlunparse

from fastapi import APIRouter, Depends
from pydantic import BaseModel, HttpUrl, field_validator

from app.interfaces.api._deps import get_conn

router = APIRouter(prefix="/api/documents", tags=["documents"])

# 파이프라인 처리 중인 상태 — 중복 트리거 방지 대상
_ACTIVE_STATES = frozenset({"PENDING", "CRAWLING", "EXTRACTING", "EXTRACTED"})


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


# ── doc_id / content_hash 생성 ─────────────────────────────────────────────

def _build_doc_id(prefix: str, url: str) -> str:
    """PREFIX_urlpart_sha8 형식 마스터 키 생성."""
    parsed = urlparse(url)
    normalized = urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", "", ""))
    url_part = re.sub(r"[:/.]", "-", normalized).strip("-")[:80]
    hash8 = hashlib.sha256(url.encode()).hexdigest()[:8]
    return f"{prefix}_{url_part}_{hash8}"


def _content_hash(url: str) -> str:
    """URL 기반 8자리 SHA-256 content hash."""
    return hashlib.sha256(url.encode()).hexdigest()[:8]


# ── 엔드포인트 ─────────────────────────────────────────────────────────────

@router.post("", status_code=201, response_model=DocumentsResponse)
async def submit_documents(
    body: DocumentsRequest,
    conn=Depends(get_conn),
):
    """외부 문서 URL을 최대 5개 입력받아 PENDING 상태로 등록.

    상태별 처리 정책 (ETag/Content-Hash 우선순위 가드레일):
    - FAILED     → staging_concepts + pipeline_logs 원자적 삭제 후 PENDING 복구 (Clean Reboot)
    - ACTIVE     → 이미 처리 중인 문서: 기존 상태 그대로 반환 (중복 트리거 방지)
    - COMMITTED  → 완료된 문서: 기존 상태 그대로 반환
    - 신규       → PENDING 으로 최초 적재
    """
    results: list[DocumentItem] = []

    for url_obj in body.urls:
        url = str(url_obj)
        doc_id = _build_doc_id("EXT", url)
        content_hash = _content_hash(url)

        existing = await conn.fetchrow(
            "SELECT state FROM documents WHERE doc_id = $1",
            doc_id,
        )

        if existing:
            state: str = existing["state"]

            if state == "FAILED":
                # FAILED 클린 리부팅: 오염된 staging/logs 원자적 제거 → PENDING 복구
                async with conn.transaction():
                    await conn.execute(
                        "DELETE FROM staging_concepts WHERE doc_id = $1", doc_id
                    )
                    await conn.execute(
                        "DELETE FROM pipeline_logs WHERE doc_id = $1", doc_id
                    )
                    await conn.execute(
                        """UPDATE documents
                              SET state = 'PENDING', content_hash = $2, updated_at = now()
                            WHERE doc_id = $1""",
                        doc_id, content_hash,
                    )
            elif state in _ACTIVE_STATES or state == "COMMITTED":
                # 처리 중이거나 완료된 문서: 기존 상태 유지 (중복 트리거 방지)
                pass
            else:
                # 알 수 없는 상태: PENDING 으로 리셋
                await conn.execute(
                    """UPDATE documents
                          SET state = 'PENDING', content_hash = $2, updated_at = now()
                        WHERE doc_id = $1""",
                    doc_id, content_hash,
                )
        else:
            await conn.execute(
                """INSERT INTO documents (doc_id, source_prefix, original_url, content_hash, state)
                   VALUES ($1, 'EXT', $2, $3, 'PENDING')
                   ON CONFLICT (doc_id) DO NOTHING""",
                doc_id, url, content_hash,
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
