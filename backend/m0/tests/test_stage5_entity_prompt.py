"""
TDD: entity_name_recall 개선 — Stage 5 프롬프트에 Organization/Role/Metric 타입 추가
현재 avg_entity_name_recall = 0.536 → 목표 0.60

문제:
  _SYSTEM_PROMPT가 "Technology / Pattern / Concept" 3종만 지시
  → Organization(조직), Role(역할), Metric(지표), Endpoint(API) 엔티티가 완전히 누락됨

이 파일은 _SYSTEM_PROMPT 내용의 완전성을 검증한다.
실제 LLM 추출 개선은 파이프라인 재실행 후 run_eval.py 결과로 확인.
"""

import pytest
from app.pipeline.stage5_metadata_agent import _SYSTEM_PROMPT, _METADATA_PROMPT


class TestStage5SystemPromptEntityGuidance:
    """_SYSTEM_PROMPT가 Concept = 역할+조직+지표 개념을 명시해야 한다."""

    def test_prompt_mentions_organization(self):
        """조직/단체 엔티티 추출이 지시되어야 한다."""
        assert "조직" in _SYSTEM_PROMPT or "organization" in _SYSTEM_PROMPT.lower()  # RED

    def test_prompt_mentions_role(self):
        """역할 엔티티 추출이 지시되어야 한다."""
        assert "역할" in _SYSTEM_PROMPT or "role" in _SYSTEM_PROMPT.lower()  # RED

    def test_prompt_mentions_metric(self):
        """지표/수치 엔티티 추출이 지시되어야 한다."""
        assert "지표" in _SYSTEM_PROMPT or "metric" in _SYSTEM_PROMPT.lower()  # RED

    def test_concept_type_explanation_includes_nontechnical(self):
        """Concept 타입 설명이 기술 개념 외 역할/조직을 포함해야 한다."""
        # "Concept" 설명 라인 근방에 '역할' 또는 '조직'이 있어야 함
        lines = _SYSTEM_PROMPT.splitlines()
        concept_lines = [l for l in lines if "Concept" in l or "concept" in l.lower()]
        combined = " ".join(concept_lines)
        assert "역할" in combined or "조직" in combined or "role" in combined.lower()  # RED

    def test_technology_type_includes_endpoints(self):
        """Technology 타입 설명에 API 엔드포인트가 포함되어야 한다."""
        assert "엔드포인트" in _SYSTEM_PROMPT or "endpoint" in _SYSTEM_PROMPT.lower()  # RED


class TestStage5MetadataPromptTagGuidance:
    """_METADATA_PROMPT가 태그 생성 언어/범위 기준을 명시해야 한다."""

    def test_metadata_prompt_specifies_tag_count(self):
        """태그 개수 기준(7~10개)이 명시되어야 한다."""
        assert "7" in _METADATA_PROMPT or "8" in _METADATA_PROMPT  # RED

    def test_metadata_prompt_specifies_korean_preference(self):
        """한국어 문서는 한국어 태그 우선을 지시해야 한다."""
        assert "한국어" in _METADATA_PROMPT or "언어" in _METADATA_PROMPT  # RED

    def test_metadata_prompt_entity_example_includes_org(self):
        """엔티티 예시에 조직 타입이 포함되어야 한다."""
        # JSON 예시 안에 organization 관련 설명이 있어야 함
        assert "조직" in _METADATA_PROMPT or "Organization" in _METADATA_PROMPT  # RED
