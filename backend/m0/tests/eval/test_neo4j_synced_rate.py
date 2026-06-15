"""
TDD Cycle 4: neo4j_synced_rate KPI 추가

문제:
  - Neo4j 동기화 여부를 평가 리포트에서 확인할 수 없음
  - pipeline_output.json의 entities 필드로 proxy 측정 (file mode)

목표:
  - stored 문서 중 entities dict가 비어 있지 않은 비율 = neo4j_synced_rate
  - compute_neo4j_kpis() 함수 추가
  - 목표 임계값: ≥ 0.80
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import pytest
from run_eval import PipelineResult, compute_neo4j_kpis


def _make_result(
    golden_id: str,
    status: str = "stored",
    entities: dict | None = None,
) -> PipelineResult:
    return PipelineResult(
        doc_id=golden_id,
        golden_id=golden_id,
        title="테스트",
        category="AI_ML",
        tags=[],
        entities=entities if entities is not None else {},
        quality_score=0.9,
        status=status,
        file_type="md",
    )


_SAMPLE_ENTITIES = {"Technology": ["GPT-4", "Claude"], "Concept": ["LLM"]}


class TestNeo4jSyncedRate:
    """compute_neo4j_kpis() 단위 테스트."""

    def test_all_stored_with_entities_returns_1(self):
        """모든 stored 문서에 엔티티가 있으면 rate = 1.0."""
        results = [
            _make_result("md_01", entities=_SAMPLE_ENTITIES),
            _make_result("md_02", entities={"Pattern": ["RAG"]}),
        ]
        kpis = compute_neo4j_kpis(results)
        assert kpis["neo4j_synced_rate"] == 1.0

    def test_half_stored_with_entities_returns_half(self):
        """stored 2개 중 1개만 엔티티 있으면 rate = 0.5."""
        results = [
            _make_result("md_01", entities=_SAMPLE_ENTITIES),
            _make_result("md_02", entities={}),
        ]
        kpis = compute_neo4j_kpis(results)
        assert kpis["neo4j_synced_rate"] == pytest.approx(0.5)

    def test_hitl_and_error_excluded_from_denominator(self):
        """hitl_pending / error 문서는 분모에서 제외."""
        results = [
            _make_result("md_01", entities=_SAMPLE_ENTITIES),
            _make_result("md_02", status="hitl_pending", entities=_SAMPLE_ENTITIES),
            _make_result("md_03", status="error", entities=_SAMPLE_ENTITIES),
        ]
        kpis = compute_neo4j_kpis(results)
        # stored = md_01만 → 1/1 = 1.0
        assert kpis["neo4j_synced_rate"] == 1.0
        assert kpis["stored_count"] == 1

    def test_no_stored_docs_returns_zero(self):
        """stored 문서가 하나도 없으면 rate = 0.0."""
        results = [
            _make_result("md_01", status="error"),
            _make_result("md_02", status="hitl_pending"),
        ]
        kpis = compute_neo4j_kpis(results)
        assert kpis["neo4j_synced_rate"] == 0.0

    def test_empty_entities_dict_counts_as_not_synced(self):
        """entities가 빈 dict {}이면 미동기화로 처리."""
        results = [_make_result("md_01", entities={})]
        kpis = compute_neo4j_kpis(results)
        assert kpis["neo4j_synced_rate"] == 0.0

    def test_returns_required_keys(self):
        """반환 dict에 필수 키가 모두 포함되어야 한다."""
        results = [_make_result("md_01", entities=_SAMPLE_ENTITIES)]
        kpis = compute_neo4j_kpis(results)
        for key in ("neo4j_synced_rate", "synced_count", "stored_count"):
            assert key in kpis, f"키 누락: {key}"

    def test_synced_count_matches_docs_with_entities(self):
        """synced_count가 엔티티 있는 stored 문서 수와 일치해야 한다."""
        results = [
            _make_result("md_01", entities=_SAMPLE_ENTITIES),
            _make_result("md_02", entities={}),
            _make_result("md_03", entities={"Concept": ["RAG"]}),
        ]
        kpis = compute_neo4j_kpis(results)
        assert kpis["synced_count"] == 2
        assert kpis["stored_count"] == 3

    def test_empty_input_returns_zero(self):
        """입력 리스트가 비어있으면 rate = 0.0."""
        kpis = compute_neo4j_kpis([])
        assert kpis["neo4j_synced_rate"] == 0.0
