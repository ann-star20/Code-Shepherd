"""m3 /review (집계→코멘트→게시→저장) + GET /review 조회 계약 테스트.

외부 의존(github_poster·llm_refiner·persist)은 app.main seam 을 monkeypatch 해 고립한다.
- 판정(verdict)은 실제 pr-comment-agent aggregator 를 통해 산출되는지 검증(재사용).
- 게시 호출됨/저장 호출됨/verdict 반환 검증.
- 토큰 없음/게시 실패 → comment_posted=false + 사유, 예외 안 터짐(정직).
- GET /review: 저장된 결과 반환 / 없으면 빈 결과.
"""
import sys
from types import SimpleNamespace

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

    def fake_refine(combined, verdict, skill, metrics=None):
        calls["refine"].append((list(combined), verdict, skill, metrics))
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

    monkeypatch.setattr(appmain, "_review_refine", lambda c, v, s, m=None: "본문")
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


# ════════════════════════════════════════════════════════════════════
# 7B — /review 가 코멘트 생성 직전, 합쳐진 이슈의 message 로 사내규칙(RAG)을
# 검색해 rag_context 를 채운다. 검색기(search_convention)는 _rag_search seam 으로
# mock 한다(실 GCP 안 붙임). 포맷(format_context)은 7A 것을 실제로 재사용한다.
# 합격 기준: 채운 rag_context 가 refine 입력까지 전달 / 빈결과·예외는 빈 인용 200 /
# RAG_ENABLED 꺼짐(기본)이면 검색조차 안 함(평소·테스트 부하 0).
# ════════════════════════════════════════════════════════════════════

_FAKE_RAG_DOCS = [
    {
        "content": "N+1 쿼리 금지: 반복문 안에서 쿼리하지 말고 selectinload 로 한 번에 로드한다.",
        "doc_title": "ORM 사용 가이드",
        "source_url": "http://kms/orm",
        "score": 0.91,
    }
]


@pytest.mark.asyncio
async def test_review_fills_rag_context_before_refine(client, spies, monkeypatch):
    """RAG_ENABLED + 검색 성공 → 각 이슈 message 로 검색한 사내규칙이 rag_context 로
    채워져 refine 입력 이슈까지 전달된다(📖·제목·본문 포함 — 포맷은 7A 재사용)."""
    monkeypatch.setenv("RAG_ENABLED", "1")
    seen: list[str] = []

    def fake_search(message):
        seen.append(message)
        return _FAKE_RAG_DOCS

    monkeypatch.setattr(appmain, "_rag_search", fake_search)

    payload = _request(
        performance=_result("performance", [_issue("Major", "PERF-001", message="N+1 의심")])
    )
    resp = await client.post("/review", json=payload)
    assert resp.status_code == 200

    # 검색은 이슈 message 통째로 호출됐다.
    assert seen == ["N+1 의심"]
    # refine 입력 combined 이슈에 rag_context 가 실려 있다.
    combined = spies["refine"][0][0]
    assert len(combined) == 1
    rag = combined[0]["rag_context"]
    assert "📖" in rag
    assert "ORM 사용 가이드" in rag
    assert "selectinload" in rag


@pytest.mark.asyncio
async def test_review_rag_empty_search_leaves_context_empty(client, spies, monkeypatch):
    """검색 결과 없음(빈 리스트) → rag_context 빈 채로, /review 정상 200(가짜 인용 금지)."""
    monkeypatch.setenv("RAG_ENABLED", "1")
    monkeypatch.setattr(appmain, "_rag_search", lambda m: [])

    payload = _request(performance=_result("performance", [_issue("Major", "PERF-001")]))
    resp = await client.post("/review", json=payload)
    assert resp.status_code == 200
    combined = spies["refine"][0][0]
    assert combined[0]["rag_context"] == ""


@pytest.mark.asyncio
async def test_review_rag_search_exception_is_honest(client, spies, monkeypatch):
    """검색이 예외를 던져도 → rag_context 빈 채로 남고 /review 는 그대로 200(500 안 됨)."""
    monkeypatch.setenv("RAG_ENABLED", "1")

    def boom(message):
        raise RuntimeError("GCP 연결 실패")

    monkeypatch.setattr(appmain, "_rag_search", boom)

    payload = _request(security_scan=_result("security_scan", [_issue("Critical", "SEC-001")]))
    resp = await client.post("/review", json=payload)
    assert resp.status_code == 200
    assert resp.json()["verdict"] == "escalate"  # 판정 회귀 없음
    combined = spies["refine"][0][0]
    assert combined[0]["rag_context"] == ""


@pytest.mark.asyncio
async def test_review_rag_disabled_skips_search(client, spies, monkeypatch):
    """RAG_ENABLED 꺼짐(기본) → 검색 자체를 호출하지 않고 rag_context 빈 채(평소·테스트 부하 0)."""
    monkeypatch.delenv("RAG_ENABLED", raising=False)
    called: list[str] = []
    monkeypatch.setattr(appmain, "_rag_search", lambda m: called.append(m) or [])

    payload = _request(performance=_result("performance", [_issue("Major", "PERF-001")]))
    resp = await client.post("/review", json=payload)
    assert resp.status_code == 200
    assert called == []  # 검색 미호출
    combined = spies["refine"][0][0]
    assert combined[0]["rag_context"] == ""


# ════════════════════════════════════════════════════════════════════
# 7D — 코멘트 '📊 지표 줄'용 측정값(metrics)을 /verify→/review→코멘트로 흘린다.
# 공유 계약 M3VerifyResponse 에 optional metrics(기본 None) additive 추가.
# coverage_line(0~1) → coverage_pct(0~100). 측정값 없으면 빈 dict(정직 — 가짜 0% 금지).
# ════════════════════════════════════════════════════════════════════


def test_review_metrics_extracts_coverage_pct():
    """test_verification.metrics.coverage_line(분수) → coverage_pct(%, 반올림)."""
    payload = SimpleNamespace(
        test_verification=SimpleNamespace(metrics={"coverage_line": 0.726}),
        performance=None,
    )
    assert appmain._review_metrics(payload) == {"coverage_pct": 73}


def test_review_metrics_empty_without_metrics():
    """metrics 없음(None) → 빈 dict (지표 줄 생략 → 가짜 숫자 금지)."""
    payload = SimpleNamespace(
        test_verification=SimpleNamespace(metrics=None),
        performance=None,
    )
    assert appmain._review_metrics(payload) == {}


def test_review_metrics_carries_max_complexity_when_present():
    """performance.metrics 에 max_complexity 가 있으면(향후) 그대로 전달."""
    payload = SimpleNamespace(
        test_verification=SimpleNamespace(metrics={"coverage_line": 0.5}),
        performance=SimpleNamespace(metrics={"max_complexity": 3}),
    )
    assert appmain._review_metrics(payload) == {"coverage_pct": 50, "max_complexity": 3}


@pytest.mark.asyncio
async def test_review_passes_metrics_to_refine(client, spies):
    """test_verification 에 coverage metrics 가 실려오면 → coverage_pct 로 변환돼 refine 까지 전달."""
    tv = _result("test_verification", [_issue("Minor", "TEST-001")])
    tv["metrics"] = {"coverage_line": 0.72}
    payload = _request(test_verification=tv)
    resp = await client.post("/review", json=payload)
    assert resp.status_code == 200
    # spies fake_refine 가 받은 4번째 인자(metrics)
    metrics = spies["refine"][0][3]
    assert metrics == {"coverage_pct": 72}


@pytest.mark.asyncio
async def test_review_no_metrics_passes_empty_to_refine(client, spies):
    """metrics 없이 온 경우 → refine 에 빈 dict 전달(지표 줄 생략)."""
    payload = _request(performance=_result("performance", [_issue("Major", "PERF-001")]))
    resp = await client.post("/review", json=payload)
    assert resp.status_code == 200
    assert spies["refine"][0][3] == {}
