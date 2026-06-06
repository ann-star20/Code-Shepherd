"""P1-T10: POST /api/documents/{doc_id}/prescan — Pre-scan 메타 추론."""

from __future__ import annotations

import difflib
import re
from typing import Optional
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.interfaces.api._deps import get_conn

router = APIRouter(prefix="/api/documents", tags=["prescan"])

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
_DOMAIN_STRIP = re.compile(r"(www\.|\.com|\.org|\.io|\.net|\.dev|\.tiangolo)")


# ── 스키마 ─────────────────────────────────────────────────────────────────

class PrescanResult(BaseModel):
    """프리스캔 추론 결과 + HITL 드롭다운 제안 페이로드."""

    doc_id: str
    original_url: str
    framework: Optional[str] = None
    version: Optional[str] = None
    lang: Optional[str] = None
    infer_confidence: float
    infer_status: str  # "auto" | "manual_required"
    suggested_frameworks: list[str] = []   # HITL 드롭다운용 기존 등록 프레임워크 목록
    suggested_versions: list[str] = []     # HITL 드롭다운용 해당 프레임워크 버전 목록


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


def _infer_from_html(  # noqa: PLR0912
    html: str, url: str
) -> tuple[Optional[str], Optional[str], Optional[str], float]:
    """HTML 메타에서 framework, version, lang, confidence 추론."""
    framework, version, base_conf = _infer_from_url(url)

    lang_match = re.search(r'<html[^>]+lang=["\']([a-zA-Z-]+)["\']', html, re.IGNORECASE)
    lang = lang_match.group(1).split("-")[0].upper() if lang_match else None
    if lang:
        base_conf += 0.1

    if not framework:
        title_match = re.search(r"<title>([^<]+)</title>", html, re.IGNORECASE)
        if title_match:
            title = title_match.group(1)
            for _, name in _FRAMEWORK_PATTERNS:
                if re.search(name, title, re.IGNORECASE):
                    framework = name
                    base_conf += 0.3
                    break

    return framework, version, lang, min(base_conf, 1.0)


def _fusion_infer(
    framework: Optional[str],
    version: Optional[str],
    confidence: float,
    url: str,
    all_frameworks: list[str],
) -> tuple[Optional[str], Optional[str], float]:
    """DB 이력과 교차 대조하여 추론 결과를 보강한다.

    1. 기존 추론 프레임워크 → DB canonical 이름으로 정규화 (오탈자·대소문자 보정)
    2. 추론 실패 시 URL 서브스트링에서 DB 프레임워크명 직접 탐색
    3. 서브스트링 실패 시 도메인 문자열 difflib fuzzy 매칭
    새로운 URL이 수집될수록 all_frameworks가 풍부해져 자동으로 정확도 향상.
    """
    if not all_frameworks:
        return framework, version, confidence

    fw_lower_map: dict[str, str] = {fw.lower(): fw for fw in all_frameworks}

    # 1. canonical 정규화
    if framework:
        close = difflib.get_close_matches(framework, all_frameworks, n=1, cutoff=0.8)
        if close and close[0] != framework:
            framework = close[0]
            confidence = min(confidence + 0.05, 1.0)

    # 2. URL 서브스트링 탐색
    if not framework:
        url_lower = url.lower()
        for fw_l, fw_orig in fw_lower_map.items():
            if fw_l in url_lower:
                framework = fw_orig
                confidence = min(confidence + 0.2, 1.0)
                break

    # 3. 도메인 fuzzy 매칭
    if not framework:
        domain = urlparse(url).netloc.lower()
        domain_clean = _DOMAIN_STRIP.sub("", domain)
        candidates = list(fw_lower_map.keys())
        matches = difflib.get_close_matches(domain_clean, candidates, n=1, cutoff=0.5)
        if matches:
            framework = fw_lower_map[matches[0]]
            confidence = min(confidence + 0.15, 1.0)

    return framework, version, confidence


# ── 엔드포인트 ─────────────────────────────────────────────────────────────

@router.post("/{doc_id}/prescan", response_model=PrescanResult)
async def prescan_document(
    doc_id: str,
    conn=Depends(get_conn),
):
    """문서 URL을 경량 스캔하여 framework/version/lang 메타데이터를 자동 추론.

    추론 단계:
      1. URL 패턴 정규식 (하드코딩 시드)
      2. HTML 메타 분석 (<html lang>, <title>)
      3. DB 이력 융합 추론 (_fusion_infer) — Self-Learning Effect
      4. manual_required 시 suggested_frameworks / suggested_versions 반환 → HITL 드롭다운 바인딩
    """
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
    except (httpx.HTTPError, OSError):
        framework, version, confidence = _infer_from_url(url)

    # DB 이력 쿼리 — self-learning 소스
    fw_rows = await conn.fetch(
        "SELECT DISTINCT framework FROM documents "
        "WHERE framework IS NOT NULL ORDER BY framework"
    )
    all_frameworks: list[str] = [r["framework"] for r in fw_rows]

    # 융합 추론
    framework, version, confidence = _fusion_infer(
        framework, version, confidence, url, all_frameworks
    )

    infer_status = "auto" if confidence >= 0.5 else "manual_required"

    # manual_required 시 드롭다운 제안 목록 반환
    suggested_frameworks = all_frameworks[:30] if infer_status == "manual_required" else []

    suggested_versions: list[str] = []
    if framework:
        ver_rows = await conn.fetch(
            "SELECT DISTINCT version FROM documents "
            "WHERE framework = $1 AND version IS NOT NULL ORDER BY version",
            framework,
        )
        suggested_versions = [r["version"] for r in ver_rows]

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
        infer_confidence=round(confidence, 3),
        infer_status=infer_status,
        suggested_frameworks=suggested_frameworks,
        suggested_versions=suggested_versions,
    )
