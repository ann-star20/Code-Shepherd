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

from dev2.db import fetch_scan_results_by_task, insert_aggregated_result
from dev2.schema import AggregateState

logger = logging.getLogger(__name__)

# Critical → Major → Minor 정렬 우선순위
_SEVERITY_ORDER = {"Critical": 0, "Major": 1, "Minor": 2}


async def _load_results(state: AggregateState) -> list[dict]:
    """
    Dev4가 처리할 M2+M3 결과를 가져온다 (DB 릴레이 우선).

    흐름:
        1. task_id로 scan_issues에서 Dev2/Dev3 적재 결과를 조회 (DB 릴레이)
        2. DB에 결과가 있으면 그것을 사용
        3. DB 조회 실패 또는 결과 없음 → state["all_results"](payload) 폴백

    DB 릴레이가 기본 경로다. payload 폴백은 하위호환(테스트/직접 호출/DB 미연결)용.
    """
    task_id = state["task_id"]
    try:
        db_results = await fetch_scan_results_by_task(task_id)
    except Exception as exc:
        logger.warning(
            "_load_results: DB 조회 실패 (task_id=%s) — payload 폴백 | %s", task_id, exc,
        )
        db_results = []

    if db_results:
        logger.info(
            "_load_results: DB 릴레이 — task_id=%s에서 에이전트 결과 %d개 조회",
            task_id, len(db_results),
        )
        return db_results

    payload_results = state.get("all_results", [])
    logger.info(
        "_load_results: DB 결과 없음 — payload all_results 사용 (%d개) [폴백]",
        len(payload_results),
    )
    return payload_results


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
    PRD 노드 I: M2+M3 결과 취합 → severity 정렬 → PostgreSQL 저장 → M4 push.

    입력 경로 (DB 릴레이):
        task_id로 scan_issues에서 Dev2/Dev3 적재 결과를 조회한다 (_load_results).
        DB에 결과가 없으면 state["all_results"](M0 payload)로 폴백한다.

    판정(lgtm/rework/escalate)은 하지 않는다 — 이슈 데이터 정리 + 전달만 담당.

    Args:
        state: AggregateState — task_id로 DB 조회, 폴백 시 all_results 사용

    Returns:
        {"aggregated_issues": [...정렬된 이슈...], "total_summary": {...}}
    """
    all_issues: list[dict] = []
    total = {"critical": 0, "major": 0, "minor": 0}

    # DB 릴레이: Dev2/Dev3가 적재한 결과를 task_id로 조회 (없으면 payload 폴백)
    all_results = await _load_results(state)

    for result in all_results:
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
