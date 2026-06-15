"""ConceptExtractionSchema 온톨로지 무결성 검증기 — Pydantic root_validator 인터락.

crawling-chunking-guide-v2.md §2 명세:
  1. description_ko에 웹사이트 메뉴/내비게이션 노이즈가 섞이면 적재를 거부한다.
  2. concept_type == 'concept'인데 mechanism이 비어 있으면 적재를 거부한다.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.domain.models import ConceptExtractionSchema, MechanismSchema


class TestDescriptionNoiseFilter:
    def test_rejects_description_containing_menu_noise(self):
        # Arrange
        payload = {
            "concept_name": "CsrfProtection",
            "concept_type": "mechanism",
            "domains": ["security"],
            "description_ko": "Menu View Events Latest Version 안내",
        }

        # Act / Assert
        with pytest.raises(ValidationError, match="노이즈"):
            ConceptExtractionSchema(**payload)

    def test_rejects_description_containing_available_as_markdown_footer(self):
        """crawling-chunking-guide-v3.md §2 — Next.js 문서 푸터 노이즈 차단."""
        # Arrange
        payload = {
            "concept_name": "CsrfProtection",
            "concept_type": "mechanism",
            "domains": ["security"],
            "description_ko": "CSRF 보호 메커니즘 설명. This page is also available as Markdown.",
        }

        # Act / Assert
        with pytest.raises(ValidationError, match="노이즈"):
            ConceptExtractionSchema(**payload)

    def test_rejects_description_containing_was_this_helpful_footer(self):
        """crawling-chunking-guide-v3.md §2 — 'Was this helpful?' 푸터 노이즈 차단."""
        # Arrange
        payload = {
            "concept_name": "CsrfProtection",
            "concept_type": "mechanism",
            "domains": ["security"],
            "description_ko": "CSRF 보호 메커니즘 설명.\nWas this helpful?",
        }

        # Act / Assert
        with pytest.raises(ValidationError, match="노이즈"):
            ConceptExtractionSchema(**payload)

    def test_rejects_description_containing_last_updated_footer(self):
        """crawling-chunking-guide-v3.md §2 — 'Last updated' 푸터 노이즈 차단."""
        # Arrange
        payload = {
            "concept_name": "CsrfProtection",
            "concept_type": "mechanism",
            "domains": ["security"],
            "description_ko": "CSRF 보호 메커니즘 설명. Last updated on 2026-01-01.",
        }

        # Act / Assert
        with pytest.raises(ValidationError, match="노이즈"):
            ConceptExtractionSchema(**payload)

    def test_accepts_clean_korean_description(self):
        # Arrange
        payload = {
            "concept_name": "CsrfProtection",
            "concept_type": "mechanism",
            "domains": ["security"],
            "description_ko": "CSRF 공격을 방지하기 위한 토큰 기반 검증 메커니즘입니다.",
        }

        # Act
        concept = ConceptExtractionSchema(**payload)

        # Assert
        assert concept.description_ko == "CSRF 공격을 방지하기 위한 토큰 기반 검증 메커니즘입니다."


class TestConceptMechanismBinding:
    def test_rejects_concept_type_concept_without_mechanism(self):
        # Arrange
        payload = {
            "concept_name": "CsrfProtection",
            "concept_type": "concept",
            "domains": ["security"],
            "description_ko": "CSRF 보호 개념",
            "mechanism": [],
        }

        # Act / Assert
        with pytest.raises(ValidationError, match="mechanism"):
            ConceptExtractionSchema(**payload)

    def test_accepts_concept_type_concept_with_mechanism(self):
        # Arrange
        payload = {
            "concept_name": "CsrfProtection",
            "concept_type": "concept",
            "domains": ["security"],
            "description_ko": "CSRF 보호 개념",
            "mechanism": [{"mechanism_name": "SynchronizerTokenPattern"}],
        }

        # Act
        concept = ConceptExtractionSchema(**payload)

        # Assert
        assert concept.mechanism == [MechanismSchema(mechanism_name="SynchronizerTokenPattern")]

    def test_non_concept_type_allows_empty_mechanism(self):
        # Arrange
        payload = {
            "concept_name": "SynchronizerTokenPattern",
            "concept_type": "mechanism",
            "domains": ["security"],
            "description_ko": "동기화 토큰 패턴",
            "mechanism": [],
        }

        # Act
        concept = ConceptExtractionSchema(**payload)

        # Assert
        assert concept.mechanism == []


class TestConceptNamePattern:
    """concept_name — crawling-chunking-guide-v3.md §2: ^[A-Z][a-zA-Z0-9]+$ PascalCase 강제."""

    def test_rejects_concept_name_with_prefix_and_hash_suffix(self):
        # Arrange
        payload = {
            "concept_name": "concept_Next.js_b6ce44",
            "concept_type": "mechanism",
            "domains": ["performance"],
            "description_ko": "잘못된 명명 규칙 예시",
        }

        # Act / Assert
        with pytest.raises(ValidationError):
            ConceptExtractionSchema(**payload)

    def test_accepts_pascal_case_concept_name(self):
        # Arrange
        payload = {
            "concept_name": "MemoryLeak",
            "concept_type": "performance_antipattern",
            "domains": ["performance"],
            "description_ko": "메모리 누수 안티패턴",
        }

        # Act
        concept = ConceptExtractionSchema(**payload)

        # Assert
        assert concept.concept_name == "MemoryLeak"


class TestConceptTypeEnum:
    """concept_type — crawling-chunking-guide-v3.md §2: 허용 리터럴 집합 강제."""

    def test_rejects_invalid_concept_type(self):
        # Arrange
        payload = {
            "concept_name": "MemoryLeak",
            "concept_type": "vulnerability_root_cause",
            "domains": ["performance"],
            "description_ko": "허용되지 않은 concept_type",
        }

        # Act / Assert
        with pytest.raises(ValidationError, match="concept_type"):
            ConceptExtractionSchema(**payload)

    def test_normalizes_concept_type_case(self):
        # Arrange
        payload = {
            "concept_name": "MemoryLeak",
            "concept_type": "PERFORMANCE_ANTIPATTERN",
            "domains": ["performance"],
            "description_ko": "대소문자 정규화 확인",
        }

        # Act
        concept = ConceptExtractionSchema(**payload)

        # Assert
        assert concept.concept_type == "performance_antipattern"

    def test_accepts_antipattern_concept_type(self):
        """시드 데이터(security/performance concept.json)는 concept_type을 'antipattern'으로 통일한다."""
        # Arrange
        payload = {
            "concept_name": "Xss",
            "concept_type": "antipattern",
            "domains": ["security"],
            "description_ko": "시드 데이터 concept_type 통일 확인",
        }

        # Act
        concept = ConceptExtractionSchema(**payload)

        # Assert
        assert concept.concept_type == "antipattern"
