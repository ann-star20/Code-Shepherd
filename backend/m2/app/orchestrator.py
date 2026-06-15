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
import logging
import time

from app import decision, progress
from app.analyzer import Agent, analyze
from app.clients import kms_client, m4_client
from app.contract import (
    AgentResult,
    KmsSearchRequest,
    M2OrchestrateRequest,
    M2OrchestrateResponse,
    build_agent_result,
    make_timeout_result,
)
from app.db import insert_scan_execution, insert_scan_issues, insert_scan_summary
from app.services import llm_judge, result_mapper, result_persist
from shared.contracts import IssueItem, IssueSummary, M2AnalyzeRequest

log = logging.getLogger(__name__)

# KMS 질의 길이 상한 (변경 파일 경로/diff 요약)
_KMS_QUERY_MAX = 512


def _stage(task_id: str | None, key: str, status: progress.StageStatus, ms: int | None = None) -> None:
    """task_id가 있으면 진행상태에 단계를 보고한다(없으면 no-op)."""
    if task_id:
        progress.set_stage(task_id, key, status, ms)


def _ms_since(t0: float) -> int:
    return int((time.perf_counter() - t0) * 1000)


def _context_is_empty(req: M2OrchestrateRequest) -> bool:
    """context 3필드가 모두 비어 있으면 True (KMS로 채울 대상)."""
    ctx = req.context
    return not (ctx.architecture_docs or ctx.coding_conventions or ctx.previous_pr_issues)


def _build_kms_query(pr_diff: str) -> str:
    """pr_diff에서 변경 파일 경로를 뽑아 KMS 검색 질의를 만든다.

    경로가 없으면 diff 앞부분으로 폴백한다.
    """
    paths: list[str] = []
    for line in pr_diff.splitlines():
        if line.startswith("+++ b/"):
            paths.append(line[len("+++ b/") :].strip())
    query = " ".join(paths) if paths else pr_diff
    return query[:_KMS_QUERY_MAX]


async def _fill_context_from_kms(req: M2OrchestrateRequest) -> bool:
    """context가 비어 있으면 KMS에서 채운다. 채웠으면 True(graceful).

    검색 결과의 chunk content를 architecture_docs에 담는다(Part 2 LLM-judge 근거).
    m0 /search 미설정·실패 시 빈 context 그대로 진행한다.
    """
    if not _context_is_empty(req):
        return False
    kms_req = KmsSearchRequest(
        query=_build_kms_query(req.pr_diff), trace_id=req.trace_id
    )
    resp = await kms_client.search(kms_req)
    if not resp or not resp.results:
        return False
    req.context.architecture_docs = [r.content for r in resp.results]
    return True


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


async def _analyze_tools(
    payload: M2AnalyzeRequest, agent: Agent
) -> tuple[list[IssueItem], IssueSummary, int, str | None]:
    """도구 실행만 수행. (issues, summary, execution_ms, error) — error None이면 성공.

    context를 사용하지 않으므로 KMS 채우기 전에 호출해도 안전하다.
    """
    try:
        issues, summary, execution_ms = await asyncio.to_thread(
            analyze, payload.pr_diff, agent
        )
        return issues, summary, execution_ms, None
    except Exception as exc:  # noqa: BLE001
        return [], IssueSummary(), 0, f"analyze_failed: {exc}"


async def _judge(
    payload: M2AnalyzeRequest, issues: list[IssueItem]
) -> tuple[list[IssueItem], IssueSummary]:
    """LLM-judge로 severity/suggestion 재판단 후 summary 재계산 (graceful).

    USE_MOCK_LLM=true(기본)이면 원본 그대로 통과한다.
    """
    issues = await llm_judge.judge_issues(issues, payload.context, payload.developer)
    return issues, llm_judge.summarize(issues)


async def _persist_scan(
    payload: M2AnalyzeRequest,
    agent: Agent,
    issues: list[IssueItem],
    summary: IssueSummary,
    execution_ms: int,
) -> None:
    """scan_executions / scan_issues / scan_summaries 저장 (graceful)."""
    try:
        issues_as_dict = [i.model_dump() for i in issues]
        summary_dict = {"critical": summary.critical, "major": summary.major, "minor": summary.minor}
        github_id = payload.developer.id if payload.developer else None
        scan_id = await insert_scan_execution(payload.task_id, payload.pr_id, execution_ms, developer_id=github_id)
        await insert_scan_issues(scan_id, issues_as_dict, agent)
        await insert_scan_summary(scan_id, agent, summary_dict)
    except Exception as exc:  # noqa: BLE001
        log.warning("m2.db.persist_failed agent=%s error=%s", agent, exc)


async def run_single_agent(payload: M2AnalyzeRequest, agent: Agent) -> AgentResult:
    """단일 분석 실행 → AgentResult. 실패 시 빈 결과(파이프라인 비중단).

    분석 완료 후 scan_executions / scan_issues / scan_summaries 저장(graceful).
    (/analyze/static·/analyze/security 엔드포인트용 — 분석부터 저장까지 묶음 실행)
    """
    issues, summary, execution_ms, error = await _analyze_tools(payload, agent)
    if error:
        return make_timeout_result(payload, agent, 0, error)

    issues, summary = await _judge(payload, issues)
    result = build_agent_result(payload, agent, issues, summary, execution_ms)
    await _persist_scan(payload, agent, issues, summary, execution_ms)
    return result


async def run_m2_orchestration(
    req: M2OrchestrateRequest, task_id: str | None = None
) -> M2OrchestrateResponse:
    """PR 1건을 분석하고 m4 판정까지 묶어 반환한다.

    task_id가 주어지면 4단계(run_tools→vector_search→llm_judge→store) 진행상태를
    progress 모듈에 실측 타이밍으로 보고한다(프론트 실시간 시각화용). task_id가 없으면
    /orchestrate/review 호출과 동일하게 보고 없이 동작한다.

    단계는 프론트 순서와 일치한다. 도구 실행(run_tools)은 context 불필요하므로 KMS
    채우기(vector_search)보다 먼저 수행하고, context는 llm_judge 직전에만 채운다.
    """
    try:
        return await _run_orchestration(req, task_id)
    except Exception as exc:  # noqa: BLE001 — 백그라운드 task 보호
        if task_id:
            progress.fail(task_id, str(exc))
        raise


async def _run_orchestration(
    req: M2OrchestrateRequest, task_id: str | None
) -> M2OrchestrateResponse:
    plan = decision.decide(req.pr_diff)

    if plan.skip:
        if task_id:
            progress.finish(task_id, {"found": False, "staticIssues": 0, "securityIssues": 0, "verdict": None})
        return M2OrchestrateResponse(
            task_id=req.task_id,
            pr_id=req.pr_id,
            status="skip",
            skip_reason=plan.reason,
            trace_id=req.trace_id,
        )

    payload = _to_analyze_request(req)
    agents: list[Agent] = []
    if plan.needs_static:
        agents.append("static_analysis")
    if plan.needs_security:
        agents.append("security_scan")

    # ── Stage 1: run_tools — 정적/보안 도구 실행만 (context 불필요) ──
    # 두 에이전트를 동시 실행한다 — _analyze_tools가 asyncio.to_thread라 병렬 가능.
    # 순차(static+security 합) 대신 max(static, security)로 단축 (탐지 결과 동일).
    _stage(task_id, "run_tools", "running")
    t0 = time.perf_counter()
    raw_list = await asyncio.gather(*(_analyze_tools(payload, ag) for ag in agents))
    raw: dict[Agent, tuple[list[IssueItem], IssueSummary, int, str | None]] = dict(
        zip(agents, raw_list)
    )
    _stage(task_id, "run_tools", "success", _ms_since(t0))

    # ── Stage 2: vector_search — KMS에서 분석 보조 context 채우기 (graceful) ──
    _stage(task_id, "vector_search", "running")
    t0 = time.perf_counter()
    kms_used = await _fill_context_from_kms(req)
    payload = _to_analyze_request(req)  # 갱신된 context 반영
    _stage(task_id, "vector_search", "success", _ms_since(t0))

    # ── Stage 3: llm_judge — context 기반 재판정 + AgentResult 생성 ──
    _stage(task_id, "llm_judge", "running")
    t0 = time.perf_counter()
    results: dict[Agent, AgentResult] = {}
    for ag in agents:
        issues, summary, execution_ms, error = raw[ag]
        if error:
            results[ag] = make_timeout_result(payload, ag, 0, error)
            continue
        issues, summary = await _judge(payload, issues)
        raw[ag] = (issues, summary, execution_ms, None)  # 저장 단계용으로 갱신
        results[ag] = build_agent_result(payload, ag, issues, summary, execution_ms)
    _stage(task_id, "llm_judge", "success", _ms_since(t0))

    # ── Stage 4: store — scan 테이블 + review_issue 영속화 ──
    _stage(task_id, "store", "running")
    t0 = time.perf_counter()
    for ag in agents:
        issues, summary, execution_ms, error = raw[ag]
        if error:
            continue
        await _persist_scan(payload, ag, issues, summary, execution_ms)

    static_result = results.get("static_analysis")
    security_result = results.get("security_scan")
    github_id = req.developer.id if req.developer else None
    persisted = await result_persist.persist_issues(
        static_result, github_id, pr_diff=req.pr_diff, pr_id=req.pr_id
    )
    persisted += await result_persist.persist_issues(
        security_result, github_id, pr_diff=req.pr_diff, pr_id=req.pr_id
    )
    _stage(task_id, "store", "success", _ms_since(t0))

    # status: 실행한 분석 중 fail이 있으면 partial, 모두 성공이면 success
    ran_results = [r for r in (static_result, security_result) if r is not None]
    any_fail = any(r.status == "fail" for r in ran_results)
    status = "partial" if any_fail else "success"

    static_n = len(static_result.issues) if static_result else 0
    security_n = len(security_result.issues) if security_result else 0
    critical_n = sum(
        1 for r in ran_results for i in r.issues if i.severity == "Critical"
    )
    local_verdict = "rework" if critical_n > 0 else ("lgtm" if (static_n + security_n) > 0 else None)

    # 진행상태 완료 보고 — 결과 노출이 m4 호출 지연을 기다리지 않게 store 직후 finish.
    if task_id:
        progress.finish(task_id, {
            "found": (static_n + security_n) > 0,
            "staticIssues": static_n,
            "securityIssues": security_n,
            "verdict": local_verdict,
        })

    # m4 /evaluate (graceful — 미설정·실패 시 분석 결과만)
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
        ran_agents=agents,
        static_analysis=static_result,
        security_scan=security_result,
        m4_called=m4_resp is not None,
        verdict=m4_resp.verdict if m4_resp else None,
        comment_body=m4_resp.comment_body if m4_resp else None,
        persisted=persisted,
        kms_used=kms_used,
        trace_id=req.trace_id,
    )
