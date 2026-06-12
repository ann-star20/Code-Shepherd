"""T_domain_01~08 — 동적 도메인 확장 (task1_multi_domain §7)."""

import pytest
from pydantic import ValidationError

from app.domain.models import ConceptExtractionSchema, StagingState
from app.infrastructure.database.domain_repo import (
    classify_domains,
    suggest_similar_domains,
)


# T01: 알려진 도메인 → known 분리
def test_T01_known_domains_classified():
    registered = {"security", "performance"}
    known, unknown = classify_domains(["security"], registered)
    assert unknown == []
    assert known == ["security"]


# T02: 미등록 도메인 → unknown 분리
def test_T02_unknown_domain_detected():
    registered = {"security", "performance"}
    known, unknown = classify_domains(["compliance"], registered)
    assert unknown == ["compliance"]
    assert known == []


# T03: 교차 도메인 — "both" 없이 리스트로 처리
def test_T03_cross_domain_list_no_both():
    schema = ConceptExtractionSchema(
        concept_name="MemoryLeak",
        domains=["security", "performance"],
        severity="high",
        description_ko="메모리 누수",
    )
    assert "both" not in schema.domains
    assert "security" in schema.domains
    assert "performance" in schema.domains


# T04: domains 빈 배열 → ValidationError
def test_T04_empty_domains_raises():
    # 포괄적인 Exception 대신 정확한 Pydantic ValidationError를 명시
    with pytest.raises(ValidationError):
        ConceptExtractionSchema(
            concept_name="X", domains=[], severity="high", description_ko="x"
        )


# T05: domains 소문자 정규화 및 공백 제거
def test_T05_domains_normalized_lowercase():
    schema = ConceptExtractionSchema(
        concept_name="X",
        domains=["Security", "  PERFORMANCE  "],
        severity="low",
        description_ko="x",
    )
    # 모델의 field_validator 로직이 정상 작동하는지 검증
    assert schema.domains == ["security", "performance"]


# T06: 유사 도메인 추천 — 순위 정렬
def test_T06_suggest_similar_domains_sorted():
    registered = {"security", "performance"}
    suggestions = suggest_similar_domains("sec", registered, top_k=2)

    assert len(suggestions) == 2
    # 첫 번째 결과가 두 번째 결과보다 유사도가 높거나 같아야 함
    assert suggestions[0]["similarity"] >= suggestions[1]["similarity"]
    assert suggestions[0]["domain"] == "security"  # "sec"와 가장 유사한 값 검증


# T07: DOMAIN_PENDING 상태 — StagingState Enum에 존재
def test_T07_domain_pending_state_in_enum():
    # Enum 객체 자체와 문자열을 비교하면 실패하므로 .value 속성으로 비교
    assert StagingState.DOMAIN_PENDING.value == "DOMAIN_PENDING"


# T08: classify_domains — 혼합 (일부 알려진, 일부 미등록)
def test_T08_mixed_domains_split():
    registered = {"security", "performance"}
    known, unknown = classify_domains(
        ["security", "compliance", "reliability"], registered
    )

    assert known == ["security"]
    # 순서 보장이 필요 없는 경우 set을 사용하여 검증하는 것이 더 견고함
    assert set(unknown) == {"compliance", "reliability"}
