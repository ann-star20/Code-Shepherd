"""
Stage 5b: 메타데이터 검증 Agent (trc_0005b)

Stage 5에서 Gemini가 추출한 메타데이터가 문서 내용과 실제로 일치하는지
다시 한번 Gemini로 검증한다.

검증 항목:
    1. title이 "제목 없음" 이거나 비어있는지 (fallback 감지)
    2. category가 유효한 값인지
    3. Gemini가 메타데이터와 문서 내용 일치 여부를 0.0~1.0으로 점수화
    4. 점수 < METADATA_QUALITY_THRESHOLD 또는 fallback 감지 시 HITL 큐 등록

출력:
    state["metadata_valid"]         True/False
    state["metadata_score"]         0.0~1.0
    state["metadata_issues"]        발견된 문제 목록
    state["hitl_required"]          True이면 파이프라인 일시 중단
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

from app.pipeline._gemini import call_gemini_with_retry

METADATA_QUALITY_THRESHOLD = float(os.getenv("METADATA_QUALITY_THRESHOLD", "0.7"))

import app.pipeline._category_definitions as _cat_defs
from app.pipeline._category_definitions import build_category_prompt_snippet

FALLBACK_TITLE = "제목 없음"

_SYSTEM_PROMPT = f"""\
당신은 사내 문서 메타데이터 검증 에이전트입니다.
Stage 5에서 추출된 메타데이터가 실제 문서 내용을 정확히 대표하는지 독립적으로 검증하는 것이 유일한 임무입니다.

출력 형식 규칙 (절대 준수):
- 응답은 반드시 순수 JSON 객체여야 합니다.
- 코드 블록(```), 설명 텍스트, 마크다운 형식을 일절 포함하지 않습니다.
- score: 0.0~1.0 범위의 부동소수점 (전반적인 메타데이터 정확도)
- category_correct, title_representative: 반드시 boolean (true/false)
- issues: 확인된 불일치만 포함하는 문자열 배열 (문제 없으면 [])

{build_category_prompt_snippet()}

검증 원칙:
- 메타데이터만 보고 판단하지 않습니다. 반드시 제공된 문서 내용과 비교합니다.
- 카테고리와 제목의 적합성을 독립적으로 판단합니다.
- issues 항목은 수정 가능한 구체적 불일치를 한국어로 기술합니다.
- 애매한 경우 엄격하게 판단합니다 (score 낮추고 issues에 기록).\
"""

_VALIDATE_PROMPT = """\
아래 메타데이터가 문서 내용을 정확하게 반영하는지 검증해주세요.

다음 JSON 형식으로만 응답하세요 (다른 텍스트 포함 금지):
{{
  "score": 0.0~1.0,
  "category_correct": true/false,
  "title_representative": true/false,
  "issues": ["발견된 문제점 1", "발견된 문제점 2"]
}}

평가 기준:
- score: 전반적인 메타데이터 정확도 (0.0=완전 틀림, 1.0=완벽)
- category_correct: 카테고리가 문서 내용에 적합한가
- title_representative: 제목이 문서 내용을 대표하는가

--- 추출된 메타데이터 ---
제목: {title}
카테고리: {category}
태그: {tags}
엔티티 수: {entity_count}개

--- 문서 내용 (앞 2000자) ---
{markdown}
"""


async def stage5b_metadata_validate(state: "DocPipelineState") -> dict:
    """LangGraph 노드: 메타데이터 품질 검증."""

    doc_id   = state["doc_id"]
    metadata = state.get("metadata") or {}
    markdown = state.get("validated_markdown") or ""
    entities = state.get("neo4j_entities") or []

    title    = metadata.get("title", "")
    category = metadata.get("category", "기타")
    tags     = metadata.get("tags", [])

    # Stage5에서 전달된 KB Evolution 필드
    category_is_new   = state.get("category_is_new", False)
    category_reasoning = state.get("category_reasoning", "")
    category_alternatives = state.get("category_alternatives", [])

    # ── 1. KB Evolution 분기 — 새 카테고리 제안 시 즉시 HITL ─────────
    if category_is_new:
        logger.warning(
            "Stage 5b: 새 카테고리 감지 — KB Evolution HITL 등록",
            extra={"doc_id": doc_id, "category": category},
        )
        issues = [
            f"새 카테고리 제안: '{category}'",
            f"AI 추론 근거: {category_reasoning}" if category_reasoning else "근거 없음",
        ]
        return {
            "metadata_valid":       False,
            "metadata_score":       0.0,
            "metadata_issues":      issues,
            "hitl_required":        True,
            "status":               "hitl_pending",
            "current_stage":        "stage5b_metadata_validate",
            "category_reasoning":   category_reasoning,
            "category_alternatives": category_alternatives,
        }

    # ── 2. 규칙 기반 사전 검사 (LLM 없이 즉시 판단) ──────────────────
    rule_issues: list[str] = []

    if not title or title == FALLBACK_TITLE:
        rule_issues.append(f"제목이 없음 (fallback 감지: '{title}')")

    if category not in _cat_defs.VALID_CATEGORIES:
        rule_issues.append(f"유효하지 않은 카테고리: '{category}'")

    if rule_issues:
        logger.warning(
            "Stage 5b: 규칙 검사 실패 — HITL 등록",
            extra={"doc_id": doc_id, "issues": rule_issues},
        )
        return {
            "metadata_valid":  False,
            "metadata_score":  0.0,
            "metadata_issues": rule_issues,
            "hitl_required":   True,
            "status":          "hitl_pending",
            "current_stage":   "stage5b_metadata_validate",
        }

    # ── 2. LLM 기반 검증 ────────────────────────────────────────────
    score, issues = await _validate_with_llm(
        title=title,
        category=category,
        tags=tags,
        entity_count=len(entities),
        markdown=markdown,
        doc_id=doc_id,
    )

    hitl_required = score < METADATA_QUALITY_THRESHOLD

    if hitl_required:
        logger.warning(
            "Stage 5b: 메타데이터 품질 미달 — HITL 등록",
            extra={"doc_id": doc_id, "score": score, "issues": issues},
        )
        return {
            "metadata_valid":  False,
            "metadata_score":  score,
            "metadata_issues": issues,
            "hitl_required":   True,
            "status":          "hitl_pending",
            "current_stage":   "stage5b_metadata_validate",
        }

    logger.info(
        "Stage 5b 완료",
        extra={"doc_id": doc_id, "score": score},
    )
    return {
        "metadata_valid":  True,
        "metadata_score":  score,
        "metadata_issues": issues if issues else None,
        "hitl_required":   False,
        "current_stage":   "stage5b_metadata_validate",
    }


async def _validate_with_llm(
    title: str,
    category: str,
    tags: list,
    entity_count: int,
    markdown: str,
    doc_id: str,
) -> tuple[float, list[str]]:
    """Gemini로 메타데이터 품질 점수를 평가한다."""

    if os.getenv("USE_MOCK_LLM", "false").lower() == "true":
        return 1.0, []

    sample = markdown[:2000] if len(markdown) > 2000 else markdown

    try:
        response = await call_gemini_with_retry([
            SystemMessage(content=_SYSTEM_PROMPT),
            HumanMessage(content=_VALIDATE_PROMPT.format(
                title=title,
                category=category,
                tags=", ".join(tags) if tags else "없음",
                entity_count=entity_count,
                markdown=sample,
            ))
        ])
        raw = response.content.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
            raw = raw.strip()
        data = json.loads(raw)

    except json.JSONDecodeError as e:
        logger.error(
            "Stage 5b: JSON 파싱 실패",
            extra={"doc_id": doc_id, "error": str(e)},
        )
        return 0.0, ["메타데이터 검증 응답 파싱 실패 — 수동 검토 필요"]

    except Exception as e:
        logger.error(
            "Stage 5b: Gemini API 호출 실패",
            extra={"doc_id": doc_id, "error": str(e)},
        )
        return 0.0, [f"메타데이터 검증 실패: {e}"]

    score: float = float(data.get("score", 0.0))
    issues: list[str] = data.get("issues", [])

    if not data.get("category_correct", True):
        issues.insert(0, f"카테고리 불일치 — '{category}'가 문서 내용과 맞지 않음")

    if not data.get("title_representative", True):
        issues.append(f"제목 '{title}'이 문서 내용을 대표하지 않음")

    return score, issues
