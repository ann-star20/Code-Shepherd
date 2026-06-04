"""
Agent Harness — LangSmith + PostgreSQL 통합 실행 추적기

모든 에이전트는 이 Harness를 통해 실행한다.
- LangSmith에 trace 자동 전송 (LANGCHAIN_* 환경변수 기반)
- PostgreSQL agent_traces 테이블에 시작/종료 기록
- 30초 타임아웃 강제 적용
- 실패 시 DB 기록 후 예외 상위 전파 (삼키지 않음)

==========================================================================
팀 공통 사용 가이드 (Dev1~5 전원 적용)
==========================================================================

[필수 환경변수 설정 — .env 파일]

    LANGCHAIN_TRACING_V2=true
    LANGCHAIN_API_KEY=ls__xxxx           # 개인 또는 팀 공용 LangSmith 키
    LANGCHAIN_PROJECT=dev1-yourGitHubId  # ⚠️ 반드시 GitHub ID 포함 (예: dev2-alice)
    POSTGRES_URL=postgresql://...

[기존 에이전트 코드 3줄 추가 — ainvoke 래핑]

    # Before:
    result = await my_agent_graph.ainvoke(state)

    # After (3줄 추가):
    from common.trace import new_pr_trace, new_sub_trace
    from common.harness import AgentHarness
    async with AgentHarness(
        trace_id=new_sub_trace(pr_trace_id, "my_agent"),
        agent_name="my_agent",
        db_pool=pool,
        task_id=state.get("task_id"),
    ) as harness:
        result = await harness.run(my_agent_graph.ainvoke, state)

[DEV별 권장 패턴]

Dev1 (문서 파이프라인):
    from common.trace import DocPipelineStage, new_pipeline_trace
    trace_id = new_pipeline_trace(DocPipelineStage.MARKDOWN_CONVERT, doc_id=doc_id)
    async with AgentHarness(trace_id=trace_id, agent_name="DocumentParserAgent",
                            db_pool=pool, doc_id=doc_id) as harness:
        result = await harness.run(graph.ainvoke, state)

Dev2/3 (PR 리뷰 병렬):
    results = await run_parallel_agents(
        agents=[
            ("static_analysis", sa_graph.ainvoke, (state,), {}),
            ("security_scan",   ss_graph.ainvoke, (state,), {}),
        ],
        db_pool=pool, pr_trace_id=pr_trace, task_id=state["task_id"],
    )

Dev4 (Evaluator):
    pr_trace = new_pr_trace()
    async with AgentHarness(
        trace_id=new_sub_trace(pr_trace, "evaluator"),
        agent_name="evaluator", db_pool=pool, task_id=state["task_id"],
    ) as harness:
        result = await harness.run(eval_graph.ainvoke, state)

Dev5 (Curriculum):
    async with AgentHarness(
        trace_id=new_sub_trace(pr_trace, "curriculum"),
        agent_name="curriculum", db_pool=pool, task_id=state["task_id"],
    ) as harness:
        result = await harness.run(curriculum_graph.ainvoke, state)

[주의사항]
- LANGCHAIN_PROJECT에 GitHub ID를 빼면 팀원 trace가 섞입니다.
- TimeoutError는 AgentHarness with 블록 바깥에서 잡아야 합니다 (CLAUDE.md 섹션 6 참고).
- DB 로그 실패는 경고만 남기고 에이전트 실행을 막지 않습니다.

==========================================================================

사용 예시 (문서 파이프라인):

    from common.trace import DocPipelineStage, new_pipeline_trace
    from common.harness import AgentHarness, run_parallel_agents

    trace_id = new_pipeline_trace(DocPipelineStage.MARKDOWN_CONVERT, doc_id=doc_id)

    async with AgentHarness(
        trace_id=trace_id,
        agent_name="DocumentParserAgent",
        db_pool=pool,
        doc_id=doc_id,
    ) as harness:
        result = await harness.run(markdown_converter_graph.ainvoke, state)

사용 예시 (PR 리뷰 병렬 에이전트):

    from common.trace import new_pr_trace
    from common.harness import run_parallel_agents

    pr_trace = new_pr_trace()

    results = await run_parallel_agents(
        agents=[
            ("static_analysis",  static_analysis_graph.ainvoke,  (state,), {}),
            ("security_scan",    security_scan_graph.ainvoke,     (state,), {}),
            ("test_verify",      test_verify_graph.ainvoke,        (state,), {}),
            ("performance",      performance_graph.ainvoke,        (state,), {}),
        ],
        db_pool=pool,
        pr_trace_id=pr_trace,
    )
"""

import asyncio
import logging
import os
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable
from uuid import UUID

import asyncpg

from common.trace import new_sub_trace, trace_metadata

logger = logging.getLogger(__name__)

AGENT_TIMEOUT_SECONDS = int(os.getenv("AGENT_TIMEOUT_SECONDS", "60"))


# ---------------------------------------------------------------------------
# AgentHarness
# ---------------------------------------------------------------------------

class AgentHarness:
    """단일 에이전트 실행을 감싸는 async context manager.

    with 블록 진입 시 agent_traces에 status='running' INSERT.
    with 블록 종료 시 status를 'success' 또는 'fail'로 UPDATE.
    LangSmith는 tracing_v2_enabled context로 프로젝트별 분리.
    """

    def __init__(
        self,
        trace_id: str,
        agent_name: str,
        db_pool: asyncpg.Pool,
        doc_id: UUID | None = None,
        task_id: str | None = None,
        langsmith_project: str | None = None,
        timeout: int | None = None,
    ) -> None:
        self.trace_id = trace_id
        self.agent_name = agent_name
        self.db_pool = db_pool
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
            asyncio.TimeoutError: AGENT_TIMEOUT_SECONDS 초과 시
            Exception: fn 내부 예외 그대로 전파
        """
        import inspect as _inspect
        _sig = _inspect.signature(fn)
        _params = _sig.parameters
        _has_var_kw = any(p.kind == _inspect.Parameter.VAR_KEYWORD for p in _params.values())

        # LangGraph ainvoke처럼 config를 받는 fn에 trace_metadata 주입
        # 호출자가 넘긴 metadata 키가 우선 (덮어쓰기 허용)
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
                    "timeout_seconds": AGENT_TIMEOUT_SECONDS,
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
        """agent_traces 테이블에 INSERT 또는 UPDATE.

        DB 로그 실패는 경고만 남기고 에이전트 실행을 막지 않는다.
        """
        try:
            async with self.db_pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO agent_traces
                        (trace_id, task_id, agent_name, doc_id, status,
                         started_at, ended_at, execution_ms, error_message)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                    ON CONFLICT (trace_id) DO UPDATE SET
                        status        = EXCLUDED.status,
                        ended_at      = EXCLUDED.ended_at,
                        execution_ms  = EXCLUDED.execution_ms,
                        error_message = EXCLUDED.error_message
                    """,
                    self.trace_id,
                    self.task_id,
                    self.agent_name,
                    self.doc_id,
                    status,
                    self._started_at,
                    ended_at,
                    execution_ms,
                    error_message,
                )
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

    Dev4 Evaluator가 해당 에이전트 없이도 판정을 계속 진행할 수 있게 함.
    CLAUDE.md 섹션 5-A Output Contract 형식 준수.
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
# Dev2/3 병렬 에이전트 실행
# ---------------------------------------------------------------------------

async def run_parallel_agents(
    agents: list[tuple[str, Callable[..., Awaitable[dict]], tuple, dict]],
    db_pool: asyncpg.Pool,
    pr_trace_id: str,
    task_id: str | None = None,
) -> list[dict]:
    """Dev2/3 에이전트 4개를 asyncio.gather로 동시 실행.

    각 에이전트는 독립적으로 추적되며, 타임아웃/실패해도
    빈 결과로 대체하여 파이프라인이 멈추지 않는다.

    Args:
        agents: [(agent_name, graph.ainvoke, args_tuple, kwargs_dict), ...]
        db_pool: asyncpg 커넥션 풀
        pr_trace_id: PR 단위 상위 trace_id (sub_trace 생성에 사용)
        task_id: PRReviewState.task_id — agent_traces에 PR 작업 단위 기록

    Returns:
        Output Contract dict 목록 (CLAUDE.md 섹션 5-A 형식)

    예시:
        results = await run_parallel_agents(
            agents=[
                ("static_analysis", sa_graph.ainvoke, (state,), {}),
                ("security_scan",   ss_graph.ainvoke, (state,), {}),
                ("test_verify",     tv_graph.ainvoke, (state,), {}),
                ("performance",     pf_graph.ainvoke, (state,), {}),
            ],
            db_pool=pool,
            pr_trace_id=pr_trace,
            task_id=state["task_id"],
        )
    """
    async def _run_one(
        agent_name: str,
        fn: Callable,
        args: tuple,
        kwargs: dict,
    ) -> dict:
        sub_trace = new_sub_trace(pr_trace_id, agent_name)
        try:
            # try/except를 with 블록 바깥에 둔다.
            # TimeoutError/Exception이 __aexit__까지 전파되어야
            # agent_traces에 status='fail'로 기록된다.
            async with AgentHarness(
                trace_id=sub_trace,
                agent_name=agent_name,
                db_pool=db_pool,
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


# ---------------------------------------------------------------------------
# DB 커넥션 풀 팩토리
# ---------------------------------------------------------------------------

async def create_db_pool() -> asyncpg.Pool:
    """환경변수 POSTGRES_URL로 asyncpg 커넥션 풀 생성.

    각 DEV 서비스 startup 시 1회 호출하여 pool을 공유한다.

    Raises:
        asyncpg.PostgresConnectionError: DB 연결 실패 시
    """
    url = os.getenv("POSTGRES_URL")
    if not url:
        raise ValueError("POSTGRES_URL 환경변수가 설정되지 않았습니다")

    pool = await asyncpg.create_pool(
        dsn=url,
        min_size=2,
        max_size=10,
        command_timeout=10,
        # Cloud SQL이 유휴 연결을 끊기 전에 asyncpg가 먼저 교체한다 (기본 idle timeout < 10분)
        max_inactive_connection_lifetime=300.0,
    )
    logger.info("PostgreSQL 커넥션 풀 생성 완료")
    return pool
