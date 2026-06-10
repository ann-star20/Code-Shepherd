"""B4 / 7C: llm_refiner.py — '리뷰 판정 + 이슈 표' 코멘트 생성.

확정된 코멘트 모양 (LLM 모드·휴리스틱 모드 둘 다 동일 구조):
  1) 헤더: 🤖 코드 리뷰 — verdict 라벨 + 왜(한 줄) + severity 카운트
  2) 이슈 표: | 심각도 | 규칙 | 위치 | 고칠 방향(suggestion) | 사내 규칙(rag_context|—) |
  3) 맨 아래: 리뷰 대시보드 링크 한 줄(환경값/localhost)

LLM 은 '왜(한 줄)'만 생성(_call_llm mock). 실패·429·빈 응답 → 휴리스틱 한 줄로 fallback,
구조(표·📖·대시보드)는 항상 코드가 결정한다.
"""
from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest

import llm_refiner
from contracts import CombinedIssue
from llm_refiner import refine


# ── 헬퍼 ──────────────────────────────────────────────────────────────────────

def _make_issue(
    severity: str = "Major",
    rule_id: str = "N+1",
    file: str = "models.py",
    line: int | None = 42,
    message: str = "N+1 쿼리 감지됨",
    suggestion: str = "select_related 사용 권장",
    rag_context: str = "",
) -> CombinedIssue:
    return CombinedIssue(
        severity=severity,
        file=file,
        line=line,
        message=message,
        rule_id=rule_id,
        suggestion=suggestion,
        rag_context=rag_context,
    )


def _no_key():
    return patch.object(llm_refiner, "_has_api_key", return_value=False)


# ── 빈 이슈 ───────────────────────────────────────────────────────────────────

class TestEmptyIssues:
    def test_empty_returns_pass_message(self):
        result = refine([], "lgtm", "mid")
        assert "리뷰 통과" in result or "✅" in result

    def test_empty_issues_no_api_call(self):
        with patch.object(llm_refiner, "_call_llm") as mock_llm:
            refine([], "lgtm", "mid")
            mock_llm.assert_not_called()


# ── 헤더: 🤖 + verdict 라벨 + severity 카운트 ─────────────────────────────────

class TestHeader:
    def test_header_has_robot_review(self):
        with _no_key():
            result = refine([_make_issue()], "rework", "mid")
        assert "## 🤖 코드 리뷰" in result

    @pytest.mark.parametrize("verdict,marker", [
        ("lgtm", "통과"),
        ("rework", "수정"),
        ("escalate", "시니어"),
    ])
    def test_header_per_verdict(self, verdict, marker):
        """verdict 별 헤더 라벨 + 원시 verdict 문자열 둘 다 포함."""
        with _no_key():
            result = refine([_make_issue()], verdict, "mid")
        assert marker in result
        assert verdict in result  # 원시 verdict(소문자)도 남긴다

    def test_severity_counts_major(self):
        with _no_key():
            result = refine([_make_issue(severity="Major")], "rework", "mid")
        assert "Major 1" in result

    def test_severity_counts_minor(self):
        issues = [_make_issue(severity="Minor"),
                  _make_issue(severity="Minor", rule_id="R2", line=10)]
        with _no_key():
            result = refine(issues, "lgtm", "mid")
        assert "Minor 2" in result


# ── 이슈 표 ───────────────────────────────────────────────────────────────────

class TestIssueTable:
    def test_table_header_and_separator(self):
        with _no_key():
            result = refine([_make_issue()], "rework", "mid")
        assert "| 심각도 | 규칙 | 위치 | 고칠 방향 | 사내 규칙 |" in result
        assert "|---|---|---|---|---|" in result

    def test_row_has_emoji_rule_loc_suggestion(self):
        issue = _make_issue(severity="Major", rule_id="N+1",
                            file="models.py", line=42,
                            suggestion="select_related 사용 권장")
        with _no_key():
            result = refine([issue], "rework", "mid")
        assert "🟡" in result            # Major 이모지
        assert "N+1" in result
        assert "models.py:42" in result   # file:line
        assert "select_related 사용 권장" in result  # 고칠 방향=suggestion

    def test_location_without_line(self):
        issue = _make_issue(file="conf.yaml", line=None)
        with _no_key():
            result = refine([issue], "rework", "mid")
        assert "conf.yaml" in result
        assert "conf.yaml:None" not in result  # line 없으면 :None 금지

    def test_multiple_issues_all_rows(self):
        issues = [
            _make_issue(rule_id="R1", file="a.py", line=1),
            _make_issue(rule_id="R2", file="b.py", line=2, severity="Minor"),
        ]
        with _no_key():
            result = refine(issues, "rework", "mid")
        assert "R1" in result and "a.py:1" in result
        assert "R2" in result and "b.py:2" in result
        # 데이터 행(이모지로 시작하는 표 행) 2개
        data_rows = [ln for ln in result.splitlines()
                     if ln.startswith("| ") and ("🟡" in ln or "🔵" in ln or "🔴" in ln)]
        assert len(data_rows) == 2


# ── 사내 규칙 칸: rag_context 인용 / 없으면 — / 가짜 링크 금지 ─────────────────

class TestRagContextCell:
    def test_rag_context_quoted_in_cell(self):
        """① rag_context 있으면 '사내 규칙' 칸에 인용(+링크)이 들어간다."""
        issue = _make_issue(rag_context="📖 [DB 접근 규칙](http://wiki/db) selectinload 표준")
        with _no_key():
            result = refine([issue], "rework", "junior")
        assert "selectinload 표준" in result
        assert "(http://wiki/db)" in result  # 있는 링크는 보존

    def test_no_rag_context_shows_dash(self):
        """② rag_context 없으면 '—'."""
        issue = _make_issue(rag_context="")
        with _no_key():
            result = refine([issue], "rework", "mid")
        # 표 데이터 행의 마지막 칸이 — 로 끝난다
        data_row = next(ln for ln in result.splitlines()
                        if ln.startswith("| ") and "N+1" in ln)
        assert data_row.rstrip().endswith("— |")

    def test_no_fake_link_when_source_url_absent(self):
        """source_url 없는 rag_context(텍스트만) → 가짜 링크 만들지 않는다."""
        issue = _make_issue(rag_context="📖 사내 ORM 가이드 본문 텍스트")
        with _no_key():
            result = refine([issue], "rework", "mid")
        assert "사내 ORM 가이드 본문 텍스트" in result
        assert "http" not in result.replace(llm_refiner._dashboard_url(), "")  # 대시보드 링크 외 URL 없음

    def test_newlines_flattened_in_cell(self):
        """rag_context 개행 → <br> 로 평탄화(표 깨짐 방지)."""
        issue = _make_issue(rag_context="📖 제목\n본문 한 줄\n또 한 줄")
        with _no_key():
            result = refine([issue], "rework", "mid")
        data_row = next(ln for ln in result.splitlines()
                        if ln.startswith("| ") and "N+1" in ln)
        assert "\n" not in data_row.strip("\n")  # 행은 한 줄
        assert "<br>" in data_row

    def test_pipe_escaped_in_cell(self):
        """rag_context 내 파이프 → 이스케이프(표 컬럼 깨짐 방지)."""
        issue = _make_issue(rag_context="규칙 A | 규칙 B")
        with _no_key():
            result = refine([issue], "rework", "mid")
        assert "규칙 A \\| 규칙 B" in result


# ── 대시보드 링크 (환경값/localhost, 하드코딩 가짜 도메인 금지) ────────────────

class TestDashboardFooter:
    def test_footer_present_default_localhost(self, monkeypatch):
        monkeypatch.delenv("REVIEW_DASHBOARD_URL", raising=False)
        with _no_key():
            result = refine([_make_issue()], "rework", "mid")
        assert "📊" in result
        assert "http://localhost:5173/review" in result

    def test_footer_uses_env_url(self, monkeypatch):
        monkeypatch.setenv("REVIEW_DASHBOARD_URL", "http://demo.internal/review")
        with _no_key():
            result = refine([_make_issue()], "rework", "mid")
        assert "http://demo.internal/review" in result
        assert "localhost" not in result


# ── LLM 모드: '왜 한 줄'만 LLM, 구조는 코드가 결정 ────────────────────────────

class TestLLMMode:
    def test_llm_called_once_for_why(self):
        with patch.object(llm_refiner, "_has_api_key", return_value=True), \
             patch.object(llm_refiner, "_call_llm", return_value="한 줄 이유") as mock_llm:
            refine([_make_issue()], "rework", "mid")
            mock_llm.assert_called_once()

    def test_llm_why_appears_in_header(self):
        why = "이 PR은 N+1 위험이 있어 수정이 필요합니다"
        with patch.object(llm_refiner, "_has_api_key", return_value=True), \
             patch.object(llm_refiner, "_call_llm", return_value=why):
            result = refine([_make_issue()], "rework", "junior")
        assert why in result

    def test_llm_mode_still_renders_table_and_footer(self):
        """LLM 모드도 휴리스틱과 '같은 구조'(표·📖·대시보드)."""
        issue = _make_issue(rag_context="📖 [규칙](http://w) 인용")
        with patch.object(llm_refiner, "_has_api_key", return_value=True), \
             patch.object(llm_refiner, "_call_llm", return_value="한 줄"):
            result = refine([issue], "rework", "mid")
        assert "| 심각도 | 규칙 | 위치 | 고칠 방향 | 사내 규칙 |" in result
        assert "인용" in result
        assert "📊" in result

    @pytest.mark.parametrize("skill", ["junior", "mid", "senior"])
    def test_skill_level_in_prompt(self, skill):
        with patch.object(llm_refiner, "_has_api_key", return_value=True), \
             patch.object(llm_refiner, "_call_llm", return_value="x") as mock_llm:
            refine([_make_issue()], "rework", skill)
            prompt = mock_llm.call_args[0][0]
        assert skill in prompt.lower()

    def test_llm_failure_falls_back_to_heuristic_structure(self):
        """LLM 예외 → 예외 전파 없이 휴리스틱 한 줄 + 같은 표 구조."""
        with patch.object(llm_refiner, "_has_api_key", return_value=True), \
             patch.object(llm_refiner, "_call_llm", side_effect=RuntimeError("network")):
            result = refine([_make_issue()], "rework", "mid")
        assert "| 심각도 | 규칙 | 위치 | 고칠 방향 | 사내 규칙 |" in result
        assert "📊" in result

    def test_llm_quota_429_falls_back(self):
        with patch.object(llm_refiner, "_has_api_key", return_value=True), \
             patch.object(llm_refiner, "_call_llm",
                          side_effect=Exception("429 Resource exhausted")):
            result = refine([_make_issue(rag_context="📖 가이드")], "rework", "mid")
        assert "## 🤖 코드 리뷰" in result
        assert "가이드" in result  # 표/📖 구조 유지
        assert "📊" in result

    def test_llm_empty_response_falls_back(self):
        with patch.object(llm_refiner, "_has_api_key", return_value=True), \
             patch.object(llm_refiner, "_call_llm", return_value="   "):
            result = refine([_make_issue()], "rework", "mid")
        assert "| 심각도 | 규칙 | 위치 | 고칠 방향 | 사내 규칙 |" in result


# ── _heuristic_refine 직접 호출 계약 (main.py fallback 경로) ──────────────────

class TestHeuristicRefineDirect:
    def test_heuristic_refine_renders_table(self):
        result = llm_refiner._heuristic_refine([_make_issue(rag_context="📖 가이드")], "rework")
        assert "## 🤖 코드 리뷰" in result
        assert "| 심각도 | 규칙 | 위치 | 고칠 방향 | 사내 규칙 |" in result
        assert "가이드" in result
        assert "📊" in result

    def test_heuristic_refine_empty_pass(self):
        result = llm_refiner._heuristic_refine([], "lgtm")
        assert "리뷰 통과" in result or "✅" in result


# ── 📊 지표 줄 (커버리지·복잡도) — 7D ──────────────────────────────────────────
# 측정값(metrics)이 있을 때만 헤더 아래 한 줄. 없으면 생략(가짜 숫자 금지).
# metrics 는 additive 키워드 인자(기본 None) — 기존 호출(표·📖·대시보드)은 회귀 0.

class TestMetricsLine:
    def test_coverage_only_renders_line(self):
        with _no_key():
            result = refine([_make_issue()], "rework", "mid", metrics={"coverage_pct": 72})
        assert "📊 커버리지 72%" in result

    def test_coverage_and_complexity_one_line(self):
        with _no_key():
            result = refine([_make_issue()], "rework", "mid",
                            metrics={"coverage_pct": 72, "max_complexity": 3})
        assert "📊 커버리지 72% · 최대 복잡도 3" in result

    def test_complexity_only_renders_line(self):
        """coverage 없고 complexity 만 있어도 그 부분만 정직하게 — (forward-compatible)."""
        with _no_key():
            result = refine([_make_issue()], "rework", "mid", metrics={"max_complexity": 4})
        assert "📊 최대 복잡도 4" in result
        assert "커버리지" not in result

    def test_no_metrics_omits_line(self):
        with _no_key():
            result = refine([_make_issue()], "rework", "mid")
        assert "커버리지" not in result
        assert "최대 복잡도" not in result

    def test_empty_metrics_omits_line(self):
        with _no_key():
            result = refine([_make_issue()], "rework", "mid", metrics={})
        assert "커버리지" not in result
        assert "최대 복잡도" not in result

    def test_metric_line_above_table(self):
        """지표 줄은 표보다 위(헤더 아래)에 온다 — 7C 표 구조 회귀 0."""
        with _no_key():
            result = refine([_make_issue()], "rework", "mid", metrics={"coverage_pct": 72})
        lines = result.splitlines()
        cov_idx = next(i for i, ln in enumerate(lines) if "커버리지 72%" in ln)
        tbl_idx = next(i for i, ln in enumerate(lines) if ln.startswith("| 심각도"))
        assert cov_idx < tbl_idx

    def test_metric_line_in_heuristic_direct(self):
        """_heuristic_refine(main.py fallback 경로)도 metrics 받으면 지표 줄을 낸다."""
        result = llm_refiner._heuristic_refine(
            [_make_issue()], "rework", metrics={"coverage_pct": 80}
        )
        assert "📊 커버리지 80%" in result


# ── _call_llm — 신 SDK(google.genai) 세임 테스트 (8-0a) ──────────────────────────

class TestCallLlmNewSDK:
    def test_call_llm_uses_genai_client(self, monkeypatch):
        """_call_llm: genai.Client(api_key=...) 호출 → client.models.generate_content → response.text 반환."""
        monkeypatch.setenv("GOOGLE_API_KEY", "test-key-abc")
        mock_resp = MagicMock()
        mock_resp.text = "N+1 쿼리 패턴으로 인해 수정이 필요합니다"
        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = mock_resp

        with patch("google.genai.Client", return_value=mock_client) as MockClient:
            result = llm_refiner._call_llm("테스트 프롬프트")

        MockClient.assert_called_once_with(api_key="test-key-abc")
        mock_client.models.generate_content.assert_called_once()
        call_kwargs = mock_client.models.generate_content.call_args
        assert call_kwargs.kwargs.get("contents") == "테스트 프롬프트"
        assert result == "N+1 쿼리 패턴으로 인해 수정이 필요합니다"

    def test_call_llm_no_key_returns_empty(self, monkeypatch):
        """GOOGLE_API_KEY 없으면 _call_llm은 '' 반환 (LLM 호출 없음)."""
        monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
        result = llm_refiner._call_llm("어떤 프롬프트")
        assert result == ""

    def test_call_llm_sdk_exception_propagates(self, monkeypatch):
        """SDK 예외는 _call_llm 밖으로 전파 → _llm_why가 잡아 '' 반환."""
        monkeypatch.setenv("GOOGLE_API_KEY", "test-key")
        with patch("google.genai.Client", side_effect=RuntimeError("network error")):
            result = llm_refiner._llm_why(
                [CombinedIssue(severity="Major", file="f.py", line=1,
                               message="m", rule_id="R", suggestion="s")],
                "rework", "mid",
            )
        assert result == ""  # 예외 → 빈 문자열 → heuristic fallback


# ── _has_api_key 단위 테스트 (보존) ───────────────────────────────────────────

class TestHasApiKey:
    def test_no_keys_returns_false(self):
        with patch.dict(os.environ, {"GOOGLE_API_KEY": ""}):
            assert llm_refiner._has_api_key() is False

    def test_only_google_key_counts(self):
        env = {"OPENAI_API_KEY": "sk-test", "ANTHROPIC_API_KEY": "ant-test", "GOOGLE_API_KEY": ""}
        with patch.dict(os.environ, env):
            assert llm_refiner._has_api_key() is False

    def test_google_key_returns_true(self):
        with patch.dict(os.environ, {"GOOGLE_API_KEY": "goog-test"}):
            assert llm_refiner._has_api_key() is True
