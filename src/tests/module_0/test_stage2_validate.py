"""Tests for Stage 2: Markdown 품질 검증 (stage2_validate)."""

from __future__ import annotations

import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from langchain_core.messages import HumanMessage, SystemMessage

from module_0_kms.pipeline.stage2_validate_agent import (
    _SYSTEM_PROMPT,
    _evaluate_quality,
    _sample_markdown,
    stage2_validate,
)


def _state(**kw) -> dict:
    return {"doc_id": "doc-s2-001", "raw_markdown": "# 가이드\n\n내용입니다.", **kw}


# ---------------------------------------------------------------------------
# 빈 Markdown 처리
# ---------------------------------------------------------------------------

class TestEmptyMarkdown:
    async def test_empty_string_triggers_hitl(self):
        result = await stage2_validate(_state(raw_markdown=""))
        assert result["hitl_required"] is True
        assert result["status"] == "hitl_pending"
        assert result["validated_markdown"] is None
        assert result["quality_score"] == 0.0

    async def test_none_markdown_triggers_hitl(self):
        result = await stage2_validate(_state(raw_markdown=None))
        assert result["hitl_required"] is True
        assert "Markdown이 없음" in result["quality_issues"][0]

    async def test_empty_markdown_sets_current_stage(self):
        result = await stage2_validate(_state(raw_markdown=""))
        assert result["current_stage"] == "stage2_validate"


# ---------------------------------------------------------------------------
# Mock LLM 경로 (USE_MOCK_LLM=true)
# ---------------------------------------------------------------------------

class TestMockLLM:
    async def test_high_quality_passes(self, monkeypatch):
        monkeypatch.setenv("USE_MOCK_LLM", "true")
        result = await stage2_validate(_state())
        assert result["hitl_required"] is False
        assert result["quality_score"] == 1.0
        assert result["quality_issues"] == []

    async def test_validated_markdown_equals_input(self, monkeypatch):
        monkeypatch.setenv("USE_MOCK_LLM", "true")
        content = "# 섹션\n\n내용\n\n## 하위"
        result = await stage2_validate(_state(raw_markdown=content))
        assert result["validated_markdown"] == content

    async def test_mock_evaluate_quality_returns_perfect(self, monkeypatch):
        monkeypatch.setenv("USE_MOCK_LLM", "true")
        score, issues, hitl = await _evaluate_quality("# 내용", "doc-001")
        assert score == 1.0
        assert issues == []
        assert hitl is False


# ---------------------------------------------------------------------------
# 실제 LLM 경로 — langchain_google_genai ChatGoogleGenerativeAI Mocking
# ---------------------------------------------------------------------------

class TestRealLLMPaths:
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

    async def test_json_parse_failure_triggers_hitl(self, monkeypatch, mock_genai):
        monkeypatch.setenv("USE_MOCK_LLM", "false")
        self._configure_llm(mock_genai, "올바르지 않은 JSON")

        score, issues, hitl = await _evaluate_quality("# 내용", "doc-001")

        assert hitl is True
        assert score == 0.0
        assert any("파싱" in i for i in issues)

    async def test_low_score_triggers_hitl(self, monkeypatch, mock_genai):
        monkeypatch.setenv("USE_MOCK_LLM", "false")
        payload = '{"score": 0.5, "issues": ["품질 낮음"], "structure_loss": false, "table_loss": false, "image_loss": false}'
        self._configure_llm(mock_genai, payload)

        score, issues, hitl = await _evaluate_quality("# 내용", "doc-001")

        assert hitl is True
        assert score == 0.5

    async def test_table_loss_triggers_hitl_and_prepends_issue(self, monkeypatch, mock_genai):
        monkeypatch.setenv("USE_MOCK_LLM", "false")
        payload = '{"score": 0.9, "issues": [], "structure_loss": false, "table_loss": true, "image_loss": false}'
        self._configure_llm(mock_genai, payload)

        score, issues, hitl = await _evaluate_quality("# 내용", "doc-001")

        assert hitl is True
        assert issues[0] == "표/이미지 구조 손실 감지"

    async def test_structure_loss_triggers_hitl(self, monkeypatch, mock_genai):
        monkeypatch.setenv("USE_MOCK_LLM", "false")
        payload = '{"score": 0.95, "issues": [], "structure_loss": true, "table_loss": false, "image_loss": false}'
        self._configure_llm(mock_genai, payload)

        _, _, hitl = await _evaluate_quality("# 내용", "doc-001")

        assert hitl is True

    async def test_api_exception_triggers_hitl(self, monkeypatch, mock_genai):
        monkeypatch.setenv("USE_MOCK_LLM", "false")
        mock_llm = AsyncMock()
        mock_llm.ainvoke = AsyncMock(side_effect=Exception("네트워크 오류"))
        mock_genai.return_value = mock_llm

        score, issues, hitl = await _evaluate_quality("# 내용", "doc-001")

        assert hitl is True
        assert score == 0.0

    async def test_good_score_no_loss_passes(self, monkeypatch, mock_genai):
        monkeypatch.setenv("USE_MOCK_LLM", "false")
        payload = '{"score": 0.95, "issues": [], "structure_loss": false, "table_loss": false, "image_loss": false}'
        self._configure_llm(mock_genai, payload)

        score, issues, hitl = await _evaluate_quality("# 내용", "doc-001")

        assert hitl is False
        assert score == 0.95


# ---------------------------------------------------------------------------
# T7: _sample_markdown — 앞/중간/끝 균등 샘플링
# ---------------------------------------------------------------------------

class TestSampleMarkdown:
    """_sample_markdown()은 긴 Markdown에서 앞/중간/끝을 균등하게 샘플링한다."""

    def test_short_text_returned_unchanged(self):
        """max_chars 이하인 텍스트는 그대로 반환돼야 한다."""
        text = "# 짧은 문서\n\n내용입니다."
        assert _sample_markdown(text, max_chars=3000) == text

    def test_text_at_exact_limit_returned_unchanged(self):
        """길이가 정확히 max_chars인 텍스트는 그대로 반환돼야 한다."""
        text = "A" * 3000
        assert _sample_markdown(text, max_chars=3000) == text

    def test_long_text_result_is_shorter_than_original(self):
        """max_chars 초과 텍스트는 원본보다 짧아야 한다."""
        text = "A" * 9000
        result = _sample_markdown(text, max_chars=3000)
        assert len(result) < len(text)

    def test_long_text_begins_with_original_start(self):
        """샘플의 첫 부분이 원본 시작 부분과 일치해야 한다."""
        text = "BEGIN_MARKER" + "X" * 9000
        result = _sample_markdown(text, max_chars=300)
        assert result.startswith("BEGIN_MARKER")

    def test_long_text_contains_original_end(self):
        """샘플의 마지막 부분이 원본 끝 부분과 일치해야 한다."""
        text = "X" * 9000 + "END_MARKER"
        result = _sample_markdown(text, max_chars=300)
        assert "END_MARKER" in result

    def test_long_text_contains_middle_section(self):
        """샘플이 원본 중간 부분을 포함해야 한다."""
        max_chars = 300
        chunk = max_chars // 3  # 100
        length = 9000
        mid_start = (length - chunk) // 2  # 4450
        text = "A" * mid_start + "MID_MARKER" + "A" * (length - mid_start - len("MID_MARKER"))
        result = _sample_markdown(text, max_chars=max_chars)
        assert "MID_MARKER" in result

    def test_long_text_contains_separator_text(self):
        """앞/중간/끝 사이에 '중략' 구분자가 있어야 한다."""
        text = "A" * 9000
        result = _sample_markdown(text, max_chars=300)
        assert "중략" in result

    def test_long_text_has_exactly_two_separators(self):
        """3개 구간이므로 구분자가 정확히 2개여야 한다."""
        text = "A" * 9000
        result = _sample_markdown(text, max_chars=300)
        assert result.count("중략") == 2

    def test_evaluate_quality_uses_sample_not_raw_prefix(self, monkeypatch):
        """_evaluate_quality가 긴 Markdown에서 앞만 자르지 않고 샘플링을 사용해야 한다.
        끝 부분 마커가 LLM 입력(HumanMessage)에 포함됐는지 확인한다."""
        monkeypatch.setenv("USE_MOCK_LLM", "false")

        captured = {}

        async def fake_gemini(messages):
            # messages[0] = SystemMessage, messages[1] = HumanMessage(질평가 프롬프트)
            captured["content"] = messages[1].content
            resp = MagicMock()
            resp.content = '{"score": 0.9, "issues": [], "structure_loss": false, "table_loss": false, "image_loss": false}'
            return resp

        import module_0_kms.pipeline.stage2_validate_agent as m
        monkeypatch.setattr(m, "call_gemini_with_retry", fake_gemini)

        # 끝에만 마커가 있는 긴 텍스트 (앞 3000자에는 없음)
        text = "A" * 9000 + "END_MARKER_CHECK"

        import asyncio
        asyncio.get_event_loop().run_until_complete(_evaluate_quality(text, "doc-t7"))

        assert "END_MARKER_CHECK" in captured["content"], (
            "앞 3000자 잘라내기만 한다면 끝 마커가 프롬프트에 없어야 하므로 이 단언이 실패한다 — "
            "균등 샘플링으로 교체해야 GREEN이 된다"
        )


# ---------------------------------------------------------------------------
# HITL 임계값 0.7 검증 (세션 42: 0.8 → 0.7 하향)
# ---------------------------------------------------------------------------

class TestQualityThreshold07:
    """MARKDOWN_QUALITY_THRESHOLD=0.7 동작 검증.

    이전 임계값 0.8에서는 score 0.7~0.79 구간이 HITL을 트리거했다.
    새 임계값 0.7에서는 해당 구간이 정상 통과돼야 한다.
    """

    @pytest.fixture
    def mock_gemini(self, monkeypatch):
        monkeypatch.setenv("USE_MOCK_LLM", "false")
        # 테스트 환경에서 .env가 로드되지 않으므로 모듈 상수를 직접 패치
        import module_0_kms.pipeline.stage2_validate_agent as m
        monkeypatch.setattr(m, "QUALITY_THRESHOLD", 0.7)
        captured = {}

        async def fake_gemini(messages):
            resp = MagicMock()
            resp.content = captured.get("payload", "")
            return resp

        monkeypatch.setattr(m, "call_gemini_with_retry", fake_gemini)
        return captured

    async def test_score_075_passes_at_threshold_07(self, mock_gemini):
        """score=0.75는 임계값 0.7 이상이므로 HITL이 트리거되지 않아야 한다."""
        mock_gemini["payload"] = (
            '{"score": 0.75, "issues": [], '
            '"structure_loss": false, "table_loss": false, "image_loss": false}'
        )
        score, issues, hitl = await _evaluate_quality("# 내용", "doc-thr-01")
        assert hitl is False, (
            f"score=0.75는 임계값 0.7 이상이므로 HITL=False여야 함. "
            f"현재 임계값이 0.7보다 높게 설정된 것으로 보임."
        )
        assert score == 0.75

    async def test_score_071_passes_at_threshold_07(self, mock_gemini):
        """score=0.71은 임계값 0.7 초과이므로 HITL이 트리거되지 않아야 한다."""
        mock_gemini["payload"] = (
            '{"score": 0.71, "issues": ["경미한 서식 오류"], '
            '"structure_loss": false, "table_loss": false, "image_loss": false}'
        )
        score, issues, hitl = await _evaluate_quality("# 내용", "doc-thr-02")
        assert hitl is False, "score=0.71 > 0.7이므로 HITL=False여야 함"

    async def test_score_070_passes_boundary(self, mock_gemini):
        """score=0.70은 threshold=0.70과 같아서 score < threshold가 False → HITL=False (경계값 통과)."""
        mock_gemini["payload"] = (
            '{"score": 0.70, "issues": ["경미한 문제"], '
            '"structure_loss": false, "table_loss": false, "image_loss": false}'
        )
        score, issues, hitl = await _evaluate_quality("# 내용", "doc-thr-03")
        assert hitl is False, "score=0.70은 0.70 < 0.70이 아니므로(False) HITL 없이 통과해야 함"

    async def test_score_068_triggers_hitl(self, mock_gemini):
        """score=0.68은 임계값 0.7 미만이므로 HITL이 트리거돼야 한다."""
        mock_gemini["payload"] = (
            '{"score": 0.68, "issues": ["심각한 품질 문제"], '
            '"structure_loss": false, "table_loss": false, "image_loss": false}'
        )
        score, issues, hitl = await _evaluate_quality("# 내용", "doc-thr-04")
        assert hitl is True, "score=0.68 < 0.7이므로 HITL=True여야 함"

    async def test_image_loss_alone_does_not_trigger_hitl_when_score_high(self, mock_gemini):
        """image_loss=True여도 score >= 0.7이고 structure_loss/table_loss=False면 HITL 없음.

        세션 42 프롬프트 개선: 이미지 미포함은 정상, score 감점 최대 -0.05.
        """
        mock_gemini["payload"] = (
            '{"score": 0.85, "issues": ["이미지 설명 없음"], '
            '"structure_loss": false, "table_loss": false, "image_loss": true}'
        )
        score, issues, hitl = await _evaluate_quality("# 내용", "doc-thr-05")
        assert hitl is False, (
            "image_loss=True이지만 score=0.85 >= 0.7이고 구조 손실 없음 → HITL=False여야 함. "
            "이미지 미포함이 단독으로 HITL을 트리거하면 안 됨."
        )

    async def test_prompt_contains_image_deprioritization_guidance(self):
        """System 프롬프트에 이미지 감점 최소화 안내가 포함돼 있어야 한다."""
        assert "image_loss" in _SYSTEM_PROMPT or "이미지" in _SYSTEM_PROMPT, (
            "System 프롬프트에 이미지 관련 안내가 없음"
        )
        assert "0.05" in _SYSTEM_PROMPT or "최소" in _SYSTEM_PROMPT, (
            "이미지 감점을 최소화하라는 안내가 System 프롬프트에 없음"
        )


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
            resp.content = '{"score": 0.9, "issues": [], "structure_loss": false, "table_loss": false, "image_loss": false}'
            return resp

        import module_0_kms.pipeline.stage2_validate_agent as m
        monkeypatch.setattr(m, "call_gemini_with_retry", fake_gemini)
        return captured

    async def test_first_message_is_system_message(self, monkeypatch):
        """LLM 호출 시 첫 번째 메시지가 SystemMessage여야 한다."""
        monkeypatch.setenv("USE_MOCK_LLM", "false")
        captured = self._capture_messages(monkeypatch)

        await _evaluate_quality("# 내용", "doc-sm-01")

        assert isinstance(captured["messages"][0], SystemMessage)

    async def test_second_message_is_human_message(self, monkeypatch):
        """LLM 호출 시 두 번째 메시지가 HumanMessage여야 한다."""
        monkeypatch.setenv("USE_MOCK_LLM", "false")
        captured = self._capture_messages(monkeypatch)

        await _evaluate_quality("# 내용", "doc-sm-02")

        assert isinstance(captured["messages"][1], HumanMessage)

    async def test_system_message_content_matches_constant(self, monkeypatch):
        """전달된 SystemMessage 내용이 _SYSTEM_PROMPT 상수와 일치해야 한다."""
        monkeypatch.setenv("USE_MOCK_LLM", "false")
        captured = self._capture_messages(monkeypatch)

        await _evaluate_quality("# 내용", "doc-sm-03")

        assert captured["messages"][0].content == _SYSTEM_PROMPT

    async def test_system_message_forbids_code_fences(self, monkeypatch):
        """SystemMessage에 코드 블록 출력 금지 지시가 포함되어야 한다."""
        monkeypatch.setenv("USE_MOCK_LLM", "false")
        captured = self._capture_messages(monkeypatch)

        await _evaluate_quality("# 내용", "doc-sm-04")

        assert "코드 블록" in captured["messages"][0].content or "```" in captured["messages"][0].content

    async def test_system_message_requires_json_only(self, monkeypatch):
        """SystemMessage에 JSON만 반환하라는 지시가 포함되어야 한다."""
        monkeypatch.setenv("USE_MOCK_LLM", "false")
        captured = self._capture_messages(monkeypatch)

        await _evaluate_quality("# 내용", "doc-sm-05")

        assert "JSON" in captured["messages"][0].content

    async def test_total_message_count_is_two(self, monkeypatch):
        """LLM 호출 시 메시지 개수가 정확히 2개(System + Human)여야 한다."""
        monkeypatch.setenv("USE_MOCK_LLM", "false")
        captured = self._capture_messages(monkeypatch)

        await _evaluate_quality("# 내용", "doc-sm-06")

        assert len(captured["messages"]) == 2


# ---------------------------------------------------------------------------
# T12: Stage 2 Agent 승격 — retry loop + _apply_targeted_fix (RED → GREEN)
# ---------------------------------------------------------------------------

class TestStage2RetryLoop:
    """stage2_validate가 품질 미달 시 수정 후 재평가하고, 최대 시도 초과 시 HITL로 넘긴다.

    현재 stage2_validate는 단순 1회 평가 후 즉시 HITL — retry 없음.
    _apply_targeted_fix()도 없음.
    """

    def _make_evaluate_quality(self, return_sequence):
        """_evaluate_quality를 호출 순서대로 다른 값을 반환하는 AsyncMock 생성."""
        call_count = {"n": 0}
        async def _mock(*_a, **_kw):
            n = call_count["n"]
            call_count["n"] += 1
            if n < len(return_sequence):
                return return_sequence[n]
            return return_sequence[-1]
        return _mock

    async def test_retry_pass_on_second_attempt(self, monkeypatch):
        """1차 평가 미달 → 수정 적용 → 2차 평가 통과 → hitl_required=False."""
        from module_0_kms.pipeline.stage2_validate_agent import _apply_targeted_fix

        # 1차: score=0.6 (미달), 2차: score=0.9 (통과)
        seq = [(0.6, ["서식 오류"], True), (0.9, [], False)]
        monkeypatch.setattr(
            "kms.pipeline.stage2_validate_agent._evaluate_quality",
            self._make_evaluate_quality(seq),
        )
        monkeypatch.setattr(
            "kms.pipeline.stage2_validate_agent._apply_targeted_fix",
            AsyncMock(return_value="# 수정된 Markdown"),
        )

        result = await stage2_validate(_state(raw_markdown="# 원본"))
        assert result["hitl_required"] is False
        assert result["quality_score"] == 0.9

    async def test_retry_exhausted_triggers_hitl(self, monkeypatch):
        """MAX_FIX_ATTEMPTS 초과 시 HITL로 전환된다."""
        # 모든 시도에서 미달 반환
        monkeypatch.setattr(
            "kms.pipeline.stage2_validate_agent._evaluate_quality",
            self._make_evaluate_quality([(0.5, ["품질 미달"], True)] * 5),
        )
        monkeypatch.setattr(
            "kms.pipeline.stage2_validate_agent._apply_targeted_fix",
            AsyncMock(return_value="# 수정 실패"),
        )
        monkeypatch.setenv("STAGE2_MAX_FIX_ATTEMPTS", "2")

        result = await stage2_validate(_state(raw_markdown="# 원본"))
        assert result["hitl_required"] is True
        assert result["status"] == "hitl_pending"

    async def test_retry_count_respects_env_var(self, monkeypatch):
        """STAGE2_MAX_FIX_ATTEMPTS=1 설정 시 수정 1회 후 HITL."""
        fix_mock = AsyncMock(return_value="# 수정됨")
        monkeypatch.setattr(
            "kms.pipeline.stage2_validate_agent._evaluate_quality",
            self._make_evaluate_quality([(0.5, ["미달"], True)] * 5),
        )
        monkeypatch.setattr(
            "kms.pipeline.stage2_validate_agent._apply_targeted_fix",
            fix_mock,
        )
        monkeypatch.setenv("STAGE2_MAX_FIX_ATTEMPTS", "1")

        result = await stage2_validate(_state(raw_markdown="# 원본"))
        assert result["hitl_required"] is True
        assert fix_mock.call_count == 1  # 1회만 수정 시도

    async def test_fixed_markdown_used_for_reeval(self, monkeypatch):
        """수정된 Markdown이 재평가에 사용되어야 한다."""
        fixed_md = "# 수정된 내용"
        call_args = []

        async def mock_evaluate(markdown, doc_id):
            call_args.append(markdown)
            if len(call_args) == 1:
                return (0.6, ["미달"], True)
            return (0.9, [], False)

        monkeypatch.setattr(
            "kms.pipeline.stage2_validate_agent._evaluate_quality",
            mock_evaluate,
        )
        monkeypatch.setattr(
            "kms.pipeline.stage2_validate_agent._apply_targeted_fix",
            AsyncMock(return_value=fixed_md),
        )

        result = await stage2_validate(_state(raw_markdown="# 원본"))
        assert call_args[1] == fixed_md  # 2차 평가는 수정된 Markdown으로
        assert result["validated_markdown"] == fixed_md


class TestApplyTargetedFix:
    """_apply_targeted_fix — issues에 따른 rule-based tool 선택."""

    async def test_table_issue_calls_post_process(self, monkeypatch):
        """issues에 'table' 포함 시 _post_process_upstage_markdown 호출."""
        from module_0_kms.pipeline.stage2_validate_agent import _apply_targeted_fix

        post_proc_mock = MagicMock(return_value="# 표 수정됨")
        monkeypatch.setattr(
            "kms.pipeline.stage2_validate_agent._post_process_upstage_markdown",
            post_proc_mock,
        )

        result = await _apply_targeted_fix("# 원본", ["표가 소실되었습니다"], {})
        post_proc_mock.assert_called_once()
        assert result == "# 표 수정됨"

    async def test_table_loss_flag_calls_post_process(self, monkeypatch):
        """data에 table_loss=True 포함 시 _post_process_upstage_markdown 호출."""
        from module_0_kms.pipeline.stage2_validate_agent import _apply_targeted_fix

        post_proc_mock = MagicMock(return_value="# 표 수정됨")
        monkeypatch.setattr(
            "kms.pipeline.stage2_validate_agent._post_process_upstage_markdown",
            post_proc_mock,
        )

        result = await _apply_targeted_fix("# 원본", [], {"table_loss": True})
        post_proc_mock.assert_called_once()

    async def test_heading_issue_calls_normalize(self, monkeypatch):
        """issues에 '제목' 포함 시 _normalize_heading_hierarchy 호출."""
        from module_0_kms.pipeline.stage2_validate_agent import _apply_targeted_fix

        norm_mock = MagicMock(return_value="# 헤딩 수정됨")
        monkeypatch.setattr(
            "kms.pipeline.stage2_validate_agent._normalize_heading_hierarchy",
            norm_mock,
        )

        result = await _apply_targeted_fix("# 원본", ["제목 계층이 붕괴됨"], {})
        norm_mock.assert_called_once()
        assert result == "# 헤딩 수정됨"

    async def test_structure_loss_calls_normalize(self, monkeypatch):
        """data에 structure_loss=True 포함 시 _normalize_heading_hierarchy 호출."""
        from module_0_kms.pipeline.stage2_validate_agent import _apply_targeted_fix

        norm_mock = MagicMock(return_value="# 구조 수정됨")
        monkeypatch.setattr(
            "kms.pipeline.stage2_validate_agent._normalize_heading_hierarchy",
            norm_mock,
        )

        result = await _apply_targeted_fix("# 원본", [], {"structure_loss": True})
        norm_mock.assert_called_once()

    async def test_other_issue_calls_gemini_format_correct(self, monkeypatch):
        """기타 이슈는 _gemini_format_correct(LLM 폴백)를 호출한다."""
        from module_0_kms.pipeline.stage2_validate_agent import _apply_targeted_fix

        gemini_mock = AsyncMock(return_value="# Gemini 수정됨")
        monkeypatch.setattr(
            "kms.pipeline.stage2_validate_agent._gemini_format_correct",
            gemini_mock,
        )

        result = await _apply_targeted_fix("# 원본", ["서식 오류"], {})
        gemini_mock.assert_called_once()
        assert result == "# Gemini 수정됨"

    async def test_html_table_in_markdown_calls_post_process(self, monkeypatch):
        """Markdown 본문에 <table이 있으면 이슈 없어도 post_process 호출."""
        from module_0_kms.pipeline.stage2_validate_agent import _apply_targeted_fix

        post_proc_mock = MagicMock(return_value="# 표 수정됨")
        monkeypatch.setattr(
            "kms.pipeline.stage2_validate_agent._post_process_upstage_markdown",
            post_proc_mock,
        )

        result = await _apply_targeted_fix("<table><tr><td>A</td></tr></table>", [], {})
        post_proc_mock.assert_called_once()
