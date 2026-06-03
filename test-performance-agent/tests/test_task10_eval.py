"""Task 10 — validation/eval.py TDD 테스트.

- fixture 5이슈 전부 탐지 → recall=1.0 / false_alarm=0.0 / PASS
- 출력에 이슈 추가 → false_alarm 증가
- 출력에서 이슈 제거 → recall < 1.0
"""
from pathlib import Path

import pytest

from contracts import AgentOutput, Issue, SummaryCount
from validation.eval import evaluate

EXPECTED_PATH = str(Path(__file__).parent / "fixtures" / "expected_output.json")


def _make_output(agent: str, issues: list[Issue]) -> AgentOutput:
    return AgentOutput(
        task_id="t1",
        scan_id=1,
        pr_id="PR-001",
        agent=agent,
        issues=issues,
        summary=SummaryCount(
            critical=sum(1 for i in issues if i.severity == "Critical"),
            major=sum(1 for i in issues if i.severity == "Major"),
            minor=sum(1 for i in issues if i.severity == "Minor"),
        ),
    )


# ── 골든 5 이슈 (기대값 일치) ──────────────────────

_TV_ISSUES = [
    Issue(severity="Major", file="(전체)", line=None, message="cov20%", rule_id="TEST-001"),
    Issue(severity="Minor", file="src/posts.py", line=4, message="get_posts", rule_id="TEST-004"),
    Issue(severity="Minor", file="src/posts.py", line=16, message="find_dups", rule_id="TEST-004"),
]
_PERF_ISSUES = [
    Issue(severity="Major", file="src/posts.py", line=7, message="N+1", rule_id="PERF-002"),
    # NOTE: complexity.py는 loop lineno=18 보고 (expected_output.json 에는 16 — 매칭은 rule_id+file)
    Issue(severity="Minor", file="src/posts.py", line=18, message="O(n^2)", rule_id="PERF-001"),
]


def test_eval_fixture_recall_1_pass():
    """기대값 5이슈 전부 탐지 → recall=1.0, false_alarm=0.0, PASS."""
    outputs = [
        _make_output("test_verification", _TV_ISSUES),
        _make_output("performance", _PERF_ISSUES),
    ]
    result = evaluate(outputs, EXPECTED_PATH)
    assert result["recall"] == 1.0
    assert result["false_alarm"] == 0.0
    assert result["pass"] is True


def test_eval_extra_issue_increases_false_alarm():
    """출력에 이슈 1개 추가 → false_alarm > 0."""
    extra_issue = Issue(
        severity="Minor", file="src/posts.py", line=99, message="extra", rule_id="TEST-004"
    )
    outputs = [
        _make_output("test_verification", _TV_ISSUES + [extra_issue]),
        _make_output("performance", _PERF_ISSUES),
    ]
    result = evaluate(outputs, EXPECTED_PATH)
    assert result["false_alarm"] > 0.0


def test_eval_missing_issue_drops_recall():
    """기대값 이슈 하나 제거 → recall < 1.0."""
    # TEST-004 get_posts (line=4) 제거
    partial_tv = [
        Issue(severity="Major", file="(전체)", line=None, message="cov", rule_id="TEST-001"),
        Issue(severity="Minor", file="src/posts.py", line=16, message="find_dups", rule_id="TEST-004"),
    ]
    outputs = [
        _make_output("test_verification", partial_tv),
        _make_output("performance", _PERF_ISSUES),
    ]
    result = evaluate(outputs, EXPECTED_PATH)
    assert result["recall"] < 1.0
