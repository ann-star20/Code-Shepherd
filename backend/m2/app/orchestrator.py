"""m2 mini-orchestrator — PR 1건 end-to-end 조율.

흐름:
  M2OrchestrateRequest
    → decision.decide()           어떤 분석을 돌릴지(skip 가능)
    → analyzer.analyze() × N       static / security (필요한 것만)
    → result_mapper                AgentResult → M4EvaluateRequest(named 필드)
    → m4_client.evaluate()         /evaluate (실패·미설정 시 분석결과만)
    → M2OrchestrateResponse

불변식:
  - 외부 연결(m4) 실패가 m2 분석을 중단시키지 않는다(graceful).
  - 기존 analyzer/contract 로직을 그대로 재사용한다(중복 구현 없음).
"""

from __future__ import annotations

import asyncio

from app import decision
from app.analyzer import Agent, analyze
from app.clients import m4_client
from app.contract import (
    AgentResult,
    M2OrchestrateRequest,
    M2OrchestrateResponse,
    build_agent_result,
    make_timeout_result,
)
from app.services import result_mapper, result_persist
from shared.contracts import M2AnalyzeRequest


def _to_analyze_request(req: M2OrchestrateRequest) -> M2AnalyzeRequest:
    """오케스트레이터 입력 → 단일 분석 입력(기존 계약)으로 다운캐스트."""
    return M2AnalyzeRequest(
        task_id=req.task_id,
        pr_id=req.pr_id,
        pr_diff=req.pr_diff,
        context=req.context,
        developer=req.developer,
        trace_id=req.trace_id,
    )


async def run_single_agent(payload: M2AnalyzeRequest, agent: Agent) -> AgentResult:
    """단일 분석 실행 → AgentResult. 실패 시 빈 결과(파이프라인 비중단).

    기존 main._run_agent와 동일한 계약을 공유한다(main이 이 함수를 재사용).
    """
    try:
        issues, summary, execution_ms = await asyncio.to_thread(
            analyze, payload.pr_diff, agent
        )
    except Exception as exc:  # noqa: BLE001 — 어떤 실패든 빈 결과로 graceful degrade
        return make_timeout_result(payload, agent, 0, f"analyze_failed: {exc}")
    return build_agent_result(payload, agent, issues, summary, execution_ms)


async def run_m2_orchestration(req: M2OrchestrateRequest) -> M2OrchestrateResponse:
    """PR 1건을 분석하고 m4 판정까지 묶어 반환한다."""
    plan = decision.decide(req.pr_diff)

    if plan.skip:
        return M2OrchestrateResponse(
            task_id=req.task_id,
            pr_id=req.pr_id,
            status="skip",
            skip_reason=plan.reason,
            trace_id=req.trace_id,
        )

    payload = _to_analyze_request(req)

    static_result: AgentResult | None = None
    security_result: AgentResult | None = None
    ran: list[Agent] = []

    if plan.needs_static:
        static_result = await run_single_agent(payload, "static_analysis")
        ran.append("static_analysis")
    if plan.needs_security:
        security_result = await run_single_agent(payload, "security_scan")
        ran.append("security_scan")

    # status: 실행한 분석 중 fail이 있으면 partial, 모두 성공이면 success
    ran_results = [r for r in (static_result, security_result) if r is not None]
    any_fail = any(r.status == "fail" for r in ran_results)
    status = "partial" if any_fail else "success"

    # review_issue 영속화 (기본 비활성 — opt-in, graceful)
    github_id = req.developer.id if req.developer else None
    persisted = await result_persist.persist_issues(static_result, github_id)
    persisted += await result_persist.persist_issues(security_result, github_id)

    # m4 /evaluate (graceful)
    m4_req = result_mapper.build_m4_request(
        task_id=req.task_id,
        pr_id=req.pr_id,
        static_result=static_result,
        security_result=security_result,
        developer=req.developer,
        trace_id=req.trace_id,
    )
    m4_resp = await m4_client.evaluate(m4_req)

    return M2OrchestrateResponse(
        task_id=req.task_id,
        pr_id=req.pr_id,
        status=status,
        ran_agents=ran,
        static_analysis=static_result,
        security_scan=security_result,
        m4_called=m4_resp is not None,
        verdict=m4_resp.verdict if m4_resp else None,
        comment_body=m4_resp.comment_body if m4_resp else None,
        persisted=persisted,
        trace_id=req.trace_id,
    )
