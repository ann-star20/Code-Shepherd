"""레이어 D — LLM 품질 테스트 (T07). PRD §10.5."""

import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).parents[2]))

import pytest
from pydantic import ValidationError
from app.domain.models import ConceptExtractionSchema, ConceptDomain


# ── T07: Extractor 출력 JSON 스키마 유효성 ──────────────────────────────────
def test_extractor_schema_validation_security():
    """보안 도메인 최소 필드 → ValidationError 없이 객체화, domain 범위 내."""
    # Arrange
    mock_output = {
        "concept_name": "XSS",
        "concept_domain": "security",
        "concept_type": "vulnerability_root_cause",
        "cwe_id": "CWE-79",
        "severity": "HIGH",
        "description_ko": "크로스 사이트 스크립팅 취약점",
        "aliases": ["Cross-Site Scripting", "크로스 사이트 스크립팅"],
    }

    # Act
    schema = ConceptExtractionSchema(**mock_output)

    # Assert
    assert schema.concept_domain == ConceptDomain.SECURITY
    assert schema.concept_domain in {
        ConceptDomain.SECURITY,
        ConceptDomain.PERFORMANCE,
        ConceptDomain.BOTH,
    }
    assert schema.severity == "HIGH"


def test_extractor_schema_validation_performance():
    """성능 도메인 → concept_domain = performance."""
    # Arrange + Act
    schema = ConceptExtractionSchema(
        concept_name="N+1Query",
        concept_domain="performance",
        severity="high",  # 소문자 입력도 정규화돼야 함
        description_ko="ORM N+1 쿼리 성능 문제",
    )

    # Assert
    assert schema.concept_domain == ConceptDomain.PERFORMANCE
    assert schema.severity == "HIGH"  # field_validator 정규화 확인


def test_extractor_schema_validation_both():
    """교차 도메인(both) → concept_domain = both."""
    # Arrange + Act
    schema = ConceptExtractionSchema(
        concept_name="MemoryLeak",
        concept_domain="both",
        severity="HIGH",
        description_ko="메모리 누수",
    )

    # Assert
    assert schema.concept_domain == ConceptDomain.BOTH


def test_extractor_schema_invalid_domain():
    """잘못된 concept_domain → ValidationError 발생."""
    # Arrange + Act + Assert
    with pytest.raises(ValidationError):
        ConceptExtractionSchema(
            concept_name="XSS",
            concept_domain="unknown_domain",  # 유효하지 않은 값
            severity="HIGH",
            description_ko="테스트",
        )


def test_extractor_schema_invalid_severity():
    """잘못된 severity → ValidationError 발생."""
    # Arrange + Act + Assert
    with pytest.raises(ValidationError):
        ConceptExtractionSchema(
            concept_name="XSS",
            concept_domain="security",
            severity="SUPER_CRITICAL",  # 허용 범위 외
            description_ko="테스트",
        )


def test_extractor_schema_optional_fields_default():
    """선택 필드 미입력 시 기본값(빈 리스트/None) 적용."""
    # Arrange + Act
    schema = ConceptExtractionSchema(
        concept_name="SQLi",
        concept_domain="security",
        severity="CRITICAL",
        description_ko="SQL 인젝션",
    )

    # Assert
    assert schema.aliases == []
    assert schema.security_mechanisms == []
    assert schema.affected_components == []
    assert schema.config_properties == []
    assert schema.cwe_id is None
    assert schema.owasp_id is None
