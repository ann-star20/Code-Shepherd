"""P1-T10: POST /api/documents/{doc_id}/prescan — Pre-scan 메타 추론."""

import re
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.interfaces.api._deps import get_conn

router = APIRouter(prefix="/api/documents", tags=["prescan"])

# URL 경로에서 프레임워크/버전 추론 패턴
_FRAMEWORK_PATTERNS = [
    (re.compile(r"djangoproject\.com"),               "Django"),
    (re.compile(r"spring\.io|docs\.spring\.io"),      "Spring"),
    (re.compile(r"flask\.palletsprojects\.com"),      "Flask"),
    (re.compile(r"fastapi\.tiangolo\.com"),           "FastAPI"),
    (re.compile(r"laravel\.com"),                     "Laravel"),
    (re.compile(r"rubyonrails\.org"),                 "Rails"),
    (re.compile(r"expressjs\.com"),                   "Express"),
    (re.compile(r"nestjs\.com"),                      "NestJS"),
    (re.compile(r"owasp\.org"),                       "OWASP"),
]

_VERSION_PATTERN = re.compile(r"/(\d+\.\d+(?:\.\d+)?)/")


# ── 스키마 ─────────────────────────────────────────────────────────────────

class PrescanResult(BaseModel):
    doc_id: str
    original_url: str
    framework: Optional[str] = None
    version: Optional[str] = None
    lang: Optional[str] = None
    infer_confidence: float
    infer_status: str  # "auto" | "manual_required"


# ── 추론 로직 ──────────────────────────────────────────────────────────────

def _infer_from_url(url: str) -> tuple[Optional[str], Optional[str], float]:
    """URL 패턴에서 framework, version, confidence 추론."""
    framework = None
    for pattern, name in _FRAMEWORK_PATTERNS:
        if pattern.search(url):
            framework = name
            break

    version_match = _VERSION_PATTERN.search(url)
    version = version_match.group(1) if version_match else None

    confidence = 0.0
    if framework:
        confidence += 0.5
    if version:
        confidence += 0.3
    return framework, version, confidence


def _infer_from_html(html: str, url: str) -> tuple[Optional[str], Optional[str], Optional[str], float]:
    """HTML 메타에서 framework, version, lang, confidence 추론."""
    framework, version, base_conf = _infer_from_url(url)

    # <html lang="..."> 추출
    lang_match = re.search(r'<html[^>]+lang=["\']([a-zA-Z-]+)["\']', html, re.IGNORECASE)
    lang = lang_match.group(1).split("-")[0].upper() if lang_match else None
    if lang:
        base_conf += 0.1

    # <title> / <h1>에서 프레임워크 키워드
    if not framework:
        title_match = re.search(r"<title>([^<]+)</title>", html, re.IGNORECASE)
        if title_match:
            title = title_match.group(1)
            for pattern, name in _FRAMEWORK_PATTERNS:
                if re.search(name, title, re.IGNORECASE):
                    framework = name
                    base_conf += 0.3
                    break

    return framework, version, lang, min(base_conf, 1.0)


# ── 엔드포인트 ─────────────────────────────────────────────────────────────

@router.post("/{doc_id}/prescan", response_model=PrescanResult)
async def prescan_document(
    doc_id: str,
    conn=Depends(get_conn),
):
    """문서 URL을 경량 스캔하여 framework/version/lang 메타데이터를 자동 추론."""
    row = await conn.fetchrow(
        "SELECT doc_id, original_url, state FROM documents WHERE doc_id = $1",
        doc_id,
    )
    if row is None:
        raise HTTPException(status_code=404, detail=f"document '{doc_id}' not found")

    url = row["original_url"]
    framework = version = lang = None
    confidence = 0.0

    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            resp = await client.get(url)
            if resp.status_code == 200:
                framework, version, lang, confidence = _infer_from_html(resp.text, url)
            else:
                framework, version, confidence = _infer_from_url(url)
    except Exception:
        # HTTP 실패 시 URL만으로 추론
        framework, version, confidence = _infer_from_url(url)

    infer_status = "auto" if confidence >= 0.5 else "manual_required"

    # documents 테이블 업데이트
    await conn.execute(
        """UPDATE documents
           SET framework = $1, version = $2, lang = $3,
               infer_confidence = $4, updated_at = now()
           WHERE doc_id = $5""",
        framework, version, lang, confidence, doc_id,
    )

    return PrescanResult(
        doc_id=doc_id,
        original_url=url,
        framework=framework,
        version=version,
        lang=lang,
        infer_confidence=confidence,
        infer_status=infer_status,
    )
