"""버그 §3.6 — execution_ms(분석 소요시간)가 scan_executions에 저장되는지.

고립 단위 테스트: 실제 DB 없이 가짜 연결(Fake conn)로 검증.
  1) _persist_to_db 가 scan_executions INSERT에 execution_ms 를 포함하는가
  2) process_pr 가 분석 시간을 재서 _persist_to_db 로 넘기는가
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import gateway
from registry import PRContext


# ─── 가짜 DB 연결 (psycopg2 불필요) ─────────────────────────────────────────────
class _FakeCursor:
    def __init__(self, calls):
        self._calls = calls

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, sql, params=None):
        self._calls.append((sql, params))

    def fetchone(self):
        return (999,)  # scan_executions.id


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


# ─── 1) INSERT에 execution_ms 포함 ─────────────────────────────────────────────
def test_scan_executions_insert_includes_execution_ms():
    conn = _FakeConn()
    results = {"test_verification_and_performance": []}

    scan_id = gateway._persist_to_db(_ctx(), results, [], execution_ms=1234, conn=conn)

    assert scan_id == 999
    insert_sql, params = conn.calls[0]          # 첫 호출 = scan_executions INSERT
    assert "scan_executions" in insert_sql
    assert "execution_ms" in insert_sql
    assert 1234 in params


# ─── 2) process_pr가 시간을 재서 넘김 ──────────────────────────────────────────
def test_process_pr_measures_and_passes_execution_ms(monkeypatch):
    captured: dict = {}

    monkeypatch.setattr(gateway, "clone_repo", lambda ctx: "/tmp/work")
    monkeypatch.setattr(gateway, "fetch_pr_diff", lambda ctx: "diff")
    monkeypatch.setattr(gateway, "run_all_agents", lambda ctx: {})

    def fake_persist(ctx, results, all_issues, execution_ms, conn=None):
        captured["ms"] = execution_ms
        return 1

    monkeypatch.setattr(gateway, "_persist_to_db", fake_persist)

    gateway.process_pr(_ctx(), do_comment=False)

    assert "ms" in captured, "process_pr가 execution_ms를 _persist_to_db로 넘기지 않음"
    assert isinstance(captured["ms"], int) and captured["ms"] >= 0
