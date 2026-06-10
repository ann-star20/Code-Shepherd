"""E2E 흐름 검증 — 'PR 신호가 왔다'고 가정하고 process_pr 를 처음부터 끝까지 흘려,
review_issue 적재가 오류 없이 일어나는지 실제 분석 결과로 확인한다.

외부 경계만 대체(자격증명 불필요):
  - clone_repo      → 실 fixture 레포 경로 (진짜 clone 안 함)
  - fetch_pr_diff   → 실 fixture PR diff
  - _persist_to_db  → scan_issues 는 이 검증 대상 아님 → 더미 id
  - DB 소켓         → 진짜 Postgres 없음 → 기록용 가짜 연결(_RecConn) 주입
분석(dev3 골든탐지기)·어댑터 dict 변환·review_issue 적재 로직은 전부 '진짜' 실행.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import gateway
from registry import PRContext, clear, register_fn

_FIX = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                    "..", "..", "test-performance-agent", "tests", "fixtures")
_SAMPLE_REPO = os.path.abspath(os.path.join(_FIX, "sample_repo"))
_SAMPLE_DIFF = os.path.abspath(os.path.join(_FIX, "sample_pr.diff"))


class _RecCursor:
    def __init__(self, calls):
        self._calls = calls

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, sql, params=None):
        self._calls.append((sql, params))


class _RecConn:
    """기록용 가짜 Postgres 연결 — 실행될 SQL·파라미터를 그대로 모은다."""
    def __init__(self):
        self.calls: list = []

    def cursor(self):
        return _RecCursor(self.calls)

    def commit(self):
        pass

    def close(self):
        pass


def test_pr_signal_flows_through_and_persists_review_issue(monkeypatch):
    # ── 1) PR 신호 수신 시뮬레이션 (webhook → PRContext) ──
    ctx = PRContext(
        repo_full_name="demoorg/demo", clone_url="https://github.com/demoorg/demo.git",
        pr_number=101, commit_sha="abc123", branch="feature/x", author="junior_dev_01",
    )

    # ── 2) 외부 경계만 대체 ──
    monkeypatch.setattr(gateway, "clone_repo", lambda c: _SAMPLE_REPO)
    monkeypatch.setattr(
        gateway, "fetch_pr_diff",
        lambda c: open(_SAMPLE_DIFF, encoding="utf-8").read())
    monkeypatch.setattr(gateway, "_persist_to_db", lambda *a, **k: 999)

    # review_issue 적재는 '진짜' 실행하되, DB 소켓만 기록용 가짜로 주입해 결과 캡처
    rec = _RecConn()
    real_persist = gateway._persist_review_issue_to_db
    monkeypatch.setattr(
        gateway, "_persist_review_issue_to_db",
        lambda c, results, conn=None: real_persist(c, results, conn=rec))

    # 분석 에이전트: dev3 하나만 등록 (import 캐시 무관하게 확정 등록)
    import agents.dev3_adapter as d3
    clear()
    register_fn("test_verification_and_performance", d3.analyze)

    # ── 3) 흐름 전체 실행 (clone→diff→분석→적재) — 예외 없이 끝나야 함 ──
    out = gateway.process_pr(ctx, do_comment=False)

    # ── 4) review_issue 에 진짜 행이 적재됐는지 확인 ──
    inserts = [(s, p) for s, p in rec.calls if s.strip().upper().startswith("INSERT")]
    assert inserts, "PR 흐름을 다 돌렸는데 review_issue 적재(INSERT)가 0건"

    for sql, params in inserts:
        assert "review_issue" in sql.lower()
        # params = (github_id, agent, severity, ... , name_of_function, pr_number)
        agent, severity = params[1], params[2]
        assert agent in ("test_verification", "performance")
        assert severity in ("critical", "high", "medium", "low")  # DB 4단계 스케일
        assert params[-2] == 101                            # PR번호 링크
        assert params[-1] == "demoorg/demo"                 # repo 링크

    # ── 사람이 눈으로 볼 수 있게 적재 내용 출력 ──
    print(f"\n[E2E] PR #{ctx.pr_number} flow done - issue_count={out.get('issue_count')}")
    print(f"[E2E] review_issue INSERT rows: {len(inserts)}")
    for _, p in inserts:
        print(f"   agent={p[1]:<18} severity={p[2]:<8} "
              f"name_of_function={p[11]!r:<18} github_id={p[0]!r}")
