"""
TDD Cycle 5: chunk_embedding_rate KPI 추가

문제:
  - pgVector에 child chunk가 실제로 임베딩되었는지 평가 리포트에서 확인할 수 없음
  - child_chunk_count (pipeline 추출 수) vs embedded_chunk_count (DB 저장 수) 비율

목표:
  - compute_chunk_embedding_kpis() 추가
  - PipelineResult에 child_chunk_count / embedded_chunk_count 필드 추가
  - file mode proxy: stored + child_chunk_count 있으면 embedded = child_chunk_count
  - 목표 임계값: ≥ 0.90
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import pytest
from run_eval import PipelineResult, compute_chunk_embedding_kpis


def _make_result(
    golden_id: str,
    status: str = "stored",
    child_chunk_count: int | None = None,
    embedded_chunk_count: int | None = None,
) -> PipelineResult:
    return PipelineResult(
        doc_id=golden_id,
        golden_id=golden_id,
        title="테스트",
        category="AI_ML",
        tags=[],
        entities={"Technology": ["GPT-4"]},
        quality_score=0.9,
        status=status,
        file_type="md",
        child_chunk_count=child_chunk_count,
        embedded_chunk_count=embedded_chunk_count,
    )


class TestChunkEmbeddingRate:
    """compute_chunk_embedding_kpis() 단위 테스트."""

    def test_all_chunks_embedded_returns_1(self):
        """모든 child chunk가 임베딩되면 rate = 1.0."""
        results = [
            _make_result("md_01", child_chunk_count=10, embedded_chunk_count=10),
            _make_result("md_02", child_chunk_count=5,  embedded_chunk_count=5),
        ]
        kpis = compute_chunk_embedding_kpis(results)
        assert kpis["chunk_embedding_rate"] == pytest.approx(1.0)

    def test_partial_embedding_returns_correct_ratio(self):
        """일부만 임베딩된 경우 전체 비율을 정확히 계산한다."""
        results = [
            _make_result("md_01", child_chunk_count=10, embedded_chunk_count=9),
            _make_result("md_02", child_chunk_count=10, embedded_chunk_count=10),
        ]
        kpis = compute_chunk_embedding_kpis(results)
        # 19 / 20 = 0.95
        assert kpis["chunk_embedding_rate"] == pytest.approx(0.95)

    def test_stored_without_explicit_embedded_count_uses_child_as_proxy(self):
        """stored 문서에 embedded_chunk_count 없으면 child_chunk_count를 proxy로 사용한다."""
        results = [_make_result("md_01", child_chunk_count=8, embedded_chunk_count=None)]
        kpis = compute_chunk_embedding_kpis(results)
        # proxy: stored → embedded = child_chunk_count
        assert kpis["chunk_embedding_rate"] == pytest.approx(1.0)
        assert kpis["total_child_chunks"] == 8
        assert kpis["total_embedded_chunks"] == 8

    def test_hitl_and_error_docs_excluded(self):
        """hitl_pending / error 문서는 집계에서 제외된다."""
        results = [
            _make_result("md_01", child_chunk_count=10, embedded_chunk_count=10),
            _make_result("md_02", status="hitl_pending", child_chunk_count=8, embedded_chunk_count=8),
            _make_result("md_03", status="error", child_chunk_count=5, embedded_chunk_count=5),
        ]
        kpis = compute_chunk_embedding_kpis(results)
        # stored = md_01만 → 10/10
        assert kpis["chunk_embedding_rate"] == pytest.approx(1.0)
        assert kpis["total_child_chunks"] == 10

    def test_no_chunk_count_info_returns_not_available(self):
        """chunk count 정보가 없으면 rate = None (N/A) 반환한다."""
        results = [_make_result("md_01", child_chunk_count=None, embedded_chunk_count=None)]
        kpis = compute_chunk_embedding_kpis(results)
        assert kpis["chunk_embedding_rate"] is None

    def test_empty_input_returns_not_available(self):
        """입력이 비어있으면 rate = None."""
        kpis = compute_chunk_embedding_kpis([])
        assert kpis["chunk_embedding_rate"] is None

    def test_returns_required_keys(self):
        """반환 dict에 필수 키가 포함되어야 한다."""
        results = [_make_result("md_01", child_chunk_count=5, embedded_chunk_count=5)]
        kpis = compute_chunk_embedding_kpis(results)
        for key in ("chunk_embedding_rate", "total_child_chunks", "total_embedded_chunks"):
            assert key in kpis, f"키 누락: {key}"

    def test_zero_child_chunks_not_included_in_denominator(self):
        """child_chunk_count = 0인 문서는 분모에 영향을 주지 않는다."""
        results = [
            _make_result("md_01", child_chunk_count=10, embedded_chunk_count=10),
            _make_result("md_02", child_chunk_count=0,  embedded_chunk_count=0),
        ]
        kpis = compute_chunk_embedding_kpis(results)
        assert kpis["chunk_embedding_rate"] == pytest.approx(1.0)
        assert kpis["total_child_chunks"] == 10


class TestPipelineResultChunkFields:
    """PipelineResult에 child_chunk_count / embedded_chunk_count 필드 존재 확인."""

    def test_pipeline_result_has_child_chunk_count(self):
        """PipelineResult 생성 시 child_chunk_count 필드를 받아야 한다."""
        result = _make_result("md_01", child_chunk_count=10)
        assert result.child_chunk_count == 10

    def test_pipeline_result_has_embedded_chunk_count(self):
        """PipelineResult 생성 시 embedded_chunk_count 필드를 받아야 한다."""
        result = _make_result("md_01", embedded_chunk_count=8)
        assert result.embedded_chunk_count == 8

    def test_pipeline_result_chunk_fields_default_to_none(self):
        """chunk count 필드의 기본값은 None이다."""
        result = PipelineResult(
            doc_id="test",
            golden_id="md_01",
            title=None,
            category=None,
            tags=[],
            entities={},
        )
        assert result.child_chunk_count is None
        assert result.embedded_chunk_count is None
