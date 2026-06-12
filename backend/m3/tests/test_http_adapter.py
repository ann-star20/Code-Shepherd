"""http_adapter 단위테스트 — pipeline·GitHub API를 mock으로 격리."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from contracts import Finding, GapReport, ReviewOutput
from src.adapters.http_adapter import (
    M3ReviewRequest,
    _map_verdict,
    _findings_to_issues,
    _findings_to_rich,
    _store_result,
    _result_store,
    app,
)


def _make_violation(rule_id: str = "CONV-API-001") -> Finding:
    return Finding(
        rule_id=rule_id,
        verdict="violation",
        severity="Major",
        rule_quote="async 함수 안에서 동기 requests 사용 금지",
        file="src/api.py",
        evidence_lines=["+    r = requests.get(url)"],
        reasoning="async 함수 내 동기 requests 호출",
        fp_note=None,
    )


def _make_no_violation() -> Finding:
    return Finding(
        rule_id="CONV-API-001",
        verdict="no_violation",
        severity="Major",
        rule_quote="httpx.AsyncClient 사용",
        file="",
        evidence_lines=[],
        reasoning="올바른 패턴 사용",
        fp_note=None,
    )


# ── _map_verdict ──────────────────────────────────────────────────────────────

def test_map_verdict_violation():
    out = ReviewOutput(
        findings=[_make_violation()],
        comment_md="## 위반",
        gap_report=None,
    )
    assert _map_verdict(out) == "rework"


def test_map_verdict_gap():
    out = ReviewOutput(
        findings=[],
        comment_md="## gap",
        gap_report=GapReport(
            pattern_summary="테스트", queries_tried=[], nearest_rule_ids=[], proposed_rule_md=""
        ),
    )
    assert _map_verdict(out) == "escalate"


def test_map_verdict_lgtm():
    out = ReviewOutput(findings=[], comment_md="## 통과", gap_report=None)
    assert _map_verdict(out) == "lgtm"


def test_map_verdict_no_violation_only():
    out = ReviewOutput(
        findings=[_make_no_violation()],
        comment_md="## 통과",
        gap_report=None,
    )
    assert _map_verdict(out) == "lgtm"


# ── _findings_to_issues ───────────────────────────────────────────────────────

def test_findings_to_issues_filters_no_violation():
    issues = _findings_to_issues([_make_violation(), _make_no_violation()])
    assert len(issues) == 1
    assert issues[0]["rule_id"] == "CONV-API-001"
    assert issues[0]["severity"] == "Major"


def test_findings_to_issues_empty():
    assert _findings_to_issues([]) == []


# ── _findings_to_rich ─────────────────────────────────────────────────────────

def test_findings_to_rich_keyword():
    rich = _findings_to_rich([_make_violation()])
    assert len(rich) == 1
    assert rich[0]["keyword"] == "동기 HTTP 호출"
    assert rich[0]["agent"] == "dev3"
    assert rich[0]["sub_category"] == "CONV-API-001"


# ── POST /review (mocked pipeline + GitHub) ───────────────────────────────────

client = TestClient(app)


def _make_payload(**kwargs) -> dict:
    base = {
        "task_id": "test-task-001",
        "pr_id": "pr-1",
        "repository": "owner/repo",
        "pr_number": 1,
    }
    base.update(kwargs)
    return base


def test_post_review_rework(monkeypatch):
    violation_output = ReviewOutput(
        findings=[_make_violation()],
        comment_md="## 위반 1건",
        gap_report=None,
    )

    async def mock_fetch_diff(*_a, **_kw):
        return "diff content"

    async def mock_post_comment(*_a, **_kw):
        return True, "https://github.com/comment/1"

    fake_trace = [{"node": "judge", "label": "④ 규칙 판정", "ms": 1,
                   "summary": "findings 1건 (violation 1)", "ok": True}]
    monkeypatch.setattr("src.adapters.http_adapter._fetch_pr_diff", mock_fetch_diff)
    monkeypatch.setattr("src.adapters.http_adapter._post_github_comment", mock_post_comment)
    monkeypatch.setattr("src.adapters.http_adapter.run_review_traced",
                        lambda _: (violation_output, fake_trace))

    r = client.post("/review", json=_make_payload())
    assert r.status_code == 200
    body = r.json()
    assert body["verdict"] == "rework"
    assert body["comment_posted"] is True
    assert body["task_id"] == "test-task-001"
    assert body["trace"] == fake_trace  # 옵셔널 trace 포함

    g = client.get("/review/owner/repo/1")
    assert g.json()["trace"] == fake_trace


def test_post_review_lgtm(monkeypatch):
    clean_output = ReviewOutput(findings=[], comment_md="## 통과", gap_report=None)

    async def mock_fetch_diff(*_a, **_kw):
        return "diff content"

    async def mock_post_comment(*_a, **_kw):
        return False, None

    monkeypatch.setattr("src.adapters.http_adapter._fetch_pr_diff", mock_fetch_diff)
    monkeypatch.setattr("src.adapters.http_adapter._post_github_comment", mock_post_comment)
    monkeypatch.setattr("src.adapters.http_adapter.run_review_traced",
                        lambda _: (clean_output, []))

    r = client.post("/review", json=_make_payload(pr_number=2))
    assert r.status_code == 200
    assert r.json()["verdict"] == "lgtm"


def test_post_review_escalate(monkeypatch):
    gap_output = ReviewOutput(
        findings=[],
        comment_md="## 지침공백",
        gap_report=GapReport(
            pattern_summary="gap", queries_tried=[], nearest_rule_ids=[], proposed_rule_md=""
        ),
    )

    async def mock_fetch_diff(*_a, **_kw):
        return "diff"

    async def mock_post_comment(*_a, **_kw):
        return False, None

    monkeypatch.setattr("src.adapters.http_adapter._fetch_pr_diff", mock_fetch_diff)
    monkeypatch.setattr("src.adapters.http_adapter._post_github_comment", mock_post_comment)
    monkeypatch.setattr("src.adapters.http_adapter.run_review_traced",
                        lambda _: (gap_output, []))

    r = client.post("/review", json=_make_payload(pr_number=3))
    assert r.status_code == 200
    assert r.json()["verdict"] == "escalate"


def test_post_review_diff_fetch_failure_continues(monkeypatch):
    clean_output = ReviewOutput(findings=[], comment_md="통과", gap_report=None)

    async def mock_fetch_diff(*_a, **_kw):
        raise httpx.ConnectError("timeout")

    async def mock_post_comment(*_a, **_kw):
        return False, None

    import httpx as _httpx
    monkeypatch.setattr("src.adapters.http_adapter._fetch_pr_diff", mock_fetch_diff)
    monkeypatch.setattr("src.adapters.http_adapter._post_github_comment", mock_post_comment)
    monkeypatch.setattr("src.adapters.http_adapter.run_review_traced",
                        lambda _: (clean_output, []))

    r = client.post("/review", json=_make_payload(pr_number=99))
    assert r.status_code == 200


# ── GET /review ────────────────────────────────────────────────────────────────

def test_get_review_not_found():
    r = client.get("/review/no/repo/9999")
    assert r.status_code == 200
    assert r.json()["found"] is False


def test_get_review_found(monkeypatch):
    violation_output = ReviewOutput(
        findings=[_make_violation()],
        comment_md="## 위반",
        gap_report=None,
    )
    _store_result("myowner", "myrepo", 42, violation_output)

    r = client.get("/review/myowner/myrepo/42")
    assert r.status_code == 200
    body = r.json()
    assert body["found"] is True
    assert body["verdict"] == "rework"
    assert len(body["issues"]) == 1
    assert len(body["rich_issues"]) == 1


# ── /health ───────────────────────────────────────────────────────────────────

def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
