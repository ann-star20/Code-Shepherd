"""
Stage 2: Markdown 검증 Agent (trc_0002)

Gemini 2.5 Flash를 사용해 변환된 Markdown의 품질을 점수화한다.
품질 점수 < 0.8 또는 표/이미지 구조 손실 감지 시 HITL 큐에 등록하고 파이프라인을 일시 중단.

출력:
    state["validated_markdown"]  검증 통과한 Markdown (hitl_required=False일 때)
    state["quality_score"]       0.0 ~ 1.0
    state["quality_issues"]      발견된 품질 문제 목록
    state["hitl_required"]       True이면 파이프라인 일시 중단
"""

from __future__ import annotations

import json
import logging
import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.pipeline.models import DocPipelineState

logger = logging.getLogger(__name__)

from langchain_core.messages import HumanMessage, SystemMessage

from app.pipeline._gemini import call_gemini_with_retry, parse_gemini_json
from app.pipeline.stage1_document_parser_agent import (
    _gemini_format_correct,
    _normalize_heading_hierarchy,
    _post_process_upstage_markdown,
)

QUALITY_THRESHOLD = float(os.getenv("MARKDOWN_QUALITY_THRESHOLD", "0.8"))
_QUALITY_THRESHOLD_PDF = float(os.getenv("MARKDOWN_QUALITY_THRESHOLD_PDF", "0.50"))
STAGE2_MAX_FIX_ATTEMPTS = int(os.getenv("STAGE2_MAX_FIX_ATTEMPTS", "2"))


def _get_quality_threshold(file_type: str) -> float:
    if file_type == "pdf":
        return _QUALITY_THRESHOLD_PDF
    return QUALITY_THRESHOLD

_SYSTEM_PROMPT = """\
당신은 문서 변환 품질 검수 에이전트입니다.
PDF, DOCX, PPTX에서 Markdown으로 변환된 결과물의 구조적 완전성을 평가하는 것이 유일한 임무입니다.

출력 형식 규칙 (절대 준수):
- 응답은 반드시 순수 JSON 객체여야 합니다.
- 코드 블록(```), 설명 텍스트, 마크다운 형식을 일절 포함하지 않습니다.
- score: 0.0~1.0 범위의 부동소수점
- issues: 확인된 문제만 포함하는 문자열 배열 (문제 없으면 [])
- structure_loss, table_loss, image_loss: 반드시 boolean (true/false)

평가 원칙:
- 추측하지 않습니다. 눈에 보이는 증거가 있는 문제만 보고합니다.
- 문제 심각도에 따라 점수를 차등 부여합니다 (표 소실 > 제목 구조 붕괴 > 리스트 누락 > 서식 오류).
- 이미지/그림이 Markdown에 포함되지 않는 것은 정상입니다. image_loss=true로 표시하되 score 감점은 최소화하세요 (최대 -0.05).
- 텍스트 내용이 정상적으로 보존되고 구조가 올바르면 score는 0.85 이상이어야 합니다.
- issues 항목은 수정 가능한 구체적 문제를 한국어로 기술합니다.\
"""


def _sample_markdown(markdown: str, max_chars: int = 3000) -> str:
    """긴 Markdown에서 앞/중간/끝을 균등 샘플링한다.

    max_chars 이하이면 그대로 반환.
    초과 시 각 max_chars//3 글자씩 앞·중간·끝을 '...(중략)...'로 연결해 반환.
    """
    if len(markdown) <= max_chars:
        return markdown

    chunk = max_chars // 3
    mid_start = (len(markdown) - chunk) // 2

    beginning = markdown[:chunk]
    middle = markdown[mid_start : mid_start + chunk]
    end = markdown[-chunk:]

    return beginning + "\n...(중략)...\n" + middle + "\n...(중략)...\n" + end


# ---------------------------------------------------------------------------
# 품질 평가 프롬프트
# ---------------------------------------------------------------------------

_QUALITY_PROMPT = """\
아래 Markdown 문서의 품질을 평가해주세요.

평가 기준 (중요도 순):
1. [필수, 감점 큼] 제목/섹션 구조가 올바르게 변환되었는가 (# ## ### 계층)
2. [필수, 감점 큼] 표가 존재한다면 Markdown 표 형식으로 정상 변환되었는가
3. [중요] 리스트 항목이 누락 없이 변환되었는가
4. [낮음] 이미지/그림 — Markdown에 이미지가 없는 것은 정상입니다. image_loss=true로 표시만 하고 score 감점은 최대 0.05로 제한하세요.
5. [필수] 텍스트 내용이 원본 의미를 보존하는가

채점 기준:
- 텍스트·구조가 정상이고 표만 없으면: 0.85 이상
- 텍스트·구조가 정상이고 표도 정상이면: 0.90 이상
- 제목 계층이 완전히 붕괴되거나 표가 소실된 경우에만 0.7 미만으로 채점
- "...(중략)..." 표시는 샘플링 처리이므로 내용 손실로 판단하지 마세요

다음 JSON 형식으로만 응답하세요 (다른 텍스트 포함 금지):
{{
  "score": 0.0~1.0,
  "issues": ["발견된 문제점 1", "발견된 문제점 2"],
  "structure_loss": true/false,
  "table_loss": true/false,
  "image_loss": true/false
}}

--- Markdown 문서 ---
{markdown}
"""


# ---------------------------------------------------------------------------
# Stage 2 노드 함수
# ---------------------------------------------------------------------------

async def stage2_validate(state: "DocPipelineState") -> dict:
    """LangGraph 노드: Markdown 품질 검증 (Agent — retry loop 포함).

    품질 미달 시 _apply_targeted_fix()로 수정 후 재평가한다.
    STAGE2_MAX_FIX_ATTEMPTS 이내에 통과하지 못하면 HITL로 전환.
    """
    markdown = state.get("raw_markdown") or ""
    doc_id = state["doc_id"]
    file_type = state.get("file_type", "")
    threshold = _get_quality_threshold(file_type)

    if not markdown:
        logger.warning("Stage 2: raw_markdown이 비어있음", extra={"doc_id": doc_id})
        return {
            "validated_markdown": None,
            "quality_score": 0.0,
            "quality_issues": ["변환된 Markdown이 없음"],
            "hitl_required": True,
            "status": "hitl_pending",
            "current_stage": "stage2_validate",
        }

    max_attempts = int(os.getenv("STAGE2_MAX_FIX_ATTEMPTS", str(STAGE2_MAX_FIX_ATTEMPTS)))
    last_score, last_issues = 0.0, []

    for attempt in range(max_attempts + 1):
        score, issues, hitl, data = await _evaluate_quality(markdown, doc_id, threshold)
        last_score, last_issues = score, issues

        if not hitl:
            logger.info("Stage 2 완료", extra={"doc_id": doc_id, "score": score, "attempt": attempt})
            return {
                "validated_markdown": markdown,
                "quality_score": score,
                "quality_issues": issues,
                "hitl_required": False,
                "current_stage": "stage2_validate",
            }

        if attempt == max_attempts:
            break

        logger.info(
            "Stage 2: 품질 미달 — 수정 재시도",
            extra={"doc_id": doc_id, "score": score, "attempt": attempt, "issues": issues},
        )
        markdown = await _apply_targeted_fix(markdown, issues, data)

    logger.warning(
        "Stage 2: 최대 재시도 초과 — HITL 큐 등록",
        extra={"doc_id": doc_id, "score": last_score, "issues": last_issues},
    )
    return {
        "validated_markdown": None,
        "quality_score": last_score,
        "quality_issues": last_issues,
        "hitl_required": True,
        "status": "hitl_pending",
        "current_stage": "stage2_validate",
    }


_TOOL_SELECT_PROMPT = """\
Markdown 품질 검증 결과를 보고 가장 적합한 수정 도구를 하나만 선택하세요.

발견된 이슈: {issues}
구조 플래그: table_loss={table_loss}, structure_loss={structure_loss}

선택 가능한 도구:
- "post_process"      : 표 소실, HTML 잔재, <table 태그 문제
- "normalize_heading" : 헤딩 계층 붕괴, 제목 구조 문제 (표 문제 아님)
- "format_correct"    : 위 두 경우가 아닌 일반 서식 오류

JSON으로만 응답하세요 (다른 텍스트 없이): {{"tool": "선택한_도구_이름"}}
"""

_KEYWORD_FALLBACK_TOOLS = {
    "table": "post_process",
    "표": "post_process",
    "제목": "normalize_heading",
    "heading": "normalize_heading",
    "structure": "normalize_heading",
}


def _keyword_rule_select(issues: list[str], data: dict, markdown: str) -> str:
    """기존 키워드 룰 도구 선택 — LLM 실패 시 폴백."""
    issues_text = " ".join(issues).lower()
    if data.get("table_loss") or "table" in issues_text or "표" in issues_text or "<table" in markdown:
        return "post_process"
    if data.get("structure_loss") or "제목" in issues_text or "heading" in issues_text or "structure" in issues_text:
        return "normalize_heading"
    return "format_correct"


async def _select_fix_tool_with_llm(issues: list[str], data: dict) -> str:
    """LLM이 issues와 data를 보고 수정 도구를 직접 선택한다.

    반환: "post_process" | "normalize_heading" | "format_correct"

    USE_MOCK_LLM=true 또는 JSON 파싱 실패 시 → 키워드 룰 폴백.
    이 함수 자체가 실패해도 파이프라인은 중단되지 않는다.
    """
    if os.getenv("USE_MOCK_LLM", "false").lower() == "true":
        return _keyword_rule_select(issues, data, "")

    prompt = _TOOL_SELECT_PROMPT.format(
        issues=issues,
        table_loss=data.get("table_loss", False),
        structure_loss=data.get("structure_loss", False),
    )
    try:
        from langchain_core.messages import HumanMessage as _HumanMessage
        response = await call_gemini_with_retry([_HumanMessage(content=prompt)])
        parsed = parse_gemini_json(response.content)
        tool = parsed.get("tool", "")
        if tool in ("post_process", "normalize_heading", "format_correct"):
            logger.debug(f"_select_fix_tool_with_llm: LLM 선택 → {tool}")
            return tool
        logger.warning(f"_select_fix_tool_with_llm: 알 수 없는 도구 '{tool}' → 키워드 룰 폴백")
    except (json.JSONDecodeError, Exception) as e:
        logger.warning(f"_select_fix_tool_with_llm: LLM 실패 ({e}) → 키워드 룰 폴백")

    return _keyword_rule_select(issues, data, "")


async def _apply_targeted_fix(markdown: str, issues: list[str], data: dict) -> str:
    """LLM이 선택한 도구로 Markdown을 수정한다.

    도구 선택: _select_fix_tool_with_llm (LLM 우선, 실패 시 키워드 룰 폴백)
    <table 태그가 본문에 있으면 항상 post_process 우선 적용.
    """
    # HTML 표 태그가 직접 포함된 경우 — LLM 판단과 무관하게 post_process 필수
    if "<table" in markdown:
        logger.debug("_apply_targeted_fix: <table 태그 감지 → post_process 강제")
        return _post_process_upstage_markdown(markdown)

    tool = await _select_fix_tool_with_llm(issues, data)
    logger.debug(f"_apply_targeted_fix: 선택된 도구 → {tool}")

    if tool == "post_process":
        return _post_process_upstage_markdown(markdown)
    if tool == "normalize_heading":
        return _normalize_heading_hierarchy(markdown)
    return await _gemini_format_correct(markdown)


async def _evaluate_quality(
    markdown: str, doc_id: str, threshold: float = QUALITY_THRESHOLD
) -> tuple[float, list[str], bool, dict]:
    """
    Gemini로 Markdown 품질 점수를 평가한다.
    반환: (score, issues, hitl_required, data)
      data: LLM 응답의 구조 플래그 딕셔너리 (table_loss, structure_loss, image_loss)
            파싱 실패 또는 Mock 경로에서는 빈 딕셔너리 {}
    """
    if os.getenv("USE_MOCK_LLM", "false").lower() == "true":
        return 1.0, [], False, {}

    sample = _sample_markdown(markdown)

    try:
        response = await call_gemini_with_retry([
            SystemMessage(content=_SYSTEM_PROMPT),
            HumanMessage(content=_QUALITY_PROMPT.format(markdown=sample)),
        ])
        data = parse_gemini_json(response.content)
    except json.JSONDecodeError as e:
        logger.error(
            "Stage 2: LLM 응답 JSON 파싱 실패",
            extra={"doc_id": doc_id, "error": str(e)},
        )
        # 파싱 실패 → 안전하게 HITL 처리
        return 0.0, ["LLM 응답 파싱 실패 — 수동 검토 필요"], True, {}
    except Exception as e:
        logger.error(
            "Stage 2: Gemini API 호출 실패",
            extra={"doc_id": doc_id, "error": str(e)},
        )
        return 0.0, [f"품질 평가 실패: {e}"], True, {}

    score: float = float(data.get("score", 0.0))
    issues: list[str] = data.get("issues", [])

    # 구조 손실은 issues에 기록만 함 — HITL 결정은 score 기준만 사용
    structure_loss = data.get("structure_loss", False) or data.get("table_loss", False)
    hitl_required = score < threshold

    if structure_loss:
        issues.insert(0, "표/이미지 구조 손실 감지")

    return score, issues, hitl_required, data
