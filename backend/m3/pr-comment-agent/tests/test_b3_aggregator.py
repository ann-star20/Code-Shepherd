"""B3: aggregator.py — verdict 판정 + 중복제거 + scan_id 검증."""
import pytest

from aggregator import aggregate
from contracts import AgentOutput, Issue, SummaryCount


def _make_output(
    scan_id: int = 1,
    pr_id: str = "pr-1",
    agent: str = "test_verification",
    issues: list[Issue] | None = None,
) -> AgentOutput:
    iss = issues or []
    summary = SummaryCount(
        critical=sum(1 for i in iss if i.severity == "Critical"),
        major=sum(1 for i in iss if i.severity == "Major"),
        minor=sum(1 for i in iss if i.severity == "Minor"),
    )
    return AgentOutput(
        task_id="task-1",
        scan_id=scan_id,
        pr_id=pr_id,
        agent=agent,
        issues=iss,
        summary=summary,
    )


def _issue(severity: str, file: str, line: int, rule_id: str) -> Issue:
    return Issue(severity=severity, file=file, line=line, message="msg", rule_id=rule_id)


# ── 기본 동작 ───────────────────────────────────────────────────────────────

class TestAggregateBasic:
    def test_empty_input_returns_lgtm_zero_issues(self):
        """빈 입력 → lgtm + 0 이슈 (graceful)."""
        combined, verdict, summary = aggregate([])
        assert verdict == "lgtm"
        assert len(combined) == 0
        assert summary.critical == 0
        assert summary.major == 0
        assert summary.minor == 0

    def test_two_outputs_issues_merged(self):
        """2개 AgentOutput 합치기 → 이슈 합계 정확."""
        out1 = _make_output(issues=[_issue("Minor", "a.py", 1, "R1")])
        out2 = _make_output(issues=[_issue("Minor", "b.py", 2, "R2")])
        combined, verdict, summary = aggregate([out1, out2])
        assert len(combined) == 2
        assert summary.minor == 2
        assert verdict == "lgtm"


# ── 중복 제거 ────────────────────────────────────────────────────────────────

class TestDeduplication:
    def test_same_rule_file_line_deduped_to_one(self):
        """(rule_id, file, line) 동일 → 1개만 유지."""
        dup = _issue("Major", "a.py", 10, "DUP01")
        out1 = _make_output(issues=[dup])
        out2 = _make_output(issues=[dup])
        combined, _, summary = aggregate([out1, out2])
        assert len(combined) == 1
        assert summary.major == 1

    def test_same_rule_different_line_not_deduped(self):
        """같은 rule_id라도 line이 다르면 별개 이슈."""
        out = _make_output(issues=[
            _issue("Major", "a.py", 1, "SAME"),
            _issue("Major", "a.py", 2, "SAME"),
        ])
        combined, _, summary = aggregate([out])
        assert len(combined) == 2
        assert summary.major == 2


# ── verdict 판정 ─────────────────────────────────────────────────────────────

class TestVerdictLogic:
    def test_critical_1_returns_escalate(self):
        """Critical ≥ 1 → escalate."""
        out = _make_output(issues=[_issue("Critical", "a.py", 1, "C1")])
        _, verdict, summary = aggregate([out])
        assert verdict == "escalate"
        assert summary.critical == 1

    def test_major_3_returns_rework(self):
        """Major ≥ 3 → rework."""
        out = _make_output(issues=[
            _issue("Major", "a.py", 1, "M1"),
            _issue("Major", "a.py", 2, "M2"),
            _issue("Major", "a.py", 3, "M3"),
        ])
        _, verdict, summary = aggregate([out])
        assert verdict == "rework"
        assert summary.major == 3

    def test_major_2_returns_rework(self):
        """F3 양성: Major 2건(예: N+1 + O(n³)) 실결함 PR → rework (임계 2)."""
        out = _make_output(issues=[
            _issue("Major", "a.py", 1, "M1"),
            _issue("Major", "a.py", 2, "M2"),
        ])
        _, verdict, summary = aggregate([out])
        assert verdict == "rework"
        assert summary.major == 2

    def test_major_1_minor_5_returns_lgtm(self):
        """F3 음성(과민 방지): Major 1 + Minor 5 → 여전히 lgtm."""
        out = _make_output(issues=[
            _issue("Major", "a.py", 1, "M1"),
            _issue("Minor", "b.py", 1, "N1"),
            _issue("Minor", "b.py", 2, "N2"),
            _issue("Minor", "b.py", 3, "N3"),
            _issue("Minor", "b.py", 4, "N4"),
            _issue("Minor", "b.py", 5, "N5"),
        ])
        _, verdict, summary = aggregate([out])
        assert verdict == "lgtm"
        assert summary.major == 1
        assert summary.minor == 5

    def test_critical_beats_major_threshold(self):
        """Critical 있으면 Major 개수 무관하게 escalate."""
        out = _make_output(issues=[
            _issue("Critical", "a.py", 1, "C1"),
            _issue("Major", "a.py", 2, "M1"),
            _issue("Major", "a.py", 3, "M2"),
            _issue("Major", "a.py", 4, "M3"),
        ])
        _, verdict, _ = aggregate([out])
        assert verdict == "escalate"


# ── rag_context 전달 (RAG §6 통로 B) ─────────────────────────────────────────

class TestRagContextPassthrough:
    def test_rag_context_carried_to_combined_issue(self):
        """Dev3 Issue.rag_context가 CombinedIssue로 그대로 전달된다."""
        iss = Issue(
            severity="Major", file="a.py", line=1, message="N+1", rule_id="PERF-002",
            rag_context="📖 사내 가이드: selectinload 표준",
        )
        combined, _, _ = aggregate([_make_output(issues=[iss])])
        assert len(combined) == 1
        assert combined[0].rag_context == "📖 사내 가이드: selectinload 표준"

    def test_no_rag_context_stays_empty(self):
        """rag_context 없는 이슈 → CombinedIssue.rag_context 빈 문자열 (하위호환)."""
        combined, _, _ = aggregate([_make_output(issues=[_issue("Minor", "a.py", 1, "R1")])])
        assert combined[0].rag_context == ""


# ── scan_id 일관성 검증 ───────────────────────────────────────────────────────

class TestScanIdValidation:
    def test_different_scan_ids_raise_value_error(self):
        """다른 scan_id 섞이면 ValueError."""
        out1 = _make_output(scan_id=1)
        out2 = _make_output(scan_id=2)
        with pytest.raises(ValueError, match="scan_id"):
            aggregate([out1, out2])

    def test_same_scan_id_accepted(self):
        """동일 scan_id → 정상 처리."""
        out1 = _make_output(scan_id=99)
        out2 = _make_output(scan_id=99)
        combined, verdict, _ = aggregate([out1, out2])
        assert verdict == "lgtm"
