"""m3 app 엔드포인트 → 실제 분석 어댑터 계약 테스트.

외부 의존(clone·docker·embed·run)은 app.main._analyze_pr seam을 monkeypatch 해 고립.
- /verify/tests        → test_verification 이슈만 IssueItem 으로 반환
- /analyze/performance → performance 이슈만 반환
- repo(clone_url) 없는 요청 → 빈 issues + 200 (가짜 만들지 않음)
"""
from types import SimpleNamespace

import pytest
from httpx import ASGITransport, AsyncClient

import app.main as appmain
from app.main import app

PAYLOAD = {
    "task_id": "t-100",
    "pr_id": "77",
    "pr_diff": "diff --git a/src/a.py b/src/a.py\n+code",
    "clone_url": "https://github.com/example/repo",
    "commit_sha": "abc123",
    "developer": {"id": "junior_dev_01"},
}


def _issue(severity, file, line, message, rule_id, suggestion):
    # 실제 Dev3 Issue 엔 keyword/code_context/rag_context 등 추가 필드가 있음
    # → IssueItem 매핑 시 반드시 버려져야 함(계약 준수 검증용).
    return SimpleNamespace(
        severity=severity, file=file, line=line, message=message,
        rule_id=rule_id, suggestion=suggestion,
        keyword="대분류", code_context="함수설명", rag_context="사내가이드",
    )


def _fake_outputs():
    tv = SimpleNamespace(agent="test_verification", issues=[
        _issue("Minor", "src/a.py", 10, "커버리지 20% < 80%", "TEST-001", "테스트 추가"),
    ])
    perf = SimpleNamespace(agent="performance", issues=[
        _issue("Major", "src/b.py", 20, "N+1 쿼리", "PERF-002", "배치 조회"),
        _issue("Minor", "src/b.py", 30, "O(n^2)", "PERF-001", "자료구조 변경"),
    ])
    return [tv, perf]


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


@pytest.mark.asyncio
async def test_verify_tests_maps_test_verification_only(client, monkeypatch):
    monkeypatch.setattr(appmain, "_analyze_pr", lambda payload: _fake_outputs(), raising=False)
    resp = await client.post("/verify/tests", json=PAYLOAD)
    assert resp.status_code == 200
    data = resp.json()
    assert data["task_id"] == "t-100"
    assert data["agent"] == "test_verification"
    assert len(data["issues"]) == 1                       # performance 이슈는 제외
    it = data["issues"][0]
    assert it == {
        "severity": "Minor", "line": 10, "file": "src/a.py",
        "message": "커버리지 20% < 80%", "rule_id": "TEST-001", "suggestion": "테스트 추가",
    }
    assert "keyword" not in it and "rag_context" not in it  # 계약 외 필드 버림
    assert data["summary"] == {"critical": 0, "major": 0, "minor": 1}


@pytest.mark.asyncio
async def test_analyze_performance_maps_performance_only(client, monkeypatch):
    monkeypatch.setattr(appmain, "_analyze_pr", lambda payload: _fake_outputs(), raising=False)
    resp = await client.post("/analyze/performance", json=PAYLOAD)
    assert resp.status_code == 200
    data = resp.json()
    assert data["agent"] == "performance"
    assert len(data["issues"]) == 2                       # test_verification 제외
    assert {i["rule_id"] for i in data["issues"]} == {"PERF-002", "PERF-001"}
    assert data["summary"] == {"critical": 0, "major": 1, "minor": 1}


@pytest.mark.asyncio
async def test_no_repo_returns_empty_issues_200(client):
    payload = {"task_id": "t-101", "pr_id": "78", "pr_diff": "diff --git ..."}  # clone_url 없음
    resp = await client.post("/verify/tests", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["issues"] == []
    assert data["summary"] == {"critical": 0, "major": 0, "minor": 0}
