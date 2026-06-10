"""SESSION 8C — '왜 한 줄' LLM-as-judge 채점기 (TDD).

judge 모델 호출(_call_judge)은 seam 으로 분리 → mock 으로 검증(실 LLM 미사용).
루브릭 4축(1~5): consistency(판정 정합성) / actionable(도움됨) /
tone(skill_level 적합) / no_hallucination(환각 없음).
LLM 미가용(빈 응답·파싱 실패) → 해당 케이스 skip(가짜 점수 금지).
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from validation import comment_judge
from validation.comment_judge import (
    JUDGE_RUBRIC,
    build_judge_prompt,
    judge_one,
    make_judge_cases,
    parse_judge,
    score_comments,
)

_AXES = ("consistency", "actionable", "tone", "no_hallucination")


def _case(why="N+1 위험이 있어 수정이 필요합니다", verdict="rework",
          skill="mid", summary="[Major] PERF-002 (models.py:42): select_related 권장",
          name="c"):
    return {"name": name, "why": why, "verdict": verdict,
            "skill_level": skill, "issues_summary": summary}


def _fake_scores(c=5, a=5, t=5, h=5, reason="ok"):
    import json
    return json.dumps({"consistency": c, "actionable": a, "tone": t,
                       "no_hallucination": h, "reason": reason}, ensure_ascii=False)


# ── 루브릭/프롬프트 (재현·검증 가능하게 명시) ─────────────────────────────────

class TestRubricAndPrompt:
    def test_rubric_has_four_axes(self):
        for axis in _AXES:
            assert axis in JUDGE_RUBRIC

    def test_prompt_embeds_rubric_axes(self):
        p = build_judge_prompt(**{k: v for k, v in _case().items() if k != "name"})
        for axis in _AXES:
            assert axis in p

    def test_prompt_includes_why_and_verdict_and_skill(self):
        c = _case(why="고유한한줄텍스트XYZ", verdict="escalate", skill="junior")
        p = build_judge_prompt(why=c["why"], verdict=c["verdict"],
                               skill_level=c["skill_level"], issues_summary=c["issues_summary"])
        assert "고유한한줄텍스트XYZ" in p
        assert "escalate" in p
        assert "junior" in p

    def test_prompt_asks_for_json(self):
        p = build_judge_prompt(why="x", verdict="rework", skill_level="mid", issues_summary="s")
        assert "JSON" in p or "json" in p


# ── parse_judge: JSON 점수 파싱 + 견고성 ──────────────────────────────────────

class TestParseJudge:
    def test_parses_plain_json(self):
        out = parse_judge(_fake_scores(5, 4, 3, 2, "reason text"))
        assert out["consistency"] == 5 and out["actionable"] == 4
        assert out["tone"] == 3 and out["no_hallucination"] == 2
        assert out["reason"] == "reason text"

    def test_parses_fenced_json(self):
        raw = "```json\n" + _fake_scores(4, 4, 4, 4) + "\n```"
        assert parse_judge(raw)["consistency"] == 4

    def test_parses_json_with_trailing_prose(self):
        raw = _fake_scores(3, 3, 3, 3) + "\n\n위 점수는 루브릭 기준입니다."
        assert parse_judge(raw)["tone"] == 3

    def test_clamps_out_of_range(self):
        out = parse_judge(_fake_scores(9, 0, 5, 1))
        assert out["consistency"] == 5  # 9 → 5
        assert out["actionable"] == 1   # 0 → 1

    def test_missing_axis_returns_none(self):
        import json
        raw = json.dumps({"consistency": 5, "actionable": 5, "tone": 5})  # no_hallucination 누락
        assert parse_judge(raw) is None

    def test_empty_returns_none(self):
        assert parse_judge("") is None
        assert parse_judge("   ") is None

    def test_garbage_returns_none(self):
        assert parse_judge("점수를 매길 수 없습니다") is None


# ── judge_one: seam mock → 점수 / 빈 응답 → skip ──────────────────────────────

class TestJudgeOne:
    def test_returns_scores_on_valid_response(self):
        with patch.object(comment_judge, "_call_judge", return_value=_fake_scores(5, 4, 5, 4)):
            out = judge_one(_case())
        assert out["actionable"] == 4

    def test_empty_response_is_skip(self):
        with patch.object(comment_judge, "_call_judge", return_value=""):
            assert judge_one(_case()) is None

    def test_call_judge_exception_is_skip(self):
        with patch.object(comment_judge, "_call_judge", side_effect=Exception("429")):
            assert judge_one(_case()) is None


# ── score_comments: 집계(항목별 평균·전체·낮은점수·skip) ──────────────────────

class TestScoreComments:
    def test_aggregates_per_axis_and_overall(self):
        cases = [_case(name="hi"), _case(name="lo")]
        responses = [_fake_scores(5, 5, 5, 5), _fake_scores(3, 1, 3, 3)]
        with patch.object(comment_judge, "_call_judge", side_effect=responses):
            result = score_comments(cases)
        assert result["scored"] == 2
        assert result["skipped"] == 0
        assert result["per_axis"]["consistency"] == 4.0   # (5+3)/2
        assert result["per_axis"]["actionable"] == 3.0     # (5+1)/2
        assert result["overall"] == 3.75                   # (4+3+4+4)/4

    def test_low_score_cases_flagged(self):
        cases = [_case(name="hi"), _case(name="lo")]
        responses = [_fake_scores(5, 5, 5, 5), _fake_scores(3, 1, 3, 3)]
        with patch.object(comment_judge, "_call_judge", side_effect=responses):
            result = score_comments(cases)
        low_names = [r["name"] for r in result["low_scores"]]
        assert "lo" in low_names      # actionable=1 ≤ 2
        assert "hi" not in low_names

    def test_skip_counted_and_excluded_from_avg(self):
        cases = [_case(name="ok"), _case(name="skipme")]
        responses = [_fake_scores(4, 4, 4, 4), ""]   # 2번째 빈 응답 → skip
        with patch.object(comment_judge, "_call_judge", side_effect=responses):
            result = score_comments(cases)
        assert result["scored"] == 1
        assert result["skipped"] == 1
        assert result["per_axis"]["consistency"] == 4.0  # skip 제외 평균
        assert result["status"] == "ok"

    def test_all_skipped_status_skip(self):
        cases = [_case(name="a"), _case(name="b")]
        with patch.object(comment_judge, "_call_judge", return_value=""):
            result = score_comments(cases)
        assert result["scored"] == 0
        assert result["status"] == "skip"
        assert result["skip_reason"]


# ── _call_judge seam: 모델 교체 가능(JUDGE_MODEL) + genai 호출 ─────────────────

class TestCallJudgeSeam:
    def test_uses_judge_model_env_and_genai(self, monkeypatch):
        monkeypatch.setenv("GOOGLE_API_KEY", "k")
        monkeypatch.setenv("JUDGE_MODEL", "gemini-test-judge")
        mock_resp = MagicMock()
        mock_resp.text = _fake_scores()
        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = mock_resp
        with patch("google.genai.Client", return_value=mock_client) as MockClient:
            out = comment_judge._call_judge("프롬프트")
        MockClient.assert_called_once_with(api_key="k")
        kwargs = mock_client.models.generate_content.call_args.kwargs
        assert kwargs.get("model") == "gemini-test-judge"
        assert kwargs.get("contents") == "프롬프트"
        assert out == mock_resp.text

    def test_no_key_returns_empty(self, monkeypatch):
        monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
        assert comment_judge._call_judge("p") == ""


# ── 적은-케이스 모드(무료쿼터용): max_cases 슬라이스 + 대표성 ─────────────────
# _has_api_key=False 로 패치 → 생성이 휴리스틱(실 LLM 호출 0)이라 쿼터 무관하게 검증.

class TestSmallMode:
    def test_respects_max_cases(self):
        with patch("llm_refiner._has_api_key", return_value=False):
            assert len(make_judge_cases(max_cases=5)) == 5
            assert len(make_judge_cases(max_cases=3)) == 3

    def test_default_at_least_ten(self):
        with patch("llm_refiner._has_api_key", return_value=False):
            assert len(make_judge_cases()) >= 10

    def test_small_slice_covers_all_three_verdicts(self):
        """앞 5건이 lgtm/rework/escalate 를 모두 덮어야(발표 대표성)."""
        with patch("llm_refiner._has_api_key", return_value=False):
            cases = make_judge_cases(max_cases=5)
        assert {c["verdict"] for c in cases} == {"lgtm", "rework", "escalate"}

    def test_small_slice_covers_all_skill_levels(self):
        with patch("llm_refiner._has_api_key", return_value=False):
            cases = make_judge_cases(max_cases=5)
        assert {c["skill_level"] for c in cases} == {"junior", "mid", "senior"}
