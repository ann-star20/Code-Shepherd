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
    """staging_concepts.state 전이."""

    DRAFT = "DRAFT"
    APPROVED = "APPROVED"
    COMMITTED = "COMMITTED"
    REJECTED = "REJECTED"
    DOMAIN_PENDING = "DOMAIN_PENDING"  # 미등록 도메인 감지 → 관리자 검토 대기


# ── LLM 추출 결과 스키마 ────────────────────────────────────────────────────


class ConceptExtractionSchema(BaseModel):
    """Extractor Agent가 Gemini로부터 받는 구조화 출력 스키마 (PRD §3.3.3 + task1_multi_domain).

    concept_domain(Enum) 폐기 → domains(list[str]) 로 변경.
    미등록 도메인은 ValidationError 없이 DOMAIN_PENDING 으로 분기.
    """

    concept_name: str
    domains: list[str]               # ["security"], ["performance"], ["security","performance"]
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

    @field_validator("domains")
    @classmethod
    def validate_domains(cls, v: list[str]) -> list[str]:
        if not v:
            raise ValueError("domains는 최소 1개 이상이어야 합니다")
        if not all(isinstance(d, str) and d.strip() for d in v):
            raise ValueError("domains 값은 비어있지 않은 문자열이어야 합니다")
        return [d.lower().strip() for d in v]

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
    동일 URL + 동일 content/etag → 항상 동일 doc_id (멱등성).
    """
    parsed = urlparse(url)
    normalized = urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", "", ""))
    url_part = re.sub(r"[:/.]", "-", normalized).strip("-")

    raw = etag if etag else (content or "")
    hash8 = hashlib.sha256(raw.encode()).hexdigest()[:8]

    return f"{prefix}_{url_part}_{hash8}"
