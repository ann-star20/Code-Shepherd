"""B4: llm_refiner.py — LLM 모드 + 휴리스틱 fallback PR 코멘트 생성."""
from __future__ import annotations

import os
from unittest.mock import patch, MagicMock
import pytest

from contracts import CombinedIssue
import llm_refiner
from llm_refiner import refine


# ── 헬퍼 ──────────────────────────────────────────────────────────────────────

def _make_issue(
    severity: str = "Major",
    rule_id: str = "N+1",
    file: str = "models.py",
    line: int = 42,
    message: str = "N+1 쿼리 감지됨",
    suggestion: str = "select_related 사용 권장",
) -> CombinedIssue:
    return CombinedIssue(
        severity=severity,
        file=file,
        line=line,
        message=message,
        rule_id=rule_id,
        suggestion=suggestion,
    )


# ── 빈 이슈 ───────────────────────────────────────────────────────────────────

class TestEmptyIssues:
    def test_empty_returns_pass_message(self):
        """빈 이슈 목록 → 리뷰 통과 ✅ 메시지."""
        result = refine([], "lgtm", "mid")
        assert "리뷰 통과" in result or "✅" in result

    def test_empty_issues_no_api_call(self):
        """빈 이슈일 때 LLM 호출 없음."""
        with patch.object(llm_refiner, "_call_llm") as mock_llm:
            refine([], "lgtm", "mid")
            mock_llm.assert_not_called()


# ── 휴리스틱 모드 (API 키 없음) ───────────────────────────────────────────────

class TestHeuristicMode:
    """_has_api_key() → False 일 때 마크다운 템플릿 직접 생성."""

    def test_header_contains_verdict(self):
        """헤더에 verdict 포함."""
        with patch.object(llm_refiner, "_has_api_key", return_value=False):
            result = refine([_make_issue()], "rework", "mid")
        assert "rework" in result

    def test_header_has_autorev_emoji(self):
        """'## 🤖 자동 리뷰' 헤더 포함."""
        with patch.object(llm_refiner, "_has_api_key", return_value=False):
            result = refine([_make_issue()], "rework", "mid")
        assert "## 🤖 자동 리뷰" in result

    def test_header_contains_major_count(self):
        """헤더에 'Major 1' 카운트 포함."""
        issue = _make_issue(severity="Major")
        with patch.object(llm_refiner, "_has_api_key", return_value=False):
            result = refine([issue], "rework", "mid")
        assert "Major 1" in result

    def test_header_contains_minor_count(self):
        """헤더에 'Minor N' 카운트 포함."""
        issues = [_make_issue(severity="Minor"), _make_issue(severity="Minor", rule_id="R2", line=10)]
        with patch.object(llm_refiner, "_has_api_key", return_value=False):
            result = refine(issues, "lgtm", "mid")
        assert "Minor 2" in result

    def test_subheader_contains_severity_and_rule_id(self):
        """### {emoji} {severity}: {rule_id} 구조 포함."""
        issue = _make_issue(severity="Major", rule_id="N+1")
        with patch.object(llm_refiner, "_has_api_key", return_value=False):
            result = refine([issue], "rework", "mid")
        assert "Major" in result
        assert "N+1" in result
        assert "###" in result

    def test_subheader_contains_file_and_line(self):
        """서브헤더에 파일명:라인 포함."""
        issue = _make_issue(file="models.py", line=42)
        with patch.object(llm_refiner, "_has_api_key", return_value=False):
            result = refine([issue], "rework", "mid")
        assert "models.py" in result
        assert "42" in result

    def test_suggestion_in_body(self):
        """suggestion이 본문에 포함됨 (💡 접두사)."""
        issue = _make_issue(suggestion="select_related 사용 권장")
        with patch.object(llm_refiner, "_has_api_key", return_value=False):
            result = refine([issue], "rework", "mid")
        assert "select_related 사용 권장" in result
        assert "💡" in result

    def test_message_in_body(self):
        """이슈 message가 본문에 포함됨."""
        issue = _make_issue(message="N+1 쿼리 감지됨")
        with patch.object(llm_refiner, "_has_api_key", return_value=False):
            result = refine([issue], "rework", "mid")
        assert "N+1 쿼리 감지됨" in result

    def test_no_api_key_never_calls_llm(self):
        """키 없음 → _call_llm 절대 호출 안 함."""
        with patch.object(llm_refiner, "_has_api_key", return_value=False):
            with patch.object(llm_refiner, "_call_llm") as mock_llm:
                refine([_make_issue()], "rework", "mid")
                mock_llm.assert_not_called()

    def test_multiple_issues_all_included(self):
        """여러 이슈 → 모두 마크다운에 포함."""
        issues = [
            _make_issue(rule_id="R1", file="a.py", line=1),
            _make_issue(rule_id="R2", file="b.py", line=2, severity="Minor"),
        ]
        with patch.object(llm_refiner, "_has_api_key", return_value=False):
            result = refine(issues, "rework", "mid")
        assert "R1" in result
        assert "R2" in result
        assert "a.py" in result
        assert "b.py" in result


# ── LLM 모드 (API 키 있음) ────────────────────────────────────────────────────

class TestLLMMode:
    """_has_api_key() → True 일 때 _call_llm 호출."""

    def test_llm_called_when_key_present(self):
        """키 있음 → _call_llm 1회 호출."""
        with patch.object(llm_refiner, "_has_api_key", return_value=True):
            with patch.object(llm_refiner, "_call_llm", return_value="## LLM result") as mock_llm:
                result = refine([_make_issue()], "rework", "mid")
                mock_llm.assert_called_once()
                assert result == "## LLM result"

    def test_junior_tone_in_prompt(self):
        """junior 레벨 → 프롬프트에 junior 톤 힌트 포함."""
        with patch.object(llm_refiner, "_has_api_key", return_value=True):
            with patch.object(llm_refiner, "_call_llm", return_value="## ok") as mock_llm:
                refine([_make_issue()], "rework", "junior")
                prompt_arg = mock_llm.call_args[0][0]
                # "junior" 키워드 또는 한국어 힌트 중 하나 포함
                assert (
                    "junior" in prompt_arg.lower()
                    or "자세" in prompt_arg
                    or "예시" in prompt_arg
                )

    def test_senior_tone_in_prompt(self):
        """senior 레벨 → 프롬프트에 senior 톤 힌트 포함."""
        with patch.object(llm_refiner, "_has_api_key", return_value=True):
            with patch.object(llm_refiner, "_call_llm", return_value="## ok") as mock_llm:
                refine([_make_issue()], "rework", "senior")
                prompt_arg = mock_llm.call_args[0][0]
                assert (
                    "senior" in prompt_arg.lower()
                    or "한 줄" in prompt_arg
                    or "요약" in prompt_arg
                )

    def test_mid_tone_in_prompt(self):
        """mid 레벨 → 프롬프트에 mid 톤 힌트 포함."""
        with patch.object(llm_refiner, "_has_api_key", return_value=True):
            with patch.object(llm_refiner, "_call_llm", return_value="## ok") as mock_llm:
                refine([_make_issue()], "rework", "mid")
                prompt_arg = mock_llm.call_args[0][0]
                assert (
                    "mid" in prompt_arg.lower()
                    or "핵심" in prompt_arg
                    or "개선" in prompt_arg
                )

    def test_llm_result_returned_as_is(self):
        """LLM 반환값이 그대로 리턴됨."""
        expected = "## 🤖 자동 리뷰 (rework · Major 1 · Minor 0)\n\nsome content"
        with patch.object(llm_refiner, "_has_api_key", return_value=True):
            with patch.object(llm_refiner, "_call_llm", return_value=expected):
                result = refine([_make_issue()], "rework", "mid")
                assert result == expected


# ── _has_api_key 단위 테스트 ─────────────────────────────────────────────────

class TestHasApiKey:
    def test_no_keys_returns_false(self):
        env = {"OPENAI_API_KEY": "", "ANTHROPIC_API_KEY": "", "GOOGLE_API_KEY": ""}
        with patch.dict(os.environ, env):
            from llm_refiner import _has_api_key
            assert _has_api_key() is False

    def test_only_google_key_counts(self):
        # Gemini로 통일: OpenAI/Anthropic 키가 있어도 GOOGLE 없으면 False
        env = {"OPENAI_API_KEY": "sk-test", "ANTHROPIC_API_KEY": "ant-test", "GOOGLE_API_KEY": ""}
        with patch.dict(os.environ, env):
            from llm_refiner import _has_api_key
            assert _has_api_key() is False

    def test_google_key_returns_true(self):
        env = {"GOOGLE_API_KEY": "goog-test"}
        with patch.dict(os.environ, env):
            from llm_refiner import _has_api_key
            assert _has_api_key() is True
