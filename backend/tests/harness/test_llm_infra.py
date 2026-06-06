"""레이어 D — LLM 인프라 추상화 테스트 (T09~T12). PRD §16."""

import pytest
from app.domain.models import ConceptExtractionSchema
from app.infrastructure.llm.interface import ILLMClient
from app.infrastructure.llm.mock_client import MockClient
from app.infrastructure.llm.factory import create_llm_client
from app.infrastructure.llm.gemini_client import GeminiClient, LLMParseError, _parse_json_safely


def test_mock_client_implements_interface():
    client = MockClient()
    assert isinstance(client, ILLMClient)
    assert hasattr(client, "extract_concepts")
    assert hasattr(client, "is_tracing_enabled")


def test_gemini_client_is_subclass_of_interface():
    assert issubclass(GeminiClient, ILLMClient)


@pytest.mark.anyio
async def test_mock_client_returns_fixed_concepts():
    """MockClient는 고정 4종 컨셉을 반환, 각 domains는 list[str]."""
    client = MockClient()
    results = await client.extract_concepts("any text", "doc_id_test", {})
    assert len(results) == 4
    assert all(isinstance(r, ConceptExtractionSchema) for r in results)
    # domains가 list[str]인지 확인 (ConceptDomain enum 아님)
    all_domains: set[str] = set()
    for r in results:
        assert isinstance(r.domains, list)
        assert all(isinstance(d, str) for d in r.domains)
        all_domains.update(r.domains)
    assert "security" in all_domains
    assert "performance" in all_domains


def test_mock_client_tracing_disabled():
    assert MockClient().is_tracing_enabled() is False


def test_factory_development_returns_mock():
    client = create_llm_client("development")
    assert isinstance(client, MockClient)
    assert client.is_tracing_enabled() is False


def test_factory_default_returns_mock():
    client = create_llm_client()
    assert isinstance(client, MockClient)


def test_parse_json_safely_valid_list():
    raw = '[{"concept_name": "XSS", "severity": "HIGH"}]'
    result = _parse_json_safely(raw)
    assert isinstance(result, list)
    assert result[0]["concept_name"] == "XSS"


def test_parse_json_safely_single_object_to_list():
    raw = '{"concept_name": "SQLi", "severity": "CRITICAL"}'
    result = _parse_json_safely(raw)
    assert isinstance(result, list)
    assert len(result) == 1


def test_parse_json_safely_markdown_wrapped():
    raw = '```json\n[{"concept_name": "CSRF", "severity": "HIGH"}]\n```'
    result = _parse_json_safely(raw)
    assert result[0]["concept_name"] == "CSRF"


def test_parse_json_safely_invalid_json_raises():
    with pytest.raises(LLMParseError) as exc_info:
        _parse_json_safely("I cannot help with that request.")
    assert "파싱 실패" in str(exc_info.value)


def test_parse_json_safely_partial_json_raises():
    with pytest.raises(LLMParseError):
        _parse_json_safely('{"concept_name": "XSS"')


@pytest.mark.anyio
async def test_mock_concepts_use_owasp_2025_ids():
    client = MockClient()
    results = await client.extract_concepts("", "", {})
    owasp_ids = [r.owasp_id for r in results if r.owasp_id]
    for oid in owasp_ids:
        assert ":2025" in oid, f"OWASP 2021 ID 발견: {oid}"
