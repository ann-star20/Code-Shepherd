"""
TDD: tags_f1 개선 — 한영 동의어 정규화
현재 avg_tags_f1 = 0.424 → 목표 0.60

문제:
  normalize_text('트랜스포머') != normalize_text('Transformer')
  → 파이프라인이 영어로 출력한 태그가 golden 한국어 태그와 매칭 안 됨

이 파일은 normalize_text 확장 + compute_tags_metrics 크로스-언어 동작 검증.
"""

import sys
import pathlib
import pytest

# run_eval은 tests/eval/ 하위에 있으므로 sys.path로 접근
sys.path.insert(0, str(pathlib.Path(__file__).parent / "eval"))
from run_eval import normalize_text, compute_tags_metrics  # noqa: E402


# ─────────────────────────────────────────────────────────────────────────────
# normalize_text 단위 테스트 (RED: 아래 assert들이 현재 실패함)
# ─────────────────────────────────────────────────────────────────────────────


class TestNormalizeTextAliases:
    """한영 동의어 쌍이 동일한 canonical 값으로 정규화되어야 한다."""

    def test_transformer_korean_english(self):
        # 현재: '트랜스포머' != 'transformer'  →  RED
        assert normalize_text("트랜스포머") == normalize_text("Transformer")

    def test_pretraining_korean_english(self):
        # 현재: '사전학습' != 'pretraining'  →  RED
        assert normalize_text("사전학습") == normalize_text("Pre-training")

    def test_knowledge_management_ko_en(self):
        # 현재: '지식관리' != 'knowledgemanagement'  →  RED
        assert normalize_text("지식관리") == normalize_text("Knowledge Management")

    def test_vector_db_ko_en(self):
        # 현재: '벡터db' != 'vectordatabase'  →  RED
        assert normalize_text("벡터DB") == normalize_text("Vector Database")

    def test_ai_agent_full_vs_short(self):
        # 현재: 'aiagent' != 'agent'  →  RED
        assert normalize_text("AI Agent") == normalize_text("Agent")

    def test_embedding_ko_en(self):
        assert normalize_text("임베딩") == normalize_text("Embedding")

    def test_architecture_ko_en(self):
        assert normalize_text("아키텍처") == normalize_text("Architecture")

    def test_personal_info_short_vs_full(self):
        # '개인정보' ⊂ '개인정보보호' — 같은 canonical
        assert normalize_text("개인정보") == normalize_text("개인정보보호")

    def test_retrospective_ko_short_vs_full(self):
        # '회고' ⊂ '프로젝트 회고'
        assert normalize_text("회고") == normalize_text("프로젝트 회고")

    def test_dev_environment_ko_variants(self):
        # '개발환경' ↔ '개발 환경 설정'
        assert normalize_text("개발환경") == normalize_text("개발 환경 설정")


# ─────────────────────────────────────────────────────────────────────────────
# compute_tags_metrics 크로스-언어 F1 테스트
# ─────────────────────────────────────────────────────────────────────────────


class TestComputeTagsMetricsCrossLanguage:

    def test_korean_golden_english_actual_f1_nonzero(self):
        """golden 한국어, actual 영어 동의어 → F1 > 0."""
        recall, prec = compute_tags_metrics(
            ["트랜스포머", "사전학습"],
            ["Transformer", "Pre-training"],
        )
        f1 = 2 * recall * prec / (recall + prec) if recall + prec else 0
        assert f1 > 0  # RED: 현재 f1 = 0

    def test_pptx01_scenario_f1_gte_50(self):
        """pptx_01 대표 시나리오: 한영 혼재 golden vs 영어 actual, F1 ≥ 0.5."""
        golden = ["KMS", "LangGraph", "AI Agent", "지식관리", "RAG", "벡터DB"]
        actual = ["AI", "LLM", "Knowledge Management", "Agent", "RAG", "Vector Database", "KMS"]
        recall, prec = compute_tags_metrics(golden, actual)
        f1 = 2 * recall * prec / (recall + prec) if recall + prec else 0
        assert f1 >= 0.5  # RED: 현재 ~0.28

    def test_md01_transformer_scenario(self):
        """md_01 대표 시나리오: golden 트랜스포머/사전학습 vs actual Transformer/Pre-training."""
        golden = ["LLM", "트랜스포머", "Attention", "NLP", "사전학습"]
        actual = ["LLM", "Transformer", "Attention", "NLP", "Pre-training", "AI"]
        recall, prec = compute_tags_metrics(golden, actual)
        f1 = 2 * recall * prec / (recall + prec) if recall + prec else 0
        assert f1 >= 0.8  # RED: 현재 0.571 (3/5 matching)

    def test_md04_personal_info_scenario(self):
        """md_04 대표 시나리오: golden '개인정보' vs actual '개인정보보호'."""
        golden = ["보안정책", "개인정보", "접근통제", "ISMS-P"]
        actual = ["보안정책", "개인정보보호", "접근통제", "ISMS-P"]
        recall, prec = compute_tags_metrics(golden, actual)
        f1 = 2 * recall * prec / (recall + prec) if recall + prec else 0
        assert f1 == 1.0  # RED: 현재 f1 = 0.857 (3/4)
