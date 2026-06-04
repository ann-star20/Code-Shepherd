"""
llm_judge 노드 — LLM severity 재판단

이 노드는 enriched 리스트의 각 이슈에 대해 LLM을 호출하여 severity를 재판단한다.
프롬프트 생성은 dev2/prompts/severity_judge.py가 담당하고,
이 노드는 LLM 호출·파싱·fallback만 처리한다. (단일 책임 원칙)

모델 라우팅 전략 (비용 최적화):
    Critical → claude-sonnet-4-6      보안/품질 직접 영향 → 가장 정확한 모델
    Major    → claude-haiku-4-5       리팩토링 필요 → 빠르고 저렴
    Minor    → LLM 생략                CLI 도구 판단 신뢰, 비용 절감

환경변수:
    USE_MOCK_LLM=true  (기본값, 개발 중) → 실제 API 호출 없이 Mock 응답
    USE_MOCK_LLM=false (통합/데모)       → 실제 claude API 호출

에러 처리:
    LLM JSON 파싱 실패 → 1회 재시도 → 실패 시 원래 severity 유지 (CLAUDE.md §12)
    LLM 타임아웃 (30초) → 원래 severity 유지 (CLAUDE.md §6)
    개별 이슈 실패 → 해당 이슈만 fallback, 나머지 계속 (CLAUDE.md §12)
"""

import asyncio
import json
import logging
import os

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage

from dev2.nodes.concept_mapper import enrich_with_concept_mapping
from dev2.prompts.severity_judge import build_severity_prompt
from dev2.schema import Dev2State

logger = logging.getLogger(__name__)

# ── 모델 라우팅 테이블 ─────────────────────────────────────────────────────────
# Week 5 교체 포인트: 팀 결정에 따라 모델 ID 변경 가능 (코드 변경 최소화)
MODEL_ROUTING: dict[str, str | None] = {
    "Critical": "claude-sonnet-4-6",          # CLAUDE.md §9: 팀 표준 LLM
    "Major":    "claude-haiku-4-5-20251001",   # 빠르고 저렴 (Major는 haiku로 충분)
    "Minor":    None,                           # LLM 생략 — CLI 도구 판단 신뢰
}

# LLM 응답에서 허용되는 severity 값 (검증용)
VALID_SEVERITIES = frozenset({"Critical", "Major", "Minor"})

# 이슈당 LLM 호출 타임아웃 (CLAUDE.md §6)
LLM_TIMEOUT_SEC = 30.0

# 모델별 ChatAnthropic 인스턴스 캐시 — 매 이슈마다 재생성 방지
_llm_cache: dict[str, "ChatAnthropic"] = {}


_MOCK_ISSUE_TYPE: dict[str, str] = {
    "Critical": "Vulnerability",
    "Major": "Bug",
    "Minor": "Code Smell",
}


def _get_mock_response(current_severity: str) -> dict:
    """
    Mock LLM 응답 반환 — USE_MOCK_LLM=true 시 사용.

    실제 LLM 응답과 동일한 키 구조를 반환해야 한다.
    → 호출 측(llm_judge_node)이 Mock/실제를 구분하지 않아도 된다.
    → CLAUDE.md §10-3: 코드 변경 없이 환경변수만으로 전환

    Args:
        current_severity: CLI 도구가 매긴 현재 severity

    Returns:
        {"severity", "issue_type", "suggestion", "resolution_example", "rationale"}
    """
    return {
        "severity": current_severity,  # Mock에서는 CLI 판단 그대로 유지
        "issue_type": _MOCK_ISSUE_TYPE.get(current_severity, "Bug"),
        "suggestion": f"[MOCK] {current_severity} 수준 이슈. 실제 환경에서 LLM 판단을 받으세요.",
        "resolution_example": "[MOCK] 실제 환경에서 구체적인 교정 코드 예시가 제공됩니다.",
        "rationale": "[MOCK] USE_MOCK_LLM=true — 개발 환경 Mock 응답",
    }


async def _call_llm_with_retry(
    prompt: str,
    model_id: str,
    max_retries: int = 1,
) -> dict:
    """
    LLM 호출 + JSON 파싱 + 재시도 패턴 (CLAUDE.md §12)

    흐름:
        1. ChatAnthropic.ainvoke() — LangChain 비동기 호출 (LangSmith 자동 추적)
        2. response.content → json.loads() 파싱
        3. severity 허용값 검증 (Critical|Major|Minor만 허용)
        4. 파싱 실패 시 max_retries번 재시도
        5. 전부 실패 → {} 반환 (호출 측에서 fallback)

    Args:
        prompt: build_severity_prompt()로 생성된 프롬프트 문자열
        model_id: 사용할 Claude 모델 ID
        max_retries: 최대 재시도 횟수 (기본 1회 — 2회 호출이 최대)

    Returns:
        {"severity": str, "suggestion": str, "rationale": str}
        파싱 2회 실패 시 {}
    """
    if model_id not in _llm_cache:
        _llm_cache[model_id] = ChatAnthropic(
            model=model_id,
            temperature=0,              # severity 분류는 결정적(deterministic) 출력 필요
            api_key=os.getenv("ANTHROPIC_API_KEY"),
        )
    llm = _llm_cache[model_id]

    for attempt in range(max_retries + 1):
        raw_text: str | None = None
        try:
            # ainvoke: LangChain 네이티브 비동기 — 이벤트 루프 블록 없음
            # LangSmith LANGCHAIN_TRACING_V2=true 시 자동으로 추적됨 (코드 변경 불필요)
            response = await llm.ainvoke([HumanMessage(content=prompt)])
            raw_text = response.content

            parsed = json.loads(raw_text)

            # 검증: severity가 허용값인지 확인
            # LLM이 "Crtical"(오타), "Blocker"(정의 외) 등을 반환할 수 있음
            if parsed.get("severity") not in VALID_SEVERITIES:
                logger.warning(
                    "llm_judge: 유효하지 않은 severity '%s' (시도 %d/%d) — 재시도",
                    parsed.get("severity"), attempt + 1, max_retries + 1,
                )
                continue

            return parsed

        except json.JSONDecodeError as exc:
            logger.warning(
                "llm_judge: JSON 파싱 실패 (시도 %d/%d) — %s | 원문: %.100s",
                attempt + 1, max_retries + 1, exc,
                raw_text if raw_text is not None else "(응답 없음)",
            )
            if attempt < max_retries:
                continue

    # max_retries + 1회 모두 실패
    logger.error(
        "llm_judge: LLM 응답 파싱 %d회 모두 실패 — 빈 dict 반환 (호출 측 fallback)",
        max_retries + 1,
    )
    return {}


async def _judge_single_issue(
    issue: dict,
    developer_level: str,
    use_mock: bool,
    tech_stack: list[str] | None = None,
) -> dict:
    """
    단일 이슈에 대해 LLM severity 재판단.

    Minor → LLM 생략 (즉시 반환)
    Critical/Major → 모델 라우팅 → 프롬프트 빌드 → LLM 호출 → 파싱
    파싱 실패 or 타임아웃 → 원래 severity 유지 (CLAUDE.md §12 fallback)

    Args:
        issue: enriched 이슈 dict. similar_issues 필드가 있어야 RAG context 활성화.
               (vector_search_node가 채운 유사 이슈 목록)
        developer_level: "junior" | "mid" | "senior"
        use_mock: True → Mock 응답 / False → 실제 LLM API 호출

    Returns:
        LLM 판단이 반영된 새 dict (원본 issue는 수정하지 않음)
        추가 필드: llm_judged(bool), llm_model(str|None), llm_rationale(str)
    """
    current_severity = issue.get("severity", "Minor")
    model_id = MODEL_ROUTING.get(current_severity)

    # ── Minor: LLM 생략 ────────────────────────────────────────────────────────
    # Minor는 CLI 도구 판단으로 충분 — LLM 호출 비용/시간 절약
    if model_id is None:
        return {**issue, "llm_judged": False, "llm_model": None, "llm_rationale": ""}

    # ── 프롬프트 빌드 (severity_judge.py에서 5가지 기법 적용) ──────────────────
    similar_cases = issue.get("similar_issues", [])
    prompt = build_severity_prompt(
        message=issue.get("message", ""),
        current_severity=current_severity,
        developer_level=developer_level,
        similar_cases=similar_cases,
        tech_stack=tech_stack,
        file_name=issue.get("file", ""),
    )

    # ── Mock 또는 실제 LLM 호출 ───────────────────────────────────────────────
    if use_mock:
        # Mock: 실제 API 호출 없음 — 개발 중 비용/속도/테스트 독립성 확보
        llm_result = _get_mock_response(current_severity)
    else:
        # 실제 LLM 호출 — 타임아웃 처리 포함 (CLAUDE.md §6)
        try:
            llm_result = await asyncio.wait_for(
                _call_llm_with_retry(prompt, model_id),
                timeout=LLM_TIMEOUT_SEC,
            )
        except asyncio.TimeoutError:
            logger.warning(
                "llm_judge: %s 이슈 LLM %g초 타임아웃 — 원래 severity 유지",
                current_severity, LLM_TIMEOUT_SEC,
            )
            llm_result = {}

    # ── Fallback: 파싱 실패 or 타임아웃 → 원래 severity 유지 ─────────────────
    if not llm_result:
        return {**issue, "llm_judged": False, "llm_model": model_id, "llm_rationale": ""}

    # ── LLM 판단 적용: severity/issue_type/suggestion/resolution_example 업데이트 ──
    return {
        **issue,
        "severity": llm_result.get("severity", current_severity),
        "issue_type": llm_result.get("issue_type", issue.get("issue_type", "Bug")),
        "suggestion": llm_result.get("suggestion", issue.get("suggestion", "")),
        "resolution_example": llm_result.get("resolution_example", issue.get("resolution_example", "")),
        "llm_rationale": llm_result.get("rationale", ""),
        "llm_judged": True,
        "llm_model": model_id,
    }


async def llm_judge_node(state: Dev2State) -> dict:
    """
    LangGraph 노드: enriched 이슈 목록에 LLM severity 재판단을 적용한다.

    흐름:
        1. enriched 읽기 (vector_search_node가 similar_issues로 보강한 이슈 목록)
        2. USE_MOCK_LLM 환경변수 확인 (Mock/실제 분기)
        3. asyncio.gather로 이슈별 병렬 LLM 판단
        4. 판단 결과를 enriched에 반영하여 반환

    Args:
        state: Dev2State — enriched, skill_level 필드 사용

    Returns:
        {"enriched": [...]} — LLM 판단이 적용된 이슈 목록
        — LangGraph가 이 dict를 state에 merge한다
    """
    enriched = state.get("enriched", [])
    if not enriched:
        logger.warning("llm_judge_node: enriched가 비어 있음 — LLM 판단 생략")
        return {"enriched": []}

    # developer_level: CLAUDE.md §12 — DB 미존재 시 "junior" 기본값으로 진행
    developer_level = state.get("skill_level", "junior")

    # USE_MOCK_LLM: CLAUDE.md §10-3 — 개발 중 기본 true (실제 API 호출 없음)
    use_mock = os.getenv("USE_MOCK_LLM", "true").lower() == "true"

    if use_mock:
        logger.info(
            "llm_judge_node: USE_MOCK_LLM=true — Mock LLM 사용 (이슈 %d개)",
            len(enriched),
        )
    else:
        logger.info(
            "llm_judge_node: 실제 LLM 호출 시작 (이슈 %d개, dev_level=%s)",
            len(enriched), developer_level,
        )

    tech_stack: list[str] = state.get("tech_stack", [])  # type: ignore[assignment]

    # ── 이슈별 병렬 LLM 판단 (asyncio.gather + return_exceptions) ─────────────
    # return_exceptions=True: 개별 이슈 실패가 전체 파이프라인을 막지 않음 (CLAUDE.md §12)
    tasks = [
        _judge_single_issue(issue, developer_level, use_mock, tech_stack)
        for issue in enriched
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    # ── 결과 취합: 예외 → fallback, 정상 → 그대로 ─────────────────────────────
    judged: list[dict] = []
    for idx, result in enumerate(results):
        if isinstance(result, Exception):
            # 개별 이슈 처리 실패 → 원본 이슈 유지 (에러 삼키지 않음, CLAUDE.md §10-4)
            logger.error(
                "llm_judge_node: 이슈 %d 처리 예외 발생 — %s | 원본 이슈 유지",
                idx, result,
            )
            judged.append({**enriched[idx], "llm_judged": False, "llm_model": None, "llm_rationale": ""})
        else:
            judged.append(result)

    # ── M4 개념 매핑 적용 ────────────────────────────────────────────────────────
    # severity 재판단 완료 후 keyword/sub_category/code_snippet/learning_context 부여
    pr_diff: str = state.get("pr_diff", "")  # type: ignore[assignment]
    judged = [
        enrich_with_concept_mapping(j, pr_diff, tech_stack)
        for j in judged
    ]

    # ── 처리 통계 로그 ─────────────────────────────────────────────────────────
    llm_called = sum(1 for j in judged if j.get("llm_judged"))
    llm_skipped = sum(1 for j in judged if j.get("llm_model") is None)
    llm_fallback = sum(1 for j in judged if not j.get("llm_judged") and j.get("llm_model") is not None)
    concept_mapped = sum(1 for j in judged if j.get("keyword"))

    logger.info(
        "llm_judge_node 완료: 총 %d개 — LLM 호출 %d개 / Minor 생략 %d개 / fallback %d개 / keyword 매핑 %d개",
        len(judged), llm_called, llm_skipped, llm_fallback, concept_mapped,
    )

    return {"enriched": judged}
