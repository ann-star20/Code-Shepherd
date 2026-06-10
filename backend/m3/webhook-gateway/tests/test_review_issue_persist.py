"""게이트웨이 review_issue 적재 — PR 처리 뒤 dev4 공용 표에 m3 이슈를 넣는다.

격리 단위 테스트: 실제 DB 없이 가짜 연결(_FakeConn)로 SQL 모양·파라미터 검증.
- m3 자기 이슈(test_verification/performance)만 넣는다 (security_scan 등은 제외).
- pull_request_id·user_id 는 m3가 모르므로 PR번호(github_pr_number)로 pull_requests 링크.
- 멱등: 그 PR·agent 기존 행 DELETE 후 INSERT (재시도해도 중복 안 쌓임).
- 넣을 m3 이슈가 없으면 연결도 안 함(조용).
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import gateway
from registry import PRContext


class _FakeCursor:
    def __init__(self, calls):
        self._calls = calls

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, sql, params=None):
        self._calls.append((sql, params))


class _FakeConn:
    def __init__(self):
        self.calls: list = []
        self.committed = False

    def cursor(self):
        return _FakeCursor(self.calls)

    def commit(self):
        self.committed = True

    def close(self):
        pass


def _ctx() -> PRContext:
    return PRContext(
        repo_full_name="owner/repo", clone_url="https://x.git",
        pr_number=7, commit_sha="sha", branch="feature", author="junior",
    )


def _perf_issue() -> dict:
    return {
        "severity": "Major", "_agent": "performance", "github_id": "dev1",
        "keyword": "성능", "sub_category": "N+1", "code_context": "설명",
        "code_snippet": "def slow(): ...", "suggestion": "고쳐",
        "name_of_function": "slow", "programming_language": "python",
        "framework": "django", "framework_version": "4.2",
        "rule_id": "PERF-002", "file": "a.py", "line": 3, "message": "N+1",
    }


def test_persists_m3_review_issue_with_pr_link():
    conn = _FakeConn()
    results = {"test_verification_and_performance": [_perf_issue()]}

    gateway._persist_review_issue_to_db(_ctx(), results, conn=conn)

    kinds = [s.strip().split()[0].upper() for s, _ in conn.calls]
    assert "DELETE" in kinds and "INSERT" in kinds
    assert kinds.index("DELETE") < kinds.index("INSERT")  # 먼저 지우고 넣음

    ins_sql, ins_params = next(
        (s, p) for s, p in conn.calls if s.strip().upper().startswith("INSERT"))
    low = ins_sql.lower()
    assert "review_issue" in low
    # PR번호 + repo 로 함께 링크 (github_pr_number 는 repo마다 중복되므로 repo 필수)
    assert "pull_requests" in low and "github_pr_number" in low
    assert "repository_full_name" in low
    assert "%s" in ins_sql                       # 파라미터 바인딩만
    assert "slow" not in ins_sql                 # 값이 SQL에 안 박힘
    assert "slow" in ins_params                  # name_of_function 살아옴
    assert "performance" in ins_params
    assert "high" in ins_params                  # severity Major→high (DB 4단계)
    assert 7 in ins_params                       # PR번호
    assert "owner/repo" in ins_params            # repo (ctx.repo_full_name)

    del_sql, del_params = next(
        (s, p) for s, p in conn.calls if s.strip().upper().startswith("DELETE"))
    assert "repository_full_name" in del_sql.lower()
    assert "performance" in del_params and 7 in del_params
    assert "owner/repo" in del_params


def test_skips_non_m3_agents_and_empty():
    # 비-m3 이슈만 → 넣을 게 없으니 연결조차 안 함(conn 미주입이어도 예외 없음)
    results = {"x": [{"severity": "Major", "_agent": "security_scan",
                      "rule_id": "S", "file": "a", "line": 1, "message": "m"}]}
    gateway._persist_review_issue_to_db(_ctx(), results)  # 예외 없이 조용히 통과


def test_ignores_issue_without_agent_tag():
    """_agent 태그 없는(=m3 소속 불명) 이슈는 review_issue 에 안 넣는다(오분류 방지).

    _normalize_agent 는 미상값을 'performance' 로 기본화하므로, 필터에 쓰면
    태그 없는 남의 이슈가 m3 것으로 잘못 들어간다. 필터는 원본 _agent 로만.
    """
    conn = _FakeConn()
    results = {"other": [{"severity": "Major", "rule_id": "X", "file": "a",
                          "line": 1, "message": "m"}]}  # _agent 키 없음
    gateway._persist_review_issue_to_db(_ctx(), results, conn=conn)
    inserts = [s for s, _ in conn.calls if s.strip().upper().startswith("INSERT")]
    assert inserts == [], "_agent 없는 이슈를 review_issue 에 넣으면 안 됨"


def test_process_pr_persists_review_issue(monkeypatch):
    called: dict = {}
    monkeypatch.setattr(gateway, "clone_repo", lambda ctx: "/tmp/w")
    monkeypatch.setattr(gateway, "fetch_pr_diff", lambda ctx: "diff")
    monkeypatch.setattr(gateway, "run_all_agents", lambda ctx: {"a": []})
    monkeypatch.setattr(gateway, "_persist_to_db", lambda *a, **k: 1)
    monkeypatch.setattr(
        gateway, "_persist_review_issue_to_db",
        lambda ctx, results, conn=None: called.setdefault("ok", True))

    gateway.process_pr(_ctx(), do_comment=False)

    assert "ok" in called, "process_pr가 review_issue 적재를 호출하지 않음"
