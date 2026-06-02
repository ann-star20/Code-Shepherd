"""
slack_notify 노드 — Critical 이슈 Slack 알림 (조건부)

이 노드는 Critical 이슈가 1건 이상일 때만 실행된다.
시니어 개발자에게 즉시 알림을 보내 에스컬레이션한다.

흐름:
    github_comment → [Critical ≥ 1?] → slack_notify → END
                   → END (Critical 없음)

CLAUDE.md 준수:
    §6     HITL: Critical 보안 이슈 ≥ 1건 → 즉시 Slack 에스컬레이션
    §12    Slack API 실패 → 로그만 남기고 무시 (파이프라인 중단 없음)
    §14    SLACK_WEBHOOK_URL, SLACK_CHANNEL_SECURITY 환경변수 사용
"""

import logging
import os

from dev2.schema import Dev2State

logger = logging.getLogger(__name__)

SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL", "")
SLACK_CHANNEL = os.getenv("SLACK_CHANNEL_SECURITY", "#team-security")


async def _send_slack_alert(
    critical_issues: list[dict],
    pr_id: str,
    developer_id: str,
    github_comment_url: str | None,
) -> None:
    """
    Slack Webhook으로 Critical 이슈 알림을 전송한다.

    [CLAUDE.md §12] Slack API 실패 → 로그만 남기고 무시.

    Args:
        critical_issues: Critical severity 이슈 목록
        pr_id: GitHub PR 번호
        developer_id: 이슈 발생 개발자 ID
        github_comment_url: 등록된 PR 코멘트 URL (있으면 링크 포함)
    """
    if not SLACK_WEBHOOK_URL:
        logger.warning(
            "_send_slack_alert: SLACK_WEBHOOK_URL 미설정 — Slack 알림 스킵 (개발 환경 정상)"
        )
        return

    issue_lines = "\n".join(
        f"• `{i.get('file', '?')}:{i.get('line', '?')}` — {i.get('message', '?')}"
        for i in critical_issues[:5]  # 최대 5건만 표시
    )
    comment_link = f"\n<{github_comment_url}|PR 코멘트 보기>" if github_comment_url else ""

    payload = {
        "channel": SLACK_CHANNEL,
        "text": f"🚨 *Critical 보안 이슈 감지* — PR #{pr_id} (개발자: {developer_id})",
        "blocks": [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        f"🚨 *Critical 보안 이슈 {len(critical_issues)}건 감지*\n"
                        f"PR: #{pr_id} | 개발자: {developer_id}{comment_link}"
                    ),
                },
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*이슈 목록:*\n{issue_lines}",
                },
            },
        ],
    }

    try:
        import httpx  # noqa: PLC0415

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                SLACK_WEBHOOK_URL,
                json=payload,
                timeout=5.0,
            )
        logger.info(
            "_send_slack_alert: Slack 알림 완료 (pr=%s, issues=%d, status=%d)",
            pr_id, len(critical_issues), resp.status_code,
        )

    except Exception as exc:
        # [CLAUDE.md §12] Slack 실패 → 로그만 남기고 파이프라인 계속
        logger.error(
            "_send_slack_alert: Slack 알림 실패 (non-fatal) — %s | 파이프라인 계속",
            exc,
        )


async def slack_notify_node(state: Dev2State) -> dict:
    """
    LangGraph 노드: Critical 이슈를 Slack으로 시니어 개발자에게 알린다.

    이 노드는 _route_after_comment 함수가 Critical ≥ 1일 때만 호출한다.

    Args:
        state: Dev2State — enriched, pr_id, developer_id, github_comment_url 사용

    Returns:
        {} — state 변경 없음
    """
    enriched: list[dict] = state.get("enriched", [])
    critical_issues = [i for i in enriched if i.get("severity") == "Critical"]
    pr_id: str = state.get("pr_id", "")
    developer_id: str = state.get("developer_id", "")
    github_comment_url: str | None = state.get("github_comment_url")

    logger.info(
        "slack_notify_node: Critical %d건 → Slack 알림 (pr=%s, task_id=%s)",
        len(critical_issues), pr_id, state.get("task_id", "?"),
    )

    await _send_slack_alert(critical_issues, pr_id, developer_id, github_comment_url)

    return {}
