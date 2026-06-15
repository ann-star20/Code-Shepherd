"""contract.py 단위 테스트 — AgentResult 빌더·검증·sub-trace ID."""

import re

from app.contract import (
    AgentResult,
    build_agent_result,
    make_sub_trace_id,
    make_timeout_result,
    validate_result,
)
from shared.contracts import IssueItem, IssueSummary, M2AnalyzeRequest

PAYLOAD = M2AnalyzeRequest(
    task_id="t-001", pr_id="42", pr_diff="diff --git ...", trace_id="pr_0123456789ab"
)

GOOD_ISSUE = IssueItem(severity="Critical", message="x", rule_id="SEC-B608")


def test_sub_trace_id_reuses_pr_base():
    sid = make_sub_trace_id("pr_0123456789ab", "static_analysis")
    assert re.fullmatch(r"pr_0123456789ab_static_analysis_[0-9a-f]{4}", sid)


def test_sub_trace_id_generates_base_when_missing():
    sid = make_sub_trace_id(None, "security_scan")
    assert re.fullmatch(r"pr_[0-9a-f]{12}_security_scan_[0-9a-f]{4}", sid)


def test_validate_skip_when_no_issues():
    assert validate_result([], 5) == "skip"


def test_validate_fail_on_zero_execution():
    assert validate_result([GOOD_ISSUE], 0) == "fail"


def test_validate_fail_on_bad_rule_id():
    bad = IssueItem(severity="Minor", message="x", rule_id="XX-001")
    assert validate_result([bad], 5) == "fail"


def test_validate_pass_on_valid_prefixes():
    assert validate_result([GOOD_ISSUE], 5) == "pass"


def test_build_agent_result_is_contract_shaped():
    res = build_agent_result(PAYLOAD, "static_analysis", [GOOD_ISSUE], IssueSummary(critical=1), 7)
    assert isinstance(res, AgentResult)
    assert res.module_id == "module_2"
    assert res.agent_name == "StaticAnalysisAgent"
    assert res.status == "success"
    assert res.validation_result == "pass"
    assert res.execution_ms == 7
    assert res.next_agent is None


def test_build_agent_result_clamps_execution_ms():
    res = build_agent_result(PAYLOAD, "static_analysis", [], IssueSummary(), 0)
    assert res.execution_ms >= 1
    assert res.validation_result == "skip"


def test_timeout_result_is_fail_empty():
    res = make_timeout_result(PAYLOAD, "security_scan", 0, "analyze_failed: boom")
    assert res.status == "fail"
    assert res.issues == []
    assert res.error_message == "analyze_failed: boom"
    assert res.agent_name == "SecurityScanAgent"
