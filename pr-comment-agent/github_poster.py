"""GitHub PR 코멘트 등록 — 토큰 있으면 실제 등록, 없으면 dry-run.

GITHUB_TOKEN 환경변수 있음 → requests로 GitHub Issues Comments API 호출.
토큰 없음 → .dry_run_comments/PR-{n}.md 파일로 저장.
빈 코멘트 → 등록 시도 없이 즉시 반환.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

import requests  # type: ignore


class GithubPosterError(Exception):
    """GitHub API 오류 또는 인증 실패."""


# ── 공개 함수 ──────────────────────────────────────────────────────────────────

def post_comment(
    pr_url: str,
    comment_body: str,
    *,
    owner: str = "",
    repo: str = "",
    pr_num: int = 0,
) -> dict:
    """PR에 코멘트를 등록하거나 dry-run 파일로 저장한다.

    Args:
        pr_url: GitHub PR URL (예: "https://github.com/owner/repo/pull/42").
                owner/repo/pr_num 키워드 인자로 직접 지정할 수도 있다.
        comment_body: 등록할 코멘트 본문 (markdown).

    Returns:
        {"mode": "github", "comment_id": int}
        {"mode": "dry_run", "path": str}
        {"mode": "skipped", "reason": str}

    Raises:
        GithubPosterError: GitHub API가 401 등 오류를 반환한 경우.
    """
    if not comment_body.strip():
        return {"mode": "skipped", "reason": "empty comment"}

    if pr_url:
        owner, repo, pr_num = _parse_pr_url(pr_url)

    token = os.getenv("GITHUB_TOKEN", "")

    if token:
        return _post_to_github(owner, repo, pr_num, comment_body, token)

    return _dry_run(pr_num, comment_body)


# ── 내부 함수 (테스트에서 patch 가능) ─────────────────────────────────────────

def _parse_pr_url(pr_url: str) -> tuple[str, str, int]:
    """GitHub PR URL에서 (owner, repo, pr_num)을 추출한다."""
    pattern = r"https://github\.com/([^/]+)/([^/]+)/pull/(\d+)"
    m = re.match(pattern, pr_url)
    if not m:
        raise ValueError(f"Invalid PR URL: {pr_url!r}")
    return m.group(1), m.group(2), int(m.group(3))


def _post_to_github(
    owner: str,
    repo: str,
    pr_num: int,
    body: str,
    token: str,
) -> dict:
    """GitHub Issues Comments API로 코멘트를 등록한다."""
    url = f"https://api.github.com/repos/{owner}/{repo}/issues/{pr_num}/comments"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    response = requests.post(url, json={"body": body}, headers=headers)

    if response.status_code == 401:
        raise GithubPosterError(
            f"GitHub 인증 실패 (401) — GITHUB_TOKEN을 확인하세요."
        )
    if not response.ok:
        raise GithubPosterError(
            f"GitHub API 오류: {response.status_code} — {response.text}"
        )

    data = response.json()
    return {"mode": "github", "comment_id": data["id"]}


def _dry_run(pr_num: int, body: str) -> dict:
    """토큰 없을 때 — .dry_run_comments/PR-{n}.md 파일로 저장한다."""
    out_dir = Path(".dry_run_comments")
    out_dir.mkdir(exist_ok=True)
    path = out_dir / f"PR-{pr_num}.md"
    path.write_text(body, encoding="utf-8")
    return {"mode": "dry_run", "path": str(path)}
