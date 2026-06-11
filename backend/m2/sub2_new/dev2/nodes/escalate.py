"""
escalate 노드 — Critical 이슈 에스컬레이션

이 노드는 llm_judge 결과에서 Critical 이슈를 감지하면
Dev4 Aggregator에 즉시 알림을 보내고 파이프라인을 계속 진행한다.

흐름:
    llm_judge → [Critical ≥ 1?] → escalate_node → store
    llm_judge → [Critical = 0]  → store (escalate 건너뜀)

CLAUDE.md 준수:
    §4     Dev4 3-Way 판정: Critical ≥ 1 → escalate (Slack 즉시 알림)
    §6     HITL: Critical 보안 이슈 ≥ 1건 → 즉시 Slack 에스컬레이션
    §10-4  에러 처리 공백: Slack/알림 실패 → 로그만 남기고 파이프라인 계속 진행
    §12    오류 처리: Slack API 실패 → 로그만 남기고 무시

설계 원칙:
    - notify_dev4 실패 → 파이프라인 중단 없음 (알림 실패가 PR 리뷰를 막으면 안 됨)
    - DEV4_WEBHOOK_URL 미설정 → 로그 경고 후 스킵 (개발 환경 기본 동작)
    - state 변경 없음 → {} 반환 (store 노드가 enriched를 직접 읽음)
"""

import logging
import os

logger = logging.getLogger(__name__)


# ── 외부 알림 ─────────────────────────────────────────────────────────────────

async def notify_dev4(critical_issues: list[dict], task_id: str) -> None:
    """
    Critical 이슈 발견 시 Dev4(평가 에이전트)에 즉시 HTTP 알림을 보낸다.

    CLAUDE.md §12:
        Slack/Dev4 알림 실패 → 로그만 남기고 파이프라인 계속 진행.
        알림 실패가 전체 PR 리뷰를 막으면 안 됨.

    DEV4_WEBHOOK_URL 미설정:
        개발 환경에서는 대부분 미설정 → 경고 로그 후 즉시 반환.
        CI/CD에서는 정상 동작.

    Args:
        critical_issues: Critical severity 이슈 목록
        task_id: PR 처리 단위 UUID (추적용)
    """
    dev4_url = os.getenv("DEV4_WEBHOOK_URL", "")
    if not dev4_url:
        logger.warning(
            "notify_dev4: DEV4_WEBHOOK_URL 미설정 — escalation 스킵 (개발 환경 정상)"
        )
        return

    try:
        # lazy import: httpx 미설치 환경에서 escalate.py 자체 import 허용
        import httpx  # noqa: PLC0415

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                dev4_url,
                json={
                    "task_id": task_id,
                    "alert": "Critical issues found",
                    "issues": critical_issues,
                },
                timeout=5.0,
            )
            logger.info(
                "notify_dev4: Dev4 알림 완료 (task_id=%s, issues=%d, status=%d)",
                task_id, len(critical_issues), resp.status_code,
            )

    except Exception as exc:
        # [CLAUDE.md §12] Slack/알림 실패는 파이프라인을 막지 않는다
        logger.error(
            "notify_dev4: Dev4 알림 실패 (non-fatal) — %s | 파이프라인 계속 진행",
            exc,
        )


# ── LangGraph 노드 ────────────────────────────────────────────────────────────

async def escalate_node(state) -> dict:
    """
    LangGraph 노드: Critical 이슈를 Dev4에 에스컬레이션한다.

    이 노드는 llm_judge → store 사이의 조건부 경로에 위치한다.
    _route_after_judge 함수가 Critical ≥ 1일 때만 이 노드를 호출한다.

    처리 흐름:
        1. enriched에서 Critical 이슈만 추출
        2. notify_dev4 호출 (실패해도 계속 진행)
        3. {} 반환 → LangGraph가 state를 변경하지 않음
           (store 노드가 enriched를 직접 읽어 처리함)

    CLAUDE.md §4:
        Critical ≥ 1 → escalate (Slack 즉시 알림)
        이 노드 이후 store 노드가 실제 DB 저장을 담당한다.

    Args:
        state: Dev2State — enriched, task_id 필드 사용

    Returns:
        {} — state 변경 없음 (store 노드가 enriched를 직접 처리)
    """
    enriched: list[dict] = state.get("enriched", [])
    critical_issues = [i for i in enriched if i.get("severity") == "Critical"]

    # [CLAUDE.md §11] PRReviewState 필드 직접 사용 (payload 대신 task_id)
    task_id: str = state.get("task_id", "")

    logger.info(
        "escalate_node: Critical 이슈 %d개 감지 (task_id=%s) — Dev4 알림 시도",
        len(critical_issues), task_id,
    )

    # 알림 실패 시에도 파이프라인 계속 진행 (notify_dev4 내부에서 예외 흡수)
    await notify_dev4(critical_issues, task_id)

    # store 노드에 enriched를 그대로 전달 (state 변경 없음)
    return {}
