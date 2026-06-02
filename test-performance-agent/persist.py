"""DB 저장 — scan_issues INSERT + scan_summaries UPSERT.

로컬 데모: SQLite (dev3_demo.db) — 자격증명 없이 동작.
GCP 운영: persist_pg(scan_id, outputs, conn=None) — POSTGRES_URL(.env) 사용.

scan_executions 행은 Dev1이 생성; Dev3는 주어진 scan_id로 자식 행만 추가.
"""
from __future__ import annotations

import json
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dev3_demo.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS scan_executions (
    id           INTEGER PRIMARY KEY,
    task_id      TEXT NOT NULL,
    pr_id        TEXT,
    developer_id TEXT,
    scanned_at   TEXT DEFAULT (datetime('now')),
    execution_ms INTEGER
);
CREATE TABLE IF NOT EXISTS scan_issues (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    scan_id    INTEGER NOT NULL REFERENCES scan_executions(id),
    agent      TEXT NOT NULL CHECK(agent IN
                 ('static_analysis','security_scan','test_verification','performance')),
    severity   TEXT NOT NULL CHECK(severity IN ('Critical','Major','Minor')),
    rule_id    TEXT NOT NULL,
    file       TEXT,
    line       INTEGER,
    message    TEXT,
    suggestion TEXT,
    keyword      TEXT,
    sub_keyword  TEXT,
    metric_value TEXT
);
CREATE TABLE IF NOT EXISTS scan_summaries (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    scan_id  INTEGER NOT NULL REFERENCES scan_executions(id),
    agent    TEXT NOT NULL CHECK(agent IN
               ('static_analysis','security_scan','test_verification','performance')),
    critical INTEGER DEFAULT 0,
    major    INTEGER DEFAULT 0,
    minor    INTEGER DEFAULT 0,
    metrics  TEXT,
    UNIQUE(scan_id, agent)
);
"""


def _conn():
    c = sqlite3.connect(DB_PATH)
    c.executescript(SCHEMA)
    return c


def persist(scan_id: int, outputs, inp=None) -> None:
    """SQLite 로컬 저장. scan_executions는 inp 제공 시만 생성."""
    conn = _conn()
    if inp is not None:
        conn.execute(
            "INSERT OR IGNORE INTO scan_executions(id, task_id, pr_id, developer_id) VALUES(?,?,?,?)",
            (scan_id, inp.task_id, inp.pr_id, inp.developer.id),
        )
    conn.execute("DELETE FROM scan_issues WHERE scan_id=?", (scan_id,))
    for out in outputs:
        for i in out.issues:
            conn.execute(
                """INSERT INTO scan_issues
                   (scan_id,agent,severity,rule_id,file,line,message,suggestion,
                    keyword,sub_keyword,metric_value)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                (scan_id, out.agent, i.severity, i.rule_id, i.file, i.line,
                 i.message, i.suggestion, i.keyword, i.sub_keyword, i.metric_value),
            )
        s = out.summary
        conn.execute(
            """INSERT INTO scan_summaries(scan_id,agent,critical,major,minor,metrics)
               VALUES(?,?,?,?,?,?)
               ON CONFLICT(scan_id,agent) DO UPDATE SET
                 critical=excluded.critical, major=excluded.major,
                 minor=excluded.minor, metrics=excluded.metrics""",
            (scan_id, out.agent, s.critical, s.major, s.minor,
             json.dumps(out.metrics) if out.metrics else None),
        )
    conn.commit()
    conn.close()


def _readback(scan_id: int):
    conn = _conn()
    issues = conn.execute(
        "SELECT agent,severity,rule_id,file,line FROM scan_issues "
        "WHERE scan_id=? ORDER BY agent,id",
        (scan_id,),
    ).fetchall()
    summaries = conn.execute(
        "SELECT agent,critical,major,minor,metrics FROM scan_summaries "
        "WHERE scan_id=? ORDER BY agent",
        (scan_id,),
    ).fetchall()
    conn.close()
    return issues, summaries


# ════════════════════════════════════════════════════════════════════
# GCP 운영 경로 — PostgreSQL (psycopg2). POSTGRES_URL(.env)로 연결.
# scan_executions 행 생성 안 함(Dev1 책임). 주어진 scan_id로 자식 행만.
# conn 주입 시 커밋은 호출자가 제어(테스트는 rollback 가능).
# ════════════════════════════════════════════════════════════════════

PG_SCAN_SUMMARIES_DDL = """
CREATE TABLE IF NOT EXISTS scan_summaries (
    id        bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    scan_id   bigint NOT NULL REFERENCES scan_executions(id) ON DELETE CASCADE,
    agent     text NOT NULL CHECK (agent IN
                ('static_analysis','security_scan','test_verification','performance')),
    critical  int NOT NULL DEFAULT 0,
    major     int NOT NULL DEFAULT 0,
    minor     int NOT NULL DEFAULT 0,
    metrics   jsonb,
    CONSTRAINT uq_scan_summaries_scan_agent UNIQUE (scan_id, agent)
);
"""


def _pg_url() -> str | None:
    url = os.getenv("POSTGRES_URL")
    if url:
        return url
    env = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if os.path.exists(env):
        for line in open(env, encoding="utf-8"):
            line = line.strip()
            if line.startswith("POSTGRES_URL="):
                return line.split("=", 1)[1]
    return None


def ensure_scan_summaries(conn) -> None:
    """scan_summaries가 없으면 생성(합의 DDL, IF NOT EXISTS)."""
    with conn.cursor() as cur:
        cur.execute(PG_SCAN_SUMMARIES_DDL)


def persist_pg(scan_id: int, outputs, conn=None) -> None:
    """GCP Postgres: scan_issues INSERT + scan_summaries UPSERT.

    conn 주입 시 커밋은 호출자가 제어(테스트 rollback 가능).
    미주입 시 자체 connect + commit + close.
    """
    import psycopg2
    from psycopg2.extras import Json

    own = conn is None
    if own:
        conn = psycopg2.connect(_pg_url(), connect_timeout=10)
    try:
        ensure_scan_summaries(conn)
        with conn.cursor() as cur:
            for out in outputs:
                cur.execute(
                    "DELETE FROM scan_issues WHERE scan_id=%s AND agent=%s",
                    (scan_id, out.agent),
                )
                for i in out.issues:
                    cur.execute(
                        """INSERT INTO scan_issues
                           (scan_id,agent,severity,rule_id,file,line,message,suggestion)
                           VALUES(%s,%s,%s,%s,%s,%s,%s,%s)""",
                        (scan_id, out.agent, i.severity, i.rule_id, i.file, i.line,
                         i.message, i.suggestion),
                    )
                s = out.summary
                cur.execute(
                    """INSERT INTO scan_summaries(scan_id,agent,critical,major,minor,metrics)
                       VALUES(%s,%s,%s,%s,%s,%s)
                       ON CONFLICT (scan_id,agent) DO UPDATE SET
                         critical=excluded.critical, major=excluded.major,
                         minor=excluded.minor, metrics=excluded.metrics""",
                    (scan_id, out.agent, s.critical, s.major, s.minor,
                     Json(out.metrics) if out.metrics else None),
                )
        if own:
            conn.commit()
    finally:
        if own:
            conn.close()


if __name__ == "__main__":
    import asyncio
    from main import run

    # 데모 실행: fixture 입력 → run(store=False) → persist()
    from contracts import Dev3Input, RepoInfo, Developer

    inp = Dev3Input(
        task_id="demo-task-persist",
        scan_id=99,
        pr_id="PR-demo",
        pr_diff="",
        repo=RepoInfo(clone_url="", commit_sha=""),
        developer=Developer(id="dev_01"),
    )
    repo = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "tests", "fixtures", "sample_repo")
    outputs = asyncio.run(run(inp, repo_path=repo, store=False))
    persist(inp.scan_id, outputs)
    issues, summaries = _readback(inp.scan_id)
    print(f"[DB readback] scan_id={inp.scan_id}  ({DB_PATH})")
    print(f"-- scan_issues ({len(issues)} rows) --")
    for r in issues:
        print("  ", r)
    print(f"-- scan_summaries ({len(summaries)} rows) --")
    for r in summaries:
        print("  ", r)
