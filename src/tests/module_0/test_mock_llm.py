from __future__ import annotations

import pytest

from module_0_kms.pipeline.stage2_validate_agent import _evaluate_quality
from module_0_kms.pipeline.stage5_metadata_agent import _extract_metadata


@pytest.mark.asyncio
async def test_stage2_uses_mock_llm_without_api_call(monkeypatch):
    monkeypatch.setenv("USE_MOCK_LLM", "true")

    score, issues, hitl_required = await _evaluate_quality("# Title\n\nBody", "doc-1")

    assert score == 1.0
    assert issues == []
    assert hitl_required is False


@pytest.mark.asyncio
async def test_stage5_uses_mock_llm_without_api_call(monkeypatch):
    monkeypatch.setenv("USE_MOCK_LLM", "true")

    metadata, entities = await _extract_metadata("# Architecture", "doc-1")

    from module_0_kms.pipeline._category_definitions import VALID_CATEGORIES
    assert metadata["title"] == "Architecture"
    assert metadata["category"] in VALID_CATEGORIES  # Mock은 기존 카테고리 반환
    assert entities == []
