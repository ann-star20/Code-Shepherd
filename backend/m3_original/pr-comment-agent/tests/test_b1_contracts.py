"""B1: contracts.py — CombinedIssue, Verdict, ReviewReport."""
import pytest
from pydantic import ValidationError

from contracts import CombinedIssue, Issue, ReviewReport, ReviewSummary


class TestIssueMirror:
    def test_rag_context_defaults_empty(self):
        """Dev3 미러 Issue도 rag_context 칸이 있어 JSON 파싱 시 안 버려짐."""
        issue = Issue(severity="Minor", file="a.py", message="m", rule_id="r")
        assert issue.rag_context == ""

    def test_rag_context_roundtrip_from_dict(self):
        """Dev3가 보낸 dict에 rag_context 있으면 그대로 유지."""
        issue = Issue.model_validate(
            {"severity": "Major", "file": "a.py", "message": "m",
             "rule_id": "r", "rag_context": "사내 가이드 내용"}
        )
        assert issue.rag_context == "사내 가이드 내용"


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

    def test_rag_context_defaults_empty(self):
        """rag_context 미지정 → 빈 문자열 (검색결과 없음/dormant)."""
        issue = CombinedIssue(severity="Minor", file="a.py", message="m", rule_id="r")
        assert issue.rag_context == ""

    def test_rag_context_accepts_value(self):
        """검색된 사내 가이드를 rag_context로 담을 수 있다 (RAG §6)."""
        issue = CombinedIssue(
            severity="Major",
            file="a.py",
            message="m",
            rule_id="r",
            rag_context="📖 [사내 가이드: ORM](http://kms/orm)\nselectinload 표준",
        )
        assert "selectinload" in issue.rag_context


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
