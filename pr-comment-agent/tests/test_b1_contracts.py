"""B1: contracts.py — CombinedIssue, Verdict, ReviewReport."""
import pytest
from pydantic import ValidationError

from contracts import CombinedIssue, ReviewReport, ReviewSummary


class TestCombinedIssue:
    def test_normal_creation(self):
        issue = CombinedIssue(
            severity="Critical",
            file="app/main.py",
            line=42,
            message="SQL injection risk",
            rule_id="S001",
        )
        assert issue.severity == "Critical"
        assert issue.file == "app/main.py"
        assert issue.rule_id == "S001"
        assert issue.line == 42

    def test_optional_line(self):
        issue = CombinedIssue(severity="Minor", file="a.py", message="m", rule_id="r")
        assert issue.line is None

    def test_invalid_severity_raises(self):
        with pytest.raises(ValidationError):
            CombinedIssue(severity="High", file="f.py", message="m", rule_id="r")


class TestReviewReport:
    def test_normal_creation(self):
        report = ReviewReport(
            verdict="lgtm",
            summary=ReviewSummary(),
            comment_md="LGTM!",
        )
        assert report.verdict == "lgtm"
        assert report.comment_md == "LGTM!"
        assert report.escalation_needed is False

    def test_invalid_verdict_raises_validation_error(self):
        with pytest.raises(ValidationError):
            ReviewReport(verdict="reject", summary=ReviewSummary())

    def test_escalation_needed_auto_set_when_verdict_is_escalate(self):
        report = ReviewReport(
            verdict="escalate",
            summary=ReviewSummary(critical=1),
        )
        assert report.escalation_needed is True

    def test_escalation_needed_false_for_lgtm_and_rework(self):
        for v in ("lgtm", "rework"):
            report = ReviewReport(verdict=v, summary=ReviewSummary())
            assert report.escalation_needed is False

    def test_summary_auto_computed_from_issues(self):
        issues = [
            CombinedIssue(severity="Critical", file="a.py", line=1, message="m1", rule_id="r1"),
            CombinedIssue(severity="Major", file="b.py", line=2, message="m2", rule_id="r2"),
            CombinedIssue(severity="Minor", file="c.py", line=3, message="m3", rule_id="r3"),
            CombinedIssue(severity="Minor", file="d.py", line=4, message="m4", rule_id="r4"),
        ]
        report = ReviewReport(verdict="escalate", issues=issues)
        assert report.summary.critical == 1
        assert report.summary.major == 1
        assert report.summary.minor == 2
