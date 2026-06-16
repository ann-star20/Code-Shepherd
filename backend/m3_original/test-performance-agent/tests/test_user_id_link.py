"""Dev4 요청 — 이슈가 '사람(user)'에 연결되는지 확인.

연결 구조:
  scan_issues.scan_id  →  scan_executions(id)  →  그 행의 user_id
Dev3는 user_id를 직접 쓰지 않는다. scan_executions 행은 Dev1이 만들고(거기에
user_id가 들어감), Dev3는 주어진 scan_id로 scan_issues 자식 행만 추가한다.
즉 이슈→사람 추적은 scan_id 외래키로 성립한다.

⚠️ 컬럼명: GCP 실제 스키마는 `user_id uuid (FK users)`. 로컬 데모 SQLite는
역할은 같지만 컬럼명이 `developer_id`. (이름만 다르고 의미는 동일 — 합의: 로컬은
GCP 핸드오프 때 함께 정렬, 지금은 안 건드림.)

이 테스트는 '이슈 → 부모 스캔 행 → 사람 식별자' 조인이 성립함을 로컬에서 못박는다.
GCP 경로(user_id 컬럼)의 동일 검증은 test_task13_persist.py(POSTGRES_URL 필요)에 있음.
"""
import sqlite3

import persist as p
from contracts import (AgentOutput, Developer, Dev3Input, Issue, RepoInfo,
                       SummaryCount)


def test_issue_joins_back_to_person_via_scan_id(tmp_path):
    """scan_issues → scan_executions 조인으로 이슈가 사람 식별자에 닿는다."""
    inp = Dev3Input(
        task_id="t", scan_id=7, pr_id="PR", pr_diff="",
        repo=RepoInfo(clone_url="", commit_sha=""),
        developer=Developer(id="user-uuid-123"),
    )
    out = AgentOutput(
        task_id="t", scan_id=7, pr_id="PR", agent="performance",
        issues=[Issue(severity="Major", file="src/x.py", line=1,
                      message="N+1", rule_id="PERF-002")],
        summary=SummaryCount(major=1),
    )

    db = str(tmp_path / "d.db")
    orig = p.DB_PATH
    p.DB_PATH = db
    try:
        # inp 제공 → scan_executions 부모 행 생성(사람 식별자 포함)
        p.persist(7, [out], inp=inp)
    finally:
        p.DB_PATH = orig

    conn = sqlite3.connect(db)
    conn.executescript(p.SCHEMA)
    row = conn.execute(
        "SELECT se.developer_id "  # GCP에서는 user_id (동일 역할)
        "FROM scan_issues si "
        "JOIN scan_executions se ON si.scan_id = se.id "
        "WHERE si.scan_id = 7"
    ).fetchone()
    conn.close()

    # 이슈 → 스캔 → 사람 식별자까지 추적 가능
    assert row == ("user-uuid-123",)
