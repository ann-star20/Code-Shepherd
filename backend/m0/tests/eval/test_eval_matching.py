"""
run_eval.py 태그/엔티티 매칭 함수 단위 테스트

Phase 1 TDD:
  - Cycle 1: pgvector ↔ 벡터DB 동의어 연결
  - PPTX/PDF 실패 케이스 기반 회귀 방지
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import pytest
from run_eval import _terms_match, normalize_text, compute_tags_metrics


# ---------------------------------------------------------------------------
# Cycle 1 RED: pgvector ↔ 벡터DB 동의어 — 현재 실패해야 함
# ---------------------------------------------------------------------------

class TestVectorDBSynonyms:
    def test_pgvector_matches_vectordb_korean(self):
        """pgVector(실제 출력)가 벡터DB(golden)와 매칭되어야 한다."""
        assert _terms_match("벡터DB", "pgVector") is True

    def test_pgvector_lowercase_matches_vectordb(self):
        """대소문자 무관하게 매칭되어야 한다."""
        assert _terms_match("벡터db", "pgvector") is True

    def test_vectordb_korean_full_matches_pgvector(self):
        """'벡터데이터베이스'도 pgVector와 매칭되어야 한다."""
        assert _terms_match("벡터데이터베이스", "pgVector") is True


# ---------------------------------------------------------------------------
# 기존 동의어가 올바르게 작동하는지 확인 (회귀 방지)
# ---------------------------------------------------------------------------

class TestExistingSynonyms:
    def test_generation_ai_with_space(self):
        """'생성형AI' ↔ '생성형 AI' — 공백 제거로 매칭되어야 한다."""
        assert _terms_match("생성형AI", "생성형 AI") is True

    def test_natural_language_processing(self):
        """'자연어처리' ↔ '자연어 처리' — 공백 제거로 매칭되어야 한다."""
        assert _terms_match("자연어처리", "자연어 처리") is True

    def test_knowledge_management_compound(self):
        """'지식관리' ↔ '지식 관리 시스템' — substring 매칭되어야 한다."""
        assert _terms_match("지식관리", "지식 관리 시스템") is True

    def test_embedding_ko_en(self):
        """'임베딩' ↔ 'embedding' — 동의어 매핑으로 매칭되어야 한다."""
        assert _terms_match("임베딩", "embedding") is True

    def test_pipeline_ko_en(self):
        """'파이프라인' ↔ 'pipeline' — 동의어 매핑으로 매칭되어야 한다."""
        assert _terms_match("파이프라인", "pipeline") is True


# ---------------------------------------------------------------------------
# compute_tags_metrics PPTX 시나리오 (Cycle 1 완료 후 GREEN 확인용)
# ---------------------------------------------------------------------------

class TestPptxTagsScenario:
    """PPTX 실패 케이스 재현 — Cycle 1 완료 후 F1 개선 확인."""

    EXPECTED = ["KMS", "LangGraph", "AI Agent", "지식관리", "RAG", "파이프라인", "벡터DB", "아키텍처", "멀티스토리지"]
    ACTUAL = ["AI Agent", "조직 지식 플랫폼", "LangGraph", "Gemini 2.5", "pgVector", "Neo4j", "RAG", "지식 관리 시스템"]

    def test_tags_f1_improves_with_pgvector_synonym(self):
        """pgVector 동의어 추가 후 PPTX F1이 0.47보다 높아야 한다."""
        recall, precision = compute_tags_metrics(self.EXPECTED, self.ACTUAL)
        f1 = 2 * recall * precision / (recall + precision) if (recall + precision) > 0 else 0.0
        assert f1 > 0.47, f"F1이 0.47 이하: {f1:.3f} (pgVector 동의어 추가로 개선 필요)"

    def test_pgvector_counted_in_recall(self):
        """pgVector가 벡터DB와 매칭되어 recall에 포함되어야 한다."""
        recall, _ = compute_tags_metrics(self.EXPECTED, self.ACTUAL)
        # pgVector 동의어 추가 전: 벡터DB recall에 미포함 → 이 테스트가 통과하면 동의어 작동
        matched_vectordb = any(_terms_match("벡터DB", a) for a in self.ACTUAL)
        assert matched_vectordb is True, "pgVector가 벡터DB와 매칭되지 않음"
