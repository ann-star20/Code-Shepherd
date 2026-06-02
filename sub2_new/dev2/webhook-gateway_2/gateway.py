"""게이트웨이 핵심 — PR 정보를 받아 clone하고, 등록된 에이전트를 모두 호출.

흐름:
  PRContext(repo·sha·pr_number)
    → git clone (코드 받아오기)
    → GitHub API로 diff 수집
    → 등록된 분석 에이전트 전부 호출 (부분 실패 허용)
    → 이슈 합치기 + 집계 + 코멘트 + GitHub 등록
"""
from __future__ import annotations

import os
import subprocess
import tempfile
import urllib.request

from registry import PRContext, registered_agents


def clone_repo(ctx: PRContext) -> str:
    """레포를 shallow clone하고 commit_sha로 checkout → 로컬 경로 반환."""
    work = tempfile.mkdtemp(prefix="gw_repo_")
    subprocess.run(
        ["git", "clone", "--depth", "1", ctx.clone_url, work],
        check=True, capture_output=True,
    )
    if ctx.commit_sha:
        subprocess.run(
            ["git", "-C", work, "fetch", "--depth", "1", "origin", ctx.commit_sha],
            check=True, capture_output=True,
        )
        subprocess.run(
            ["git", "-C", work, "checkout", ctx.commit_sha],
            check=True, capture_output=True,
        )
    return work


def fetch_pr_diff(ctx: PRContext, token: str = "") -> str:
    """GitHub API로 PR의 unified diff를 가져온다 (토큰 없으면 빈 문자열)."""
    token = token or os.getenv("GITHUB_TOKEN", "")
    url = f"https://api.github.com/repos/{ctx.repo_full_name}/pulls/{ctx.pr_number}"
    req = urllib.request.Request(url)
    req.add_header("Accept", "application/vnd.github.v3.diff")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except Exception:
        return ""


def run_all_agents(ctx: PRContext) -> dict[str, list[dict]]:
    """등록된 모든 분석 에이전트를 호출. 결과를 {agent_name: issues[]}로 반환.

    부분 실패 허용: 한 에이전트가 죽어도 나머지는 계속.
    """
    results: dict[str, list[dict]] = {}
    for agent in registered_agents():
        try:
            issues = agent.fn(ctx) or []
        except Exception as e:  # noqa: BLE001
            print(f"  [partial_fail] {agent.name}: {e}")
            issues = []
        results[agent.name] = issues
    return results


def process_pr(ctx: PRContext, *, do_comment: bool = True) -> dict:
    """PR 1건 전체 처리: clone → diff → 분석 → (집계·코멘트).

    Returns:
        {"context": ctx, "results": {...}, "verdict": str, "comment": str, "post": {...}}
    """
    # 1. clone + diff
    ctx.work_dir = clone_repo(ctx)
    if not ctx.pr_diff:
        ctx.pr_diff = fetch_pr_diff(ctx)

    # 2. 등록된 에이전트 전부 호출
    results = run_all_agents(ctx)
    all_issues = [i for issues in results.values() for i in issues]

    out: dict = {
        "context": ctx,
        "results": results,
        "issue_count": len(all_issues),
    }

    # 3. (선택) 집계·코멘트 — pr-comment-agent 연결
    if do_comment:
        try:
            verdict, comment, post = _aggregate_and_comment(ctx, all_issues)
            out.update(verdict=verdict, comment=comment, post=post)
        except Exception as e:  # noqa: BLE001
            print(f"  [comment skipped] {e}")

    return out


def _aggregate_and_comment(ctx: PRContext, issues: list[dict]):
    """pr-comment-agent의 집계·코멘트·등록을 호출 (지연 import)."""
    import sys
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    prc = os.path.join(root, "pr-comment-agent")
    sys.path.insert(0, prc)

    # pr-comment-agent/.env 의 GITHUB_TOKEN·GOOGLE_API_KEY 로드 (게이트웨이가 공유)
    prc_env = os.path.join(prc, ".env")
    if os.path.exists(prc_env):
        for ln in open(prc_env, encoding="utf-8"):
            ln = ln.strip()
            if ln and not ln.startswith("#") and "=" in ln:
                k, v = ln.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())

    from contracts import CombinedIssue  # type: ignore
    from llm_refiner import refine
    from github_poster import post_comment

    combined = [
        CombinedIssue(
            severity=i["severity"], file=i.get("file", ""), line=i.get("line"),
            message=i.get("message", ""), rule_id=i.get("rule_id", ""),
            suggestion=i.get("suggestion", ""), source_agent=i.get("_agent", ""),
        )
        for i in issues
    ]
    crit = sum(1 for i in combined if i.severity == "Critical")
    major = sum(1 for i in combined if i.severity == "Major")
    verdict = "escalate" if crit >= 1 else ("rework" if major >= 3 else "lgtm")

    comment = refine(combined, verdict, "junior")
    owner, name = ctx.repo_full_name.split("/", 1)
    post = post_comment("", comment, owner=owner, repo=name, pr_num=ctx.pr_number)
    return verdict, comment, post
