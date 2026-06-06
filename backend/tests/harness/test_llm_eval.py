"""레이어 D — LLM 품질 테스트 (T07). PRD §10.5 — domains: list[str] 스키마."""

import pytest
from pydantic import ValidationError
from app.domain.models import ConceptExtractionSchema


def test_extractor_schema_validation_security():
    """보안 도메인 → domains=['security'], severity 정규화."""
    schema = ConceptExtractionSchema(
        concept_name="XSS",
        domains=["security"],
        concept_type="vulnerability_root_cause",
        cwe_id="CWE-79",
        severity="high",
        description_ko="크로스 사이트 스크립팅 취약점",
        aliases=["Cross-Site Scripting"],
    )
    assert "security" in schema.domains
    assert "both" not in schema.domains
    assert schema.severity == "high"


def test_extractor_schema_validation_performance():
    """성능 도메인 → domains=['performance'], severity 소문자 정규화."""
    schema = ConceptExtractionSchema(
        concept_name="N+1Query",
        domains=["performance"],
        severity="high",
        description_ko="ORM N+1 쿼리 성능 문제",
    )
    assert schema.domains == ["performance"]
    assert schema.severity == "high"


def test_extractor_schema_validation_cross_domain():
    """교차 도메인 → domains=['security','performance'], 'both' 없음."""
    schema = ConceptExtractionSchema(
        concept_name="MemoryLeak",
        domains=["security", "performance"],
        severity="high",
        description_ko="메모리 누수",
    )
    assert "both" not in schema.domains
    assert set(schema.domains) == {"security", "performance"}


def test_extractor_schema_empty_domains_raises():
    """domains=[] → ValidationError (최소 1개 필요)."""
    with pytest.raises(ValidationError):
        ConceptExtractionSchema(
            concept_name="XSS",
            domains=[],
            severity="high",
            description_ko="테스트",
        )


def test_extractor_schema_invalid_severity():
    """잘못된 severity → ValidationError."""
    with pytest.raises(ValidationError):
        ConceptExtractionSchema(
            concept_name="XSS",
            domains=["security"],
            severity="SUPER_CRITICAL",
            description_ko="테스트",
        )


def test_extractor_schema_optional_fields_default():
    """선택 필드 미입력 시 기본값 적용."""
    schema = ConceptExtractionSchema(
        concept_name="SQLi",
        domains=["security"],
        severity=critical,
        description_ko="SQL 인젝션",
    )
    assert schema.aliases == []
    assert schema.security_mechanisms == []
    assert schema.affected_components == []
    assert schema.config_properties == []
    assert schema.cwe_id is None
    assert schema.owasp_id is None
