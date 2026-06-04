"""G4: extract_concepts usecase 테스트."""

import pytest
from pydantic import ValidationError

from app.domain.models import ConceptExtractionSchema, ConceptDomain
from app.infrastructure.llm.interface import ILLMClient
from app.usecases.extract_concepts import extract_concepts

# ── 테스트용 Mock LLM ────────────────────────────────────────────────────────

_VALID_XSS = {
    "concept_name": "XSS",
    "concept_domain": ConceptDomain.SECURITY,
    "concept_type": "vulnerability_root_cause",
    "cwe_id": "CWE-79",
    "severity": "HIGH",
    "description_ko": "크로스 사이트 스크립팅",
    "aliases": ["Cross-Site Scripting"],
}

_VALID_BOTH = {
    "concept_name": "MemoryLeak",
    "concept_domain": "both",
    "concept_type": "vulnerability_root_cause",
    "severity": "HIGH",
    "description_ko": "메모리 누수",
}


class _FixedMock(ILLMClient):
    def __init__(self, data: list[dict]):
        self._data = data

    async def extract_concepts(self, text_chunk, doc_id, metadata):
        return [ConceptExtractionSchema(**d) for d in self._data]

    def is_tracing_enabled(self):
        return False


class _InvalidMock(ILLMClient):
    """severity='UNKNOWN' → ValidationError 유발."""

    async def extract_concepts(self, text_chunk, doc_id, metadata):
        return [ConceptExtractionSchema(
            concept_name="Bad",
            concept_domain="security",
            severity="UNKNOWN",  # 잘못된 값 → validator 에러
            description_ko="invalid",
        )]

    def is_tracing_enabled(self):
        return False


# ── 테스트 ────────────────────────────────────────────────────────────────────

@pytest.mark.anyio
async def test_extract_schema_valid():
    mock = _FixedMock([_VALID_XSS])
    result = await extract_concepts("doc1", ["chunk1"], mock)
    assert len(result) == 1
    assert isinstance(result[0], ConceptExtractionSchema)
    assert result[0].concept_name == "XSS"


@pytest.mark.anyio
async def test_extract_dedup():
    # 2청크 모두 XSS 반환 → 중복 제거 → 1개
    mock = _FixedMock([_VALID_XSS])
    result = await extract_concepts("doc1", ["chunk1", "chunk2"], mock)
    assert len(result) == 1


@pytest.mark.anyio
async def test_extract_domain_both():
    mock = _FixedMock([_VALID_BOTH])
    result = await extract_concepts("doc1", ["chunk1"], mock)
    assert result[0].concept_domain == ConceptDomain.BOTH


@pytest.mark.anyio
async def test_extract_invalid_filtered():
    # ValidationError 발생 시 해당 항목 제외 (빈 결과 반환)
    mock = _InvalidMock()
    result = await extract_concepts("doc1", ["chunk1"], mock)
    assert result == []
