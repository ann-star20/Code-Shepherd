"""
TDD Cycle 2: Stage 5 제목 정제 — 문서 상태 접미사 제거

문제:
  - DOCX eval 결과: "재혁회사 취업규칙 샘플 문서" (actual) vs "재혁회사 취업규칙" (expected)
  - '샘플 문서', '초안', '개정판' 같은 문서 상태 표시어가 제목에 포함돼 title_accuracy 0.00

목표:
  - _clean_document_title() 함수가 문서 상태 접미사를 제거한다.
  - Stage 5 _extract_h1_title이 이 정제 함수를 적용한다.
"""

import pytest

from app.pipeline.stage5_metadata_agent import _clean_document_title, _extract_h1_title


class TestCleanDocumentTitle:
    """_clean_document_title() — 문서 상태 접미사 제거."""

    def test_removes_sample_doc_suffix(self):
        assert _clean_document_title("재혁회사 취업규칙 샘플 문서") == "재혁회사 취업규칙"

    def test_removes_draft_suffix(self):
        assert _clean_document_title("KMS 설계 문서 초안") == "KMS 설계 문서"

    def test_removes_revision_suffix(self):
        assert _clean_document_title("보안 정책 개정판") == "보안 정책"

    def test_removes_test_suffix(self):
        assert _clean_document_title("온보딩 가이드 테스트 문서") == "온보딩 가이드"

    def test_removes_temp_suffix(self):
        assert _clean_document_title("API 명세서 임시") == "API 명세서"

    def test_leaves_normal_title_unchanged(self):
        """접미사 없는 정상 제목은 변경하지 않는다."""
        assert _clean_document_title("대규모 언어 모델(LLM) 기술 개요") == "대규모 언어 모델(LLM) 기술 개요"

    def test_leaves_title_with_sample_in_middle_unchanged(self):
        """'샘플'이 중간에 있는 경우(접미사 아님)는 제거하지 않는다."""
        assert _clean_document_title("샘플 데이터 분석 보고서") == "샘플 데이터 분석 보고서"

    def test_empty_string_returns_empty(self):
        assert _clean_document_title("") == ""

    def test_removes_trailing_whitespace_after_clean(self):
        """접미사 제거 후 공백이 남지 않아야 한다."""
        result = _clean_document_title("취업규칙 샘플 문서")
        assert result == result.strip()


class TestExtractH1TitleWithCleaning:
    """_extract_h1_title이 정제 함수를 적용해 반환한다."""

    def test_h1_with_sample_suffix_is_cleaned(self):
        md = "# 재혁회사 취업규칙 샘플 문서\n\n본문"
        result = _extract_h1_title(md)
        assert result == "재혁회사 취업규칙"

    def test_h1_without_suffix_unchanged(self):
        md = "# 대규모 언어 모델(LLM) 기술 개요\n\n본문"
        result = _extract_h1_title(md)
        assert result == "대규모 언어 모델(LLM) 기술 개요"
