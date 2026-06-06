"""common/harness.py — Dev2 에이전트 병렬 실행 + LangSmith 계측 인프라.

제공하는 것:
  run_parallel_agents()   에이전트 여러 개를 asyncio로 병렬 실행, 30초 타임아웃 자동 처리
  make_timeout_result()   타임아웃 발생 시 반환할 빈 Output Contract
  instrument()            LangSmith trace용 데코레이터 (Dev3 harness와 동일 인터페이스)
  AgentHarness            내부 컨텍스트 매니저 (agent_traces INSERT/UPDATE 담당)

CLAUDE.md §6 타임아웃 주의사항:
  asyncio.TimeoutError를 'async with AgentHarness()' 블록 안에서 잡으면
  __aexit__이 예외를 보지 못해 agent_traces.status가 'success'로 기록된다.
  반드시 try/except를 async with 바깥에 위치시킨다.

    # 올바른 패턴
    try:
        async with AgentHarness(...) as harness:
            return await harness.run(fn, *args, **kwargs)
    except asyncio.TimeoutError:
        return make_timeout_result(agent_name)

호출 예시 (Dev1 Orchestrator):
    results = await run_parallel_agents(
        agents=[
            ("static_analysis", sa_graph.ainvoke, (state,), {}),
            ("security_scan",   ss_graph.ainvoke, (state,), {}),
        ],
        db_pool=pool,
        pr_trace_id=pr_trace,
        task_id=state["task_id"],
    )
"""
from __future__ import annotations

import asyncio
import logging
import os
import secrets
import time
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable

logger = logging.getLogger(__name__)

# ── 상수 ──────────────────────────────────────────────────────────────────────

AGENT_TIMEOUT_SECONDS: int = 30  # CLAUDE.md §6 — 모든 분석 에이전트 타임아웃


# ── Output Contract ───────────────────────────────────────────────────────────

def make_timeout_result(agent_name: str) -> dict:
    """타임아웃 발생 시 반환할 빈 Output Contract (CLAUDE.md §5-A 형식).

    에이전트가 30초 안에 응답하지 않으면 이 결과로 대체된다.
    summary는 모두 0, issues는 빈 리스트 — Dev4가 "결과 없음"으로 처리한다.

    Args:
        agent_name: 타임아웃된 에이전트 이름 (예: "static_analysis")

    Returns:
        CLAUDE.md §5-A Output Contract 형식의 dict
    """
    return {
        "agent": agent_name,
        "issues": [],
        "summary": {"critical": 0, "major": 0, "minor": 0},
        "execution_ms": AGENT_TIMEOUT_SECONDS * 1000,
        "error": "timeout",
    }


# ── AgentHarness 컨텍스트 매니저 ──────────────────────────────────────────────

class AgentHarness:
    """단일 에이전트 실행을 감싸는 컨텍스트 매니저.

    역할:
      - 진입 시(__aenter__): agent_traces에 status='running' INSERT
      - 종료 시(__aexit__): status를 'success' 또는 'fail'로 UPDATE
      - run(): asyncio.wait_for로 30초 타임아웃 적용 (TimeoutError는 전파)

    사용법:
        try:
            async with AgentHarness(...) as h:
                result = await h.run(fn, *args, **kwargs)
        except asyncio.TimeoutError:
            result = make_timeout_result(agent_name)

    db_pool이 None이면 DB 기록 없이 실행만 수행 (테스트/Mock 환경 대응).
    """

    def __init__(
        self,
        agent_name: str,
        trace_id: str,
        task_id: str | None,
        db_pool: Any | None,
        timeout: int = AGENT_TIMEOUT_SECONDS,
    ) -> None:
        self.agent_name = agent_name
        self.trace_id = trace_id
        self.task_id = task_id
        self.db_pool = db_pool
        self.timeout = timeout
        self._started_at: datetime | None = None
        self._exc_type: type | None = None

    async def __aenter__(self) -> "AgentHarness":
        self._started_at = datetime.now(timezone.utc)
        await self._insert_trace(status="running")
        return self

    async def __aexit__(
        self,
        exc_type: type | None,
        exc_val: BaseException | None,
        exc_tb: object,
    ) -> bool:
        """종료 처리 — 예외가 있으면 status='fail', 없으면 status='success'.

        Returns:
            False — 예외를 억제하지 않음. TimeoutError가 바깥 try/except로 전파됨.
        """
        self._exc_type = exc_type
        ended_at = datetime.now(timezone.utc)
        execution_ms = int(
            (ended_at - self._started_at).total_seconds() * 1000
        ) if self._started_at else 0

        status = "fail" if exc_type else "success"
        error_msg = str(exc_val) if exc_val else None

        await self._update_trace(
            status=status,
            ended_at=ended_at,
            execution_ms=execution_ms,
            error_message=error_msg,
        )
        return False  # 예외 억제하지 않음 — TimeoutError가 바깥으로 전파됨

    async def run(
        self,
        fn: Callable[..., Awaitable[Any]],
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        """에이전트 함수를 타임아웃과 함께 실행한다.

        TimeoutError는 잡지 않고 그대로 전파한다.
        바깥의 _run_one()에서 try/except로 처리한다 (CLAUDE.md §6).

        Args:
            fn: await 가능한 에이전트 함수 (예: graph.ainvoke)
            *args, **kwargs: fn에 전달할 인자

        Returns:
            fn(*args, **kwargs)의 반환값

        Raises:
            asyncio.TimeoutError: timeout 초 초과 시
        """
        return await asyncio.wait_for(fn(*args, **kwargs), timeout=self.timeout)

    # ── 내부 DB 헬퍼 ──────────────────────────────────────────────────────────

    async def _insert_trace(self, status: str) -> None:
        """agent_traces 테이블에 시작 레코드 INSERT.

        db_pool이 None이면 로그만 남기고 건너뜀 (테스트 환경).
        """
        if self.db_pool is None:
            logger.debug(
                "[AgentHarness] DB pool 없음 — trace INSERT 건너뜀 (agent=%s)",
                self.agent_name,
            )
            return
        try:
            async with self.db_pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO agent_traces
                        (trace_id, task_id, agent_name, status, started_at)
                    VALUES ($1, $2, $3, $4, $5)
                    ON CONFLICT (trace_id) DO UPDATE
                        SET status = EXCLUDED.status,
                            started_at = EXCLUDED.started_at
                    """,
                    self.trace_id,
                    self.task_id,
                    self.agent_name,
                    status,
                    self._started_at,
                )
        except Exception as exc:  # noqa: BLE001
            # DB 실패가 에이전트 실행을 막으면 안 됨 (CLAUDE.md §12 Slack 실패 패턴과 동일)
            logger.warning(
                "[AgentHarness] agent_traces INSERT 실패 (agent=%s): %s",
                self.agent_name, exc,
            )

    async def _update_trace(
        self,
        status: str,
        ended_at: datetime,
        execution_ms: int,
        error_message: str | None,
    ) -> None:
        """agent_traces 테이블의 상태를 종료 시점에 UPDATE."""
        if self.db_pool is None:
            logger.debug(
                "[AgentHarness] DB pool 없음 — trace UPDATE 건너뜀 (agent=%s, status=%s)",
                self.agent_name, status,
            )
            return
        try:
            async with self.db_pool.acquire() as conn:
                await conn.execute(
                    """
                    UPDATE agent_traces
                    SET status        = $1,
                        ended_at      = $2,
                        execution_ms  = $3,
                        error_message = $4
                    WHERE trace_id = $5
                    """,
                    status,
                    ended_at,
                    execution_ms,
                    error_message,
                    self.trace_id,
                )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "[AgentHarness] agent_traces UPDATE 실패 (agent=%s): %s",
                self.agent_name, exc,
            )


# ── _run_one — 에이전트 1개 실행 단위 ─────────────────────────────────────────

async def _run_one(
    agent_name: str,
    fn: Callable[..., Awaitable[Any]],
    args: tuple,
    kwargs: dict,
    db_pool: Any | None,
    pr_trace_id: str,
    task_id: str | None,
) -> Any:
    """에이전트 1개를 AgentHarness로 감싸서 실행한다.

    서브 trace ID 생성 규칙 (CLAUDE.md §3):
        {pr_trace_id}_{agent_name}_{4자리 hex}
        예: pr_3a9f1c2b44e0_static_analysis_a1b2

    타임아웃 처리 (CLAUDE.md §6):
        try/except가 async with 바깥에 위치 — __aexit__이 status='fail' 기록 후
        TimeoutError가 이 except 블록으로 전파된다.

    Args:
        agent_name: 에이전트 이름 (trace ID 생성에 사용)
        fn:         실행할 async 함수
        args:       fn 위치 인자
        kwargs:     fn 키워드 인자
        db_pool:    asyncpg 커넥션 풀 (None이면 DB 기록 생략)
        pr_trace_id: 부모 trace ID
        task_id:    PR 작업 단위 UUID

    Returns:
        fn(*args, **kwargs) 반환값, 또는 타임아웃 시 make_timeout_result()
    """
    # 서브 trace ID: {parent}_{agent}_{4hex}
    suffix = secrets.token_hex(2)  # 4자리 hex
    trace_id = f"{pr_trace_id}_{agent_name}_{suffix}"

    logger.info("[run_parallel_agents] 시작 agent=%s trace=%s", agent_name, trace_id)
    t0 = time.monotonic()

    try:
        async with AgentHarness(
            agent_name=agent_name,
            trace_id=trace_id,
            task_id=task_id,
            db_pool=db_pool,
        ) as harness:
            # TimeoutError는 여기서 발생, __aexit__으로 전파 후 아래 except에 도달
            result = await harness.run(fn, *args, **kwargs)

    except asyncio.TimeoutError:
        elapsed_ms = int((time.monotonic() - t0) * 1000)
        logger.warning(
            "[run_parallel_agents] 타임아웃 agent=%s elapsed=%dms — 빈 결과로 대체",
            agent_name, elapsed_ms,
        )
        return make_timeout_result(agent_name)

    except Exception as exc:
        elapsed_ms = int((time.monotonic() - t0) * 1000)
        logger.error(
            "[run_parallel_agents] 실패 agent=%s elapsed=%dms error=%s",
            agent_name, elapsed_ms, exc,
        )
        # 타임아웃 외 예외는 상위로 전파 (CLAUDE.md §10-4: 에러는 삼키지 않는다)
        raise

    elapsed_ms = int((time.monotonic() - t0) * 1000)
    logger.info(
        "[run_parallel_agents] 완료 agent=%s elapsed=%dms", agent_name, elapsed_ms,
    )
    return result


# ── run_parallel_agents — 공개 API ────────────────────────────────────────────

async def run_parallel_agents(
    agents: list[tuple[str, Callable[..., Awaitable[Any]], tuple, dict]],
    db_pool: Any | None,
    pr_trace_id: str,
    task_id: str | None = None,
) -> list[Any]:
    """에이전트 여러 개를 asyncio로 병렬 실행한다. (CLAUDE.md §6)

    각 에이전트는 독립적으로 30초 타임아웃이 적용된다.
    타임아웃 발생 시 해당 에이전트 결과만 make_timeout_result()로 대체되고
    나머지 에이전트는 계속 실행된다.

    Args:
        agents: [(agent_name, fn, args_tuple, kwargs_dict), ...] 형태의 리스트
                예: [("static_analysis", sa_graph.ainvoke, (state,), {})]
        db_pool: asyncpg 커넥션 풀. None이면 agent_traces 기록 생략 (테스트용).
        pr_trace_id: 부모 trace ID (CLAUDE.md §3 서브 trace 생성에 사용)
                     예: "pr_3a9f1c2b44e0"
        task_id: PR 리뷰 작업 단위 UUID (agent_traces.task_id 연결용)

    Returns:
        각 에이전트 결과의 리스트. 순서는 agents 입력 순서와 동일.
        타임아웃된 에이전트는 make_timeout_result() dict로 대체.

    사용 예:
        results = await run_parallel_agents(
            agents=[
                ("static_analysis", sa_graph.ainvoke, (state,), {}),
                ("security_scan",   ss_graph.ainvoke, (state,), {}),
            ],
            db_pool=pool,
            pr_trace_id=pr_trace,
            task_id=state["task_id"],
        )
    """
    tasks = [
        _run_one(
            agent_name=name,
            fn=fn,
            args=args,
            kwargs=kwargs,
            db_pool=db_pool,
            pr_trace_id=pr_trace_id,
            task_id=task_id,
        )
        for name, fn, args, kwargs in agents
    ]

    # return_exceptions=False: 타임아웃 외 예외는 즉시 전파
    # 타임아웃은 _run_one 내부에서 이미 처리되어 make_timeout_result()로 대체됨
    return list(await asyncio.gather(*tasks))


# ── instrument — LangSmith 데코레이터 (Dev3 harness와 동일 인터페이스) ──────────

def instrument(name: str, run_type: str = "tool"):
    """탐지기/LLM 호출을 LangSmith run으로 감싼다. 키 없으면 원본 함수 그대로.

    Dev3 test-performance-agent/harness.py와 동일한 인터페이스.
    task_id·pr_trace_id는 parent run context에서 자동 상속된다
    (데코레이터는 definition time 적용 → runtime 값 직접 주입 불가).

    LANGCHAIN_API_KEY 환경변수:
      없으면 → no-op (원본 함수 그대로 반환, import 실패 없음)
      있으면 → langsmith.traceable 로 감쌈

    사용 예:
        @instrument(name="bandit_scan", run_type="tool")
        async def run_bandit(diff: str) -> dict:
            ...
    """
    def deco(fn):
        if not os.getenv("LANGCHAIN_API_KEY"):
            return fn
        try:
            from langsmith import traceable  # lazy import — 미설치여도 키 없으면 안 탐
        except ImportError:
            return fn
        return traceable(name=name, run_type=run_type)(fn)
    return deco
