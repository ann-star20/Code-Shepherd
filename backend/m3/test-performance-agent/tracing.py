"""실행 추적 — agent_traces 로깅.

로컬 데모: SQLite (dev3_demo.db).
GCP 운영: log_trace_pg(conn, ...) — agent_traces 실제 스키마에 맞춤.

GCP agent_traces 실제 스키마 제약:
  - status CHECK (running/success/fail/review) — 'partial_fail' 허용 안됨
    → Dev3 'partial_fail' → 'success' 매핑, 원인은 error_message + output_summary에 보존
  - task_id uuid 타입 → uuid 변환 성공 시 저장, 실패 시 NULL + output_summary에 원본 동봉
  - scan_id 전용 컬럼 없음 → output_summary JSON 텍스트에 동봉
  - execution_ms CHECK (>= 0) → max(0, ...) 보정
"""
from __future__ import annotations

import json
import os
import sqlite3
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dev3_demo.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS agent_traces (
    trace_id      TEXT PRIMARY KEY,
    agent_name    TEXT NOT NULL,
    task_id       TEXT,
    scan_id       INTEGER,
    status        TEXT,
    started_at    TEXT,
    ended_at      TEXT,
    execution_ms  INTEGER,
    error_message TEXT
);
"""

# GCP agent_traces.status CHECK 허용값 매핑
_GCP_STATUS: dict[str, str] = {
    "success":      "success",
    "fail":         "fail",
    "running":      "running",
    "review":       "review",
    "partial_fail": "success",   # partial_fail → success, 원인은 error_message에 보존
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def log_trace(trace_id: str, agent_name: str, task_id: str, scan_id: int,
              status: str, execution_ms: int,
              started_at: str | None = None,
              error_message: str | None = None) -> None:
    """SQLite 로컬 로깅 — 데모/오프라인용."""
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(SCHEMA)
    conn.execute(
        """INSERT INTO agent_traces
           (trace_id,agent_name,task_id,scan_id,status,started_at,ended_at,execution_ms,error_message)
           VALUES(?,?,?,?,?,?,?,?,?)
           ON CONFLICT(trace_id) DO UPDATE SET
             status=excluded.status, ended_at=excluded.ended_at,
             execution_ms=excluded.execution_ms, error_message=excluded.error_message""",
        (trace_id, agent_name, task_id, scan_id, status,
         started_at or _now(), _now(), execution_ms, error_message),
    )
    conn.commit()
    conn.close()


def _readback():
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(SCHEMA)
    rows = conn.execute(
        "SELECT trace_id,agent_name,task_id,scan_id,status,execution_ms,error_message "
        "FROM agent_traces"
    ).fetchall()
    conn.close()
    return rows


def log_trace_pg(conn, trace_id: str, agent_name: str, task_id, scan_id: int,
                 status: str, execution_ms: int,
                 started_at=None, ended_at=None,
                 error_message: str | None = None) -> None:
    """GCP Postgres agent_traces에 요약 1행 INSERT.

    conn 주입 필수 — 커밋은 호출자가 제어(테스트 rollback 가능).

    매핑 규칙:
      - status: partial_fail → 'success', 원인은 error_message + output_summary.dev3_status에 보존
      - task_id: uuid 문자열이면 컬럼에 저장, 아니면 NULL + output_summary에 원본 동봉
      - scan_id: output_summary JSON에 동봉
      - execution_ms: max(0, ...) 보정 (CHECK >= 0)
    """
    import uuid as _uuid

    now = datetime.now(timezone.utc)
    gstatus = _GCP_STATUS.get(status, "success")

    try:
        tid = str(_uuid.UUID(str(task_id)))
    except (ValueError, TypeError, AttributeError):
        tid = None

    note = error_message
    if status in ("partial_fail", "fail") and not note:
        note = f"[{status}]"

    out_summary = json.dumps(
        {"scan_id": scan_id, "task_id": str(task_id), "dev3_status": status},
        ensure_ascii=False,
    )

    with conn.cursor() as cur:
        cur.execute(
            """INSERT INTO agent_traces
               (trace_id, task_id, agent_name, status, started_at, ended_at,
                execution_ms, error_message, output_summary)
               VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (
                trace_id, tid, agent_name, gstatus,
                started_at or now, ended_at or now,
                max(0, int(execution_ms or 0)),
                note, out_summary,
            ),
        )


if __name__ == "__main__":
    import asyncio
    from main import run
    from contracts import Dev3Input, RepoInfo, Developer
    import time

    inp = Dev3Input(
        task_id="demo-task-trace",
        scan_id=99,
        pr_id="PR-demo",
        pr_diff="",
        repo=RepoInfo(clone_url="", commit_sha=""),
        developer=Developer(id="dev_01"),
    )
    repo = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "tests", "fixtures", "sample_repo")
    t0 = time.monotonic()
    outputs = asyncio.run(run(inp, repo_path=repo, store=False))
    ms = int((time.monotonic() - t0) * 1000)

    for out in outputs:
        log_trace(
            trace_id=f"demo-{out.agent}",
            agent_name=out.agent,
            task_id=inp.task_id,
            scan_id=inp.scan_id,
            status="success",
            execution_ms=ms,
        )

    print(f"[trace readback] ({DB_PATH})")
    for r in _readback():
        print("  ", r)
