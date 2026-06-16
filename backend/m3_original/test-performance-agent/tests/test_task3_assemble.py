"""Task 3 — assemble/output.py: AgentOutput 조립 테스트."""
from contracts import Issue


def _make_issue(severity: str) -> Issue:
    return Issue(severity=severity, file="src/posts.py", line=1,
                 message="msg", rule_id="TEST-001")


def test_empty_issues_all_zero():
    from assemble.output import assemble_output
    out = assemble_output("t", 1, "p", "test_verification", [], None, 0)
    assert out.summary.critical == 0
    assert out.summary.major == 0
    assert out.summary.minor == 0
    assert out.issues == []


def test_severity_counts_correct():
    """3 Critical + 2 Major + 5 Minor → 정확히 카운트."""
    from assemble.output import assemble_output
    issues = (
        [_make_issue("Critical")] * 3
        + [_make_issue("Major")] * 2
        + [_make_issue("Minor")] * 5
    )
    out = assemble_output("t", 42, "p", "performance", issues, None, 100)
    assert out.summary.critical == 3
    assert out.summary.major == 2
    assert out.summary.minor == 5


def test_performance_agent_metrics_none():
    """performance 에이전트는 metrics=None 허용 (PRD §8.3)."""
    from assemble.output import assemble_output
    out = assemble_output("t", 1, "p", "performance", [], None, 50)
    assert out.agent == "performance"
    assert out.metrics is None


def test_fields_propagated():
    """task_id, scan_id, pr_id, execution_ms 정확히 전달."""
    from assemble.output import assemble_output
    out = assemble_output("uuid-9999", 99, "PR-777", "test_verification",
                          [], {"coverage_line": 0.5}, 2345)
    assert out.task_id == "uuid-9999"
    assert out.scan_id == 99
    assert out.pr_id == "PR-777"
    assert out.execution_ms == 2345
    assert out.metrics == {"coverage_line": 0.5}


def test_returns_agent_output_type():
    from assemble.output import assemble_output
    from contracts import AgentOutput
    out = assemble_output("t", 1, "p", "test_verification", [], None, 0)
    assert isinstance(out, AgentOutput)
