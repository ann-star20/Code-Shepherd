"""B6: main.py — aggregator → llm_refiner → github_poster 오케스트레이션."""
from __future__ import annotations

from unittest.mock import patch, MagicMock
import pytest

from contracts import AgentOutput, CombinedIssue, Developer, Issue, ReviewReport, SummaryCount


# ── 헬퍼 ──────────────────────────────────────────────────────────────────────

def _make_output(
    agent: str = "static_security",
    scan_id: int = 1,
    pr_id: str = "PR-001",
    issues: list | None = None,
) -> AgentOutput:
    return AgentOutput(
        task_id=f"task-{agent}",
        scan_id=scan_id,
        pr_id=pr_id,
        agent=agent,
        issues=issues or [],
    )


def _make_issue(severity: str = "Major", rule_id: str = "R1", file: str = "a.py", line: int = 1) -> Issue:
    return Issue(
        severity=severity,
        file=file,
        line=line,
        message="test issue",
        rule_id=rule_id,
        suggestion="fix it",
    )


PR_URL = "https://github.com/acme/repo/pull/1"
DEV = Developer(name="alice", skill_level="mid")


# ── 정상 흐름 ─────────────────────────────────────────────────────────────────

class TestNormalFlow:
    """aggregator → llm_refiner → github_poster 각 1회 호출, ReviewReport 반환."""

    def test_aggregator_called_once(self):
        """aggregate() 정확히 1회 호출됨."""
        import main
        outputs = [_make_output()]
        agg_result = ([], "lgtm", SummaryCount())

        with patch.object(main, "aggregate", return_value=agg_result) as mock_agg, \
             patch.object(main, "refine", return_value="## ok"), \
             patch.object(main, "post_comment", return_value={"mode": "dry_run", "path": "x"}):
            main.run_review(outputs, DEV, PR_URL)
            mock_agg.assert_called_once_with(outputs)

    def test_refine_called_once_with_correct_args(self):
        """refine(issues, verdict, skill_level) 1회 호출."""
        import main
        issues = [CombinedIssue(severity="Major", file="a.py", line=1, message="m", rule_id="R")]
        agg_result = (issues, "rework", SummaryCount(major=1))

        with patch.object(main, "aggregate", return_value=agg_result), \
             patch.object(main, "refine", return_value="## md") as mock_ref, \
             patch.object(main, "post_comment", return_value={"mode": "dry_run", "path": "x"}):
            main.run_review([_make_output()], DEV, PR_URL)
            mock_ref.assert_called_once_with(issues, "rework", DEV.skill_level)

    def test_post_comment_called_once(self):
        """post_comment(pr_url, comment_md) 1회 호출."""
        import main
        agg_result = ([], "lgtm", SummaryCount())

        with patch.object(main, "aggregate", return_value=agg_result), \
             patch.object(main, "refine", return_value="## review") as _, \
             patch.object(main, "post_comment", return_value={"mode": "dry_run", "path": "x"}) as mock_post:
            main.run_review([_make_output()], DEV, PR_URL)
            mock_post.assert_called_once_with(PR_URL, "## review")

    def test_returns_review_report(self):
        """반환값이 ReviewReport 인스턴스."""
        import main
        agg_result = ([], "lgtm", SummaryCount())

        with patch.object(main, "aggregate", return_value=agg_result), \
             patch.object(main, "refine", return_value="## lgtm"), \
             patch.object(main, "post_comment", return_value={"mode": "dry_run", "path": "x"}):
            result = main.run_review([_make_output()], DEV, PR_URL)
            assert isinstance(result, ReviewReport)

    def test_gh_response_stored_in_report(self):
        """gh_response가 ReviewReport.gh_response에 저장됨."""
        import main
        agg_result = ([], "lgtm", SummaryCount())
        gh_resp = {"mode": "dry_run", "path": ".dry_run_comments/PR-1.md"}

        with patch.object(main, "aggregate", return_value=agg_result), \
             patch.object(main, "refine", return_value="## ok"), \
             patch.object(main, "post_comment", return_value=gh_resp):
            result = main.run_review([_make_output()], DEV, PR_URL)
            assert result.gh_response == gh_resp


# ── escalate → escalation_needed ─────────────────────────────────────────────

class TestEscalate:
    def test_escalate_verdict_sets_escalation_needed(self):
        """verdict=escalate → ReviewReport.escalation_needed=True."""
        import main
        critical_issue = CombinedIssue(
            severity="Critical", file="a.py", line=1, message="crit", rule_id="C1"
        )
        agg_result = ([critical_issue], "escalate", SummaryCount(critical=1))

        with patch.object(main, "aggregate", return_value=agg_result), \
             patch.object(main, "refine", return_value="## escalate"), \
             patch.object(main, "post_comment", return_value={"mode": "dry_run", "path": "x"}):
            result = main.run_review([_make_output()], DEV, PR_URL)
            assert result.escalation_needed is True

    def test_lgtm_verdict_escalation_false(self):
        """verdict=lgtm → escalation_needed=False."""
        import main
        agg_result = ([], "lgtm", SummaryCount())

        with patch.object(main, "aggregate", return_value=agg_result), \
             patch.object(main, "refine", return_value="## lgtm"), \
             patch.object(main, "post_comment", return_value={"mode": "dry_run", "path": "x"}):
            result = main.run_review([_make_output()], DEV, PR_URL)
            assert result.escalation_needed is False


# ── LLM 실패 → 휴리스틱 폴백 ─────────────────────────────────────────────────

class TestLLMFailureFallback:
    """refine()이 예외를 던져도 흐름이 끊기지 않고 휴리스틱 fallback으로 계속된다."""

    def test_llm_failure_does_not_raise(self):
        """refine() 예외 → 전체 run_review가 예외 없이 완료."""
        import main
        agg_result = ([], "lgtm", SummaryCount())

        with patch.object(main, "aggregate", return_value=agg_result), \
             patch.object(main, "refine", side_effect=RuntimeError("LLM timeout")), \
             patch.object(main, "post_comment", return_value={"mode": "dry_run", "path": "x"}):
            result = main.run_review([_make_output()], DEV, PR_URL)
            assert isinstance(result, ReviewReport)

    def test_llm_failure_comment_md_not_empty(self):
        """LLM 실패 후 휴리스틱 폴백 → comment_md가 빈 문자열이 아님."""
        import main
        issues = [CombinedIssue(severity="Major", file="a.py", line=5, message="msg", rule_id="R1")]
        agg_result = (issues, "rework", SummaryCount(major=1))

        with patch.object(main, "aggregate", return_value=agg_result), \
             patch.object(main, "refine", side_effect=Exception("API error")), \
             patch.object(main, "post_comment", return_value={"mode": "dry_run", "path": "x"}):
            result = main.run_review([_make_output()], DEV, PR_URL)
            assert result.comment_md != ""

    def test_llm_failure_post_still_called(self):
        """LLM 실패 후에도 post_comment는 호출됨 (흐름 계속)."""
        import main
        agg_result = ([], "lgtm", SummaryCount())

        with patch.object(main, "aggregate", return_value=agg_result), \
             patch.object(main, "refine", side_effect=Exception("timeout")), \
             patch.object(main, "post_comment", return_value={"mode": "dry_run", "path": "x"}) as mock_post:
            main.run_review([_make_output()], DEV, PR_URL)
            mock_post.assert_called_once()


# ── GitHub 실패 → 에러 전파 ──────────────────────────────────────────────────

class TestGithubFailure:
    """post_comment()가 GithubPosterError를 던지면 run_review도 에러를 전파한다."""

    def test_github_error_propagates(self):
        """post_comment() 예외 → run_review에서 동일 예외 전파."""
        import main
        from github_poster import GithubPosterError
        agg_result = ([], "lgtm", SummaryCount())

        with patch.object(main, "aggregate", return_value=agg_result), \
             patch.object(main, "refine", return_value="## ok"), \
             patch.object(main, "post_comment", side_effect=GithubPosterError("401")):
            with pytest.raises(GithubPosterError):
                main.run_review([_make_output()], DEV, PR_URL)
