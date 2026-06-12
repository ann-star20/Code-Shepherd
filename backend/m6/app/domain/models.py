"""도메인 모델 — 개념 추출 스키마."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


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

    concept_name: str
    concept_type: str = "vulnerability_root_cause"
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
