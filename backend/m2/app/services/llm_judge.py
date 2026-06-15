"""LLM-judge 레이어 — 도구가 뽑은 이슈의 severity/suggestion을 LLM이 재판단.

dev2/nodes/llm_judge.py 청사진을 app/ 계약(IssueItem)에 맞춰 자립형으로 미러링.
context(architecture_docs / coding_conventions / previous_pr_issues)를 프롬프트에
주입해 판단 근거를 보강한다.

설계 불변식:
  - **mock = 무해 no-op**: USE_MOCK_LLM=true(현재 운영 기본값)에서는 원본 이슈를
    그대로 반환한다. app/은 라이브 스텁이므로 mock placeholder로 출력을 오염시키지
    않는다. 실제 재판단은 USE_MOCK_LLM=false일 때만 수행한다.
  - **graceful**: 타임아웃·파싱실패·개별 이슈 예외 시 원본 severity/suggestion 유지
    (CLAUDE.md §6·§12). LLM 실패가 분석을 중단시키지 않는다.
  - **lazy import**: langchain_anthropic는 실제 호출 경로에서만 import한다
    (mock/미설치 환경에서 모듈 로드가 깨지지 않도록).

모델 라우팅(비용 최적화):
  Critical → claude-sonnet-4-6   (보안/품질 직접 영향)
  Major    → claude-haiku-4-5    (빠르고 저렴)
  Minor    → LLM 생략             (CLI 도구 판단 신뢰)
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re

from shared.contracts import AnalysisContext, DeveloperProfile, IssueItem, IssueSummary

log = logging.getLogger(__name__)

MODEL_ROUTING: dict[str, str | None] = {
    "Critical": "claude-sonnet-4-6",
    "Major": "claude-haiku-4-5-20251001",
    "Minor": None,  # LLM 생략 — CLI 도구 판단 신뢰
}

VALID_SEVERITIES = frozenset({"Critical", "Major", "Minor"})
LLM_TIMEOUT_SEC = 30.0

# 모델별 ChatAnthropic 인스턴스 캐시
_llm_cache: dict[str, object] = {}


def _use_mock() -> bool:
    return os.getenv("USE_MOCK_LLM", "true").lower() == "true"


def summarize(issues: list[IssueItem]) -> IssueSummary:
    """재판단 후 issues로부터 severity 요약을 다시 계산한다."""
    summary = IssueSummary()
    for issue in issues:
        if issue.severity == "Critical":
            summary.critical += 1
        elif issue.severity == "Major":
            summary.major += 1
        else:
            summary.minor += 1
    return summary


# ── 프롬프트 빌더 ──────────────────────────────────────────────────────────

def build_judge_prompt(
    issue: IssueItem,
    context: AnalysisContext,
    developer_level: str,
    tech_stack: list[str],
) -> str:
    """context 3필드를 주입한 severity 재판단 프롬프트를 만든다.

    - coding_conventions  → 컨벤션 위반이면 가중
    - previous_pr_issues  → 반복 실수면 severity 상향/강조
    - architecture_docs   → 아키텍처 맥락 근거
    """
    parts: list[str] = []
    if context.coding_conventions:
        parts.append(f"[사내 코딩 컨벤션]\n{context.coding_conventions}")
    if context.previous_pr_issues:
        joined = "\n".join(f"- {p}" for p in context.previous_pr_issues)
        parts.append(
            "[이 개발자의 과거 반복 이슈]\n"
            f"{joined}\n"
            "위 패턴과 일치하면 반복 실수이므로 severity를 상향하거나 강조하라."
        )
    if context.architecture_docs:
        docs = "\n---\n".join(context.architecture_docs[:3])
        parts.append(f"[관련 아키텍처/지식 문서]\n{docs}")

    context_block = "\n\n".join(parts) if parts else "(추가 context 없음)"
    stack = ", ".join(tech_stack) if tech_stack else "미상"

    return (
        "당신은 시니어 코드 리뷰어다. 정적/보안 도구가 발견한 이슈 1건의 severity를 "
        "주어진 사내 context를 근거로 재판단한다.\n\n"
        f"개발자 숙련도: {developer_level} / 기술 스택: {stack}\n\n"
        f"{context_block}\n\n"
        "[도구가 발견한 이슈]\n"
        f"- 파일: {issue.file}\n"
        f"- 라인: {issue.line}\n"
        f"- 규칙: {issue.rule_id}\n"
        f"- 현재 severity: {issue.severity}\n"
        f"- 메시지: {issue.message}\n\n"
        "다음 JSON만 출력하라(코드펜스/설명 금지):\n"
        '{"severity": "Critical|Major|Minor", "suggestion": "구체적 교정 방향", '
        '"rationale": "판단 근거 한 줄"}'
    )


# ── LLM 응답 파싱 ──────────────────────────────────────────────────────────

def _extract_json_object(content: object) -> str:
    """LLM 응답에서 json.loads에 넘길 JSON 본문을 추출(코드펜스/잡텍스트 제거)."""
    if isinstance(content, list):
        text = "".join(
            b.get("text", "") if isinstance(b, dict) else str(b) for b in content
        )
    else:
        text = content if isinstance(content, str) else str(content)

    s = text.strip()
    if s.startswith("```"):
        s = re.sub(r"^```[a-zA-Z0-9_-]*[ \t]*\r?\n?", "", s)
        s = re.sub(r"\r?\n?```[ \t]*$", "", s).strip()
    if not s.startswith("{"):
        start = s.find("{")
        end = s.rfind("}")
        if start != -1 and end > start:
            s = s[start : end + 1]
    return s.strip()


def _get_llm(model_id: str):
    """ChatAnthropic 인스턴스(캐시). langchain_anthropic은 여기서만 lazy import."""
    if model_id not in _llm_cache:
        from langchain_anthropic import ChatAnthropic  # lazy — 실제 호출 경로에서만

        _llm_cache[model_id] = ChatAnthropic(
            model=model_id,
            temperature=0,  # severity 분류는 결정적 출력 필요
            api_key=os.getenv("ANTHROPIC_API_KEY"),
        )
    return _llm_cache[model_id]


async def _call_llm_with_retry(prompt: str, model_id: str, max_retries: int = 1) -> dict:
    """LLM 호출 + JSON 파싱 + 재시도(CLAUDE.md §12). 전부 실패 시 {} 반환."""
    from langchain_core.messages import HumanMessage  # lazy

    llm = _get_llm(model_id)
    for attempt in range(max_retries + 1):
        raw_text: str | None = None
        try:
            response = await llm.ainvoke([HumanMessage(content=prompt)])
            raw_text = _extract_json_object(response.content)
            parsed = json.loads(raw_text)
            if parsed.get("severity") not in VALID_SEVERITIES:
                log.warning(
                    "llm_judge: invalid severity '%s' (%d/%d) — retry",
                    parsed.get("severity"), attempt + 1, max_retries + 1,
                )
                continue
            return parsed
        except json.JSONDecodeError as exc:
            log.warning(
                "llm_judge: JSON parse fail (%d/%d) — %s | raw=%.100s",
                attempt + 1, max_retries + 1, exc,
                raw_text if raw_text is not None else "(no response)",
            )
    log.error("llm_judge: all %d attempts failed — fallback", max_retries + 1)
    return {}


async def _judge_single_issue(
    issue: IssueItem,
    context: AnalysisContext,
    developer_level: str,
    tech_stack: list[str],
) -> IssueItem:
    """단일 이슈 재판단. Minor 생략, 실패/타임아웃 시 원본 유지."""
    model_id = MODEL_ROUTING.get(issue.severity)
    if model_id is None:  # Minor — LLM 생략
        return issue

    prompt = build_judge_prompt(issue, context, developer_level, tech_stack)
    try:
        llm_result = await asyncio.wait_for(
            _call_llm_with_retry(prompt, model_id), timeout=LLM_TIMEOUT_SEC
        )
    except asyncio.TimeoutError:
        log.warning("llm_judge: %s 타임아웃 — 원본 유지", issue.severity)
        llm_result = {}

    if not llm_result:  # 파싱 실패·타임아웃 → 원본 유지
        return issue

    new_severity = llm_result.get("severity", issue.severity)
    new_suggestion = llm_result.get("suggestion", issue.suggestion)
    return issue.model_copy(update={"severity": new_severity, "suggestion": new_suggestion})


async def judge_issues(
    issues: list[IssueItem],
    context: AnalysisContext,
    developer: DeveloperProfile | None,
) -> list[IssueItem]:
    """이슈 목록에 LLM severity 재판단을 적용한다.

    USE_MOCK_LLM=true(기본)이면 원본 그대로 반환(no-op). 실제 LLM은 false일 때만.
    개별 이슈 예외는 원본으로 fallback(CLAUDE.md §12) — 전체 중단 없음.
    """
    if not issues or _use_mock():
        return issues

    developer_level = developer.skill_level if developer else "junior"
    tech_stack = developer.tech_stack if developer else []

    tasks = [
        _judge_single_issue(issue, context, developer_level, tech_stack)
        for issue in issues
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    judged: list[IssueItem] = []
    for idx, result in enumerate(results):
        if isinstance(result, Exception):
            log.error("llm_judge: 이슈 %d 예외 — %s | 원본 유지", idx, result)
            judged.append(issues[idx])
        else:
            judged.append(result)
    return judged
