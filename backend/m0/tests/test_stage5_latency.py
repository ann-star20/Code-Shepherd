"""
TDD: Stage 5 LLM latency measurement (T5)

목표:
  stage5_metadata()가 stage5_latency_ms(int, ms 단위)를 반환 dict에 포함해야 한다.
  build_output_entry()가 stage5_latency_ms 파라미터를 받아 output에 포함해야 한다.

동기:
  현재 avg_processing_time_ms = 33,700ms — 어느 stage가 병목인지 모름.
  Stage 5 (Gemini LLM 호출)가 주요 병목으로 의심되므로 per-stage 타이밍을 측정한다.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _make_state(markdown: str = "# 테스트\n내용") -> dict:
    return {
        "doc_id": "test-doc-id",
        "validated_markdown": markdown,
        "chunks": [],
    }


_FAKE_GEMINI_RESPONSE = (
    '{"title":"테스트 문서","category":"AI_ML","category_reasoning":"테스트용",'
    '"category_alternatives":[],"team":null,"author":null,'
    '"tags":["테스트"],"entities":[]}'
)


class TestStage5LatencyInState:
    """stage5_metadata() 반환 dict에 stage5_latency_ms 포함 여부."""

    @pytest.mark.asyncio
    async def test_returns_stage5_latency_ms_key(self):
        """정상 LLM 응답 시 stage5_latency_ms 키가 반환돼야 한다."""
        from app.pipeline.stage5_metadata_agent import stage5_metadata

        with patch(
            "app.pipeline.stage5_metadata_agent.call_gemini_quality",
            new_callable=AsyncMock,
        ) as mock_gemini:
            mock_gemini.return_value = MagicMock(content=_FAKE_GEMINI_RESPONSE)
            result = await stage5_metadata(_make_state())

        assert "stage5_latency_ms" in result, (
            f"stage5_latency_ms 키 없음. 실제 반환 키: {sorted(result.keys())}"
        )

    @pytest.mark.asyncio
    async def test_stage5_latency_ms_is_non_negative_int(self):
        """stage5_latency_ms는 0 이상의 정수여야 한다."""
        from app.pipeline.stage5_metadata_agent import stage5_metadata

        with patch(
            "app.pipeline.stage5_metadata_agent.call_gemini_quality",
            new_callable=AsyncMock,
        ) as mock_gemini:
            mock_gemini.return_value = MagicMock(content=_FAKE_GEMINI_RESPONSE)
            result = await stage5_metadata(_make_state())

        latency = result.get("stage5_latency_ms")
        assert isinstance(latency, int), (
            f"stage5_latency_ms가 int가 아님: {type(latency).__name__} = {latency}"
        )
        assert latency >= 0, f"stage5_latency_ms가 음수: {latency}"

    @pytest.mark.asyncio
    async def test_stage5_latency_ms_recorded_on_llm_failure(self):
        """LLM 호출 실패(Exception) 시에도 stage5_latency_ms가 기록돼야 한다."""
        from app.pipeline.stage5_metadata_agent import stage5_metadata

        with patch(
            "app.pipeline.stage5_metadata_agent.call_gemini_quality",
            side_effect=Exception("Gemini API 오류"),
        ):
            result = await stage5_metadata(_make_state())

        assert "stage5_latency_ms" in result, (
            "LLM 실패 경로(fallback)에서도 stage5_latency_ms 없음"
        )
        assert isinstance(result["stage5_latency_ms"], int)
        assert result["stage5_latency_ms"] >= 0

    @pytest.mark.asyncio
    async def test_stage5_latency_ms_recorded_on_json_parse_failure(self):
        """JSON 파싱 실패 시에도 stage5_latency_ms가 기록돼야 한다."""
        from app.pipeline.stage5_metadata_agent import stage5_metadata

        with patch(
            "app.pipeline.stage5_metadata_agent.call_gemini_quality",
            new_callable=AsyncMock,
        ) as mock_gemini:
            mock_gemini.return_value = MagicMock(content="invalid json {{{{")
            result = await stage5_metadata(_make_state())

        assert "stage5_latency_ms" in result, (
            "JSON 파싱 실패 경로에서도 stage5_latency_ms 없음"
        )


class TestBuildOutputEntryStage5Latency:
    """run_pipeline.py의 build_output_entry()가 stage5_latency_ms를 포함하는지."""

    def test_build_output_entry_accepts_stage5_latency_ms(self):
        """build_output_entry()는 stage5_latency_ms 파라미터를 받아야 한다."""
        from tests.eval.run_pipeline import build_output_entry

        entry = build_output_entry(
            golden_id="md_01",
            doc_id="test-doc-id",
            file_type="md",
            title="테스트",
            category="AI_ML",
            tags=["테스트"],
            entities={},
            quality_score=0.9,
            status="stored",
            processing_time_ms=30000,
            child_chunk_count=10,
            stage5_latency_ms=8500,
        )

        assert "stage5_latency_ms" in entry, (
            f"build_output_entry 반환값에 stage5_latency_ms 없음. 키: {sorted(entry.keys())}"
        )
        assert entry["stage5_latency_ms"] == 8500

    def test_build_output_entry_stage5_latency_ms_none_when_omitted(self):
        """stage5_latency_ms 미전달 시 None으로 기본값 처리돼야 한다."""
        from tests.eval.run_pipeline import build_output_entry

        entry = build_output_entry(
            golden_id="md_01",
            doc_id="test-doc-id",
            file_type="md",
            title="테스트",
            category="AI_ML",
            tags=[],
            entities={},
            quality_score=0.9,
            status="stored",
        )

        assert entry.get("stage5_latency_ms") is None
