"""DB 저장 — scan_issues INSERT + scan_summaries UPSERT.

로컬 데모: SQLite (dev3_demo.db) — 자격증명 없이 동작.
GCP 운영: persist_pg(scan_id, outputs, conn=None) — POSTGRES_URL(.env) 사용.

scan_executions 행은 Dev1이 생성; Dev3는 주어진 scan_id로 자식 행만 추가.
"""
from __future__ import annotations

import json
import logging
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

log = logging.getLogger(__name__)

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
    sub_category TEXT,
    code_context TEXT,
    github_id            TEXT,
    code_snippet         TEXT,
    programming_language TEXT,
    framework            TEXT,
    framework_version    TEXT
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
CREATE TABLE IF NOT EXISTS review_results (
    owner      TEXT NOT NULL,
    repo       TEXT NOT NULL,
    pr_number  INTEGER NOT NULL,
    verdict    TEXT NOT NULL,
    comment    TEXT,
    issues     TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    PRIMARY KEY (owner, repo, pr_number)
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
                    keyword,sub_category,code_context,
                    github_id,code_snippet,programming_language,framework,framework_version)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (scan_id, out.agent, i.severity, i.rule_id, i.file, i.line,
                 i.message, i.suggestion, i.keyword,
                 i.sub_category, i.code_context,
                 i.github_id, i.code_snippet, i.programming_language,
                 i.framework, i.framework_version),
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
# 리뷰 결과 저장/조회 — m3 /review 가 산출한 {verdict, comment, issues} 보관.
# (owner, repo, pr_number) 기준 UPSERT. 프론트(GET /review)가 읽어 표시한다.
# scan_issues 와 별개: verdict·comment 를 담아야 하므로 전용 테이블 사용.
# ════════════════════════════════════════════════════════════════════

def save_review(owner, repo, pr_number, verdict, comment, issues) -> None:
    """리뷰 결과 1건을 (owner, repo, pr_number) 키로 UPSERT 저장."""
    conn = _conn()
    try:
        conn.execute(
            """INSERT INTO review_results(owner,repo,pr_number,verdict,comment,issues)
               VALUES(?,?,?,?,?,?)
               ON CONFLICT(owner,repo,pr_number) DO UPDATE SET
                 verdict=excluded.verdict, comment=excluded.comment,
                 issues=excluded.issues, created_at=datetime('now')""",
            (owner, repo, int(pr_number), verdict, comment,
             json.dumps(issues, ensure_ascii=False)),
        )
        conn.commit()
    finally:
        conn.close()


def get_review(owner, repo, pr_number):
    """저장된 리뷰 결과를 dict 로 반환. 없으면 None."""
    conn = _conn()
    try:
        row = conn.execute(
            "SELECT verdict, comment, issues FROM review_results "
            "WHERE owner=? AND repo=? AND pr_number=?",
            (owner, repo, int(pr_number)),
        ).fetchone()
    finally:
        conn.close()
    if not row:
        return None
    verdict, comment, issues_json = row
    return {
        "verdict": verdict,
        "comment": comment or "",
        "issues": json.loads(issues_json) if issues_json else [],
    }


# ════════════════════════════════════════════════════════════════════
# review_issue 적재 — dev4 공용 테이블. m3는 자기 분석 이슈(test_verification·
# performance)만 한 행씩 넣는다. 풍부한 필드(keyword/code_snippet/
# name_of_function/framework…)는 run() 의 list[AgentOutput] Issue 에만 살아있으므로
# enrich 끝난 그 outputs 를 그대로 받는다(IssueItem 응답은 버려서 못 씀).
#
# 컬럼 매핑(review_issue ← m3 Issue/AgentOutput): id/pull_request_id/user_id/
# created_at 은 m3가 넣지 않음(dev4·DB 기본값). 나머지 12개 내용 컬럼만 INSERT.
# severity 는 REVIEW_SEVERITY_MAP 한 곳에서만 매핑(dev4 합의 시 여기만 수정).
# ════════════════════════════════════════════════════════════════════

# 실 GCP review_issue CHECK 허용값 = critical/high/medium/low. m3 3단계 → 그 4단계로 매핑.
# (Critical→critical, Major→high, Minor→medium. dev4 합의 시 이 dict 한 곳만 수정.)
REVIEW_SEVERITY_MAP = {"Critical": "critical", "Major": "high", "Minor": "medium"}

# 로컬·테스트용 스키마: id/created_at 은 DB 기본값, pull_request_id/user_id 는 NULL 허용.
REVIEW_ISSUE_SCHEMA = """
CREATE TABLE IF NOT EXISTS review_issue (
    id                   TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    pull_request_id      TEXT,
    user_id              TEXT,
    github_id            TEXT,
    agent                TEXT,
    severity             TEXT,
    keyword              TEXT,
    sub_category         TEXT,
    code_context         TEXT,
    code_snippet         TEXT,
    suggestion           TEXT,
    programming_language TEXT,
    framework            TEXT,
    framework_version    TEXT,
    name_of_function     TEXT,
    created_at           TEXT DEFAULT (datetime('now'))
);
"""

# id/pull_request_id/user_id/created_at 은 생략 → DB 기본값/NULL. 12개 내용 컬럼만.
_REVIEW_ISSUE_COLUMNS = (
    "github_id", "agent", "severity", "keyword", "sub_category",
    "code_context", "code_snippet", "suggestion", "programming_language",
    "framework", "framework_version", "name_of_function",
)


def _review_issue_row(agent: str, i) -> tuple:
    """한 Issue → review_issue INSERT 값 12개(_REVIEW_ISSUE_COLUMNS 순서)."""
    return (
        i.github_id,
        agent,
        REVIEW_SEVERITY_MAP.get(i.severity, i.severity),
        i.keyword,
        i.sub_category,
        i.code_context,
        i.code_snippet,
        i.suggestion,
        i.programming_language,
        i.framework,
        i.framework_version,
        i.name_of_function,
    )


def persist_review_issue(outputs) -> None:
    """review_issue 적재(로컬 SQLite). outputs 안 모든 issue 를 각각 한 행으로.

    정직성: DB 미가용·예외 시 적재만 조용히 skip(예외를 위로 던지지 않음, 로그만).
    가짜 행을 만들지 않는다. 파라미터 바인딩(?)만 — f-string SQL 금지.
    """
    placeholders = ",".join("?" * len(_REVIEW_ISSUE_COLUMNS))
    sql = (
        "INSERT INTO review_issue ("
        + ",".join(_REVIEW_ISSUE_COLUMNS)
        + ") VALUES (" + placeholders + ")"
    )
    try:
        conn = sqlite3.connect(DB_PATH)
        try:
            conn.execute(REVIEW_ISSUE_SCHEMA)
            for out in outputs:
                for i in out.issues:
                    conn.execute(sql, _review_issue_row(out.agent, i))
            conn.commit()
        finally:
            conn.close()
    except Exception as exc:  # noqa: BLE001 — 적재만 정직하게 skip
        log.warning("review_issue persist skipped: %s: %s",
                    type(exc).__name__, exc)


def persist_review_issue_pg(outputs, github_pr_number,
                            repository_full_name, conn=None) -> None:
    """GCP Postgres review_issue 적재 — persist_pg 와 같은 형태(파라미터 %s).

    pull_request_id·user_id 는 m3가 내부 번호를 모르므로 직접 넣지 않고,
    아는 GitHub PR 번호(github_pr_number) + 레포 풀네임(repository_full_name)으로
    dev4 pull_requests 행을 찾아 그 행의 id(→pull_request_id)·user_id 를 서브쿼리로 채운다.
      ★ PR 번호는 레포마다 중복되므로(예: 데모 #2, 다른레포 #2 동시 존재) repository_full_name
        까지 매칭해야 정확히 1행 = 엉뚱한 레포 PR 에 붙는 오매칭 방지.
      → 매칭 행이 없으면(아직 미등록 PR) 0행 INSERT = 고아 행을 만들지 않음(정직).
    id·created_at 은 DB 기본값. conn 주입 시 커밋은 호출자가 제어(테스트 rollback).
    정직성: DB 미가용·예외 시 적재만 skip(예외 안 던짐, 로그만).

    ※ dev4 스키마 확정 시 아래 SQL 의 식별자만 수정:
       테이블 pull_requests / PK pr.id / pr.user_id /
       매칭 pr.github_pr_number · pr.repository_full_name.
    """
    content_ph = ",".join(["%s"] * len(_REVIEW_ISSUE_COLUMNS))
    insert_sql = (
        "INSERT INTO review_issue (pull_request_id,user_id,"
        + ",".join(_REVIEW_ISSUE_COLUMNS) + ") "
        "SELECT pr.id, pr.user_id, " + content_ph + " "
        "FROM pull_requests pr "
        "WHERE pr.github_pr_number = %s AND pr.repository_full_name = %s"
    )
    # 멱등: 재적재 시 중복 행 방지 — 그 PR·레포·agent 기존 행을 먼저 지운다
    # (scan_issues 의 DELETE WHERE scan_id,agent 패턴과 동일). review_issue 엔 dedup 키가 없음.
    delete_sql = (
        "DELETE FROM review_issue WHERE agent = %s AND pull_request_id IN "
        "(SELECT pr.id FROM pull_requests pr "
        " WHERE pr.github_pr_number = %s AND pr.repository_full_name = %s)"
    )
    own = conn is None
    try:
        if own:
            import psycopg2  # noqa: PLC0415
            conn = psycopg2.connect(_pg_url(), connect_timeout=10)
        with conn.cursor() as cur:
            for out in outputs:
                cur.execute(
                    delete_sql,
                    (out.agent, github_pr_number, repository_full_name),
                )
                for i in out.issues:
                    cur.execute(
                        insert_sql,
                        _review_issue_row(out.agent, i)
                        + (github_pr_number, repository_full_name),
                    )
        if own:
            conn.commit()
    except Exception as exc:  # noqa: BLE001 — 적재만 정직하게 skip
        log.warning("review_issue persist_pg skipped: %s: %s",
                    type(exc).__name__, exc)
    finally:
        if own and conn is not None:
            conn.close()


# 리뷰 페이지용 rich 행 조회 컬럼 — review_issue 에서 그대로 SELECT 하는 순서.
_REVIEW_ISSUE_FETCH_COLUMNS = (
    "agent", "severity", "keyword", "sub_category", "code_context",
    "code_snippet", "suggestion", "name_of_function",
    "programming_language", "framework",
)


def get_review_issues_pg(github_pr_number, repository_full_name,
                         conn=None) -> list[dict]:
    """리뷰 페이지용 — 그 PR의 m3 rich 행(review_issue)을 dict 목록으로 조회.

    매칭 기준은 적재(persist_review_issue_pg)와 동일: pull_requests 의
    github_pr_number + repository_full_name. m3 소유 agent 행만.
    정직성: DB 미가용·예외 시 빈 목록 반환(예외 안 던짐, 로그만).
    """
    sql = (
        "SELECT " + ",".join(f"ri.{c}" for c in _REVIEW_ISSUE_FETCH_COLUMNS) + " "
        "FROM review_issue ri "
        "JOIN pull_requests pr ON pr.id = ri.pull_request_id "
        "WHERE pr.github_pr_number = %s AND pr.repository_full_name = %s "
        "AND ri.agent IN ('test_verification','performance') "
        "ORDER BY ri.agent, ri.created_at"
    )
    own = conn is None
    try:
        if own:
            import psycopg2  # noqa: PLC0415
            conn = psycopg2.connect(_pg_url(), connect_timeout=10)
        with conn.cursor() as cur:
            cur.execute(sql, (github_pr_number, repository_full_name))
            rows = cur.fetchall()
        return [dict(zip(_REVIEW_ISSUE_FETCH_COLUMNS, r)) for r in rows]
    except Exception as exc:  # noqa: BLE001 — 조회만 정직하게 빈 목록
        log.warning("review_issue fetch skipped: %s: %s",
                    type(exc).__name__, exc)
        return []
    finally:
        if own and conn is not None:
            try:
                conn.close()
            except Exception:  # noqa: BLE001
                pass


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


_PLACEHOLDER_MARKERS = ("@host:", "password@host", "user:password")


def _is_placeholder_url(url: str) -> bool:
    return any(m in url for m in _PLACEHOLDER_MARKERS)


def _pg_url() -> str | None:
    url = os.getenv("POSTGRES_URL")
    if url and not _is_placeholder_url(url):
        return url
    env = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if os.path.exists(env):
        for line in open(env, encoding="utf-8"):
            line = line.strip()
            if line.startswith("POSTGRES_URL="):
                val = line.split("=", 1)[1]
                if not _is_placeholder_url(val):
                    return val
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
    persist_review_issue(outputs)  # scan_issues 저장 옆에 review_issue 저장 (같은 outputs)
    issues, summaries = _readback(inp.scan_id)
    print(f"[DB readback] scan_id={inp.scan_id}  ({DB_PATH})")
    print(f"-- scan_issues ({len(issues)} rows) --")
    for r in issues:
        print("  ", r)
    print(f"-- scan_summaries ({len(summaries)} rows) --")
    for r in summaries:
        print("  ", r)
    ri = sqlite3.connect(DB_PATH).execute(
        "SELECT count(*) FROM review_issue").fetchone()[0]
    print(f"-- review_issue ({ri} rows) --")
