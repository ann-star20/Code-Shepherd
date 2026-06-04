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
    from module_0_kms.pipeline.models import DocPipelineState

logger = logging.getLogger(__name__)

from langchain_core.messages import HumanMessage, SystemMessage

from module_0_kms.pipeline._gemini import call_gemini_with_retry
from module_0_kms.pipeline.stage1_document_parser_agent import (
    _gemini_format_correct,
    _normalize_heading_hierarchy,
    _post_process_upstage_markdown,
)

QUALITY_THRESHOLD = float(os.getenv("MARKDOWN_QUALITY_THRESHOLD", "0.8"))
STAGE2_MAX_FIX_ATTEMPTS = int(os.getenv("STAGE2_MAX_FIX_ATTEMPTS", "2"))

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
        score, issues, hitl = await _evaluate_quality(markdown, doc_id)
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
        markdown = await _apply_targeted_fix(markdown, issues, {})

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


async def _apply_targeted_fix(markdown: str, issues: list[str], data: dict) -> str:
    """issues/data에 따라 rule-based로 수정 함수를 선택해 실행.

    우선순위:
    1. table_loss=True 또는 issues에 'table'/'표' 또는 본문에 <table 태그 → HTML 후처리
    2. structure_loss=True 또는 issues에 '제목'/'heading' → 헤딩 정규화
    3. 기타 → Gemini 서식 교정 (LLM 폴백)
    """
    issues_text = " ".join(issues).lower()

    if (
        data.get("table_loss")
        or "table" in issues_text
        or "표" in issues_text
        or "<table" in markdown
    ):
        logger.debug("_apply_targeted_fix: table issue → _post_process_upstage_markdown")
        return _post_process_upstage_markdown(markdown)

    if (
        data.get("structure_loss")
        or "제목" in issues_text
        or "heading" in issues_text
        or "structure" in issues_text
    ):
        logger.debug("_apply_targeted_fix: heading/structure issue → _normalize_heading_hierarchy")
        return _normalize_heading_hierarchy(markdown)

    logger.debug("_apply_targeted_fix: general issue → _gemini_format_correct")
    return await _gemini_format_correct(markdown)


async def _evaluate_quality(markdown: str, doc_id: str) -> tuple[float, list[str], bool]:
    """
    Claude로 Markdown 품질 점수를 평가한다.
    반환: (score, issues, hitl_required)
    """
    if os.getenv("USE_MOCK_LLM", "false").lower() == "true":
        return 1.0, [], False

    sample = _sample_markdown(markdown)

    try:
        response = await call_gemini_with_retry([
            SystemMessage(content=_SYSTEM_PROMPT),
            HumanMessage(content=_QUALITY_PROMPT.format(markdown=sample)),
        ])
        raw = response.content.strip()
        # Gemini가 ```json ... ``` 블록으로 감싸는 경우 제거
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
            raw = raw.strip()
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        logger.error(
            "Stage 2: LLM 응답 JSON 파싱 실패",
            extra={"doc_id": doc_id, "error": str(e)},
        )
        # 파싱 실패 → 안전하게 HITL 처리
        return 0.0, ["LLM 응답 파싱 실패 — 수동 검토 필요"], True
    except Exception as e:
        logger.error(
            "Stage 2: Gemini API 호출 실패",
            extra={"doc_id": doc_id, "error": str(e)},
        )
        return 0.0, [f"품질 평가 실패: {e}"], True

    score: float = float(data.get("score", 0.0))
    issues: list[str] = data.get("issues", [])

    # 구조 손실이 감지되거나 점수 미달이면 HITL
    structure_loss = data.get("structure_loss", False) or data.get("table_loss", False)
    hitl_required = score < QUALITY_THRESHOLD or structure_loss

    if structure_loss:
        issues.insert(0, "표/이미지 구조 손실 감지")

    return score, issues, hitl_required
