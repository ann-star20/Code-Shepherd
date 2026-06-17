"""pr-comment-agent 오케스트레이션 — aggregator → llm_refiner → github_poster."""
from __future__ import annotations

import json
import sys
from pathlib import Path

from aggregator import aggregate
from contracts import AgentOutput, Developer, ReviewReport
from github_poster import post_comment
from llm_refiner import _heuristic_refine, refine


def run_review(
    outputs: list[AgentOutput],
    developer: Developer,
    pr_url: str,
) -> ReviewReport:
    """M2+M3 AgentOutput을 집계해 PR 코멘트를 작성하고 GitHub에 등록한다.

    Args:
        outputs: M2(정적·보안)+M3(테스트·성능) AgentOutput 목록.
        developer: 코멘트 톤을 결정할 개발자 정보.
        pr_url: 코멘트를 등록할 GitHub PR URL.

    Returns:
        ReviewReport (verdict, summary, comment_md, gh_response, escalation_needed).

    Raises:
        GithubPosterError: GitHub API 인증 실패 등 복구 불가 오류.
    """
    # Step 1: 이슈 집계 → (combined_issues, verdict, summary)
    combined_issues, verdict, _summary = aggregate(outputs)

    # Step 2: LLM 코멘트 생성 (실패 시 휴리스틱 fallback)
    try:
        comment_md = refine(combined_issues, verdict, developer.skill_level)
    except Exception:
        comment_md = _heuristic_refine(combined_issues, verdict)

    # Step 3: GitHub PR 코멘트 등록 (토큰 없으면 dry-run)
    gh_response = post_comment(pr_url, comment_md)

    return ReviewReport(
        verdict=verdict,
        issues=combined_issues,
        comment_md=comment_md,
        gh_response=gh_response,
    )


# ── CLI 진입점 ────────────────────────────────────────────────────────────────

def _load_fixtures(fixtures_path: str | None = None) -> tuple[list[AgentOutput], str]:
    """fixtures JSON을 읽어 (outputs, pr_url) 반환. 경로 미지정 시 기본 경로 사용."""
    base = Path(__file__).parent
    path = Path(fixtures_path) if fixtures_path else base / "validation" / "fixtures" / "sample_outputs.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    outputs = [AgentOutput(**entry) for entry in data]
    pr_id = outputs[0].pr_id if outputs else "PR-001"
    pr_num = str(int(pr_id.replace("PR-", ""))) if pr_id.startswith("PR-") and pr_id[3:].isdigit() else "1"
    pr_url = f"https://github.com/acme/repo/pull/{pr_num}"
    return outputs, pr_url


if __name__ == "__main__":
    fixtures_arg = sys.argv[1] if len(sys.argv) > 1 else None
    outputs, pr_url = _load_fixtures(fixtures_arg)
    developer = Developer(name="dev", skill_level="mid")

    print(f"[run_review] PR: {pr_url}  |  {len(outputs)} agent outputs")
    report = run_review(outputs, developer, pr_url)

    import sys
    out = sys.stdout.buffer if hasattr(sys.stdout, "buffer") else sys.stdout

    def _safe_print(text: str) -> None:
        out.write((text + "\n").encode("utf-8", errors="replace"))
        out.flush()

    _safe_print(f"\n{'='*60}")
    _safe_print(f"  verdict          : {report.verdict}")
    _safe_print(f"  escalation_needed: {report.escalation_needed}")
    _safe_print(f"  summary          : critical={report.summary.critical}  major={report.summary.major}  minor={report.summary.minor}")
    _safe_print(f"  gh_response      : {report.gh_response}")
    _safe_print(f"{'='*60}")
    _safe_print(f"\n--- comment_md ---\n{report.comment_md}\n")
