"""Domain models — 프레임워크 무관 순수 Python/Pydantic 엔티티."""

import hashlib
import re
from enum import Enum
from urllib.parse import urlparse, urlunparse

from pydantic import BaseModel, field_validator


# ── 상태 Enum ──────────────────────────────────────────────────────────────


class PipelineState(str, Enum):
    """documents.state 전이: PENDING→CRAWLING→EXTRACTED→APPROVED→COMMITTED|FAILED"""

    PENDING = "PENDING"
    CRAWLING = "CRAWLING"
    EXTRACTED = "EXTRACTED"
    APPROVED = "APPROVED"
    COMMITTED = "COMMITTED"
    FAILED = "FAILED"


class StagingState(str, Enum):
    """staging_concepts.state 전이: DRAFT→APPROVED→COMMITTED | REJECTED"""

    DRAFT = "DRAFT"
    APPROVED = "APPROVED"
    COMMITTED = "COMMITTED"
    REJECTED = "REJECTED"


class ConceptDomain(str, Enum):
    """LLM 추출 결과의 도메인 분류."""

    SECURITY = "security"
    PERFORMANCE = "performance"
    BOTH = "both"


# ── LLM 추출 결과 스키마 ────────────────────────────────────────────────────


class ConceptExtractionSchema(BaseModel):
    """Extractor Agent가 Gemini로부터 받는 구조화 출력 스키마 (PRD §3.3.3).

    필수 필드: concept_name, concept_domain, severity, description_ko
    선택 필드: cwe_id, owasp_id, concept_type, aliases, security_mechanisms,
               affected_components, config_properties, root_cause
    """

    concept_name: str
    concept_domain: ConceptDomain
    severity: str
    description_ko: str
    concept_type: str | None = None
    cwe_id: str | None = None
    owasp_id: str | None = None
    aliases: list[str] = []
    security_mechanisms: list[str] = []
    affected_components: list[str] = []
    config_properties: list[dict] = []
    root_cause: str | None = None

    @field_validator("severity")
    @classmethod
    def severity_must_be_valid(cls, v: str) -> str:
        allowed = {"CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"}
        if v.upper() not in allowed:
            raise ValueError(f"severity must be one of {allowed}, got '{v}'")
        return v.upper()


# ── 마스터 키 생성 ──────────────────────────────────────────────────────────


def build_doc_id(prefix: str, url: str, content: str = "", etag: str = "") -> str:
    """문서 고유 식별자를 생성한다 (PRD §3.1.4).

    형식: {PREFIX}_{정규화된_URL}_{SHA256_앞8자리}

    Args:
        prefix:  출처 유형 (예: "EXT", "KMS")
        url:     원본 URL (쿼리스트링·앵커 제거 후 정규화)
        content: 본문 텍스트 (etag 없을 때 해시 소스)
        etag:    HTTP ETag 헤더값 (있으면 content보다 우선)

    Returns:
        예) "EXT_https---docs-djangoproject-com-en-6-0-topics-security-_a3f9c21b"

    Note:
        동일 URL + 동일 content/etag → 항상 동일 doc_id (멱등성).
        동일 URL + 다른 content/etag → 다른 해시 suffix (버전 추적).
    """
    parsed = urlparse(url)
    normalized = urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", "", ""))
    url_part = re.sub(r"[:/.]", "-", normalized).strip("-")

    raw = etag if etag else (content or "")
    hash8 = hashlib.sha256(raw.encode()).hexdigest()[:8]

    return f"{prefix}_{url_part}_{hash8}"
