"""TDD (RED): Stage 5b — category_alternatives >= 2 시 HITL 분기 (Phase 2).

현재 문제:
    키워드 리스트에 없는 신규 도메인 문서가 Stage 5b를 그냥 통과함.
    Gemini는 이미 category_alternatives로 불확실성 신호를 보내고 있지만 무시됨.

목표:
    len(category_alternatives) >= 2 → hitl_required=True
    len(category_alternatives) <= 1 → 이 조건으로는 HITL 미발동

테스트 대상:
    app.pipeline.stage5b_metadata_validate_agent.stage5b_metadata_validate
"""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, patch


def _make_state(
    category_alternatives: list[str],
    category: str = "아키텍처",
    category_is_new: bool = False,
    title: str = "일반 기술 문서",
    markdown: str = "## 내용\n일반적인 기술 문서입니다.",
) -> dict:
    return {
        "doc_id": "test-doc-id",
        "metadata": {
            "title": title,
            "category": category,
            "tags": [],
        },
        "validated_markdown": markdown,
        "neo4j_entities": [],
        "category_is_new": category_is_new,
        "category_reasoning": "테스트 추론 근거",
        "category_alternatives": category_alternatives,
    }


# ---------------------------------------------------------------------------
# Journey 1: Gemini 대안 2개 이상 → HITL 분기
# ---------------------------------------------------------------------------

class TestCategoryAlternativesHitl:

    @pytest.mark.asyncio
    async def test_two_alternatives_triggers_hitl(self):
        """category_alternatives 2개 → hitl_required=True."""
        state = _make_state(category_alternatives=["보안", "아키텍처"])

        with patch(
            "app.pipeline.stage5b_metadata_validate_agent._validate_with_llm",
            new_callable=AsyncMock,
            return_value=(0.9, []),
        ):
            from app.pipeline.stage5b_metadata_validate_agent import stage5b_metadata_validate
            result = await stage5b_metadata_validate(state)

        assert result["hitl_required"] is True, (
            "category_alternatives 2개일 때 HITL이 발동되지 않았습니다."
        )
        assert result["status"] == "hitl_pending"

    @pytest.mark.asyncio
    async def test_three_alternatives_triggers_hitl(self):
        """category_alternatives 3개 → hitl_required=True."""
        state = _make_state(category_alternatives=["보안", "아키텍처", "AI_ML"])

        with patch(
            "app.pipeline.stage5b_metadata_validate_agent._validate_with_llm",
            new_callable=AsyncMock,
            return_value=(0.9, []),
        ):
            from app.pipeline.stage5b_metadata_validate_agent import stage5b_metadata_validate
            result = await stage5b_metadata_validate(state)

        assert result["hitl_required"] is True

    @pytest.mark.asyncio
    async def test_hitl_output_includes_alternatives(self):
        """HITL 분기 시 category_alternatives가 출력에 포함되어야 한다."""
        alts = ["보안", "아키텍처"]
        state = _make_state(category_alternatives=alts)

        with patch(
            "app.pipeline.stage5b_metadata_validate_agent._validate_with_llm",
            new_callable=AsyncMock,
            return_value=(0.9, []),
        ):
            from app.pipeline.stage5b_metadata_validate_agent import stage5b_metadata_validate
            result = await stage5b_metadata_validate(state)

        assert result.get("category_alternatives") == alts, (
            "HITL 출력에 category_alternatives가 없으면 팀장이 어떤 카테고리가 후보였는지 알 수 없습니다."
        )

    @pytest.mark.asyncio
    async def test_hitl_issues_mention_alternatives_count(self):
        """HITL metadata_issues에 대안 수가 언급되어야 한다."""
        state = _make_state(category_alternatives=["보안", "아키텍처"])

        with patch(
            "app.pipeline.stage5b_metadata_validate_agent._validate_with_llm",
            new_callable=AsyncMock,
            return_value=(0.9, []),
        ):
            from app.pipeline.stage5b_metadata_validate_agent import stage5b_metadata_validate
            result = await stage5b_metadata_validate(state)

        issues_text = " ".join(result.get("metadata_issues", []))
        assert "2" in issues_text or "대안" in issues_text or "alternatives" in issues_text.lower(), (
            "HITL 이슈 메시지에 대안 카테고리 수 또는 '대안' 언급이 없습니다."
        )


# ---------------------------------------------------------------------------
# Journey 2: 대안 1개 이하 → alternatives 조건으로 HITL 미발동
# ---------------------------------------------------------------------------

class TestCategoryAlternativesNoHitl:

    @pytest.mark.asyncio
    async def test_one_alternative_does_not_trigger_alternatives_hitl(self):
        """category_alternatives 1개 → alternatives 조건으로 HITL 미발동."""
        state = _make_state(category_alternatives=["보안"])

        with patch(
            "app.pipeline.stage5b_metadata_validate_agent._validate_with_llm",
            new_callable=AsyncMock,
            return_value=(0.9, []),  # score 충분히 높음
        ):
            from app.pipeline.stage5b_metadata_validate_agent import stage5b_metadata_validate
            result = await stage5b_metadata_validate(state)

        assert result["hitl_required"] is False, (
            "alternatives 1개는 불확실성 신호가 아닙니다. HITL이 잘못 발동됐습니다."
        )

    @pytest.mark.asyncio
    async def test_zero_alternatives_does_not_trigger_alternatives_hitl(self):
        """category_alternatives 0개 → alternatives 조건으로 HITL 미발동."""
        state = _make_state(category_alternatives=[])

        with patch(
            "app.pipeline.stage5b_metadata_validate_agent._validate_with_llm",
            new_callable=AsyncMock,
            return_value=(0.9, []),
        ):
            from app.pipeline.stage5b_metadata_validate_agent import stage5b_metadata_validate
            result = await stage5b_metadata_validate(state)

        assert result["hitl_required"] is False

    @pytest.mark.asyncio
    async def test_alternatives_check_is_independent_of_keyword_check(self):
        """keyword 리스트에 없는 신규 도메인도 alternatives >= 2면 HITL 분기."""
        state = _make_state(
            category_alternatives=["보안", "아키텍처"],
            # 키워드 리스트에 없는 도메인
            markdown="## 뉴로모픽 컴퓨팅\n신경 회로 구조를 모방한 차세대 반도체 설계.",
            title="뉴로모픽 컴퓨팅 기술 개요",
        )

        with patch(
            "app.pipeline.stage5b_metadata_validate_agent._validate_with_llm",
            new_callable=AsyncMock,
            return_value=(0.85, []),
        ):
            from app.pipeline.stage5b_metadata_validate_agent import stage5b_metadata_validate
            result = await stage5b_metadata_validate(state)

        assert result["hitl_required"] is True, (
            "키워드 리스트에 없는 신규 도메인이 alternatives >= 2임에도 HITL을 통과했습니다."
        )
