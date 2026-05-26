import os
import json
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import text

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://user:password@localhost:5432/dev2_db"
)

# [CLAUDE.md §10-3] Lazy 초기화 패턴
# asyncpg 미설치 환경(CI/테스트)에서 db.py import 시 에러가 나지 않도록
# create_async_engine + sessionmaker를 최초 사용 시점까지 지연한다.
_engine = None
_session_factory = None


def _get_session_factory():
    """asyncpg가 실제로 필요한 시점에만 엔진+세션팩토리를 초기화한다."""
    global _engine, _session_factory
    if _session_factory is None:
        _engine = create_async_engine(DATABASE_URL)
        _session_factory = sessionmaker(
            _engine, class_=AsyncSession, expire_on_commit=False
        )
    return _session_factory


def AsyncSessionLocal():
    """
    AsyncSession 컨텍스트 매니저를 반환한다.

    사용 패턴:
        async with AsyncSessionLocal() as s:
            await s.execute(...)

    최초 호출 시 asyncpg 엔진을 lazy 초기화한다.
    테스트에서 patch("dev2.db.AsyncSessionLocal")으로 교체 가능.
    """
    return _get_session_factory()()


async def insert_scan_execution(payload: dict, execution_ms: int, trace_id: str) -> int:
    """
    scan_executions에 스캔 실행 기록을 INSERT한다.
    trace_id: CLAUDE.md §3 형식 ("pr_{12hex}" 또는 서브 에이전트 trace)
    """
    async with AsyncSessionLocal() as s:
        r = await s.execute(text("""
            INSERT INTO scan_executions (task_id, trace_id, pr_id, developer_id, execution_ms)
            VALUES (:task_id, :trace_id, :pr_id, :developer_id, :execution_ms)
            RETURNING id
        """), {
            "task_id": payload["task_id"],
            "trace_id": trace_id,           # agent_traces 연결 키 (CLAUDE.md §3)
            "pr_id": payload["pr_id"],
            "developer_id": payload["developer"]["id"],
            "execution_ms": execution_ms,
        })
        await s.commit()
        return r.scalar()  # bigint 반환


async def insert_scan_issues(scan_id: int, issues: list[dict], agent: str):
    if not issues:
        return
    async with AsyncSessionLocal() as s:
        for i in issues:
            await s.execute(text("""
                INSERT INTO scan_issues
                  (scan_id, agent, severity, rule_id, file, line, message, suggestion, similar_issues)
                VALUES
                  (:scan_id, :agent, :severity, :rule_id, :file, :line, :message, :suggestion, :similar_issues)
            """), {
                "scan_id": scan_id,
                "agent": agent,
                "severity": i["severity"],
                "rule_id": i["rule_id"],
                "file": i.get("file", ""),
                "line": i.get("line", 0),
                "message": i["message"],
                "suggestion": i["suggestion"],
                "similar_issues": json.dumps(i.get("similar_issues", [])),
            })
        await s.commit()


async def insert_scan_summary(scan_id: int, agent: str, summary: dict):
    async with AsyncSessionLocal() as s:
        # UPSERT: 재스캔 시 덮어쓰기 (uq_scan_summaries_scan_agent 활용)
        await s.execute(text("""
            INSERT INTO scan_summaries (scan_id, agent, critical, major, minor)
            VALUES (:scan_id, :agent, :critical, :major, :minor)
            ON CONFLICT (scan_id, agent)
            DO UPDATE SET
                critical = EXCLUDED.critical,
                major    = EXCLUDED.major,
                minor    = EXCLUDED.minor
        """), {"scan_id": scan_id, "agent": agent, **summary})
        await s.commit()
