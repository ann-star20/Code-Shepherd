"""Tests for Stage 5b: 메타데이터 검증 (stage5b_metadata_validate)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytestmark = pytest.mark.asyncio

from langchain_core.messages import HumanMessage, SystemMessage

from module_0_kms.pipeline.stage5b_metadata_validate_agent import (
    _SYSTEM_PROMPT,
    FALLBACK_TITLE,
    METADATA_QUALITY_THRESHOLD,
    VALID_CATEGORIES,
    _validate_with_llm,
    stage5b_metadata_validate,
)


def _state(**kw) -> dict:
    base = {
        "doc_id": "doc-s5b-001",
        "validated_markdown": "# 신입 온보딩 가이드\n\nPython 설치 및 개발 환경 구성 방법을 설명한다.",
        "metadata": {
            "title": "신입 온보딩 가이드",
            "category": "온보딩",
            "tags": ["온보딩", "환경설정"],
            "source": "upload",
        },
        "neo4j_entities": [],
    }
    base.update(kw)
    return base


# ---------------------------------------------------------------------------
# 규칙 기반 검사 — LLM 없이 즉시 판단
# ---------------------------------------------------------------------------

class TestRuleBasedChecks:
    async def test_fallback_title_triggers_hitl(self):
        state = _state(metadata={"title": FALLBACK_TITLE, "category": "온보딩", "tags": []})
        result = await stage5b_metadata_validate(state)

        assert result["hitl_required"] is True
        assert result["metadata_valid"] is False
        assert result["metadata_score"] == 0.0
        assert any("제목" in issue for issue in result["metadata_issues"])

    async def test_empty_title_triggers_hitl(self):
        state = _state(metadata={"title": "", "category": "온보딩", "tags": []})
        result = await stage5b_metadata_validate(state)

        assert result["hitl_required"] is True
        assert result["metadata_valid"] is False

    async def test_invalid_category_triggers_hitl(self):
        state = _state(metadata={"title": "유효한 제목", "category": "존재하지않는카테고리", "tags": []})
        result = await stage5b_metadata_validate(state)

        assert result["hitl_required"] is True
        assert result["metadata_valid"] is False
        assert any("카테고리" in issue for issue in result["metadata_issues"])

    async def test_rule_hitl_sets_status_hitl_pending(self):
        state = _state(metadata={"title": FALLBACK_TITLE, "category": "온보딩", "tags": []})
        result = await stage5b_metadata_validate(state)

        assert result["status"] == "hitl_pending"
        assert result["current_stage"] == "stage5b_metadata_validate"

    async def test_all_valid_categories_pass_rule_check(self, monkeypatch):
        monkeypatch.setenv("USE_MOCK_LLM", "true")
        for cat in VALID_CATEGORIES:
            state = _state(metadata={"title": "유효한 제목", "category": cat, "tags": []})
            result = await stage5b_metadata_validate(state)
            assert result.get("metadata_valid") is True, f"카테고리 '{cat}' 통과 실패"


# ---------------------------------------------------------------------------
# Mock LLM 경로
# ---------------------------------------------------------------------------

class TestMockLLM:
    async def test_mock_returns_valid(self, monkeypatch):
        monkeypatch.setenv("USE_MOCK_LLM", "true")
        result = await stage5b_metadata_validate(_state())

        assert result["metadata_valid"] is True
        assert result["metadata_score"] == 1.0
        assert result["hitl_required"] is False

    async def test_mock_sets_current_stage(self, monkeypatch):
        monkeypatch.setenv("USE_MOCK_LLM", "true")
        result = await stage5b_metadata_validate(_state())

        assert result["current_stage"] == "stage5b_metadata_validate"

    async def test_mock_no_status_field_on_success(self, monkeypatch):
        monkeypatch.setenv("USE_MOCK_LLM", "true")
        result = await stage5b_metadata_validate(_state())

        assert "status" not in result  # 성공 시 status 설정 없음 (LangGraph가 유지)

    async def test_mock_empty_issues_on_success(self, monkeypatch):
        monkeypatch.setenv("USE_MOCK_LLM", "true")
        result = await stage5b_metadata_validate(_state())

        assert result["metadata_issues"] is None or result["metadata_issues"] == []


# ---------------------------------------------------------------------------
# LLM 기반 검증 — 점수 기반 HITL 판단
# ---------------------------------------------------------------------------

class TestLLMValidation:
    async def test_high_score_passes(self, monkeypatch):
        monkeypatch.setenv("USE_MOCK_LLM", "false")
        with patch(
            "kms.pipeline.stage5b_metadata_validate_agent._validate_with_llm",
            new=AsyncMock(return_value=(0.92, [])),
        ):
            result = await stage5b_metadata_validate(_state())

        assert result["metadata_valid"] is True
        assert result["metadata_score"] == pytest.approx(0.92)
        assert result["hitl_required"] is False

    async def test_low_score_triggers_hitl(self, monkeypatch):
        monkeypatch.setenv("USE_MOCK_LLM", "false")
        with patch(
            "kms.pipeline.stage5b_metadata_validate_agent._validate_with_llm",
            new=AsyncMock(return_value=(0.5, ["카테고리 불일치"])),
        ):
            result = await stage5b_metadata_validate(_state())

        assert result["metadata_valid"] is False
        assert result["hitl_required"] is True
        assert result["metadata_score"] == pytest.approx(0.5)

    async def test_score_at_threshold_passes(self, monkeypatch):
        monkeypatch.setenv("USE_MOCK_LLM", "false")
        with patch(
            "kms.pipeline.stage5b_metadata_validate_agent._validate_with_llm",
            new=AsyncMock(return_value=(METADATA_QUALITY_THRESHOLD, [])),
        ):
            result = await stage5b_metadata_validate(_state())

        assert result["metadata_valid"] is True
        assert result["hitl_required"] is False

    async def test_category_incorrect_adds_issue(self, monkeypatch):
        monkeypatch.setenv("USE_MOCK_LLM", "false")
        with patch(
            "kms.pipeline.stage5b_metadata_validate_agent._validate_with_llm",
            new=AsyncMock(return_value=(0.85, ["카테고리 불일치"])),
        ):
            result = await stage5b_metadata_validate(_state())

        assert any("카테고리" in issue for issue in (result["metadata_issues"] or []))

    async def test_title_not_representative_adds_issue(self, monkeypatch):
        monkeypatch.setenv("USE_MOCK_LLM", "false")
        with patch(
            "kms.pipeline.stage5b_metadata_validate_agent._validate_with_llm",
            new=AsyncMock(return_value=(0.85, ["제목이 대표적이지 않음"])),
        ):
            result = await stage5b_metadata_validate(_state())

        assert any("제목" in issue for issue in (result["metadata_issues"] or []))


# ---------------------------------------------------------------------------
# 오류 처리
# ---------------------------------------------------------------------------

class TestErrorHandling:
    async def test_json_parse_error_returns_score_zero(self, monkeypatch):
        monkeypatch.setenv("USE_MOCK_LLM", "false")
        with patch(
            "kms.pipeline.stage5b_metadata_validate_agent._validate_with_llm",
            new=AsyncMock(return_value=(0.0, ["메타데이터 검증 응답 파싱 실패 — 수동 검토 필요"])),
        ):
            result = await stage5b_metadata_validate(_state())

        assert result["metadata_score"] == 0.0
        assert result["hitl_required"] is True

    async def test_api_exception_returns_score_zero(self, monkeypatch):
        monkeypatch.setenv("USE_MOCK_LLM", "false")
        with patch(
            "kms.pipeline.stage5b_metadata_validate_agent._validate_with_llm",
            new=AsyncMock(return_value=(0.0, ["메타데이터 검증 실패: API 오류"])),
        ):
            result = await stage5b_metadata_validate(_state())

        assert result["metadata_score"] == 0.0
        assert result["hitl_required"] is True

    async def test_missing_metadata_uses_defaults(self, monkeypatch):
        monkeypatch.setenv("USE_MOCK_LLM", "true")
        state = _state(metadata=None)
        result = await stage5b_metadata_validate(state)

        # metadata=None → title="" → HITL
        assert result["hitl_required"] is True

    async def test_none_entities_treated_as_empty(self, monkeypatch):
        monkeypatch.setenv("USE_MOCK_LLM", "true")
        state = _state(neo4j_entities=None)
        result = await stage5b_metadata_validate(state)

        assert result["metadata_valid"] is True  # entities=None → 0개로 처리, 정상 통과


# ---------------------------------------------------------------------------
# T6: _validate_with_llm 직접 테스트 (lines 167-198 커버)
# ---------------------------------------------------------------------------

class TestValidateWithLLM:
    """_validate_with_llm()의 실제 LLM 경로를 call_gemini_with_retry Mock으로 테스트."""

    @pytest.fixture
    def mock_gemini(self):
        """_gemini 싱글턴 리셋 + ChatGoogleGenerativeAI 교체."""
        import module_0_kms.pipeline._gemini as gm
        original_llm = gm._gemini_llm
        gm._gemini_llm = None
        with patch("kms.pipeline._gemini.ChatGoogleGenerativeAI") as mock_cls:
            yield mock_cls
        gm._gemini_llm = original_llm

    def _configure_response(self, mock_cls, content: str) -> None:
        mock_response = MagicMock()
        mock_response.content = content
        mock_llm = AsyncMock()
        mock_llm.ainvoke = AsyncMock(return_value=mock_response)
        mock_cls.return_value = mock_llm

    async def test_success_path_returns_score_and_issues(self, monkeypatch, mock_gemini):
        """LLM이 유효한 JSON을 반환하면 (score, issues) 파싱돼야 한다 (lines 167-198)."""
        monkeypatch.setenv("USE_MOCK_LLM", "false")
        payload = '{"score": 0.9, "category_correct": true, "title_representative": true, "issues": []}'
        self._configure_response(mock_gemini, payload)

        score, issues = await _validate_with_llm(
            title="테스트 제목", category="기타", tags=[], entity_count=0,
            markdown="내용", doc_id="doc-t6-001",
        )
        assert score == pytest.approx(0.9)
        assert issues == []

    async def test_markdown_code_block_json_is_parsed(self, monkeypatch, mock_gemini):
        """```json ... ``` 형식 응답도 파싱되어야 한다 (lines 168-172)."""
        monkeypatch.setenv("USE_MOCK_LLM", "false")
        raw = '```json\n{"score": 0.85, "category_correct": true, "title_representative": true, "issues": []}\n```'
        self._configure_response(mock_gemini, raw)

        score, issues = await _validate_with_llm(
            title="제목", category="기타", tags=[], entity_count=0,
            markdown="내용", doc_id="doc-t6-002",
        )
        assert score == pytest.approx(0.85)

    async def test_json_parse_error_returns_zero_score(self, monkeypatch, mock_gemini):
        """LLM 응답이 유효하지 않은 JSON이면 (0.0, [오류메시지])를 반환해야 한다 (lines 175-180)."""
        monkeypatch.setenv("USE_MOCK_LLM", "false")
        self._configure_response(mock_gemini, "not valid json at all")

        score, issues = await _validate_with_llm(
            title="제목", category="기타", tags=[], entity_count=0,
            markdown="내용", doc_id="doc-t6-003",
        )
        assert score == 0.0
        assert len(issues) > 0


# ---------------------------------------------------------------------------
# 카테고리 정의 공유 확인 — stage5와 동일 기준 사용
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# T2: Stage5b — 새 카테고리 감지 → KB Evolution HITL 분기
# ---------------------------------------------------------------------------

class TestNewCategoryHitlBranch:
    """Stage5가 새 카테고리를 제안하면 Stage5b는 KB Evolution HITL을 발동해야 한다.

    category_is_new=True → HITL 발동 + category_reasoning 전달
    → HITL UI에서 사람이 카테고리 확장 여부를 결정
    """

    def _state_new_category(self, **kw) -> dict:
        base = {
            "doc_id": "doc-kb-001",
            "validated_markdown": "# NCS SW아키텍처수행관리\n\nNCS 기반 교육 내용입니다.",
            "metadata": {
                "title": "NCS SW아키텍처수행관리",
                "category": "NCS교육",
                "tags": [],
                "source": "upload",
            },
            "neo4j_entities": [],
            "category_is_new": True,
            "category_reasoning": "이 문서는 NCS 기반 SW아키텍처 교육 자료입니다.",
            "category_alternatives": ["아키텍처", "온보딩"],
        }
        base.update(kw)
        return base

    async def test_new_category_triggers_hitl(self, monkeypatch):
        """category_is_new=True이면 stage5b가 HITL을 발동해야 한다."""
        monkeypatch.setenv("USE_MOCK_LLM", "true")
        result = await stage5b_metadata_validate(self._state_new_category())
        assert result.get("hitl_required") is True, (
            "새 카테고리인데 HITL 미발동 — KB Evolution 불가"
        )

    async def test_new_category_hitl_includes_reasoning(self, monkeypatch):
        """HITL 발동 시 category_reasoning 원문이 출력에 포함되어야 한다."""
        monkeypatch.setenv("USE_MOCK_LLM", "true")
        result = await stage5b_metadata_validate(self._state_new_category())
        # category_reasoning 이 result에 보존되거나 issues에 포함되어야 함
        reasoning_in_result = result.get("category_reasoning") == "이 문서는 NCS 기반 SW아키텍처 교육 자료입니다."
        issues = result.get("metadata_issues") or []
        reasoning_in_issues = any("NCS 기반 SW아키텍처 교육" in i for i in issues)
        assert reasoning_in_result or reasoning_in_issues, (
            f"category_reasoning 원문이 HITL 출력에 없음. result keys: {list(result.keys())}, issues: {issues}"
        )

    async def test_new_category_hitl_preserves_alternatives(self, monkeypatch):
        """HITL 발동 시 category_alternatives 가 result에 보존되어야 한다."""
        monkeypatch.setenv("USE_MOCK_LLM", "true")
        result = await stage5b_metadata_validate(self._state_new_category())
        assert result.get("category_alternatives") == ["아키텍처", "온보딩"], (
            f"category_alternatives가 result에 없거나 다름: {result.get('category_alternatives')}"
        )

    async def test_existing_valid_category_skips_new_branch(self, monkeypatch):
        """category_is_new=False이면 기존 검증 흐름을 탄다 (KB Evolution 분기 미진입)."""
        monkeypatch.setenv("USE_MOCK_LLM", "true")
        state = self._state_new_category(
            metadata={"title": "아키텍처 가이드", "category": "아키텍처", "tags": []},
            category_is_new=False,
            category_reasoning="아키텍처 카테고리에 명확히 해당",
        )
        result = await stage5b_metadata_validate(state)
        # Mock LLM → score=1.0 → PASS (HITL 없음)
        assert not result.get("hitl_required"), (
            "기존 카테고리인데 KB Evolution HITL 발동됨"
        )


class TestSharedCategoryDefinitions:
    """stage5b 가 stage5 와 동일한 _category_definitions 모듈을 사용해야 한다.

    stage5가 '아키텍처'로 분류하면 stage5b도 같은 기준으로 평가해서
    NCS SW아키텍처 문서가 HITL 없이 통과되어야 한다.
    """

    # pytestmark = asyncio 가 파일 전체에 적용되므로 sync 테스트는
    # pytest.mark.asyncio 를 명시적으로 제거하기 위해 mark 오버라이드
    pytestmark = pytest.mark.usefixtures()  # reset global asyncio mark

    def test_valid_categories_match_shared_module(self):
        """VALID_CATEGORIES 가 _category_definitions.VALID_CATEGORIES 와 일치해야 한다."""
        from module_0_kms.pipeline._category_definitions import VALID_CATEGORIES as shared
        assert VALID_CATEGORIES == shared, (
            "stage5b VALID_CATEGORIES가 공통 모듈과 다름 — "
            "stage5와 stage5b의 카테고리 기준이 불일치할 수 있음"
        )

    def test_system_prompt_includes_category_definitions(self):
        """stage5b _SYSTEM_PROMPT 에도 카테고리 정의가 포함되어야 한다."""
        assert "NCS" in _SYSTEM_PROMPT or "수행" in _SYSTEM_PROMPT, (
            "stage5b 프롬프트에 NCS/수행 키워드 없음 — "
            "stage5와 다른 기준으로 '아키텍처' 카테고리를 평가할 수 있음"
        )

    def test_system_prompt_marks_giteo_as_last_resort(self):
        """stage5b 도 '기타'가 마지막 수단임을 알아야 한다."""
        assert "마지막" in _SYSTEM_PROMPT or "해당하지" in _SYSTEM_PROMPT, (
            "stage5b 프롬프트에 '기타는 마지막 수단' 안내 없음"
        )


# TestValidateWithLLM 에 속하는 나머지 테스트 — 원래 위치로 복원
class TestValidateWithLLMExtended:
    """_validate_with_llm 추가 경로 커버 — TestValidateWithLLM 과 동일한 fixture 방식."""

    @pytest.fixture
    def mock_gemini(self):
        import module_0_kms.pipeline._gemini as gm
        original_llm = gm._gemini_llm
        gm._gemini_llm = None
        with patch("kms.pipeline._gemini.ChatGoogleGenerativeAI") as mock_cls:
            yield mock_cls
        gm._gemini_llm = original_llm

    def _configure_response(self, mock_cls, content: str) -> None:
        mock_response = MagicMock()
        mock_response.content = content
        mock_llm = AsyncMock()
        mock_llm.ainvoke = AsyncMock(return_value=mock_response)
        mock_cls.return_value = mock_llm

    async def test_category_incorrect_prepends_issue(self, monkeypatch, mock_gemini):
        """category_correct=false이면 카테고리 불일치 메시지가 issues 앞에 추가돼야 한다."""
        monkeypatch.setenv("USE_MOCK_LLM", "false")
        payload = '{"score": 0.8, "category_correct": false, "title_representative": true, "issues": []}'
        self._configure_response(mock_gemini, payload)

        score, issues = await _validate_with_llm(
            title="제목", category="기타", tags=[], entity_count=0,
            markdown="내용", doc_id="doc-t6-004",
        )
        assert any("카테고리" in issue for issue in issues)

    async def test_title_not_representative_appends_issue(self, monkeypatch, mock_gemini):
        """title_representative=false이면 제목 관련 메시지가 issues에 추가돼야 한다."""
        monkeypatch.setenv("USE_MOCK_LLM", "false")
        payload = '{"score": 0.8, "category_correct": true, "title_representative": false, "issues": []}'
        self._configure_response(mock_gemini, payload)

        score, issues = await _validate_with_llm(
            title="제목", category="기타", tags=[], entity_count=0,
            markdown="내용", doc_id="doc-t6-005",
        )
        assert any("제목" in issue for issue in issues)


# ---------------------------------------------------------------------------
# SystemMessage 구조 검증
# ---------------------------------------------------------------------------

class TestSystemMessage:
    """call_gemini_with_retry에 [SystemMessage, HumanMessage] 순서로 전달되는지 검증."""

    def _capture_messages(self, monkeypatch) -> dict:
        captured = {}

        async def fake_gemini(messages):
            captured["messages"] = messages
            resp = MagicMock()
            resp.content = '{"score": 0.9, "category_correct": true, "title_representative": true, "issues": []}'
            return resp

        import module_0_kms.pipeline.stage5b_metadata_validate_agent as m
        monkeypatch.setattr(m, "call_gemini_with_retry", fake_gemini)
        return captured

    async def test_first_message_is_system_message(self, monkeypatch):
        """LLM 호출 시 첫 번째 메시지가 SystemMessage여야 한다."""
        monkeypatch.setenv("USE_MOCK_LLM", "false")
        captured = self._capture_messages(monkeypatch)

        await _validate_with_llm(
            title="테스트 제목", category="기타", tags=[], entity_count=0,
            markdown="내용", doc_id="doc-sm-01",
        )

        assert isinstance(captured["messages"][0], SystemMessage)

    async def test_second_message_is_human_message(self, monkeypatch):
        """LLM 호출 시 두 번째 메시지가 HumanMessage여야 한다."""
        monkeypatch.setenv("USE_MOCK_LLM", "false")
        captured = self._capture_messages(monkeypatch)

        await _validate_with_llm(
            title="테스트 제목", category="기타", tags=[], entity_count=0,
            markdown="내용", doc_id="doc-sm-02",
        )

        assert isinstance(captured["messages"][1], HumanMessage)

    async def test_system_message_content_matches_constant(self, monkeypatch):
        """전달된 SystemMessage 내용이 _SYSTEM_PROMPT 상수와 일치해야 한다."""
        monkeypatch.setenv("USE_MOCK_LLM", "false")
        captured = self._capture_messages(monkeypatch)

        await _validate_with_llm(
            title="테스트 제목", category="기타", tags=[], entity_count=0,
            markdown="내용", doc_id="doc-sm-03",
        )

        assert captured["messages"][0].content == _SYSTEM_PROMPT

    async def test_system_message_requires_document_comparison(self, monkeypatch):
        """SystemMessage에 문서 내용과 비교하라는 지시가 포함되어야 한다."""
        monkeypatch.setenv("USE_MOCK_LLM", "false")
        captured = self._capture_messages(monkeypatch)

        await _validate_with_llm(
            title="테스트 제목", category="기타", tags=[], entity_count=0,
            markdown="내용", doc_id="doc-sm-04",
        )

        assert "문서 내용" in captured["messages"][0].content

    async def test_system_message_requires_json_only(self, monkeypatch):
        """SystemMessage에 JSON만 반환하라는 지시가 포함되어야 한다."""
        monkeypatch.setenv("USE_MOCK_LLM", "false")
        captured = self._capture_messages(monkeypatch)

        await _validate_with_llm(
            title="테스트 제목", category="기타", tags=[], entity_count=0,
            markdown="내용", doc_id="doc-sm-05",
        )

        assert "JSON" in captured["messages"][0].content

    async def test_total_message_count_is_two(self, monkeypatch):
        """LLM 호출 시 메시지 개수가 정확히 2개(System + Human)여야 한다."""
        monkeypatch.setenv("USE_MOCK_LLM", "false")
        captured = self._capture_messages(monkeypatch)

        await _validate_with_llm(
            title="테스트 제목", category="기타", tags=[], entity_count=0,
            markdown="내용", doc_id="doc-sm-06",
        )

        assert len(captured["messages"]) == 2
