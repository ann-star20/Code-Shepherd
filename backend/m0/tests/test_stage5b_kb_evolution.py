"""
TDD Cycle P1: Stage 5b KB Evolution HITL 감지 보강

문제:
  - hitl_02 (양자컴퓨팅 기반 암호화 기술 가이드) 가 Stage 5에서 "보안"으로 분류됨
  - category_is_new=False 이므로 Stage 5b KB Evolution 분기가 발동하지 않음
  - 결과: HITL Recall FN=1, 탐지율 66.7% (목표 ≥ 80%)

목표:
  - Stage 5b가 category_is_new 와 무관하게, 신규 기술 도메인 키워드를
    문서 내용(태그/제목/markdown)에서 탐지하면 KB Evolution HITL을 발동한다.
  - 키워드: 양자컴퓨팅, 양자 컴퓨팅, Post-Quantum, PQC, QKD, 블록체인, Web3,
            뇌-컴퓨터 인터페이스, BCI, 메타버스 도메인 분류 등

대상 함수:
  - app.pipeline.stage5b_metadata_validate_agent.detect_emerging_domain_keywords()
  - stage5b_metadata_validate() 의 KB Evolution 분기 로직
"""

import pytest

from app.pipeline.stage5b_metadata_validate_agent import (
    detect_emerging_domain_keywords,
    stage5b_metadata_validate,
)

# ────────────────────────────────────────────────────────────────
# Unit: detect_emerging_domain_keywords()
# ────────────────────────────────────────────────────────────────

class TestDetectEmergingDomainKeywords:
    """신규 도메인 키워드 감지 함수."""

    def test_detects_quantum_computing_korean(self):
        """'양자컴퓨팅' 키워드 감지."""
        assert detect_emerging_domain_keywords(
            title="양자컴퓨팅 기반 암호화 기술 가이드",
            tags=["양자컴퓨팅", "QKD", "Post-Quantum"],
            markdown="양자컴퓨팅은 기존 RSA 암호를 무력화할 수 있다.",
        ) is True

    def test_detects_pqc_keyword(self):
        """'Post-Quantum', 'PQC' 키워드 감지."""
        assert detect_emerging_domain_keywords(
            title="PQC 표준화 동향",
            tags=["PQC", "NIST"],
            markdown="Post-Quantum Cryptography(PQC)는 양자 내성 암호화 기술이다.",
        ) is True

    def test_detects_qkd_keyword(self):
        """'QKD' 키워드 감지."""
        assert detect_emerging_domain_keywords(
            title="QKD 보안 프로토콜",
            tags=["QKD"],
            markdown="QKD(양자 키 분배)는 BB84 프로토콜을 사용한다.",
        ) is True

    def test_no_false_positive_for_regular_security_doc(self):
        """일반 보안 문서는 신규 도메인으로 감지하지 않는다."""
        assert detect_emerging_domain_keywords(
            title="사내 네트워크 보안 정책",
            tags=["TLS", "방화벽", "VPN"],
            markdown="모든 데이터 전송은 TLS 1.3 이상을 사용한다.",
        ) is False

    def test_no_false_positive_for_ai_ml_doc(self):
        """AI/ML 문서는 신규 도메인으로 감지하지 않는다."""
        assert detect_emerging_domain_keywords(
            title="RAG 시스템 설계 가이드",
            tags=["RAG", "LLM", "벡터DB"],
            markdown="RAG는 Retrieval-Augmented Generation의 약자다.",
        ) is False

    def test_detects_keyword_in_tags_only(self):
        """제목/markdown에 없어도 태그에 있으면 감지한다."""
        assert detect_emerging_domain_keywords(
            title="신기술 동향 보고서",
            tags=["PQC", "CRYSTALS-Kyber"],
            markdown="최신 암호화 기술 동향을 정리한 문서이다.",
        ) is True

    def test_detects_quantum_with_space(self):
        """'양자 컴퓨팅' (띄어쓰기 있는 형태) 도 감지한다."""
        assert detect_emerging_domain_keywords(
            title="양자 컴퓨팅 입문",
            tags=["보안"],
            markdown="양자 컴퓨팅은 전통적인 컴퓨팅과 다른 원리로 작동한다.",
        ) is True


# ────────────────────────────────────────────────────────────────
# Integration: stage5b_metadata_validate() KB Evolution 분기
# ────────────────────────────────────────────────────────────────

class TestStage5bKbEvolutionHitl:
    """stage5b 가 category_is_new=False 이더라도 신규 도메인 키워드 감지 시 HITL 발동."""

    @pytest.mark.asyncio
    async def test_hitl_triggered_for_quantum_doc_even_if_category_is_not_new(self):
        """
        hitl_02 시나리오:
        - Stage5 가 category='보안' 으로 분류 (기존 카테고리) → category_is_new=False
        - 하지만 문서 내용/태그에 '양자컴퓨팅', 'PQC', 'QKD' 키워드 있음
        - Stage5b 는 HITL 을 발동해야 한다.
        """
        import os
        os.environ["USE_MOCK_LLM"] = "true"

        state = {
            "doc_id": "hitl_02_test",
            "metadata": {
                "title": "양자컴퓨팅 기반 암호화 기술 가이드",
                "category": "보안",
                "tags": ["양자컴퓨팅", "QKD", "Post-Quantum", "암호화"],
            },
            "validated_markdown": (
                "# 양자컴퓨팅 기반 암호화 기술 가이드\n\n"
                "양자컴퓨팅(Quantum Computing)은 기존 RSA/ECC 암호화를 무력화할 수 있다.\n"
                "Post-Quantum Cryptography(PQC)는 이에 대응하는 차세대 암호 표준이다.\n"
                "QKD(양자 키 분배)는 BB84 프로토콜로 절대 안전한 키 교환을 실현한다.\n"
                "NIST는 CRYSTALS-Kyber, CRYSTALS-Dilithium을 PQC 표준으로 선정했다.\n"
            ),
            "neo4j_entities": [{"name": "CRYSTALS-Kyber"}, {"name": "BB84"}],
            "category_is_new": False,       # Stage5 가 기존 카테고리로 분류
            "category_reasoning": "",
            "category_alternatives": [],
        }

        result = await stage5b_metadata_validate(state)

        assert result["hitl_required"] is True, (
            "양자컴퓨팅 도메인 키워드가 있는 문서는 category_is_new=False 여도 HITL 발동해야 함"
        )
        assert result["status"] == "hitl_pending"
        assert any("양자" in issue or "KB Evolution" in issue or "신규 도메인" in issue
                   for issue in result["metadata_issues"]), (
            "issues 에 신규 도메인 감지 이유가 포함되어야 함"
        )

    @pytest.mark.asyncio
    async def test_normal_security_doc_not_triggered(self):
        """일반 보안 문서는 KB Evolution HITL이 발동되지 않아야 한다."""
        import os
        os.environ["USE_MOCK_LLM"] = "true"

        state = {
            "doc_id": "security_normal",
            "metadata": {
                "title": "사내 네트워크 보안 정책",
                "category": "보안",
                "tags": ["TLS", "방화벽", "VPN", "접근제어"],
            },
            "validated_markdown": (
                "# 사내 네트워크 보안 정책\n\n"
                "모든 데이터 전송은 TLS 1.3 이상을 사용한다.\n"
                "방화벽은 인바운드 트래픽을 엄격히 제한한다.\n"
                "VPN을 통해 원격 접속 시 MFA를 적용한다.\n"
            ),
            "neo4j_entities": [{"name": "TLS"}, {"name": "VPN"}],
            "category_is_new": False,
            "category_reasoning": "",
            "category_alternatives": [],
        }

        result = await stage5b_metadata_validate(state)

        assert result.get("hitl_required", False) is False, (
            "일반 보안 문서는 KB Evolution HITL이 발동되면 안 됨"
        )
