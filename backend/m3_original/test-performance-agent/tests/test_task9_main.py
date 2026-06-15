"""Task 9 — main.run() TDD 테스트.

- mocked 탐지기 결과 → 2개 AgentOutput 반환
- 한 탐지기 Exception → 그 결과만 빈 리스트, 나머지 정상
- scan_id / pr_id / task_id 정확 전달
- 탐지기 이슈가 올바른 agent로 분배
"""
from unittest.mock import patch

import pytest

from contracts import AgentOutput, Developer, Dev3Input, Issue, RepoInfo
from main import run


def _make_input(pr_diff: str = "") -> Dev3Input:
    if not pr_diff:
        pr_diff = (
            "diff --git a/src/foo.py b/src/foo.py\n"
            "+++ b/src/foo.py\n"
            "@@ -0,0 +1,1 @@\n"
            "+x=1\n"
        )
    return Dev3Input(
        task_id="t-001",
        scan_id=42,
        pr_id="PR-999",
        pr_diff=pr_diff,
        repo=RepoInfo(clone_url="http://example.com", commit_sha="abc"),
        developer=Developer(id="dev1"),
    )


# ──────────────────────────────────────────
# 기본 반환 구조
# ──────────────────────────────────────────


def test_run_returns_exactly_two_outputs(tmp_path):
    """모든 탐지기 정상 → AgentOutput 정확히 2개 반환."""
    inp = _make_input()
    with (
        patch("main.coverage.measure", return_value=([], {})),
        patch("main.missing_funcs.detect", return_value=[]),
        patch("main.nplus1.detect", return_value=[]),
        patch("main.complexity.detect", return_value=[]),
    ):
        outputs = run(inp, str(tmp_path))

    assert len(outputs) == 2
    agents = {o.agent for o in outputs}
    assert agents == {"test_verification", "performance"}


def test_run_scan_id_pr_id_task_id_passed_through(tmp_path):
    """scan_id / pr_id / task_id 가 AgentOutput 모두에 정확히 전달된다."""
    inp = _make_input()
    with (
        patch("main.coverage.measure", return_value=([], None)),
        patch("main.missing_funcs.detect", return_value=[]),
        patch("main.nplus1.detect", return_value=[]),
        patch("main.complexity.detect", return_value=[]),
    ):
        outputs = run(inp, str(tmp_path))

    for o in outputs:
        assert o.scan_id == 42
        assert o.pr_id == "PR-999"
        assert o.task_id == "t-001"


# ──────────────────────────────────────────
# 부분 실패 허용
# ──────────────────────────────────────────


def test_run_nplus1_exception_graceful(tmp_path):
    """nplus1.detect 예외 → performance 이슈에 PERF-002 없고 나머지 정상."""
    cx_issue = Issue(
        severity="Minor",
        file="src/foo.py",
        line=1,
        message="O(n^2)",
        rule_id="PERF-001",
    )
    inp = _make_input()
    with (
        patch("main.coverage.measure", return_value=([], None)),
        patch("main.missing_funcs.detect", return_value=[]),
        patch("main.nplus1.detect", side_effect=RuntimeError("db 연결 실패")),
        patch("main.complexity.detect", return_value=[cx_issue]),
    ):
        outputs = run(inp, str(tmp_path))

    assert len(outputs) == 2
    perf = next(o for o in outputs if o.agent == "performance")
    # nplus1 실패 → PERF-002 없음
    assert all(i.rule_id != "PERF-002" for i in perf.issues)
    # complexity 정상 → PERF-001 있음 (src/foo.py:1 은 diff 안)
    assert any(i.rule_id == "PERF-001" for i in perf.issues)


# ──────────────────────────────────────────
# 이슈 분배
# ──────────────────────────────────────────


def test_run_issues_routed_to_correct_agent(tmp_path):
    """커버리지+누락함수 → test_verification, N+1+복잡도 → performance."""
    cov_issue = Issue(
        severity="Major", file="(전체)", line=None, message="cov", rule_id="TEST-001"
    )
    mf_issue = Issue(
        severity="Minor", file="src/foo.py", line=1, message="mf", rule_id="TEST-004"
    )
    n1_issue = Issue(
        severity="Major", file="src/foo.py", line=1, message="n+1", rule_id="PERF-002"
    )
    cx_issue = Issue(
        severity="Minor", file="src/foo.py", line=1, message="cx", rule_id="PERF-001"
    )
    inp = _make_input()
    with (
        patch("main.coverage.measure", return_value=([cov_issue], {"coverage_line": 0.5})),
        patch("main.missing_funcs.detect", return_value=[mf_issue]),
        patch("main.nplus1.detect", return_value=[n1_issue]),
        patch("main.complexity.detect", return_value=[cx_issue]),
    ):
        outputs = run(inp, str(tmp_path))

    tv = next(o for o in outputs if o.agent == "test_verification")
    perf = next(o for o in outputs if o.agent == "performance")
    tv_rule_ids = {i.rule_id for i in tv.issues}
    perf_rule_ids = {i.rule_id for i in perf.issues}
    assert "TEST-001" in tv_rule_ids
    assert "TEST-004" in tv_rule_ids
    assert "PERF-002" in perf_rule_ids
    assert "PERF-001" in perf_rule_ids
