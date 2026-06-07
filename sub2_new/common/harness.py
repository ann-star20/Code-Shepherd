"""Agent Harness — LangSmith + PostgreSQL 통합 실행 추적기.

모든 에이전트는 이 Harness를 통해 실행한다.
- LangSmith에 trace 자동 전송 (LANGCHAIN_* 환경변수 기반)
- PostgreSQL agent_traces 테이블에 시작/종료 기록 (SQLAlchemy async)
- timeout 강제 적용 (AGENT_TIMEOUT_SECONDS, 기본 30초)
- 실패 시 DB 기록 후 예외 상위 전파 (삼키지 않음)

[통합 메모] 이 파일은 팀 공용 backend/_shared/shared/harness.py와 동일한 시그니처다.
공개 API가 db_session_factory(SQLAlchemy async_sessionmaker)를 받도록 정합돼 있다.
(구버전은 db_pool=asyncpg.Pool 이었음 — Week 5 통합 시 import 경로만
 common.* → shared.* 로 교체하면 드롭인 된다.)

==========================================================================
팀 공통 사용 가이드 (Module 0 ~ 5 전원 적용)
==========================================================================

[필수 환경변수 설정 — .env 파일]

    LANGCHAIN_TRACING_V2=true
    LANGCHAIN_API_KEY=ls__xxxx
    LANGCHAIN_PROJECT=module{N}-{yourGitHubId}  # ⚠️ GitHub ID 포함 필수
    POSTGRES_URL=postgresql+asyncpg://...

[기본 사용 패턴 (단일 에이전트)]

    from common.trace import new_sub_trace
    from common.harness import AgentHarness

    try:
        async with AgentHarness(
            trace_id=new_sub_trace(pr_trace_id, "my_agent"),
            agent_name="my_agent",
            db_session_factory=session_factory,
            task_id=state.get("task_id"),
        ) as harness:
            result = await harness.run(my_agent_graph.ainvoke, state)
    except asyncio.TimeoutError:
        return make_timeout_result("my_agent")  # with 블록 바깥에서 처리

[m0 문서 파이프라인 패턴]

    from common.trace import DocPipelineStage, new_pipeline_trace
    from common.harness import AgentHarness

    trace_id = new_pipeline_trace(DocPipelineStage.MARKDOWN_CONVERT, doc_id=doc_id)

    try:
        async with AgentHarness(
            trace_id=trace_id,
            agent_name="DocumentParserAgent",
            db_session_factory=session_factory,
            doc_id=doc_id,
        ) as harness:
            result = await harness.run(graph.ainvoke, state)
    except asyncio.TimeoutError:
        return make_timeout_result("DocumentParserAgent")

[m2/m3 병렬 에이전트 패턴]

    from common.harness import run_parallel_agents

    results = await run_parallel_agents(
        agents=[
            ("static_analysis", sa_graph.ainvoke, (state,), {}),
            ("security_scan",   ss_graph.ainvoke, (state,), {}),
        ],
        db_session_factory=session_factory,
        pr_trace_id=pr_trace,
        task_id=state["task_id"],
    )

[주의사항]
- LANGCHAIN_PROJECT에 GitHub ID를 빼면 팀원 trace가 섞입니다.
- TimeoutError는 반드시 AgentHarness with 블록 바깥에서 잡아야 합니다.
  안쪽에서 잡으면 __aexit__이 성공으로 판단해 agent_traces에 'success'로 기록됩니다.
==========================================================================
"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from common.trace import new_sub_trace, trace_metadata

logger = logging.getLogger(__name__)

AGENT_TIMEOUT_SECONDS = int(os.getenv("AGENT_TIMEOUT_SECONDS", "30"))


# ---------------------------------------------------------------------------
# AgentHarness
# ---------------------------------------------------------------------------

class AgentHarness:
    """단일 에이전트 실행을 감싸는 async context manager.

    with 블록 진입 시 agent_traces에 status='running' UPSERT.
    with 블록 종료 시 status를 'success' 또는 'fail'로 UPDATE.
    LangSmith는 LANGCHAIN_TRACING_V2 환경변수로 자동 활성화.
    """

    def __init__(
        self,
        trace_id: str,
        agent_name: str,
        db_session_factory: async_sessionmaker[AsyncSession],
        doc_id: UUID | None = None,
        task_id: str | None = None,
        langsmith_project: str | None = None,
        timeout: int | None = None,
    ) -> None:
        self.trace_id = trace_id
        self.agent_name = agent_name
        self.db_session_factory = db_session_factory
        self.doc_id = doc_id
        self.task_id = task_id
        self.project = langsmith_project or os.getenv(
            "LANGCHAIN_PROJECT", "onboarding-platform"
        )
        self.timeout = timeout if timeout is not None else AGENT_TIMEOUT_SECONDS
        self._started_at: datetime | None = None

    async def __aenter__(self) -> "AgentHarness":
        self._started_at = datetime.now(timezone.utc)
        await self._upsert_trace(status="running")
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> bool:
        ended_at = datetime.now(timezone.utc)
        execution_ms = int(
            (ended_at - self._started_at).total_seconds() * 1000
        )

        if exc_type is None:
            await self._upsert_trace(
                status="success",
                ended_at=ended_at,
                execution_ms=execution_ms,
            )
        else:
            error_msg = f"{exc_type.__name__}: {exc_val}"
            await self._upsert_trace(
                status="fail",
                ended_at=ended_at,
                execution_ms=execution_ms,
                error_message=error_msg,
            )
            logger.error(
                "Agent execution failed",
                extra={
                    "trace_id": self.trace_id,
                    "agent_name": self.agent_name,
                    "error": error_msg,
                    "execution_ms": execution_ms,
                },
            )

        return False  # 예외를 삼키지 않는다 — 상위로 전파

    async def run(
        self,
        fn: Callable[..., Awaitable[Any]],
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        """에이전트 함수를 LangSmith tracing + 타임아웃으로 실행.

        fn은 LangGraph graph.ainvoke 또는 일반 async 함수 모두 가능.
        LangGraph의 경우 config["metadata"]에 trace_id가 자동 포함됨.

        Raises:
            asyncio.TimeoutError: timeout 초과 시 (with 블록 바깥에서 처리할 것)
            Exception: fn 내부 예외 그대로 전파
        """
        import inspect as _inspect
        _sig = _inspect.signature(fn)
        _params = _sig.parameters
        _has_var_kw = any(
            p.kind == _inspect.Parameter.VAR_KEYWORD for p in _params.values()
        )

        if "config" in _params or _has_var_kw:
            _meta = trace_metadata(
                self.trace_id,
                self.agent_name,
                str(self.doc_id) if self.doc_id else None,
            )
            _cfg = dict(kwargs.get("config") or {})
            _cfg["metadata"] = {**_meta, **(_cfg.get("metadata") or {})}
            kwargs["config"] = _cfg

        if not _has_var_kw:
            kwargs = {k: v for k, v in kwargs.items() if k in _params}

        try:
            return await asyncio.wait_for(
                fn(*args, **kwargs),
                timeout=self.timeout,
            )
        except asyncio.TimeoutError:
            logger.error(
                "Agent timed out",
                extra={
                    "trace_id": self.trace_id,
                    "agent_name": self.agent_name,
                    "timeout_seconds": self.timeout,
                },
            )
            raise

    async def _upsert_trace(
        self,
        status: str,
        ended_at: datetime | None = None,
        execution_ms: int | None = None,
        error_message: str | None = None,
    ) -> None:
        """agent_traces 테이블에 UPSERT.

        DB 로그 실패는 경고만 남기고 에이전트 실행을 막지 않는다.
        """
        try:
            async with self.db_session_factory() as session:
                await session.execute(
                    text("""
                        INSERT INTO agent_traces
                            (trace_id, task_id, agent_name, doc_id, status,
                             started_at, ended_at, execution_ms, error_message)
                        VALUES
                            (:trace_id, :task_id, :agent_name, :doc_id, :status,
                             :started_at, :ended_at, :execution_ms, :error_message)
                        ON CONFLICT (trace_id) DO UPDATE SET
                            status        = EXCLUDED.status,
                            ended_at      = EXCLUDED.ended_at,
                            execution_ms  = EXCLUDED.execution_ms,
                            error_message = EXCLUDED.error_message
                    """),
                    {
                        "trace_id": self.trace_id,
                        "task_id": self.task_id,
                        "agent_name": self.agent_name,
                        "doc_id": str(self.doc_id) if self.doc_id else None,
                        "status": status,
                        "started_at": self._started_at,
                        "ended_at": ended_at,
                        "execution_ms": execution_ms,
                        "error_message": error_message,
                    },
                )
                await session.commit()
        except Exception as e:
            logger.warning(
                "agent_traces DB 기록 실패 (에이전트 실행은 계속)",
                extra={"trace_id": self.trace_id, "error": str(e)},
            )


# ---------------------------------------------------------------------------
# 타임아웃 시 빈 결과 생성
# ---------------------------------------------------------------------------

def make_timeout_result(agent_name: str) -> dict:
    """타임아웃 시 반환할 Output Contract 형식의 빈 결과.

    Evaluator(m4)가 해당 에이전트 없이도 판정을 계속 진행할 수 있게 함.
    """
    return {
        "task_id": "",
        "agent": agent_name,
        "issues": [],
        "summary": {"critical": 0, "major": 0, "minor": 0},
        "execution_ms": AGENT_TIMEOUT_SECONDS * 1000,
        "error": "timeout",
    }


# ---------------------------------------------------------------------------
# m2/m3 병렬 에이전트 실행
# ---------------------------------------------------------------------------

async def run_parallel_agents(
    agents: list[tuple[str, Callable[..., Awaitable[dict]], tuple, dict]],
    db_session_factory: async_sessionmaker[AsyncSession],
    pr_trace_id: str,
    task_id: str | None = None,
) -> list[dict]:
    """에이전트 목록을 asyncio.gather로 동시 실행.

    각 에이전트는 독립적으로 추적되며, 타임아웃/실패해도
    빈 결과로 대체하여 파이프라인이 멈추지 않는다.

    Args:
        agents: [(agent_name, graph.ainvoke, args_tuple, kwargs_dict), ...]
        db_session_factory: SQLAlchemy async_sessionmaker
        pr_trace_id: PR 단위 상위 trace_id (sub_trace 생성에 사용)
        task_id: 작업 단위 연결 키 — agent_traces.task_id

    Returns:
        Output Contract dict 목록
    """
    async def _run_one(
        agent_name: str,
        fn: Callable,
        args: tuple,
        kwargs: dict,
    ) -> dict:
        sub_trace = new_sub_trace(pr_trace_id, agent_name)
        try:
            async with AgentHarness(
                trace_id=sub_trace,
                agent_name=agent_name,
                db_session_factory=db_session_factory,
                task_id=task_id,
            ) as harness:
                return await harness.run(fn, *args, **kwargs)
        except asyncio.TimeoutError:
            return make_timeout_result(agent_name)
        except Exception as e:
            logger.error(
                f"{agent_name} 실행 실패, 빈 결과로 대체",
                extra={"sub_trace": sub_trace, "error": str(e)},
            )
            return {**make_timeout_result(agent_name), "error": str(e)}

    tasks = [_run_one(name, fn, args, kwargs) for name, fn, args, kwargs in agents]
    return list(await asyncio.gather(*tasks))
