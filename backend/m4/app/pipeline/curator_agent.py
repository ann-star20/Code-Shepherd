"""T11 — Curator 에이전트: 개발자 프로필 + 이슈를 바탕으로 Builder가 따를 카드 생성 지시(curator_instruction)를 만든다 (D22, Section 7).

Phase 1의 고정 규칙 — D15(RAG 검색 필드), D16(card_type 분기), D18(depth 결정) — 을
대체해 개발자 한 명 한 명에게 맞춘 동적인 카드 설계를 가능하게 한다.
"""

import asyncio
import json
from typing import TypedDict

import google.generativeai as genai
from langsmith import traceable

from app.kms.search_adapter import build_search1_text, build_search2_text
from app.models.review_issue import ReviewIssue

CURATOR_MODEL_NAME = "gemini-2.5-flash"
GEMINI_TIMEOUT_SECONDS = 60

# "보안"/"코딩컨벤션"이 비어 있으면 embed_query("")로 인해 rag_search가 None을 반환해
# llm_fallback(=docs_concept/docs_example is None)이 오탐으로 True가 된다 — D15 고정
# 검색어로 채운다. "코드성능검증"은 llm_fallback 판정과 무관해 대상에서 제외한다.
_QUERY_FIELD_FALLBACKS = {
    "보안": build_search1_text,
    "코딩컨벤션": build_search2_text,
}


class DeveloperProfile(TypedDict):
    weak_categories: list[str]
    past_mistakes: list[str]


_CURATOR_PROMPT_BODY = (
    "개발자가 자주 틀리는 분야(weak_categories): {weak_categories}\n"
    "과거 실수 이력(past_mistakes): {past_mistakes}\n"
    "이번 코드 리뷰 이슈 — keyword: {keyword}, severity: {severity}, sub_category: {sub_category}\n"
    "code_context: {code_context}\n"
    "code_snippet:\n{code_snippet}\n"
    "language: {programming_language}, framework: {framework} {framework_version}\n"
    "{retry_hint}"
    "다음 키를 가진 JSON 객체만 반환해: "
    '{{"depth": "deep"|"quick", "focus": string, "analogy": string, '
    '"key_points": [string], "card_type": "concept"|"code_fix", '
    '"query_fields": {{"보안": string, "코딩컨벤션": string, "코드성능검증": string}}}}'
)

CURATOR_PROMPT = (
    "당신은 개발자 한 명 한 명에게 맞춘 학습 카드를 설계하는 큐레이터입니다. "
    "아래 개발자 프로필과 이번 이슈를 바탕으로, Builder 에이전트가 카드를 만들 때 따라야 할 "
    "지시(curator_instruction)를 JSON으로 작성해줘 — 이 개발자에게 가장 효과적인 깊이, "
    "설명 초점, 비유, 핵심 포인트, 카드 종류, RAG 검색 필드를 직접 정해줘.\n" + _CURATOR_PROMPT_BODY
)

# D26 — Curator 재시도 전략: RAGAS 실패 reason에 따라 다른 방향의 재지시 문구를 추가한다.
_NARROW_QUERY_HINT = (
    "참고: 이전 시도에서 검색 문서의 신뢰도(faithfulness) 평가가 낮았다 — "
    "query_fields를 더 좁고 구체적인 키워드로 다시 정해서 검색 범위를 좁혀줘.\n"
)
_CHANGE_FRAMING_HINT = (
    "참고: 이전 시도에서 카드 설명의 적합도(answer_relevancy) 평가가 낮았다 — "
    "focus와 analogy를 바꿔서 다른 설명 방식으로 다시 설계해줘.\n"
)


def _retry_hint(hint: str | None) -> str:
    if hint == "narrow_query":
        return _NARROW_QUERY_HINT
    if hint == "change_framing":
        return _CHANGE_FRAMING_HINT
    return ""


def _format_list(items: list[str]) -> str:
    return ", ".join(items) if items else "(기록 없음)"


def _fill_empty_query_fields(query_fields: dict[str, str], issue: ReviewIssue) -> dict[str, str]:
    return {
        category: value or _QUERY_FIELD_FALLBACKS[category](issue) if category in _QUERY_FIELD_FALLBACKS else value
        for category, value in query_fields.items()
    }


@traceable(run_type="llm", name="curator_agent")
async def curator_agent(
    *,
    profile: DeveloperProfile,
    issue: ReviewIssue,
    hint: str | None = None,
) -> dict:
    """Curator Agent (gemini-2.5-flash) — 개발자 프로필 + 이슈 → curator_instruction(D22) JSON을 반환한다."""
    prompt = CURATOR_PROMPT.format(
        weak_categories=_format_list(profile["weak_categories"]),
        past_mistakes=_format_list(profile["past_mistakes"]),
        keyword=issue.keyword,
        severity=issue.severity,
        sub_category=issue.sub_category or "(없음)",
        code_context=issue.code_context or "(없음)",
        code_snippet=(issue.code_snippet[:300] if issue.code_snippet else "(없음)"),
        programming_language=issue.programming_language or "(없음)",
        framework=issue.framework or "(없음)",
        framework_version=issue.framework_version or "",
        retry_hint=_retry_hint(hint),
    )
    model = genai.GenerativeModel(CURATOR_MODEL_NAME)
    # response_mime_type 미지정 시 Gemini가 JSON을 마크다운 코드펜스로 감싸 반환해 json.loads가 실패함 (build_card와 동일 이슈)
    try:
        response = await asyncio.wait_for(
            model.generate_content_async(
                prompt,
                generation_config=genai.GenerationConfig(response_mime_type="application/json"),
            ),
            timeout=GEMINI_TIMEOUT_SECONDS,
        )
    except TimeoutError as exc:
        raise TimeoutError(f"curator_agent: Gemini 응답 시간 초과 ({GEMINI_TIMEOUT_SECONDS}s)") from exc
    instruction = json.loads(response.text)
    instruction["query_fields"] = _fill_empty_query_fields(instruction["query_fields"], issue)
    return instruction
