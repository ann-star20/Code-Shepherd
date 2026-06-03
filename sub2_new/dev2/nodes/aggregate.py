"""
aggregate 노드 (PRD 노드 I) — M2+M3 결과 취합 + PostgreSQL 저장 + M4 push

파이프라인 2의 진입 노드. M0(Orchestrator)가 보낸 M2(static_analysis,
security_scan) + M3(test_verification, performance)의 AgentOutput을 모두
취합하여 severity 순으로 정렬하고 PostgreSQL에 1행 저장한다.

흐름:
    aggregate → comment_refine → github_comment → [Critical?] → slack_notify

CLAUDE.md 준수:
    §5-A   AgentOutput Output Contract 입력
    §10-2  판정(lgtm/rework/escalate)은 하지 않음 — 데이터 정리 + 전달만 담당
    §12    M4 push 실패 → 로그만 남기고 파이프라인 계속 (DB 저장 실패는 re-raise)
"""

import logging
import os

from dev2.db import insert_aggregated_result
from dev2.schema import AggregateState

logger = logging.getLogger(__name__)

# Critical → Major → Minor 정렬 우선순위
_SEVERITY_ORDER = {"Critical": 0, "Major": 1, "Minor": 2}


async def _notify_m4(state: AggregateState, sorted_issues: list[dict], total: dict) -> None:
    """
    M4 커리큘럼 모듈에 취합 결과를 push한다.

    M4가 pull 요청을 보내는 것이 아니라 Dev2 취합이 끝나면 자동으로 전송.
    Critical 여부와 무관하게 항상 호출.
    [CLAUDE.md §12] 실패 시 로그만 남기고 파이프라인 계속 진행.
    """
    m4_url = os.getenv("M4_WEBHOOK_URL", "")
    if not m4_url:
        logger.warning(
            "aggregate_node: M4_WEBHOOK_URL 미설정 — M4 push 스킵 (개발 환경 정상)"
        )
        return

    payload = {
        "task_id":           state["task_id"],
        "pr_id":             state["pr_id"],
        "developer_id":      state["developer_id"],
        "skill_level":       state.get("skill_level", "junior"),
        "tech_stack":        state.get("tech_stack", []),
        "aggregated_issues": sorted_issues,
        "summary":           total,
    }

    try:
        import httpx  # noqa: PLC0415

        async with httpx.AsyncClient() as client:
            resp = await client.post(m4_url, json=payload, timeout=5.0)
        logger.info(
            "aggregate_node: M4 push 완료 (task_id=%s, status=%d)",
            state["task_id"], resp.status_code,
        )
    except Exception as exc:
        # [CLAUDE.md §12] M4 알림 실패 → 로그만 남기고 파이프라인 계속
        logger.error("aggregate_node: M4 push 실패 (non-fatal) — %s", exc)


async def aggregate_node(state: AggregateState) -> dict:
    """
    PRD 노드 I: M2+M3 AgentOutput 전체 취합 → severity 정렬 → PostgreSQL 저장 → M4 push.

    판정(lgtm/rework/escalate)은 하지 않는다 — 이슈 데이터 정리 + 전달만 담당.

    Args:
        state: AggregateState — all_results, task_id, pr_id, developer_id 사용

    Returns:
        {"aggregated_issues": [...정렬된 이슈...], "total_summary": {...}}
    """
    all_issues: list[dict] = []
    total = {"critical": 0, "major": 0, "minor": 0}

    for result in state.get("all_results", []):
        agent = result.get("agent", "unknown")
        for issue in result.get("issues", []):
            all_issues.append({**issue, "agent": agent})
        s = result.get("summary", {})
        for k in total:
            total[k] += s.get(k, 0)

    # Critical → Major → Minor 순 정렬
    sorted_issues = sorted(
        all_issues,
        key=lambda x: _SEVERITY_ORDER.get(x.get("severity", "Minor"), 3),
    )

    try:
        await insert_aggregated_result(
            task_id=state["task_id"],
            pr_id=state["pr_id"],
            developer_id=state["developer_id"],
            issues=sorted_issues,
            summary=total,
        )
    except Exception as exc:
        # [CLAUDE.md §4/§12] DB 저장은 핵심 기능 — 삼키지 않고 상위 전파
        logger.error("aggregate_node: DB 저장 실패 — %s", exc)
        raise

    logger.info(
        "aggregate_node: PR #%s 취합 완료 (critical=%d, major=%d, minor=%d)",
        state["pr_id"], total["critical"], total["major"], total["minor"],
    )

    # DB 저장 완료 후 M4에 자동 push (pull 방식 아님)
    await _notify_m4(state, sorted_issues, total)

    return {"aggregated_issues": sorted_issues, "total_summary": total}
