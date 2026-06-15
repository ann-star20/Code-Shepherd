"""
Stage 5b MetadataValidateAgent HITL 트리거 조건 단위 테스트.

KMS에서 HITL은 "잘못된 지식이 저장되지 않도록 막는 안전망"이다.
아래 케이스들은 반드시 HITL로 분기되어야 한다:
  - title = "제목 없음" (Stage 5 fallback 감지)
  - category가 VALID_CATEGORIES에 없음
  - 새 카테고리 제안 (category_is_new=True)
  - metadata_score < METADATA_QUALITY_THRESHOLD (0.7)

반대로 정상 문서는 HITL로 가면 안 된다 (False HITL 방지).
"""

from __future__ import annotations

import json
import pytest
from unittest.mock import AsyncMock, patch, MagicMock


# ---------------------------------------------------------------------------
# stage5b 모듈 import
# ---------------------------------------------------------------------------

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[2] / "app"))

from app.pipeline.stage5b_metadata_validate_agent import (
    stage5b_metadata_validate,
    METADATA_QUALITY_THRESHOLD,
    FALLBACK_TITLE,
)


# ---------------------------------------------------------------------------
# 기본 정상 state 팩토리
# ---------------------------------------------------------------------------

def _make_state(
    title: str = "정상 문서 제목",
    category: str = "AI_ML",
    tags: list | None = None,
    category_is_new: bool = False,
    markdown: str = "# 정상 문서\n\n본문 내용입니다.",
    metadata_score_mock: float = 0.9,
) -> dict:
    return {
        "doc_id": "test-doc-001",
        "metadata": {
            "title": title,
            "category": category,
            "tags": tags or ["AI", "ML"],
        },
        "validated_markdown": markdown,
        "neo4j_entities": [{"name": "테스트", "type": "Concept"}],
        "category_is_new": category_is_new,
        "category_reasoning": "",
        "category_alternatives": [],
        "_mock_score": metadata_score_mock,
    }


def _llm_response(score: float, issues: list | None = None) -> str:
    return json.dumps({
        "score": score,
        "category_correct": score >= METADATA_QUALITY_THRESHOLD,
        "title_representative": score >= METADATA_QUALITY_THRESHOLD,
        "issues": issues or [],
    })


# ---------------------------------------------------------------------------
# 반드시 HITL이 발동되어야 하는 케이스
# ---------------------------------------------------------------------------

class TestHitlMustTrigger:

    @pytest.mark.asyncio
    async def test_fallback_title_triggers_hitl(self):
        """title = '제목 없음'이면 규칙 기반 즉시 HITL."""
        state = _make_state(title=FALLBACK_TITLE)

        result = await stage5b_metadata_validate(state)

        assert result["hitl_required"] is True
        assert result["status"] == "hitl_pending"
        assert any("제목" in issue for issue in result["metadata_issues"])

    @pytest.mark.asyncio
    async def test_empty_title_triggers_hitl(self):
        """title = ''이면 규칙 기반 즉시 HITL."""
        state = _make_state(title="")

        result = await stage5b_metadata_validate(state)

        assert result["hitl_required"] is True
        assert result["status"] == "hitl_pending"

    @pytest.mark.asyncio
    async def test_invalid_category_triggers_hitl(self):
        """유효하지 않은 카테고리는 규칙 기반 즉시 HITL."""
        state = _make_state(category="존재하지않는카테고리_XYZ")

        result = await stage5b_metadata_validate(state)

        assert result["hitl_required"] is True
        assert result["status"] == "hitl_pending"
        assert any("카테고리" in issue for issue in result["metadata_issues"])

    @pytest.mark.asyncio
    async def test_new_category_triggers_kb_evolution_hitl(self):
        """category_is_new=True이면 KB Evolution HITL (카테고리 유효 여부 무관)."""
        state = _make_state(
            category="신규카테고리_블록체인",
            category_is_new=True,
        )

        result = await stage5b_metadata_validate(state)

        assert result["hitl_required"] is True
        assert result["status"] == "hitl_pending"
        assert any("새 카테고리" in issue for issue in result["metadata_issues"])

    @pytest.mark.asyncio
    async def test_low_llm_score_triggers_hitl(self):
        """metadata_score < 0.7이면 LLM 검증 후 HITL."""
        state = _make_state(category="AI_ML")
        low_score_response = MagicMock()
        low_score_response.content = _llm_response(score=0.55)

        with patch(
            "app.pipeline.stage5b_metadata_validate_agent.call_gemini_with_retry",
            new_callable=AsyncMock,
            return_value=low_score_response,
        ):
            result = await stage5b_metadata_validate(state)

        assert result["hitl_required"] is True
        assert result["status"] == "hitl_pending"
        assert result["metadata_score"] == pytest.approx(0.55)

    @pytest.mark.asyncio
    async def test_llm_api_failure_triggers_hitl(self):
        """Gemini API 호출 실패 시 HITL (보수적 처리)."""
        state = _make_state(category="AI_ML")

        with patch(
            "app.pipeline.stage5b_metadata_validate_agent.call_gemini_with_retry",
            new_callable=AsyncMock,
            side_effect=Exception("Gemini API 장애"),
        ):
            result = await stage5b_metadata_validate(state)

        assert result["hitl_required"] is True
        assert result["status"] == "hitl_pending"

    @pytest.mark.asyncio
    async def test_llm_json_parse_failure_triggers_hitl(self):
        """Gemini 응답 JSON 파싱 실패 시 HITL."""
        state = _make_state(category="AI_ML")
        bad_response = MagicMock()
        bad_response.content = "이것은 JSON이 아닙니다"

        with patch(
            "app.pipeline.stage5b_metadata_validate_agent.call_gemini_with_retry",
            new_callable=AsyncMock,
            return_value=bad_response,
        ):
            result = await stage5b_metadata_validate(state)

        assert result["hitl_required"] is True
        assert result["status"] == "hitl_pending"


# ---------------------------------------------------------------------------
# HITL이 발동되면 안 되는 케이스 (False HITL 방지)
# ---------------------------------------------------------------------------

class TestHitlMustNotTrigger:

    @pytest.mark.asyncio
    async def test_valid_doc_passes_without_hitl(self):
        """정상 문서 (유효 제목·카테고리·높은 점수)는 HITL 없이 통과."""
        state = _make_state(
            title="신입 개발자 온보딩 가이드",
            category="온보딩",
        )
        good_response = MagicMock()
        good_response.content = _llm_response(score=0.92)

        with patch(
            "app.pipeline.stage5b_metadata_validate_agent.call_gemini_with_retry",
            new_callable=AsyncMock,
            return_value=good_response,
        ):
            result = await stage5b_metadata_validate(state)

        assert result["hitl_required"] is False
        assert result.get("status") != "hitl_pending"
        assert result["metadata_score"] == pytest.approx(0.92)

    @pytest.mark.asyncio
    async def test_borderline_score_above_threshold_passes(self):
        """threshold 바로 위 점수 (0.71)는 HITL 없이 통과."""
        state = _make_state(category="AI_ML")
        border_response = MagicMock()
        border_response.content = _llm_response(score=0.71)

        with patch(
            "app.pipeline.stage5b_metadata_validate_agent.call_gemini_with_retry",
            new_callable=AsyncMock,
            return_value=border_response,
        ):
            result = await stage5b_metadata_validate(state)

        assert result["hitl_required"] is False

    @pytest.mark.asyncio
    async def test_threshold_boundary_exactly_at_threshold_passes(self):
        """score == METADATA_QUALITY_THRESHOLD (0.7)는 HITL 미발동."""
        state = _make_state(category="AI_ML")
        exact_response = MagicMock()
        exact_response.content = _llm_response(score=METADATA_QUALITY_THRESHOLD)

        with patch(
            "app.pipeline.stage5b_metadata_validate_agent.call_gemini_with_retry",
            new_callable=AsyncMock,
            return_value=exact_response,
        ):
            result = await stage5b_metadata_validate(state)

        # score == threshold는 미달이 아님 (hitl_required = score < threshold)
        assert result["hitl_required"] is False


# ---------------------------------------------------------------------------
# metadata_score 반환값 검증
# ---------------------------------------------------------------------------

class TestMetadataScoreReturned:

    @pytest.mark.asyncio
    async def test_metadata_score_is_in_state_on_pass(self):
        """통과 시 metadata_score가 state에 포함되어야 한다."""
        state = _make_state(category="AI_ML")
        resp = MagicMock()
        resp.content = _llm_response(score=0.85)

        with patch(
            "app.pipeline.stage5b_metadata_validate_agent.call_gemini_with_retry",
            new_callable=AsyncMock,
            return_value=resp,
        ):
            result = await stage5b_metadata_validate(state)

        assert "metadata_score" in result
        assert result["metadata_score"] == pytest.approx(0.85)

    @pytest.mark.asyncio
    async def test_metadata_score_zero_on_rule_hitl(self):
        """규칙 기반 HITL 시 metadata_score = 0.0."""
        state = _make_state(title=FALLBACK_TITLE)
        result = await stage5b_metadata_validate(state)

        assert result["metadata_score"] == 0.0

    @pytest.mark.asyncio
    async def test_metadata_score_from_llm_on_llm_hitl(self):
        """LLM 점수 미달 HITL 시 실제 LLM score가 metadata_score에 반영된다."""
        state = _make_state(category="AI_ML")
        resp = MagicMock()
        resp.content = _llm_response(score=0.45)

        with patch(
            "app.pipeline.stage5b_metadata_validate_agent.call_gemini_with_retry",
            new_callable=AsyncMock,
            return_value=resp,
        ):
            result = await stage5b_metadata_validate(state)

        assert result["metadata_score"] == pytest.approx(0.45)
