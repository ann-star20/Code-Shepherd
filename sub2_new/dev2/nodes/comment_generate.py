"""
comment_generate 노드 — LLM 코멘트 정제

이 노드는 store 노드가 완료된 후 실행된다.
enriched 이슈를 바탕으로 LLM이 개발자 수준(skill_level)에 맞춘
GitHub PR 코멘트 마크다운을 생성한다.

흐름:
    store → comment_generate → github_comment

CLAUDE.md 준수:
    §4     skill_level: junior | mid | senior 기반 개인화
    §9     LLM: Critical → claude-sonnet-4-6 / 그 외 → claude-haiku-4-5
    §12    LLM 응답 파싱 실패 → fallback 텍스트 반환 (파이프라인 중단 없음)
"""

import logging
import os

from dev2.prompts.comment_builder import build_comment_prompt
from dev2.schema import Dev2State

logger = logging.getLogger(__name__)

USE_MOCK_LLM = os.getenv("USE_MOCK_LLM", "true").lower() == "true"


def _mock_comment(issues: list[dict], skill_level: str, pr_id: str) -> str:
    """테스트용 Mock 코멘트 (USE_MOCK_LLM=true 시 사용)"""
    critical = [i for i in issues if i.get("severity") == "Critical"]
    major = [i for i in issues if i.get("severity") == "Major"]
    minor = [i for i in issues if i.get("severity") == "Minor"]

    lines = [f"## 🔍 코드 리뷰 결과 — PR #{pr_id}\n"]
    lines.append(f"**개발자 수준**: {skill_level}\n")

    if critical:
        lines.append("### 🚨 Critical 이슈")
        for i in critical:
            lines.append(f"- `{i.get('file', '?')}:{i.get('line', '?')}` — {i.get('message', '?')}")
            lines.append(f"  - 수정 방법: {i.get('suggestion', '?')}")

    if major:
        lines.append("\n### ⚠️ Major 이슈")
        for i in major:
            lines.append(f"- `{i.get('file', '?')}:{i.get('line', '?')}` — {i.get('message', '?')}")
            lines.append(f"  - 수정 방법: {i.get('suggestion', '?')}")

    if minor:
        lines.append("\n### ℹ️ Minor 이슈")
        for i in minor:
            lines.append(f"- `{i.get('file', '?')}:{i.get('line', '?')}` — {i.get('message', '?')}")

    lines.append(f"\n**요약**: Critical {len(critical)}건 / Major {len(major)}건 / Minor {len(minor)}건")
    return "\n".join(lines)


async def _call_llm(prompt: str, has_critical: bool) -> str:
    """
    LLM 호출 — Critical 여부에 따라 모델 라우팅.

    Args:
        prompt: build_comment_prompt()가 생성한 프롬프트
        has_critical: Critical 이슈 존재 여부

    Returns:
        LLM이 생성한 마크다운 코멘트 문자열
    """
    model = "claude-sonnet-4-6" if has_critical else "claude-haiku-4-5-20251001"

    try:
        import anthropic  # noqa: PLC0415

        client = anthropic.AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY", ""))
        response = await client.messages.create(
            model=model,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text.strip()

    except Exception as exc:
        logger.error("_call_llm: LLM 호출 실패 (%s) — %s", model, exc)
        raise


async def comment_generate_node(state: Dev2State) -> dict:
    """
    LangGraph 노드: enriched 이슈를 바탕으로 PR 코멘트를 생성한다.

    흐름:
        1. enriched에서 이슈 추출
        2. skill_level에 맞는 프롬프트 조립
        3. LLM 호출 (Critical → sonnet, 그 외 → haiku, Mock → 스킵)
        4. comment_body state 저장

    Args:
        state: Dev2State — enriched, skill_level, pr_id 필드 사용

    Returns:
        {"comment_body": str}
    """
    enriched: list[dict] = state.get("enriched", [])
    skill_level: str = state.get("skill_level", "junior")
    pr_id: str = state.get("pr_id", "?")
    has_critical = any(i.get("severity") == "Critical" for i in enriched)

    if not enriched:
        logger.warning("comment_generate_node: enriched 비어 있음 — 기본 코멘트 반환")
        return {"comment_body": f"## 코드 리뷰 결과 — PR #{pr_id}\n\n이슈가 발견되지 않았습니다. ✅"}

    if USE_MOCK_LLM:
        logger.debug("comment_generate_node: Mock 모드 — LLM 미호출")
        comment = _mock_comment(enriched, skill_level, pr_id)
        return {"comment_body": comment}

    prompt = build_comment_prompt(enriched, skill_level, pr_id)

    try:
        comment = await _call_llm(prompt, has_critical)
    except Exception:
        # [CLAUDE.md §12] LLM 실패 → fallback 코멘트로 파이프라인 계속
        logger.error("comment_generate_node: LLM 실패 — fallback 코멘트 사용")
        comment = _mock_comment(enriched, skill_level, pr_id)

    logger.info(
        "comment_generate_node 완료: comment %d자 (task_id=%s)",
        len(comment), state.get("task_id", "?"),
    )
    return {"comment_body": comment}
