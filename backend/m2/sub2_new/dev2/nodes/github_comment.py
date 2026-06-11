"""
github_comment 노드 — GitHub PR 코멘트 작성

이 노드는 comment_generate 노드가 생성한 마크다운을
GitHub PR에 코멘트로 등록한다.

흐름:
    comment_generate → github_comment → [Critical?] → slack_notify | END

CLAUDE.md 준수:
    §6     자동 머지 코드 작성 금지 — 코멘트만 달고 머지 판단은 사람이 한다
    §12    GitHub API 실패 → 로그 + 스킵 (알림 실패가 파이프라인을 막으면 안 됨)
    §14    GITHUB_TOKEN, GITHUB_REPO 환경변수 사용
"""

import logging
import os

from dev2.schema import Dev2State

logger = logging.getLogger(__name__)

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
GITHUB_REPO = os.getenv("GITHUB_REPO", "")   # "owner/repo" 형식


async def _post_github_comment(pr_id: str, body: str) -> str | None:
    """
    GitHub PR에 코멘트를 등록한다.

    Args:
        pr_id: GitHub PR 번호 (문자열)
        body: 마크다운 코멘트 본문

    Returns:
        등록된 코멘트 URL (성공 시) 또는 None (실패 시)
    """
    if not GITHUB_TOKEN or not GITHUB_REPO:
        logger.warning(
            "_post_github_comment: GITHUB_TOKEN 또는 GITHUB_REPO 미설정 — 스킵 (개발 환경 정상)"
        )
        return None

    try:
        import httpx  # noqa: PLC0415

        url = f"https://api.github.com/repos/{GITHUB_REPO}/issues/{pr_id}/comments"
        headers = {
            "Authorization": f"Bearer {GITHUB_TOKEN}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                url,
                json={"body": body},
                headers=headers,
                timeout=10.0,
            )

        if resp.status_code == 201:
            comment_url = resp.json().get("html_url", "")
            logger.info(
                "_post_github_comment: PR #%s 코멘트 등록 완료 (%s)",
                pr_id, comment_url,
            )
            return comment_url
        else:
            logger.error(
                "_post_github_comment: GitHub API 오류 (status=%d, pr=%s) — %s",
                resp.status_code, pr_id, resp.text[:200],
            )
            return None

    except Exception as exc:
        logger.error(
            "_post_github_comment: 코멘트 등록 실패 (pr=%s) — %s | 파이프라인 계속",
            pr_id, exc,
        )
        return None


async def github_comment_node(state: Dev2State) -> dict:
    """
    LangGraph 노드: comment_body를 GitHub PR 코멘트로 등록한다.

    [CLAUDE.md §6] 자동 머지 없음 — 코멘트 등록만 수행.

    Args:
        state: Dev2State — comment_body, pr_id 필드 사용

    Returns:
        {"github_comment_url": str | None}
    """
    comment_body: str = state.get("comment_body", "")
    pr_id: str = state.get("pr_id", "")

    if not comment_body:
        logger.warning("github_comment_node: comment_body 없음 — 스킵")
        return {"github_comment_url": None}

    comment_url = await _post_github_comment(pr_id, comment_body)

    logger.info(
        "github_comment_node 완료: pr=%s, url=%s (task_id=%s)",
        pr_id, comment_url, state.get("task_id", "?"),
    )
    return {"github_comment_url": comment_url}
