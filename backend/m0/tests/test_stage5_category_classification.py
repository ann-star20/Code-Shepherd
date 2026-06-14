"""
TDD Cycle P2: Stage 5 카테고리 오분류 교정

문제:
  - md_06 (RAG 시스템 설계): LLM이 "아키텍처"로 분류 → golden 기대값 "AI_ML"
  - pdf_03 (SQM 검색 품질 지표): LLM이 VALID_CATEGORIES 에 없는 "코딩품질관리" 반환
    → Stage 5b rule-check 에서 HITL 발동 → completion_rate 저하

원인 분석:
  - "설계(design)" 키워드가 있는 문서를 LLM이 "아키텍처"로 분류하는 경향
  - "검색 품질" 관련 문서를 ML/AI 영역으로 인식 못함
  - SQM/검색 품질 지표는 AI_ML 영역이지만 LLM이 코딩품질로 혼동

해결 전략:
  1. _disambiguate_category() 함수 추가 — LLM 분류 이후 RAG/ML 시그널 기반 교정
  2. AI_ML 카테고리 정의에 "RAG 시스템 설계", "검색 품질 지표" 명시
  3. Stage 5 파이프라인에서 LLM 결과에 교정 함수 적용

대상 함수:
  - app.pipeline.stage5_metadata_agent._disambiguate_category()  [신규]
  - stage5_metadata() 의 카테고리 교정 적용 경로
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.pipeline.stage5_metadata_agent import (
    _disambiguate_category,
    stage5_metadata,
)


# ────────────────────────────────────────────────────────────────
# Unit: _disambiguate_category()
# ────────────────────────────────────────────────────────────────


class TestDisambiguateCategory:
    """LLM 오분류 교정 함수 단위 테스트."""

    # ── md_06 시나리오 ───────────────────────────────────────────

    def test_rag_system_design_reclassified_to_ai_ml(self):
        """
        md_06 시나리오:
        LLM이 '아키텍처'로 분류했지만 RAG 시그널 있음 → AI_ML 교정
        """
        result = _disambiguate_category(
            llm_category="아키텍처",
            title="RAG 시스템 설계 가이드",
            tags=["RAG", "벡터DB", "임베딩", "LLM", "청크"],
            markdown=(
                "# RAG 시스템 설계 가이드\n\n"
                "RAG(Retrieval-Augmented Generation)는 외부 지식 베이스를 "
                "검색해 LLM 응답 품질을 높이는 기술이다.\n"
                "pgvector를 활용한 벡터 검색 파이프라인을 설계한다.\n"
            ),
        )
        assert result == "AI_ML", (
            "RAG 관련 문서는 '아키텍처'로 분류되더라도 AI_ML로 교정되어야 함"
        )

    def test_rag_in_tags_only_reclassified(self):
        """태그에만 RAG가 있어도 교정한다."""
        result = _disambiguate_category(
            llm_category="아키텍처",
            title="사내 검색 시스템 구축 방안",
            tags=["RAG", "Elasticsearch", "LLM"],
            markdown="# 검색 시스템 구축\n검색 인프라 설계 문서입니다.",
        )
        assert result == "AI_ML"

    def test_embedding_design_doc_reclassified(self):
        """임베딩 설계 문서도 AI_ML 교정 대상."""
        result = _disambiguate_category(
            llm_category="아키텍처",
            title="임베딩 파이프라인 아키텍처",
            tags=["임베딩", "벡터검색", "pgvector"],
            markdown="# 임베딩 파이프라인\n텍스트를 벡터로 변환해 pgvector에 저장한다.",
        )
        assert result == "AI_ML"

    # ── pdf_03 시나리오 ──────────────────────────────────────────

    def test_sqm_invalid_category_reclassified_to_ai_ml(self):
        """
        pdf_03 시나리오:
        LLM이 VALID_CATEGORIES 에 없는 '코딩품질관리'를 반환 + 검색 품질 시그널 있음
        → AI_ML 교정
        """
        result = _disambiguate_category(
            llm_category="코딩품질관리",
            title="좋은 검색을 판단하는 지표, SQM",
            tags=["검색 품질", "Precision", "Recall", "NDCG", "MRR"],
            markdown=(
                "# 좋은 검색을 판단하는 지표, SQM\n\n"
                "Search Quality Metrics(SQM)는 검색 엔진의 품질을 측정하는 지표다.\n"
                "Precision@k, Recall@k, NDCG, MRR 등이 대표적인 지표이다.\n"
            ),
        )
        assert result == "AI_ML", (
            "검색 품질 지표(SQM) 문서는 AI_ML로 교정되어야 함"
        )

    def test_search_quality_metrics_reclassified(self):
        """검색 품질 지표 키워드(Precision@k, NDCG 등)가 있으면 AI_ML."""
        result = _disambiguate_category(
            llm_category="기타",
            title="검색 랭킹 품질 평가",
            tags=["NDCG", "검색", "랭킹 알고리즘"],
            markdown="NDCG(Normalized Discounted Cumulative Gain)는 검색 품질 지표다.",
        )
        assert result == "AI_ML"

    def test_mlops_doc_reclassified_from_invalid_category(self):
        """MLOps 문서가 유효하지 않은 카테고리로 분류되면 AI_ML."""
        result = _disambiguate_category(
            llm_category="개발운영",   # VALID_CATEGORIES 에 없음
            title="MLOps 파이프라인 운영 가이드",
            tags=["MLOps", "모델 배포", "모니터링"],
            markdown="# MLOps\n모델 학습부터 배포까지 자동화하는 방법론이다.",
        )
        assert result == "AI_ML"

    # ── 교정 대상 아님 ───────────────────────────────────────────

    def test_correct_ai_ml_category_unchanged(self):
        """이미 AI_ML이면 변경하지 않는다."""
        result = _disambiguate_category(
            llm_category="AI_ML",
            title="LLM 프롬프트 엔지니어링 가이드",
            tags=["LLM", "GPT", "프롬프트"],
            markdown="# LLM 프롬프트 엔지니어링",
        )
        assert result == "AI_ML"

    def test_pure_architecture_doc_unchanged(self):
        """RAG/ML 시그널 없는 일반 아키텍처 문서는 교정하지 않는다."""
        result = _disambiguate_category(
            llm_category="아키텍처",
            title="마이크로서비스 아키텍처 패턴",
            tags=["마이크로서비스", "API Gateway", "서비스 메시", "MSA"],
            markdown=(
                "# 마이크로서비스 아키텍처\n"
                "각 서비스를 독립적으로 배포하는 아키텍처 패턴이다.\n"
                "API Gateway로 클라이언트 요청을 라우팅한다.\n"
            ),
        )
        assert result == "아키텍처"

    def test_security_doc_unchanged(self):
        """보안 문서는 교정 대상이 아니다."""
        result = _disambiguate_category(
            llm_category="보안",
            title="사내 네트워크 보안 정책",
            tags=["TLS", "방화벽", "VPN", "접근제어"],
            markdown="# 보안 정책\nTLS 1.3 이상 사용 필수.",
        )
        assert result == "보안"

    def test_invalid_category_without_ai_ml_signal_falls_back_to_etc(self):
        """AI/ML 시그널 없는 유효하지 않은 카테고리는 '기타'로 교정."""
        result = _disambiguate_category(
            llm_category="존재하지않는카테고리",
            title="사내 경비 처리 규정",
            tags=["경비", "회계", "비용 청구"],
            markdown="# 경비 처리 규정\n출장 경비 청구 절차를 안내합니다.",
        )
        assert result == "기타"


# ────────────────────────────────────────────────────────────────
# Integration: stage5_metadata() 교정 경로 검증
# ────────────────────────────────────────────────────────────────


class TestStage5CategoryIntegration:
    """stage5_metadata() 통합 테스트 — LLM 오분류 시 교정되는지."""

    @pytest.mark.asyncio
    async def test_md_06_rag_design_gets_ai_ml_after_correction(self):
        """
        md_06 시나리오: LLM이 '아키텍처' 반환
        → _disambiguate_category() 로 'AI_ML' 교정
        → metadata["category"] == "AI_ML"
        """
        mock_response = MagicMock()
        mock_response.content = """{
            "title": "RAG 시스템 설계 가이드",
            "category": "아키텍처",
            "category_reasoning": "시스템 설계 문서로 판단",
            "category_alternatives": ["AI_ML"],
            "team": null,
            "author": null,
            "tags": ["RAG", "벡터DB", "임베딩", "LLM", "pgvector", "청크", "검색"],
            "entities": []
        }"""

        with patch(
            "app.pipeline.stage5_metadata_agent.call_gemini_quality",
            new_callable=AsyncMock,
            return_value=mock_response,
        ):
            state = {
                "doc_id": "md_06_test",
                "validated_markdown": (
                    "# RAG 시스템 설계 가이드\n\n"
                    "RAG(Retrieval-Augmented Generation)는 LLM에 외부 지식을 주입하는 기술이다.\n"
                    "pgvector를 사용해 임베딩 벡터를 저장하고 유사도 검색을 수행한다.\n"
                ),
                "chunks": [],
            }
            result = await stage5_metadata(state)

        assert result["metadata"]["category"] == "AI_ML", (
            "RAG 설계 문서에서 LLM이 '아키텍처'를 반환해도 AI_ML로 교정되어야 함"
        )

    @pytest.mark.asyncio
    async def test_pdf_03_sqm_gets_ai_ml_after_correction(self):
        """
        pdf_03 시나리오: LLM이 유효하지 않은 '코딩품질관리' 반환
        → _disambiguate_category() 로 'AI_ML' 교정
        → Stage 5b rule-check HITL 발동 없이 통과 가능
        """
        mock_response = MagicMock()
        mock_response.content = """{
            "title": "좋은 검색을 판단하는 지표, SQM",
            "category": "코딩품질관리",
            "category_reasoning": "코드 품질 측정 문서로 판단",
            "category_alternatives": ["AI_ML", "코드성능검증"],
            "team": null,
            "author": null,
            "tags": ["SQM", "검색 품질", "Precision", "Recall", "NDCG", "MRR", "랭킹"],
            "entities": []
        }"""

        with patch(
            "app.pipeline.stage5_metadata_agent.call_gemini_quality",
            new_callable=AsyncMock,
            return_value=mock_response,
        ):
            state = {
                "doc_id": "pdf_03_test",
                "validated_markdown": (
                    "# 좋은 검색을 판단하는 지표, SQM\n\n"
                    "Search Quality Metrics(SQM)는 검색 결과의 품질을 측정하는 지표다.\n"
                    "Precision@k, Recall@k, NDCG, MRR이 핵심 지표이다.\n"
                ),
                "chunks": [],
            }
            result = await stage5_metadata(state)

        assert result["metadata"]["category"] == "AI_ML", (
            "SQM 문서에서 LLM이 '코딩품질관리'를 반환해도 AI_ML로 교정되어야 함"
        )
        assert result.get("category_is_new") is False, (
            "AI_ML은 VALID_CATEGORIES 내 카테고리이므로 category_is_new=False 여야 함"
        )
