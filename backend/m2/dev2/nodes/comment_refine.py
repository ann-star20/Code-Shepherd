"""
comment_refine 노드 (PRD 노드 M) — 파이프라인 2 LLM PR 코멘트 생성

aggregate_node가 취합한 전체 이슈(aggregated_issues)를 바탕으로 LLM이
개발자 수준(skill_level)에 맞춘 GitHub PR 코멘트 마크다운을 생성한다.

흐름:
    aggregate → comment_refine → github_comment → [Critical?] → slack_notify

CLAUDE.md 준수:
    §4   skill_level 기반 개인화
    §7   USE_MOCK_LLM=true → 실제 API 없이 결정적 Mock 코멘트
    §9   LLM: claude-sonnet-4-6 (팀 표준)
    §12  LLM 실패 → fallback 코멘트로 파이프라인 계속 (중단 없음)
"""

import logging
import os

from dev2.prompts.comment_refine import build_comment_prompt
from dev2.schema import AggregateState

# langchain_anthropic가 미설치된 환경에서도 모듈 import가 가능하도록 보호.
# 테스트는 patch("dev2.nodes.comment_refine.ChatAnthropic")로 이 심볼을 교체한다.
try:
    from langchain_anthropic import ChatAnthropic
except ImportError:  # pragma: no cover - 선택적 의존성
    ChatAnthropic = None

logger = logging.getLogger(__name__)


def _use_mock_llm() -> bool:
    """USE_MOCK_LLM 환경변수를 호출 시점에 평가한다 (테스트 patch 반영)."""
    return os.getenv("USE_MOCK_LLM", "true").lower() == "true"


def _build_mock_comment(state: AggregateState) -> str:
    """USE_MOCK_LLM=true 또는 LLM 실패 시 사용하는 결정적 폴백 코멘트."""
    s = state.get("total_summary", {})
    issues = state.get("aggregated_issues", [])
    lines = [
        f"| {i.get('file', '')} | {i.get('line', '')} | {i.get('severity', '')} | {i.get('message', '')} |"
        for i in issues[:10]
    ]
    table = "\n".join(lines) if lines else "이슈 없음"
    return (
        f"## 자동 코드 리뷰 결과\n\n"
        f"**Critical**: {s.get('critical', 0)}건 | "
        f"**Major**: {s.get('major', 0)}건 | "
        f"**Minor**: {s.get('minor', 0)}건\n\n"
        f"| 파일 | 라인 | Severity | 이슈 |\n|---|---|---|---|\n{table}"
    )


async def comment_refine_node(state: AggregateState) -> dict:
    """
    PRD 노드 M: LLM으로 사용자 수준 맞춤 PR 코멘트 생성.

    USE_MOCK_LLM=true → 결정적 Mock 코멘트 반환 (실제 API 없음).
    LLM 실패 / 미설치 → 폴백 코멘트 생성 (파이프라인 중단 없음, CLAUDE.md §12).

    Args:
        state: AggregateState — aggregated_issues, total_summary, skill_level 등 사용

    Returns:
        {"comment_body": str}
    """
    if _use_mock_llm() or ChatAnthropic is None:
        return {"comment_body": _build_mock_comment(state)}

    try:
        prompt = build_comment_prompt(
            issues=state.get("aggregated_issues", []),
            summary=state.get("total_summary", {}),
            skill_level=state.get("skill_level", "junior"),
            tech_stack=state.get("tech_stack", []),
            architecture_docs=state.get("architecture_docs", []),
            previous_pr_issues=state.get("previous_pr_issues", []),
        )
        llm = ChatAnthropic(model="claude-sonnet-4-6", temperature=0)
        response = await llm.ainvoke(prompt)
        body = getattr(response, "content", response)
        logger.info(
            "comment_refine_node: LLM 코멘트 생성 완료 (task_id=%s)",
            state.get("task_id", "?"),
        )
        return {"comment_body": body}

    except Exception as exc:
        # [CLAUDE.md §12] LLM 실패 → 폴백 코멘트로 파이프라인 계속
        logger.error("comment_refine_node: LLM 실패, 폴백 코멘트 사용 — %s", exc)
        return {"comment_body": _build_mock_comment(state)}
