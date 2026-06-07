"""Domain models — 4-레이어 지식 그래프 아키텍처 핵심 엔티티.

계층 구조:
  Layer 1 — :Domain          (name: 소문자 고정)
  Layer 2 — :Concept         (name: 영문 파스칼케이스, APOC 동적 다중 라벨)
  Layer 3 — :Mechanism       (name: 소문자 스네이크케이스 강제)
           — :Property       (unq_key: 소문자 스네이크케이스 강제)
           — :RootCause      (name: 소문자 스네이크케이스)
           — :Component      (name: 소문자 스네이크케이스)
  Layer 4 — :CodeExample     (unq_id: {mech}_{lang}_{lang_ver}_{fw}_{fw_ver})

프론트엔드 구형 필드 수렴 계약 (입구 단 자동 정규화):
  security_mechanism : list[str]        → list[MechanismIn]
  config_properties  : list[dict]       → list[PropertyIn]
  code_examples      : list[dict] flat  → 첫 번째 MechanismIn.code_examples 귀속
  owasp_category     : str              → owasp_id 병합
"""

from __future__ import annotations

import hashlib
import re
from enum import Enum
from typing import Any, Literal, Optional
from urllib.parse import urlparse, urlunparse

from pydantic import BaseModel, Field, model_validator


# ─── 상태 Enum ────────────────────────────────────────────────────────────────

class PipelineState(str, Enum):
    PENDING   = "PENDING"
    CRAWLING  = "CRAWLING"
    EXTRACTED = "EXTRACTED"
    APPROVED  = "APPROVED"
    COMMITTED = "COMMITTED"
    FAILED    = "FAILED"


class StagingState(str, Enum):
    DRAFT          = "DRAFT"
    DOMAIN_PENDING = "DOMAIN_PENDING"
    APPROVED       = "APPROVED"
    COMMITTED      = "COMMITTED"
    REJECTED       = "REJECTED"


# ─── 유틸리티 ─────────────────────────────────────────────────────────────────

def _to_snake(s: str) -> str:
    """어떤 포맷 문자열도 완전 소문자_스네이크_케이스로 강제 변환."""
    s = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", s)
    s = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", s).lower()
    s = re.sub(r"[\s\-\.]+", "_", s)
    s = re.sub(r"[^a-z0-9_]", "", s)
    s = re.sub(r"_+", "_", s)
    return s.strip("_")


def build_doc_id(prefix: str, url: str, content: str = "", etag: str = "") -> str:
    """PREFIX_{url_part}_{sha256[:8]} 형식 마스터 키 생성."""
    parsed = urlparse(url)
    normalized = urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", "", ""))
    url_part = re.sub(r"[:/.]", "-", normalized).strip("-")[:80]
    raw = etag if etag else (content or url)
    hash8 = hashlib.sha256(raw.encode()).hexdigest()[:8]
    return f"{prefix}_{url_part}_{hash8}"


# ─── Layer 4: CodeExample ─────────────────────────────────────────────────────

class CodeExampleIn(BaseModel):
    lang: str
    lang_version: str = "*"
    framework: str = ""
    framework_version: str = "*"
    code: str
    description: str = ""


# ─── Layer 3: Mechanism ───────────────────────────────────────────────────────

class MechanismIn(BaseModel):
    """
    :Mechanism 노드 입력.
    mechanism_name → 소문자 스네이크케이스로 강제 변환하여 적재 정합성 사전 확보.
    """

    mechanism_name: str
    code_examples: list[CodeExampleIn] = Field(default_factory=list)

    @model_validator(mode="after")
    def _normalize_name(self) -> MechanismIn:
        self.mechanism_name = _to_snake(self.mechanism_name)
        return self


# ─── Layer 3: Property ────────────────────────────────────────────────────────

class PropertyIn(BaseModel):
    """
    :Property 노드 입력.
    key (= unq_key) → 소문자 스네이크케이스로 강제 변환.
    """

    key: str
    value: str
    type: Literal["security", "tuning"] = "security"

    @model_validator(mode="after")
    def _normalize_key(self) -> PropertyIn:
        self.key = _to_snake(self.key)
        return self


# ─── 내부 수렴 헬퍼 ──────────────────────────────────────────────────────────

def _coerce_mechanism(item: Any) -> MechanismIn:
    if isinstance(item, MechanismIn):
        return item
    if isinstance(item, str):
        return MechanismIn(mechanism_name=item)
    if isinstance(item, dict):
        return MechanismIn(**item)
    raise ValueError(f"MechanismIn으로 수렴 불가: {type(item)!r}")


def _coerce_property(item: Any) -> PropertyIn:
    if isinstance(item, PropertyIn):
        return item
    if isinstance(item, dict):
        return PropertyIn(**item)
    raise ValueError(f"PropertyIn으로 수렴 불가: {type(item)!r}")


def _coerce_code_example(item: Any) -> CodeExampleIn:
    if isinstance(item, CodeExampleIn):
        return item
    if isinstance(item, dict):
        return CodeExampleIn(**item)
    raise ValueError(f"CodeExampleIn으로 수렴 불가: {type(item)!r}")


# ─── Layer 2: Concept 핵심 스키마 ─────────────────────────────────────────────

class ConceptExtractionSchema(BaseModel):
    """
    LLM Extractor 출력 + 프론트엔드 입력을 단일 수렴하는 핵심 도메인 엔티티.

    구형(legacy) → 신형(new) 자동 수렴:
      security_mechanism : list[str]              → list[MechanismIn]
      config_properties  : list[{key, value}]     → list[PropertyIn]  (type='security' 기본)
      code_examples      : list[dict] flat        → 첫 번째 MechanismIn.code_examples 귀속
      owasp_category     : str                    → owasp_id 병합
    """

    concept_name: str
    concept_type: str = "vulnerability_root_cause"
    cwe_id: Optional[str] = None
    owasp_id: Optional[str] = None
    owasp_category: Optional[str] = None       # 구형 alias
    severity: Optional[Literal["critical", "high", "medium", "low", "info"]] = None
    domains: list[str] = Field(default_factory=lambda: ["security"])
    description_ko: str = ""
    aliases: list[str] = Field(default_factory=list)
    doc_id: Optional[str] = None

    # 구형/신형 공용 — model_validator 내에서 정규화됨
    security_mechanism: list[Any] = Field(default_factory=list)
    config_properties: list[Any] = Field(default_factory=list)
    affected_components: list[str] = Field(default_factory=list)
    root_cause: Optional[str] = None

    # 구형 flat 코드 예시 (정규화 후 비워짐)
    code_examples: list[Any] = Field(default_factory=list)

    model_config = {"populate_by_name": True}

    @model_validator(mode="after")
    def _normalize(self) -> ConceptExtractionSchema:
        # ① owasp_category → owasp_id 수렴
        if self.owasp_category and not self.owasp_id:
            self.owasp_id = self.owasp_category

        # ② concept_name 트림
        self.concept_name = self.concept_name.strip()

        # ③ domains 소문자 정규화
        self.domains = [d.lower() for d in self.domains]

        # ④ security_mechanism 수렴 (str | dict | MechanismIn → MechanismIn)
        self.security_mechanism = [_coerce_mechanism(x) for x in self.security_mechanism]

        # ⑤ config_properties 수렴 (dict | PropertyIn → PropertyIn)
        self.config_properties = [_coerce_property(x) for x in self.config_properties]

        # ⑥ 구형 flat code_examples → 첫 번째 Mechanism에 귀속 / default mech 생성
        if self.code_examples:
            parsed = [_coerce_code_example(ex) for ex in self.code_examples]
            if self.security_mechanism:
                for mech in self.security_mechanism:
                    if not mech.code_examples:
                        mech.code_examples = parsed
                        break
                else:
                    self.security_mechanism[0].code_examples.extend(parsed)
            else:
                self.security_mechanism = [
                    MechanismIn(mechanism_name="general_mitigation", code_examples=parsed)
                ]
            self.code_examples = []

        return self

    # ── 편의 프로퍼티 ──────────────────────────────────────────────────────────

    @property
    def mechanisms(self) -> list[MechanismIn]:
        return self.security_mechanism  # type: ignore[return-value]

    @property
    def properties(self) -> list[PropertyIn]:
        return self.config_properties  # type: ignore[return-value]

    @property
    def neo4j_extra_labels(self) -> list[str]:
        """domains 배열 → Neo4j 물리 라벨 목록 (Security, Performance)."""
        _MAP = {"security": "Security", "performance": "Performance"}
        return [_MAP[d] for d in self.domains if d in _MAP]


# 신형 명칭 alias
ConceptIn = ConceptExtractionSchema


# ─── 부분 수정 모델 ───────────────────────────────────────────────────────────

class ConceptUpdate(BaseModel):
    """PUT /concepts/{name} 바디 — None 필드는 SET 대상 제외."""

    concept_type: Optional[str] = None
    cwe_id: Optional[str] = None
    owasp_id: Optional[str] = None
    severity: Optional[Literal["critical", "high", "medium", "low"]] = None
    domains: Optional[list[str]] = None
    description_ko: Optional[str] = None
    aliases: Optional[list[str]] = None
    is_deprecated: Optional[bool] = None

    def to_neo4j_dict(self) -> dict[str, Any]:
        data = self.model_dump(exclude_none=True)
        if "domains" in data:
            data["domains"] = [d.lower() for d in data["domains"]]
        return data


# ─── Document ─────────────────────────────────────────────────────────────────

class DocumentIn(BaseModel):
    prefix: Literal["EXT", "INT"] = "EXT"
    url: str
    title: str = ""
    source: str = ""
    content: str = ""
    etag: str = ""

    @property
    def doc_id(self) -> str:
        return build_doc_id(self.prefix, self.url, self.content, self.etag)
