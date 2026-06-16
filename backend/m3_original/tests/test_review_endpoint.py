"""m3 /review (집계→코멘트→게시→저장) + GET /review 조회 계약 테스트.

외부 의존(github_poster·llm_refiner·persist)은 app.main seam 을 monkeypatch 해 고립한다.
- 판정(verdict)은 실제 pr-comment-agent aggregator 를 통해 산출되는지 검증(재사용).
- 게시 호출됨/저장 호출됨/verdict 반환 검증.
- 토큰 없음/게시 실패 → comment_posted=false + 사유, 예외 안 터짐(정직).
- GET /review: 저장된 결과 반환 / 없으면 빈 결과.
"""
import sys

import pytest
from httpx import ASGITransport, AsyncClient

import app.main as appmain
from app.main import app


def test_review_aggregate_survives_tp_at_path_front():
    """순서 회귀: persist/get 가 _TP(test-performance-agent)를 sys.path 앞에 꽂아둔 상태에서도
    _review_aggregate 가 pr-comment-agent 의 contracts(CombinedIssue)를 올바로 import 해야 한다.
    (이전엔 _TP 가 앞에 있으면 'from contracts import CombinedIssue' 가 _TP/contracts.py 로 풀려
     ImportError → /review 500 이 났다.)"""
    sys.path.insert(0, appmain._TP)  # 오염 재현
    try:
        verdict, combined = appmain._review_aggregate(
            [
                {
                    "agent": "performance",
                    "issues": [
                        {
                            "severity": "Critical",
                            "file": "a.py",
                            "line": 1,
                            "message": "m",
                            "rule_id": "PERF-001",
                            "suggestion": "",
                        }
                    ],
                }
            ]
        )
        assert verdict == "escalate"
        assert len(combined) == 1
    finally:
        while appmain._TP in sys.path:
            sys.path.remove(appmain._TP)


def _result(agent, issues):
    """M2AnalyzeResponse / M3VerifyResponse 모양의 dict."""
    return {
        "task_id": "t-1",
        "agent": agent,
        "issues": issues,
        "summary": {"critical": 0, "major": 0, "minor": 0},
        "execution_ms": 0,
    }


def _issue(severity, rule_id, file="src/a.py", line=10, message="문제", suggestion="고치세요"):
    return {
        "severity": severity, "line": line, "file": file,
        "message": message, "rule_id": rule_id, "suggestion": suggestion,
    }


def _request(**results):
    """results: static_analysis/security_scan/test_verification/performance 중 일부."""
    body = {
        "task_id": "task-1",
        "pr_id": "5",
        "repository": "octocat/hello",
        "pr_number": 5,
        "developer": {"id": "junior_dev_01", "skill_level": "junior"},
    }
    body.update(results)
    return body


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


@pytest.fixture
def spies(monkeypatch):
    """refine·post·persist seam 을 spy 로 교체. 판정(aggregate)은 실제 로직 유지."""
    calls = {"refine": [], "post": [], "persist": []}

    def fake_refine(combined, verdict, skill):
        calls["refine"].append((list(combined), verdict, skill))
        return "## 자동 리뷰\n본문"

    def fake_post(owner, repo, pr_number, body):
        calls["post"].append((owner, repo, pr_number, body))
        return {"posted": True, "url": "https://github.com/octocat/hello/pull/5#issuecomment-1", "reason": "github"}

    def fake_persist(owner, repo, pr_number, verdict, comment, issues):
        calls["persist"].append((owner, repo, pr_number, verdict, comment, list(issues)))
        return True

    monkeypatch.setattr(appmain, "_review_refine", fake_refine)
    monkeypatch.setattr(appmain, "_review_post_comment", fake_post)
    monkeypatch.setattr(appmain, "_review_persist", fake_persist)
    return calls


@pytest.mark.asyncio
async def test_review_escalate_on_critical(client, spies):
    """Critical 1개 → escalate. 게시·저장 호출됨, comment_posted/url/persisted 반영."""
    payload = _request(security_scan=_result("security_scan", [_issue("Critical", "SEC-001")]))
    resp = await client.post("/review", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["task_id"] == "task-1"
    assert data["pr_id"] == "5"
    assert data["verdict"] == "escalate"          # 실제 aggregator 판정
    assert data["comment_posted"] is True
    assert data["comment_url"].endswith("#issuecomment-1")
    assert data["persisted"] is True

    # 게시 호출됨 — owner/repo/pr_number + 생성된 코멘트 본문 전달
    assert len(spies["post"]) == 1
    owner, repo, pr_number, body = spies["post"][0]
    assert (owner, repo, pr_number) == ("octocat", "hello", 5)
    assert body == "## 자동 리뷰\n본문"
    # 저장 호출됨 — verdict + 코멘트 + 이슈
    assert len(spies["persist"]) == 1
    assert spies["persist"][0][3] == "escalate"


@pytest.mark.asyncio
async def test_review_rework_on_three_major(client, spies):
    """서로 다른 Major 3개 → rework."""
    issues = [_issue("Major", f"PERF-{n}", line=n) for n in (1, 2, 3)]
    payload = _request(performance=_result("performance", issues))
    resp = await client.post("/review", json=payload)
    assert resp.status_code == 200
    assert resp.json()["verdict"] == "rework"


@pytest.mark.asyncio
async def test_review_lgtm_on_minor_only(client, spies):
    """Minor 만 → lgtm."""
    payload = _request(test_verification=_result("test_verification", [_issue("Minor", "TEST-001")]))
    resp = await client.post("/review", json=payload)
    assert resp.status_code == 200
    assert resp.json()["verdict"] == "lgtm"


@pytest.mark.asyncio
async def test_review_no_results_lgtm(client, spies):
    """결과 4개 전부 없음 → 빈 이슈 → lgtm, 예외 없음."""
    resp = await client.post("/review", json=_request())
    assert resp.status_code == 200
    assert resp.json()["verdict"] == "lgtm"


@pytest.mark.asyncio
async def test_review_post_failure_is_honest(client, monkeypatch):
    """게시 실패/토큰 없음 → comment_posted=False + 사유, 예외 안 터짐.

    실제 _review_post_comment seam 을 쓰되, 내부 GitHub 호출(_gh_post)만 실패시켜
    seam 의 정직-skip 로직을 검증한다. (refine·persist 는 가볍게 spy)
    """
    def failing_gh_post(owner, repo, pr_number, body):
        raise RuntimeError("GitHub 인증 실패 (401)")

    monkeypatch.setattr(appmain, "_review_refine", lambda c, v, s: "본문")
    monkeypatch.setattr(appmain, "_review_persist", lambda *a, **k: True)
    monkeypatch.setattr(appmain, "_gh_post", failing_gh_post)

    payload = _request(security_scan=_result("security_scan", [_issue("Critical", "SEC-001")]))
    resp = await client.post("/review", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["verdict"] == "escalate"
    assert data["comment_posted"] is False
    assert data["comment_url"] is None


def test_gh_post_dry_run_not_counted_as_posted(monkeypatch):
    """토큰 없어 dry_run 이면 실제 게시 아님 → posted False (가짜 게시 금지)."""
    monkeypatch.setattr(appmain, "_gh_post", lambda o, r, n, b: {"mode": "dry_run", "path": "x"})
    res = appmain._review_post_comment("octocat", "hello", 5, "본문")
    assert res["posted"] is False
    assert res["url"] is None


def test_gh_post_github_builds_comment_url(monkeypatch):
    """실제 게시(mode=github) → posted True + issuecomment URL 구성."""
    monkeypatch.setattr(appmain, "_gh_post", lambda o, r, n, b: {"mode": "github", "comment_id": 999})
    res = appmain._review_post_comment("octocat", "hello", 5, "본문")
    assert res["posted"] is True
    assert res["url"] == "https://github.com/octocat/hello/pull/5#issuecomment-999"


@pytest.mark.asyncio
async def test_get_review_returns_stored(client, monkeypatch):
    """GET /review/{owner}/{repo}/{pr} → 저장된 {verdict, comment, issues} 반환."""
    stored = {"verdict": "rework", "comment": "본문", "issues": [{"rule_id": "PERF-1"}]}
    monkeypatch.setattr(appmain, "_get_stored_review", lambda o, r, n: stored)
    resp = await client.get("/review/octocat/hello/5")
    assert resp.status_code == 200
    data = resp.json()
    assert data["found"] is True
    assert data["verdict"] == "rework"
    assert data["comment"] == "본문"
    assert data["issues"] == [{"rule_id": "PERF-1"}]


@pytest.mark.asyncio
async def test_get_review_empty_when_missing(client, monkeypatch):
    """저장 없음 → 빈 결과(found False), 200."""
    monkeypatch.setattr(appmain, "_get_stored_review", lambda o, r, n: None)
    resp = await client.get("/review/octocat/hello/404")
    assert resp.status_code == 200
    data = resp.json()
    assert data["found"] is False
    assert data["verdict"] is None
    assert data["issues"] == []
