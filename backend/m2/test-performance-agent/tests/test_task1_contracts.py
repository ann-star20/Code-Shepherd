"""Task 1 — contracts.py: Pydantic 모델 검증 테스트."""
import pytest
from pydantic import ValidationError


def test_issue_valid_severity():
    from contracts import Issue
    issue = Issue(severity="Major", file="src/posts.py", line=7,
                  message="N+1 감지", rule_id="PERF-002", suggestion="joinedload 사용")
    assert issue.severity == "Major"
    assert issue.line == 7


def test_issue_invalid_severity_raises():
    from contracts import Issue
    with pytest.raises(ValidationError):
        Issue(severity="WrongValue", file="src/posts.py",
              message="msg", rule_id="TEST-001")


def test_issue_line_optional():
    from contracts import Issue
    issue = Issue(severity="Major", file="(전체)", message="커버리지 부족",
                  rule_id="TEST-001")
    assert issue.line is None
    assert issue.suggestion == ""


def test_agent_output_valid():
    from contracts import AgentOutput, Issue, SummaryCount
    out = AgentOutput(
        task_id="uuid-1234",
        scan_id=42,
        pr_id="PR-001",
        agent="test_verification",
        issues=[Issue(severity="Major", file="(전체)", message="20%<80%",
                      rule_id="TEST-001")],
        summary=SummaryCount(critical=0, major=1, minor=0),
        metrics={"coverage_line": 0.2},
        execution_ms=1500,
    )
    assert out.metrics["coverage_line"] == 0.2
    assert out.agent == "test_verification"


def test_agent_output_invalid_agent():
    from contracts import AgentOutput
    with pytest.raises(ValidationError):
        AgentOutput(task_id="t", scan_id=1, pr_id="p",
                    agent="unknown_agent")


def test_summary_count_mutable():
    from contracts import SummaryCount
    s = SummaryCount()
    assert s.critical == 0
    s.major += 1
    assert s.major == 1


def test_dev3_input_requires_repo():
    from contracts import Dev3Input
    with pytest.raises(ValidationError):
        Dev3Input(task_id="t", scan_id=1, pr_id="p", pr_diff="", developer=None)


def test_dev3_input_valid():
    from contracts import Dev3Input, RepoInfo, Developer
    inp = Dev3Input(
        task_id="uuid-1234",
        scan_id=42,
        pr_id="PR-001",
        pr_diff="diff --git a/src/posts.py ...",
        repo=RepoInfo(clone_url="https://github.com/team/proj.git",
                      commit_sha="abc123"),
        developer=Developer(id="junior_dev_01"),
    )
    assert inp.scan_id == 42
    assert inp.repo.language == "python"
