"""MODULE_CONTRACT §Module 2 — AgentResult 계약 구현.

docs/MODULE_CONTRACT.md(및 backend/m2/MODULE_CONTRACT.md)가 정의하는
m2 출력 계약(AgentResult)을 실제로 생성·검증한다.

설계 원칙(하위호환):
  - AgentResult는 기존 M2AnalyzeResponse(task_id/agent/issues/summary/execution_ms)의
    **상위집합**이다. m1은 `M2AnalyzeResponse(**resp.json())`로 역직렬화하며
    Pydantic v2 기본값(extra="ignore")으로 추가 계약 필드를 무시한다.
  - 따라서 본 모듈을 도입해도 m1/m3 호출 경로는 깨지지 않는다.
"""

from __future__ import annotations

import secrets
from typing import Literal

from pydantic import BaseModel, Field

from shared.contracts import (
    AnalysisContext,
    DeveloperProfile,
    IssueItem,
    IssueSummary,
    M2AnalyzeRequest,
)

Agent = Literal["static_analysis", "security_scan"]

# agent → 계약상 에이전트 이름 (MODULE_CONTRACT agent_name)
_AGENT_NAME: dict[Agent, str] = {
    "static_analysis": "StaticAnalysisAgent",
    "security_scan": "SecurityScanAgent",
}

# rule_id 접두사 — 도구 출처(검증 3차 규칙)
_VALID_RULE_PREFIXES = ("SA-", "JS-", "SEC-", "OWASP-")


class AgentResult(BaseModel):
    """MODULE_CONTRACT §Module 2 출력 계약 (M2AnalyzeResponse 상위집합)."""

    # ── M2AnalyzeResponse 호환 필드 (하위호환 보장) ──
    task_id: str
    agent: Agent
    issues: list[IssueItem] = Field(default_factory=list)
    summary: IssueSummary = Field(default_factory=IssueSummary)
    execution_ms: int = 0

    # ── MODULE_CONTRACT AgentResult 추가 필드 ──
    trace_id: str | None = None
    sub_trace_id: str | None = None
    agent_name: Literal["StaticAnalysisAgent", "SecurityScanAgent"]
    module_id: Literal["module_2"] = "module_2"
    status: Literal["success", "fail", "hitl_pending"] = "success"
    validation_result: Literal["pass", "fail", "skip"] = "pass"
    error_message: str | None = None
    next_agent: None = None


class M2OrchestrateRequest(BaseModel):
    """m2 mini-orchestrator 입력 — PR 1건에 대한 end-to-end 분석 요청.

    기존 M2AnalyzeRequest와 호환 가능한 필드를 유지하되, 오케스트레이션에 필요한
    repository/pr_number를 추가로 받는다(웹훅/영속화 단계에서 사용).
    """

    task_id: str
    pr_id: str
    pr_diff: str
    repository: str | None = None  # "owner/repo" — 영속화/코멘트 대상
    pr_number: int | None = None
    context: AnalysisContext = Field(default_factory=AnalysisContext)
    developer: DeveloperProfile | None = None  # developer.id = github_id
    trace_id: str | None = None


class M2OrchestrateResponse(BaseModel):
    """m2 mini-orchestrator 출력 — 2개 분석 결과 + m4 판정(있으면)."""

    task_id: str
    pr_id: str
    status: Literal["success", "skip", "partial", "fail"] = "success"
    ran_agents: list[Agent] = Field(default_factory=list)
    skip_reason: str | None = None

    static_analysis: AgentResult | None = None
    security_scan: AgentResult | None = None

    # m4 /evaluate 결과 (호출 실패·미설정 시 None — graceful)
    m4_called: bool = False
    verdict: Literal["lgtm", "rework", "escalate"] | None = None
    comment_body: str | None = None

    # review_issue에 영속화된 이슈 수 (영속화 비활성·실패 시 0 — graceful)
    persisted: int = 0

    # KMS context를 채웠는지 (m0 /search 미설정·실패 시 False — graceful)
    kms_used: bool = False

    trace_id: str | None = None
    error_message: str | None = None


# ---------------------------------------------------------------------------
# m0 KMS 검색 계약 (m2 → m0)
#
# m2가 m0 KMS에서 분석 context(아키텍처 청크 등)를 가져올 때 쓰는 요청/응답 형태.
# 실제 m0 엔드포인트는 GET /kms/search?q=&limit=&category= (kms_routes.py) 이며,
# 응답 SearchResponse{query, results[chunk_id, content, score, ...], total}의
# 부분집합(chunk_id/content/score)만 사용한다.
# 계약은 m2 내부에 두고, 추후 m0 담당자와 합의 시 공통 계약으로 이관한다.
# (query→q, top_k→limit 매핑은 kms_client에서 수행)
# ---------------------------------------------------------------------------

class KmsSearchRequest(BaseModel):
    """m0 KMS 검색 요청 — pgVector 유사도 검색용 질의."""

    query: str  # pr_diff 요약 또는 변경 파일 경로 기반 질의 (→ m0 q)
    top_k: int = 3  # → m0 limit (1~20)
    trace_id: str | None = None


class KmsSearchResult(BaseModel):
    chunk_id: str
    content: str
    score: float = 0.0


class KmsSearchResponse(BaseModel):
    results: list[KmsSearchResult] = Field(default_factory=list)


def make_sub_trace_id(trace_id: str | None, agent: Agent) -> str:
    """Sub-trace ID 생성 — 패턴: ``pr_{12hex}_{agent}_{4hex}``.

    m1이 ``pr_`` 접두 trace_id를 주면 그 베이스를 재사용하고,
    없으면 새 12자리 hex 베이스를 만든다.
    """
    base = trace_id if (trace_id and trace_id.startswith("pr_")) else f"pr_{secrets.token_hex(6)}"
    return f"{base}_{agent}_{secrets.token_hex(2)}"


def validate_result(
    issues: list[IssueItem], execution_ms: int
) -> Literal["pass", "fail", "skip"]:
    """계약 validation_rule 2·3차 검증.

    - 2차: execution_ms > 0, issues 목록 타입 검증
    - 3차: rule_id 형식 확인 (SA-/JS-/SEC-/OWASP- 접두사)

    반환:
        "skip" — 이슈 없음 (검증 대상 없음)
        "fail" — execution_ms<=0 이거나 형식 위반 rule_id 존재
        "pass" — 이슈 존재 + 모든 rule_id 형식 유효
    """
    if execution_ms <= 0:
        return "fail"
    if not issues:
        return "skip"
    for issue in issues:
        rid = issue.rule_id or ""
        if not rid.startswith(_VALID_RULE_PREFIXES):
            return "fail"
    return "pass"


def build_agent_result(
    payload: M2AnalyzeRequest,
    agent: Agent,
    issues: list[IssueItem],
    summary: IssueSummary,
    execution_ms: int,
) -> AgentResult:
    """분석 결과를 계약 AgentResult로 변환한다."""
    exec_ms = max(execution_ms, 1)  # 계약 2차: execution_ms > 0
    vr = validate_result(issues, exec_ms)
    return AgentResult(
        task_id=payload.task_id,
        agent=agent,
        issues=issues,
        summary=summary,
        execution_ms=exec_ms,
        trace_id=payload.trace_id,
        sub_trace_id=make_sub_trace_id(payload.trace_id, agent),
        agent_name=_AGENT_NAME[agent],
        status="fail" if vr == "fail" else "success",
        validation_result=vr,
        error_message=None,
    )


def make_timeout_result(
    payload: M2AnalyzeRequest,
    agent: Agent,
    execution_ms: int,
    error: str,
) -> AgentResult:
    """계약 retry/error_rule — 타임아웃·분석 실패 시 빈 AgentResult(status=fail).

    파이프라인 중단 없이 빈 결과를 반환하여 m1이 계속 진행하도록 한다.
    """
    return AgentResult(
        task_id=payload.task_id,
        agent=agent,
        issues=[],
        summary=IssueSummary(),
        execution_ms=max(execution_ms, 1),
        trace_id=payload.trace_id,
        sub_trace_id=make_sub_trace_id(payload.trace_id, agent),
        agent_name=_AGENT_NAME[agent],
        status="fail",
        validation_result="skip",
        error_message=error,
    )
