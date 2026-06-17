"""도메인 모델 — 개념 추출 스키마."""

from __future__ import annotations

import re
from typing import Optional

from pydantic import BaseModel, Field, field_validator, model_validator

# crawling-chunking-guide-v2/v3.md §2 — 공식 문서 외곽 배너/메뉴판/푸터 노이즈 차단 트리거
# (description_ko를 공백 제거 + 소문자로 정규화한 뒤 동일하게 정규화한 트리거와 비교한다)
_DESCRIPTION_NOISE_TRIGGERS = (
    "menu",
    "view events",
    "latest version",
    "next.js nights",
    "app router",
    "available as markdown",
    "next.js documentation",
    "llms.txt",
    "last updated",
    "was this helpful",
    "menu bars",
)

# crawling-chunking-guide-v3.md §2 — concept_type 허용 리터럴
_ALLOWED_CONCEPT_TYPES = (
    "concept",
    "mechanism",
    "property",
    "root_cause",
    "component",
    "performance_antipattern",
    "antipattern",
)


class CodeExampleSchema(BaseModel):
    lang: str
    lang_version: str = ""
    framework: str = ""
    framework_version: str = ""
    code: str = ""
    description: str = ""


class MechanismSchema(BaseModel):
    mechanism_name: str
    code_examples: list[CodeExampleSchema] = Field(default_factory=list)


class ConceptExtractionSchema(BaseModel):
    """AI 추출 개념 단위 — staging 적재 + Neo4j MERGE 입력."""

    concept_name: str = Field(
        ...,
        pattern=r"^[A-Z][a-zA-Z0-9+-]+$",
        description=(
            "핵심 주제어. 반드시 PascalCase 단일 명사여야 함 (예: CsrfProtection, NextProxy). "
            "'concept_' 접두사나 해시 접미사(_b6ce44 등) 절대 금지."
        ),
    )
    concept_type: str = "component"
    domains: list[str] = Field(default_factory=list)
    cwe_id: Optional[str] = None
    owasp_id: Optional[str] = None
    severity: Optional[str] = None
    description_ko: str = ""
    root_cause: str = ""
    aliases: list[str] = Field(default_factory=list)
    mechanism: list[MechanismSchema] = Field(default_factory=list)
    affected_components: list[str] = Field(default_factory=list)
    name_vector: Optional[list[float]] = None
    desc_vector: Optional[list[float]] = None

    @field_validator("concept_type")
    @classmethod
    def _validate_concept_type(cls, v: str) -> str:
        """crawling-chunking-guide-v3.md §2 — concept_type 리터럴 제한."""
        if v.lower() not in _ALLOWED_CONCEPT_TYPES:
            raise ValueError(f"concept_type은 반드시 {_ALLOWED_CONCEPT_TYPES} 중 하나여야 합니다.")
        return v.lower()

    @model_validator(mode="after")
    def _validate_ontology_logic(self) -> "ConceptExtractionSchema":
        """LLM 출력의 구조적/논리적 무결성 인터락 (crawling-chunking-guide-v2/v3.md §2)."""
        normalized_desc = re.sub(r"\s+", "", (self.description_ko or "").lower())
        if any(re.sub(r"\s+", "", trigger) in normalized_desc for trigger in _DESCRIPTION_NOISE_TRIGGERS):
            raise ValueError(
                "description_ko 필드에 기술문서 본문과 무관한 웹사이트 레이아웃 UI "
                "노이즈가 포함되어 있습니다."
            )

        if self.concept_type == "concept" and not self.mechanism:
            raise ValueError(
                "concept_type='concept' 엔티티는 이를 해결/방어하기 위한 "
                "mechanism 요소가 최소 1개 이상 바인딩되어야 합니다."
            )

        return self
