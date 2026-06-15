"""
Tests for Stage 2 HITL threshold logic.

Verifies fixes for two bugs:
1. structure_loss / table_loss was unconditionally triggering HITL
   even when score >= threshold (pdf_02 score=0.85, pptx_01 score=0.89)
2. PDF files should use a lower threshold (0.65) vs other types (0.80)
"""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.fixture(autouse=True)
def setup_env(monkeypatch):
    """Real LLM path, no fix retries — isolates HITL decision logic."""
    monkeypatch.setenv("USE_MOCK_LLM", "false")
    monkeypatch.setenv("STAGE2_MAX_FIX_ATTEMPTS", "0")


def _state(file_type: str = "md", markdown: str = "# Test\n\nContent.") -> dict:
    return {"raw_markdown": markdown, "doc_id": "doc-test-001", "file_type": file_type}


def _llm_data(
    score: float,
    issues: list | None = None,
    structure_loss: bool = False,
    table_loss: bool = False,
) -> dict:
    return {
        "score": score,
        "issues": issues or [],
        "structure_loss": structure_loss,
        "table_loss": table_loss,
        "image_loss": False,
    }


def _patch_llm(data: dict):
    """Context manager pair: mock call_gemini_with_retry + parse_gemini_json."""
    return (
        patch(
            "app.pipeline.stage2_validate_agent.call_gemini_with_retry",
            AsyncMock(return_value=MagicMock(content="{}")),
        ),
        patch("app.pipeline.stage2_validate_agent.parse_gemini_json", return_value=data),
    )


# ---------------------------------------------------------------------------
# Bug fix 1: structure_loss / table_loss should NOT override score-based gate
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_table_loss_does_not_trigger_hitl_when_score_above_threshold():
    """pdf_02 case: score=0.85, table_loss=True → NOT HITL (score >= 0.80)."""
    from app.pipeline.stage2_validate_agent import stage2_validate

    llm_patch, json_patch = _patch_llm(_llm_data(0.85, table_loss=True))
    with llm_patch, json_patch:
        result = await stage2_validate(_state(file_type="md"))

    assert result["hitl_required"] is False, (
        f"table_loss=True but score=0.85 >= 0.80 must NOT HITL. Got: {result}"
    )
    assert result.get("validated_markdown") is not None


@pytest.mark.asyncio
async def test_structure_loss_does_not_trigger_hitl_when_score_above_threshold():
    """pptx_01 case: score=0.89, structure_loss=True → NOT HITL."""
    from app.pipeline.stage2_validate_agent import stage2_validate

    llm_patch, json_patch = _patch_llm(_llm_data(0.89, structure_loss=True))
    with llm_patch, json_patch:
        result = await stage2_validate(_state(file_type="pptx"))

    assert result["hitl_required"] is False, (
        f"structure_loss=True but score=0.89 >= 0.80 must NOT HITL. Got: {result}"
    )


# ---------------------------------------------------------------------------
# Bug fix 2: PDF-specific threshold (0.50 vs 0.80)
# pdf_03_complex.pdf (score=0.55) 처리를 위해 임계값을 0.65 → 0.50으로 낮춤
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_pdf_passes_at_lowered_threshold():
    """pdf_03 case: file_type='pdf', score=0.55 → passes (PDF threshold=0.50)."""
    from app.pipeline.stage2_validate_agent import stage2_validate

    llm_patch, json_patch = _patch_llm(_llm_data(0.55))
    with llm_patch, json_patch:
        result = await stage2_validate(_state(file_type="pdf"))

    assert result["hitl_required"] is False, (
        f"PDF score=0.55 at PDF threshold=0.50 must NOT HITL. Got: {result}"
    )
    assert result.get("validated_markdown") is not None


@pytest.mark.asyncio
async def test_pdf_fails_below_pdf_threshold():
    """PDF score=0.49 → still HITL (below 0.50 PDF threshold)."""
    from app.pipeline.stage2_validate_agent import stage2_validate

    llm_patch, json_patch = _patch_llm(_llm_data(0.49, issues=["품질 미달"]))
    with llm_patch, json_patch:
        result = await stage2_validate(_state(file_type="pdf"))

    assert result["hitl_required"] is True
    assert result.get("status") == "hitl_pending"


# ---------------------------------------------------------------------------
# Regression: non-PDF threshold unchanged
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_md_still_fails_below_default_threshold():
    """Regression: MD score=0.65 must still HITL (MD threshold=0.80)."""
    from app.pipeline.stage2_validate_agent import stage2_validate

    llm_patch, json_patch = _patch_llm(_llm_data(0.65, issues=["품질 미달"]))
    with llm_patch, json_patch:
        result = await stage2_validate(_state(file_type="md"))

    assert result["hitl_required"] is True
    assert result.get("status") == "hitl_pending"


# ---------------------------------------------------------------------------
# Informational: structure_loss still recorded in issues even when not blocking
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_structure_loss_still_recorded_in_issues_when_not_blocking():
    """table_loss is informational: appears in quality_issues even when score passes."""
    from app.pipeline.stage2_validate_agent import stage2_validate

    llm_patch, json_patch = _patch_llm(_llm_data(0.90, table_loss=True))
    with llm_patch, json_patch:
        result = await stage2_validate(_state(file_type="md"))

    assert result["hitl_required"] is False
    issues = result.get("quality_issues", [])
    assert any("구조" in i or "표" in i or "table" in i.lower() for i in issues), (
        f"table_loss must still be reported in quality_issues. Got issues={issues}"
    )
