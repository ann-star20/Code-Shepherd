"""m2 AgentResult → m4 입력 계약(M4EvaluateRequest) 변환.

AgentResult는 M2AnalyzeResponse의 상위집합이므로 호환 필드만 추려 다운캐스트한다.
m3 자리(test_verification/performance)는 Phase 2 전까지 None으로 비운다.
"""

from __future__ import annotations

from app.contract import AgentResult
from shared.contracts import (
    DeveloperProfile,
    M2AnalyzeResponse,
    M4EvaluateRequest,
)


def to_analyze_response(result: AgentResult | None) -> M2AnalyzeResponse | None:
    """AgentResult → M2AnalyzeResponse (m4가 받는 형식). None은 그대로 통과."""
    if result is None:
        return None
    return M2AnalyzeResponse(
        task_id=result.task_id,
        agent=result.agent,
        issues=result.issues,
        summary=result.summary,
        execution_ms=result.execution_ms,
    )


def build_m4_request(
    task_id: str,
    pr_id: str,
    static_result: AgentResult | None,
    security_result: AgentResult | None,
    developer: DeveloperProfile | None,
    trace_id: str | None,
) -> M4EvaluateRequest:
    """2개 m2 결과를 m4 named-필드 계약으로 묶는다(test/perf = None)."""
    return M4EvaluateRequest(
        task_id=task_id,
        pr_id=pr_id,
        static_analysis=to_analyze_response(static_result),
        security_scan=to_analyze_response(security_result),
        test_verification=None,
        performance=None,
        developer=developer,
        trace_id=trace_id,
    )
