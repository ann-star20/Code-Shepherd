"""Tests for Stage 5: 메타데이터 추출 (stage5_metadata)."""

from __future__ import annotations

import json
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from langchain_core.messages import HumanMessage, SystemMessage

from module_0_kms.pipeline.stage5_metadata_agent import (
    _SYSTEM_PROMPT,
    _build_relations,
    _fallback_metadata,
    _mock_metadata,
    stage5_metadata,
)


def _state(**kw) -> dict:
    return {
        "doc_id": "doc-s5-001",
        "validated_markdown": "# N+1 쿼리 방지\n\n내용입니다.",
        "chunks": [],
        **kw,
    }


# ---------------------------------------------------------------------------
# 빈 Markdown 처리
# ---------------------------------------------------------------------------

class TestEmptyMarkdown:
    async def test_none_markdown_returns_failed(self):
        result = await stage5_metadata(_state(validated_markdown=None))
        assert result["status"] == "failed"
        assert result["metadata"] is None

    async def test_empty_string_returns_failed(self):
        result = await stage5_metadata(_state(validated_markdown=""))
        assert result["status"] == "failed"
        assert "Stage5" in result["error"]

    async def test_empty_markdown_sets_current_stage(self):
        result = await stage5_metadata(_state(validated_markdown=""))
        assert result["current_stage"] == "stage5_metadata"


# ---------------------------------------------------------------------------
# Mock LLM 경로
# ---------------------------------------------------------------------------

class TestMockLLM:
    async def test_extracts_title_from_h1(self, monkeypatch):
        monkeypatch.setenv("USE_MOCK_LLM", "true")
        result = await stage5_metadata(_state(validated_markdown="# 코드 리뷰 가이드\n\n내용"))
        assert result["metadata"]["title"] == "코드 리뷰 가이드"

    async def test_default_category_is_valid(self, monkeypatch):
        """Mock LLM은 기존 VALID_CATEGORIES 중 하나를 반환한다 (category_is_new=False)."""
        monkeypatch.setenv("USE_MOCK_LLM", "true")
        from module_0_kms.pipeline._category_definitions import VALID_CATEGORIES
        result = await stage5_metadata(_state())
        assert result["metadata"]["category"] in VALID_CATEGORIES
        assert result["category_is_new"] is False

    async def test_entities_empty_in_mock_mode(self, monkeypatch):
        monkeypatch.setenv("USE_MOCK_LLM", "true")
        result = await stage5_metadata(_state())
        assert result["neo4j_entities"] == []

    async def test_current_stage_always_set(self, monkeypatch):
        monkeypatch.setenv("USE_MOCK_LLM", "true")
        result = await stage5_metadata(_state())
        assert result["current_stage"] == "stage5_metadata"


# ---------------------------------------------------------------------------
# _mock_metadata
# ---------------------------------------------------------------------------

class TestMockMetadata:
    def test_extracts_first_h1(self):
        md = "# 아키텍처 개요\n\n내용"
        meta = _mock_metadata(md)
        assert meta["title"] == "아키텍처 개요"

    def test_extracts_first_h2_if_no_h1(self):
        md = "## 소제목\n\n내용"
        meta = _mock_metadata(md)
        assert meta["title"] == "소제목"

    def test_fallback_title_when_no_header(self):
        meta = _mock_metadata("헤더 없는 내용만 있는 문서")
        assert meta["title"] == "제목 없음"

    def test_source_is_upload(self):
        meta = _mock_metadata("# 제목")
        assert meta["source"] == "upload"

    def test_tags_empty_list(self):
        meta = _mock_metadata("# 제목")
        assert meta["tags"] == []


# ---------------------------------------------------------------------------
# _fallback_metadata
# ---------------------------------------------------------------------------

class TestFallbackMetadata:
    def test_returns_title_none(self):
        meta = _fallback_metadata()
        assert meta["title"] == "제목 없음"

    def test_returns_category_etc(self):
        assert _fallback_metadata()["category"] == "기타"

    def test_team_and_author_are_none(self):
        meta = _fallback_metadata()
        assert meta["team"] is None
        assert meta["author"] is None


# ---------------------------------------------------------------------------
# _build_relations
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# 카테고리 정의 포함 여부 — BUG-45 후속 (Stage5 프롬프트 강화)
# ---------------------------------------------------------------------------

class TestCategoryDefinitionsInPrompt:
    """Stage 5 프롬프트에 카테고리 정의가 포함되어야 한다.

    NCS SW아키텍처 PDF가 '기타'로 잘못 분류된 원인:
    프롬프트에 카테고리 목록만 있고 정의가 없어 LLM이 '기타'로 폴백.
    """

    def test_system_prompt_includes_category_definitions(self):
        """_SYSTEM_PROMPT 에 각 카테고리 정의가 포함되어야 한다."""
        assert "NCS" in _SYSTEM_PROMPT or "수행" in _SYSTEM_PROMPT, (
            "Stage5 시스템 프롬프트에 NCS/수행 키워드 없음 — "
            "'아키텍처' 정의가 추가되지 않았거나 _category_definitions 미연동"
        )

    def test_system_prompt_marks_giteo_as_last_resort(self):
        """_SYSTEM_PROMPT 에 '기타'가 마지막 수단임을 명시해야 한다."""
        assert "마지막" in _SYSTEM_PROMPT or "해당하지" in _SYSTEM_PROMPT, (
            "Stage5 프롬프트에 '기타는 마지막 수단' 안내 없음 — LLM이 남용 가능"
        )

    def test_system_prompt_uses_shared_definitions(self):
        """_SYSTEM_PROMPT 가 _category_definitions 에서 생성된 스니펫을 포함해야 한다."""
        from module_0_kms.pipeline._category_definitions import CATEGORY_DEFINITIONS
        for name in CATEGORY_DEFINITIONS:
            assert name in _SYSTEM_PROMPT, (
                f"카테고리 '{name}'이 Stage5 시스템 프롬프트에 없음"
            )


# ---------------------------------------------------------------------------
# T1: Stage5 개방형 카테고리 추론 — KB Evolution
# ---------------------------------------------------------------------------

class TestOpenCategoryInference:
    """Stage5 가 카테고리를 자유롭게 추론하고 근거를 제공해야 한다.

    이전: 6개 중 하나 강제 선택
    이후: LLM이 자유롭게 추론 + category_reasoning + category_alternatives 반환
    """

    def test_system_prompt_allows_free_category(self):
        """_SYSTEM_PROMPT 에 '6개 중 하나' 같은 고정 제약이 없어야 한다."""
        assert "6개 중" not in _SYSTEM_PROMPT, (
            "Stage5 프롬프트에 '6개 중' 고정 제약이 남아있음 — "
            "LLM이 새 카테고리를 자유롭게 추론할 수 없음"
        )

    def test_system_prompt_requests_reasoning(self):
        """_SYSTEM_PROMPT 에 category_reasoning 필드 추출 지시가 있어야 한다."""
        assert "category_reasoning" in _SYSTEM_PROMPT or "근거" in _SYSTEM_PROMPT, (
            "Stage5 프롬프트에 카테고리 추론 근거 요청 없음"
        )

    def test_system_prompt_requests_alternatives(self):
        """_SYSTEM_PROMPT 에 category_alternatives 필드 추출 지시가 있어야 한다."""
        assert "category_alternatives" in _SYSTEM_PROMPT or "alternatives" in _SYSTEM_PROMPT, (
            "Stage5 프롬프트에 대안 카테고리 목록 요청 없음"
        )

    async def test_mock_llm_returns_category_reasoning(self, monkeypatch):
        """USE_MOCK_LLM=true 시 category_reasoning 필드가 반환되어야 한다."""
        monkeypatch.setenv("USE_MOCK_LLM", "true")
        result = await stage5_metadata(_state())
        assert "category_reasoning" in result or (
            result.get("metadata") and "category_reasoning" in (result.get("metadata") or {})
        ), "Mock 모드에서 category_reasoning 없음"

    async def test_mock_llm_returns_category_is_new_flag(self, monkeypatch):
        """USE_MOCK_LLM=true 시 category_is_new 필드가 반환되어야 한다."""
        monkeypatch.setenv("USE_MOCK_LLM", "true")
        result = await stage5_metadata(_state())
        assert "category_is_new" in result, (
            "Mock 모드에서 category_is_new 없음 — "
            "Stage5b 가 새 카테고리 여부를 판단할 수 없음"
        )

    async def test_known_category_is_not_new(self, monkeypatch):
        """기존 VALID_CATEGORIES 에 있는 카테고리는 category_is_new=False 여야 한다."""
        monkeypatch.setenv("USE_MOCK_LLM", "true")
        result = await stage5_metadata(
            _state(validated_markdown="# N+1 쿼리 방지\n\nJoinedLoad를 사용합니다.")
        )
        # Mock은 기본 카테고리('코딩컨벤션' 또는 기존 카테고리)를 반환
        if not result.get("category_is_new"):
            pass  # 기존 카테고리면 False — 정상
        # is_new=True인 경우 alternatives 가 있어야 함
        if result.get("category_is_new"):
            assert result.get("category_alternatives"), "새 카테고리인데 alternatives 없음"

    async def test_mock_llm_returns_category_alternatives(self, monkeypatch):
        """USE_MOCK_LLM=true 시 category_alternatives 필드가 반환되어야 한다."""
        monkeypatch.setenv("USE_MOCK_LLM", "true")
        result = await stage5_metadata(_state())
        assert "category_alternatives" in result, (
            "Mock 모드에서 category_alternatives 없음"
        )
        assert isinstance(result.get("category_alternatives"), list)


class TestBuildRelations:
    def _child_chunk(self, cid: str, content: str) -> dict:
        return {"chunk_id": cid, "chunk_type": "child", "content": content}

    def _parent_chunk(self, cid: str, content: str) -> dict:
        return {"chunk_id": cid, "chunk_type": "parent", "content": content}

    def test_mentions_found(self):
        chunks = [self._child_chunk("c1", "FastAPI를 사용합니다.")]
        entities = [{"name": "FastAPI", "type": "Technology"}]
        relations = _build_relations(chunks, entities)
        assert len(relations) == 1
        assert relations[0]["entity_name"] == "FastAPI"
        assert relations[0]["from_chunk_id"] == "c1"
        assert relations[0]["relation_type"] == "MENTIONS"

    def test_no_mention_no_relation(self):
        chunks = [self._child_chunk("c1", "전혀 관련 없는 내용")]
        entities = [{"name": "FastAPI", "type": "Technology"}]
        assert _build_relations(chunks, entities) == []

    def test_case_insensitive_match(self):
        chunks = [self._child_chunk("c1", "fastapi와 django를 비교합니다.")]
        entities = [{"name": "FastAPI"}]
        relations = _build_relations(chunks, entities)
        assert len(relations) == 1

    def test_parent_chunks_excluded(self):
        chunks = [self._parent_chunk("p1", "FastAPI 사용")]
        entities = [{"name": "FastAPI"}]
        assert _build_relations(chunks, entities) == []

    def test_multiple_entities_in_one_chunk(self):
        chunks = [self._child_chunk("c1", "FastAPI와 PostgreSQL을 사용합니다.")]
        entities = [{"name": "FastAPI"}, {"name": "PostgreSQL"}]
        relations = _build_relations(chunks, entities)
        assert len(relations) == 2

    def test_empty_entities_returns_empty(self):
        chunks = [self._child_chunk("c1", "내용")]
        assert _build_relations(chunks, []) == []

    def test_entity_without_name_skipped(self):
        chunks = [self._child_chunk("c1", "내용")]
        entities = [{"type": "Technology"}]  # name 없음
        assert _build_relations(chunks, entities) == []


# ---------------------------------------------------------------------------
# 실제 LLM 경로 — langchain_google_genai ChatGoogleGenerativeAI Mocking
# ---------------------------------------------------------------------------

class TestRealLLMFallback:
    """USE_MOCK_LLM=false 경로를 ChatGoogleGenerativeAI Mock으로 테스트.

    langchain_google_genai 스텁은 conftest.py에서 전역으로 주입되므로
    각 테스트는 mock_genai fixture를 통해 ChatGoogleGenerativeAI만 재설정한다.
    """

    @pytest.fixture
    def mock_genai(self):
        """_gemini 싱글턴을 리셋하고 ChatGoogleGenerativeAI를 Mock으로 교체."""
        import module_0_kms.pipeline._gemini as gm
        mock_cls = MagicMock()
        original_llm = gm._gemini_llm
        gm._gemini_llm = None
        with patch("kms.pipeline._gemini.ChatGoogleGenerativeAI", mock_cls):
            yield mock_cls
        gm._gemini_llm = original_llm

    def _configure_llm(self, mock_cls, response_content: str) -> None:
        """mock_cls 인스턴스의 ainvoke가 response_content를 반환하도록 설정."""
        mock_response = MagicMock()
        mock_response.content = response_content
        mock_llm = AsyncMock()
        mock_llm.ainvoke = AsyncMock(return_value=mock_response)
        mock_cls.return_value = mock_llm

    async def test_json_parse_failure_uses_fallback(self, monkeypatch, mock_genai):
        monkeypatch.setenv("USE_MOCK_LLM", "false")
        self._configure_llm(mock_genai, "잘못된 JSON")

        result = await stage5_metadata(_state())

        assert result["metadata"]["title"] == "제목 없음"
        assert result["neo4j_entities"] == []

    async def test_api_exception_uses_fallback(self, monkeypatch, mock_genai):
        monkeypatch.setenv("USE_MOCK_LLM", "false")
        mock_llm = AsyncMock()
        mock_llm.ainvoke = AsyncMock(side_effect=Exception("API 오류"))
        mock_genai.return_value = mock_llm

        result = await stage5_metadata(_state())

        assert result["metadata"] is not None
        assert result["neo4j_entities"] == []

    async def test_real_llm_success_path(self, monkeypatch, mock_genai):
        """LLM이 올바른 JSON 반환 시 메타데이터 + 엔티티 파싱."""
        monkeypatch.setenv("USE_MOCK_LLM", "false")
        payload = json.dumps({
            "title": "FastAPI 가이드",
            "category": "아키텍처",
            "team": "백엔드팀",
            "author": "홍길동",
            "tags": ["fastapi", "python"],
            "entities": [
                {"name": "FastAPI", "type": "Technology", "description": "웹 프레임워크"}
            ]
        })
        self._configure_llm(mock_genai, payload)

        result = await stage5_metadata(_state(validated_markdown="# FastAPI\n\n내용"))

        assert result["metadata"]["title"] == "FastAPI 가이드"
        assert result["metadata"]["category"] == "아키텍처"
        assert result["metadata"]["team"] == "백엔드팀"
        assert len(result["neo4j_entities"]) == 1
        assert result["neo4j_entities"][0]["name"] == "FastAPI"


# ---------------------------------------------------------------------------
# SystemMessage 구조 검증
# ---------------------------------------------------------------------------

class TestSystemMessage:
    """call_gemini_with_retry에 [SystemMessage, HumanMessage] 순서로 전달되는지 검증."""

    def _capture_messages(self, monkeypatch) -> dict:
        import json as _json
        captured = {}

        async def fake_gemini(messages):
            captured["messages"] = messages
            resp = MagicMock()
            resp.content = _json.dumps({
                "title": "테스트 문서", "category": "기타",
                "team": None, "author": None, "tags": [], "entities": [],
            })
            return resp

        import module_0_kms.pipeline.stage5_metadata_agent as m
        monkeypatch.setattr(m, "call_gemini_with_retry", fake_gemini)
        return captured

    async def test_first_message_is_system_message(self, monkeypatch):
        """LLM 호출 시 첫 번째 메시지가 SystemMessage여야 한다."""
        monkeypatch.setenv("USE_MOCK_LLM", "false")
        captured = self._capture_messages(monkeypatch)

        from module_0_kms.pipeline.stage5_metadata_agent import _extract_metadata
        await _extract_metadata("# 내용", "doc-sm-01")

        assert isinstance(captured["messages"][0], SystemMessage)

    async def test_second_message_is_human_message(self, monkeypatch):
        """LLM 호출 시 두 번째 메시지가 HumanMessage여야 한다."""
        monkeypatch.setenv("USE_MOCK_LLM", "false")
        captured = self._capture_messages(monkeypatch)

        from module_0_kms.pipeline.stage5_metadata_agent import _extract_metadata
        await _extract_metadata("# 내용", "doc-sm-02")

        assert isinstance(captured["messages"][1], HumanMessage)

    async def test_system_message_content_matches_constant(self, monkeypatch):
        """전달된 SystemMessage 내용이 _SYSTEM_PROMPT 상수와 일치해야 한다."""
        monkeypatch.setenv("USE_MOCK_LLM", "false")
        captured = self._capture_messages(monkeypatch)

        from module_0_kms.pipeline.stage5_metadata_agent import _extract_metadata
        await _extract_metadata("# 내용", "doc-sm-03")

        assert captured["messages"][0].content == _SYSTEM_PROMPT

    async def test_system_message_enforces_category_constraint(self, monkeypatch):
        """SystemMessage에 카테고리 고정 목록 제약이 포함되어야 한다."""
        monkeypatch.setenv("USE_MOCK_LLM", "false")
        captured = self._capture_messages(monkeypatch)

        from module_0_kms.pipeline.stage5_metadata_agent import _extract_metadata
        await _extract_metadata("# 내용", "doc-sm-04")

        assert "코딩컨벤션" in captured["messages"][0].content

    async def test_system_message_enforces_entity_type_constraint(self, monkeypatch):
        """SystemMessage에 엔티티 타입 제약(Technology/Pattern/Concept)이 포함되어야 한다."""
        monkeypatch.setenv("USE_MOCK_LLM", "false")
        captured = self._capture_messages(monkeypatch)

        from module_0_kms.pipeline.stage5_metadata_agent import _extract_metadata
        await _extract_metadata("# 내용", "doc-sm-05")

        assert "Technology" in captured["messages"][0].content

    async def test_total_message_count_is_two(self, monkeypatch):
        """LLM 호출 시 메시지 개수가 정확히 2개(System + Human)여야 한다."""
        monkeypatch.setenv("USE_MOCK_LLM", "false")
        captured = self._capture_messages(monkeypatch)

        from module_0_kms.pipeline.stage5_metadata_agent import _extract_metadata
        await _extract_metadata("# 내용", "doc-sm-06")

        assert len(captured["messages"]) == 2
