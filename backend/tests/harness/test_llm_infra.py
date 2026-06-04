"""레이어 D — LLM 인프라 추상화 테스트 (T09~T12). PRD §16."""

import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).parents[2]))

import pytest
from app.domain.models import ConceptExtractionSchema, ConceptDomain
from app.infrastructure.llm.interface import ILLMClient
from app.infrastructure.llm.mock_client import MockClient
from app.infrastructure.llm.factory import create_llm_client
from app.infrastructure.llm.gemini_client import (
    GeminiClient,
    LLMParseError,
    _parse_json_safely,
)


# ── T09: ILLMClient 인터페이스 계약 ──────────────────────────────────────────
def test_mock_client_implements_interface():
    """MockClient는 ILLMClient의 모든 추상 메서드를 구현한다."""
    # Arrange + Act
    client = MockClient()
    # Assert
    assert isinstance(client, ILLMClient)
    assert hasattr(client, "extract_concepts")
    assert hasattr(client, "is_tracing_enabled")


def test_gemini_client_is_subclass_of_interface():
    """GeminiClient는 ILLMClient 서브클래스다 (인스턴스화 없이 확인)."""
    assert issubclass(GeminiClient, ILLMClient)


# ── T10: MockClient 즉시 반환 + 트레이싱 비활성화 ──────────────────────────
@pytest.mark.anyio
async def test_mock_client_returns_fixed_concepts():
    """MockClient는 네트워크 없이 고정 4종 컨셉을 즉시 반환한다."""
    # Arrange
    client = MockClient()
    # Act
    results = await client.extract_concepts("any text", "doc_id_test", {})
    # Assert
    assert len(results) == 4
    assert all(isinstance(r, ConceptExtractionSchema) for r in results)
    domains = {r.concept_domain for r in results}
    assert ConceptDomain.SECURITY in domains
    assert ConceptDomain.PERFORMANCE in domains
    assert ConceptDomain.BOTH in domains


def test_mock_client_tracing_disabled():
    """MockClient.is_tracing_enabled() → False."""
    assert MockClient().is_tracing_enabled() is False


# ── T11: factory APP_MODE 분기 ────────────────────────────────────────────
def test_factory_development_returns_mock():
    """APP_MODE=development → MockClient 반환."""
    # Arrange + Act
    client = create_llm_client("development")
    # Assert
    assert isinstance(client, MockClient)
    assert client.is_tracing_enabled() is False


def test_factory_default_returns_mock():
    """APP_MODE 기본값 → MockClient 반환."""
    client = create_llm_client()
    assert isinstance(client, MockClient)


# ── T12: _parse_json_safely 에러 케이스 → LLMParseError ─────────────────
def test_parse_json_safely_valid_list():
    """정상 JSON 배열 → 리스트 반환."""
    raw = '[{"concept_name": "XSS", "severity": "HIGH"}]'
    result = _parse_json_safely(raw)
    assert isinstance(result, list)
    assert result[0]["concept_name"] == "XSS"


def test_parse_json_safely_single_object_to_list():
    """단일 JSON 객체 → 리스트로 감싸서 반환."""
    raw = '{"concept_name": "SQLi", "severity": "CRITICAL"}'
    result = _parse_json_safely(raw)
    assert isinstance(result, list)
    assert len(result) == 1


def test_parse_json_safely_markdown_wrapped():
    """마크다운 코드 블록(```json ... ```) → 파싱 성공."""
    raw = '```json\n[{"concept_name": "CSRF", "severity": "HIGH"}]\n```'
    result = _parse_json_safely(raw)
    assert result[0]["concept_name"] == "CSRF"


def test_parse_json_safely_invalid_json_raises():
    """잘못된 JSON → LLMParseError 발생 (FAILED 상태 트리거 신호)."""
    # Arrange
    bad_raw = "I cannot help with that request."
    # Act + Assert
    with pytest.raises(LLMParseError) as exc_info:
        _parse_json_safely(bad_raw)
    assert "파싱 실패" in str(exc_info.value)


def test_parse_json_safely_partial_json_raises():
    """불완전한 JSON → LLMParseError 발생."""
    with pytest.raises(LLMParseError):
        _parse_json_safely('{"concept_name": "XSS"')  # 닫는 괄호 없음


# ── Mock 개념 데이터 정합성 검증 ──────────────────────────────────────────────
@pytest.mark.anyio
async def test_mock_concepts_use_owasp_2025_ids():
    """MockClient 고정 데이터는 OWASP 2025 ID(연도 :2025)를 사용한다."""
    client = MockClient()
    results = await client.extract_concepts("", "", {})
    owasp_ids = [r.owasp_id for r in results if r.owasp_id]
    for oid in owasp_ids:
        assert ":2025" in oid, f"OWASP 2021 ID 발견: {oid} — 2025로 업데이트 필요"
