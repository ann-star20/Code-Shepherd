"""
Stage 3 청킹 단위 테스트
"""

from __future__ import annotations

import pytest
from unittest.mock import patch, MagicMock

from module_0_kms.pipeline.stage3_chunk import (
    _split_by_headers,
    _make_parent_chunks,
    _make_child_chunks,
    _hard_split,
    _count_tokens,
    _get_tiktoken_encoder,
    _split_sentences,
    stage3_chunk,
)

SAMPLE_MARKDOWN = """\
## 1. API 설계 원칙

RESTful 원칙을 따른다. 모든 엔드포인트는 명사 복수형을 사용한다.
버전 관리를 위해 /v1/ 접두사를 사용한다.

## 2. 인증 처리

JWT 토큰 기반 인증을 사용한다. 토큰 만료 시간은 1시간이다.
Refresh 토큰을 별도로 관리한다. 보안을 위해 HTTPS만 허용한다.

## 3. 오류 처리

표준 HTTP 상태 코드를 사용한다. 오류 응답은 JSON 형식으로 반환한다.
"""


class TestSplitByHeaders:
    def test_splits_on_double_hash(self):
        sections = _split_by_headers(SAMPLE_MARKDOWN)
        assert len(sections) == 3

    def test_no_headers_returns_single_section(self):
        sections = _split_by_headers("헤더 없는 텍스트")
        assert len(sections) == 1
        assert sections[0][0] == ""

    def test_header_text_preserved(self):
        sections = _split_by_headers(SAMPLE_MARKDOWN)
        headers = [s[0] for s in sections]
        assert any("API 설계 원칙" in h for h in headers)


class TestMakeParentChunks:
    def test_returns_parent_type(self):
        sections = _split_by_headers(SAMPLE_MARKDOWN)
        parents = _make_parent_chunks(sections, "test-doc-id")
        assert all(c["chunk_type"] == "parent" for c in parents)

    def test_parent_chunk_id_is_none(self):
        sections = _split_by_headers(SAMPLE_MARKDOWN)
        parents = _make_parent_chunks(sections, "test-doc-id")
        assert all(c["parent_chunk_id"] is None for c in parents)

    def test_doc_id_propagated(self):
        sections = _split_by_headers(SAMPLE_MARKDOWN)
        parents = _make_parent_chunks(sections, "my-doc-id")
        assert all(c["doc_id"] == "my-doc-id" for c in parents)

    def test_section_header_preserved(self):
        sections = _split_by_headers(SAMPLE_MARKDOWN)
        parents = _make_parent_chunks(sections, "test-doc-id")
        headers = [c["section_header"] for c in parents if c["section_header"]]
        assert any("API 설계 원칙" in h for h in headers)

    def test_merged_sections_include_all_headings_in_content(self):
        """여러 섹션이 하나의 parent로 병합될 때 각 섹션 헤딩이 content에 포함되어야 한다.

        BUG: _make_parent_chunks가 buffer.append(content)만 하고 header를 빠뜨려
        두 번째 이후 섹션 헤딩이 content에서 사라짐 → 임베딩 품질 저하.
        """
        md = (
            "## 4. 코드 리뷰 기준\n\n"
            "PR 리뷰 시 아래 기준으로 피드백을 제공합니다.\n\n"
            "## 5. 자주 묻는 질문 (FAQ)\n\n"
            "Q. 로컬에서 DB를 어떻게 실행하나요?\n"
        )
        sections = _split_by_headers(md)
        parents = _make_parent_chunks(sections, "doc-001")
        # 두 섹션이 작아서 하나의 parent로 병합됨
        assert len(parents) == 1, "작은 두 섹션은 하나의 parent로 병합되어야 한다"
        content = parents[0]["content"]
        # 두 헤딩 모두 content에 포함되어야 한다
        assert "4. 코드 리뷰 기준" in content, "첫 번째 헤딩이 content에 포함되어야 한다"
        assert "5. 자주 묻는 질문" in content, "두 번째 헤딩이 content에 포함되어야 한다"

    def test_single_section_includes_heading_in_content(self):
        """단일 섹션도 헤딩이 content에 포함되어야 한다."""
        md = "## API 설계 원칙\n\nREST API는 명사 기반 URL을 사용한다.\n"
        sections = _split_by_headers(md)
        parents = _make_parent_chunks(sections, "doc-001")
        assert len(parents) == 1
        assert "API 설계 원칙" in parents[0]["content"]


class TestMakeChildChunks:
    def test_child_type(self):
        parent = {
            "chunk_id": "parent-001",
            "doc_id": "test-doc",
            "chunk_type": "parent",
            "content": "첫 번째 문단.\n\n두 번째 문단.\n\n세 번째 문단.",
            "token_count": 50,
            "page_number": None,
            "section_header": "테스트",
        }
        children = _make_child_chunks(parent)
        assert all(c["chunk_type"] == "child" for c in children)

    def test_child_links_to_parent(self):
        parent = {
            "chunk_id": "parent-001",
            "doc_id": "test-doc",
            "chunk_type": "parent",
            "content": "문단 1.\n\n문단 2.\n\n문단 3.",
            "token_count": 30,
            "page_number": None,
            "section_header": None,
        }
        children = _make_child_chunks(parent)
        assert all(c["parent_chunk_id"] == "parent-001" for c in children)


class TestStage3Chunk:
    @pytest.mark.asyncio
    async def test_produces_parent_and_child_chunks(self):
        state = {
            "doc_id": "test-doc-001",
            "validated_markdown": SAMPLE_MARKDOWN,
        }
        result = await stage3_chunk(state)

        chunks = result["chunks"]
        assert chunks is not None
        assert len(chunks) > 0
        assert any(c["chunk_type"] == "parent" for c in chunks)
        assert any(c["chunk_type"] == "child" for c in chunks)

    @pytest.mark.asyncio
    async def test_empty_markdown_returns_failed(self):
        state = {
            "doc_id": "test-doc-002",
            "validated_markdown": "",
        }
        result = await stage3_chunk(state)

        assert result["status"] == "failed"
        assert result["chunks"] == []

    @pytest.mark.asyncio
    async def test_all_children_have_valid_parent(self):
        state = {
            "doc_id": "test-doc-003",
            "validated_markdown": SAMPLE_MARKDOWN,
        }
        result = await stage3_chunk(state)

        chunks = result["chunks"]
        parent_ids = {c["chunk_id"] for c in chunks if c["chunk_type"] == "parent"}
        children = [c for c in chunks if c["chunk_type"] == "child"]

        for child in children:
            assert child["parent_chunk_id"] in parent_ids, (
                f"Child {child['chunk_id']}의 parent_chunk_id {child['parent_chunk_id']}가 없음"
            )


# ---------------------------------------------------------------------------
# T5: tiktoken 인코더 lazy singleton (RED → GREEN)
# ---------------------------------------------------------------------------

class TestTiktokenSingleton:
    """
    _count_tokens()를 N회 호출해도 tiktoken.get_encoding()은 1회만 호출해야 한다.
    인코더 로드 비용(대용량 vocabulary 파일)이 청크마다 반복되면 안 된다.
    """

    def test_get_tiktoken_encoder_returns_singleton(self):
        """
        _get_tiktoken_encoder()는 두 번 호출해도 get_encoding을 한 번만 호출해야 한다.
        """
        import module_0_kms.pipeline.stage3_chunk as m
        original_enc = m._tiktoken_enc
        m._tiktoken_enc = None  # 싱글턴 리셋
        try:
            fake_enc = MagicMock()
            with patch("kms.pipeline.stage3_chunk.tiktoken") as mock_tiktoken:
                mock_tiktoken.get_encoding.return_value = fake_enc

                enc1 = _get_tiktoken_encoder()
                enc2 = _get_tiktoken_encoder()

            assert enc1 is enc2, "두 번 호출해도 같은 인코더여야 한다"
            assert mock_tiktoken.get_encoding.call_count == 1, (
                f"get_encoding이 {mock_tiktoken.get_encoding.call_count}회 호출됨 — 1회만 허용"
            )
        finally:
            m._tiktoken_enc = original_enc  # 이후 테스트 오염 방지

    def test_count_tokens_calls_get_encoding_once_for_multiple_texts(self):
        """
        _count_tokens()를 5회 호출해도 get_encoding은 1회만 호출되어야 한다 (N+1 방지).
        """
        import module_0_kms.pipeline.stage3_chunk as m
        original_enc = m._tiktoken_enc
        m._tiktoken_enc = None  # 싱글턴 리셋
        try:
            fake_enc = MagicMock()
            fake_enc.encode.return_value = [1, 2, 3]  # 3 tokens

            with patch("kms.pipeline.stage3_chunk.tiktoken") as mock_tiktoken:
                mock_tiktoken.get_encoding.return_value = fake_enc

                results = [_count_tokens(f"텍스트 {i}") for i in range(5)]

            assert mock_tiktoken.get_encoding.call_count == 1, (
                f"get_encoding이 {mock_tiktoken.get_encoding.call_count}회 호출됨 — 1회만 허용"
            )
            assert all(r == 3 for r in results), "모든 결과가 3 토큰이어야 한다"
        finally:
            m._tiktoken_enc = original_enc  # 이후 테스트 오염 방지


# ---------------------------------------------------------------------------
# T6: _hard_split 직접 테스트 (lines 164-204 커버)
# ---------------------------------------------------------------------------

class TestHardSplit:
    """_hard_split()은 max_tokens를 초과하는 텍스트를 강제로 분할한다."""

    def test_splits_text_exceeding_max_tokens(self):
        """max_tokens=100으로 500단어 텍스트를 분할 시 여러 청크가 생성돼야 한다."""
        large_text = " ".join(f"word{i}" for i in range(500))
        chunks = _hard_split(large_text, 100, "test-doc-id", "## Section")
        assert len(chunks) > 1
        assert all(c["chunk_type"] == "parent" for c in chunks)
        assert all(c["token_count"] <= 100 for c in chunks)

    def test_hard_split_preserves_doc_id(self):
        """모든 분할 청크가 동일한 doc_id를 가져야 한다."""
        large_text = " ".join(f"word{i}" for i in range(300))
        chunks = _hard_split(large_text, 50, "my-doc-id", "## Header")
        assert all(c["doc_id"] == "my-doc-id" for c in chunks)

    def test_hard_split_section_header_extracted(self):
        """헤더 마크다운 기호(##)가 제거된 제목이 section_header에 설정돼야 한다."""
        large_text = " ".join(f"word{i}" for i in range(300))
        chunks = _hard_split(large_text, 50, "doc-id", "## My Section")
        assert all(c["section_header"] == "My Section" for c in chunks)

    def test_hard_split_parent_chunk_id_is_none(self):
        """_hard_split()으로 생성된 청크의 parent_chunk_id는 None이어야 한다."""
        large_text = " ".join(f"word{i}" for i in range(200))
        chunks = _hard_split(large_text, 50, "doc-id", "## Header")
        assert all(c["parent_chunk_id"] is None for c in chunks)

    def test_short_text_returns_single_chunk(self):
        """max_tokens보다 짧은 텍스트는 1개의 청크로 반환돼야 한다."""
        short_text = "짧은 텍스트"
        chunks = _hard_split(short_text, 1000, "doc-id", "## Header")
        assert len(chunks) == 1


# ---------------------------------------------------------------------------
# T8: _split_sentences — 문장 경계 분할 (lines 162-204 개선)
# ---------------------------------------------------------------------------

class TestSplitSentences:
    """_split_sentences()는 텍스트를 문장 단위로 분리한다 (. ? ! 경계)."""

    def test_single_sentence_returns_one_element(self):
        """마침표 하나짜리 문장은 리스트 1개로 반환돼야 한다."""
        assert _split_sentences("하나의 문장입니다.") == ["하나의 문장입니다."]

    def test_two_sentences_separated_by_period_space(self):
        """'. ' 기준으로 두 문장이 분리돼야 한다."""
        result = _split_sentences("첫 문장. 두 번째 문장.")
        assert len(result) == 2
        assert result[0] == "첫 문장."
        assert result[1] == "두 번째 문장."

    def test_sentence_terminator_preserved_in_result(self):
        """분리된 각 문장에 마침표가 포함돼야 한다."""
        result = _split_sentences("문장 A. 문장 B.")
        assert all(s.endswith(".") for s in result)

    def test_question_mark_is_sentence_boundary(self):
        """'? ' 도 문장 경계로 인식돼야 한다."""
        result = _split_sentences("질문입니까? 답입니다.")
        assert len(result) == 2

    def test_exclamation_mark_is_sentence_boundary(self):
        """'! ' 도 문장 경계로 인식돼야 한다."""
        result = _split_sentences("주의! 위험합니다.")
        assert len(result) == 2

    def test_empty_string_returns_empty_list(self):
        """빈 문자열은 빈 리스트를 반환해야 한다."""
        assert _split_sentences("") == []

    def test_text_with_no_boundary_returns_single_element(self):
        """문장 경계가 없는 텍스트는 그대로 반환돼야 한다."""
        text = "경계가 없는 텍스트"
        result = _split_sentences(text)
        assert result == [text]

    def test_three_sentences_returns_three_elements(self):
        """세 문장 텍스트는 정확히 3개로 분리돼야 한다."""
        text = "문장 하나. 문장 둘. 문장 셋."
        result = _split_sentences(text)
        assert len(result) == 3


class TestHardSplitSentenceBoundary:
    """_hard_split()은 문장 경계를 우선 존중해 분할해야 한다."""

    def test_split_point_falls_at_sentence_boundary(self):
        """s1+s2 < max_tokens < s1+s2+s2_half 인 경우 첫 청크가 s1 전체(마침표 포함)가 돼야 한다."""
        s1 = "alpha beta gamma delta."
        s2 = "epsilon zeta eta theta."

        tokens_s1 = _count_tokens(s1)
        tokens_s2_half = _count_tokens("epsilon zeta")  # s2의 앞 절반
        max_tokens = tokens_s1 + tokens_s2_half  # s1은 들어가되 s1+s2 전체는 초과

        text = s1 + " " + s2
        chunks = _hard_split(text, max_tokens, "doc-id", "## Section")

        assert len(chunks) >= 2
        # 문장 경계 기반: 첫 청크 = s1 그대로
        # 단어 기반: 첫 청크 = s1 + s2의 일부 단어 (마침표로 안 끝남)
        assert chunks[0]["content"] == s1, (
            f"첫 청크가 문장 경계에서 끝나지 않음: '{chunks[0]['content']}'"
        )

    def test_first_chunk_ends_with_sentence_terminator(self):
        """분할 시 첫 청크(비마지막)가 문장 종결 기호로 끝나야 한다."""
        s1 = "sentence one ends here."
        s2 = "sentence two starts here."

        # max_tokens = s1 토큰 수 + s2 앞 2단어 — word-split은 중간에서 자름
        tokens_s1 = _count_tokens(s1)
        tokens_partial = _count_tokens("sentence two")
        max_tokens = tokens_s1 + tokens_partial

        text = f"{s1} {s2}"
        chunks = _hard_split(text, max_tokens, "doc-id", "## Header")

        assert len(chunks) >= 2
        assert chunks[0]["content"].rstrip().endswith("."), (
            f"첫 청크가 문장 경계에서 끝나지 않음: '{chunks[0]['content']}'"
        )

    def test_long_single_sentence_falls_back_to_word_split(self):
        """단일 문장이 max_tokens 초과 시 단어 단위 fallback으로 여러 청크가 생성돼야 한다."""
        long_sentence = " ".join(f"word{i}" for i in range(100)) + "."
        max_tokens = 10

        chunks = _hard_split(long_sentence, max_tokens, "doc-id", "## Section")

        assert len(chunks) > 1, "단일 긴 문장도 max_tokens 초과 시 분할돼야 한다"
        assert all(c["token_count"] <= max_tokens for c in chunks), (
            "모든 청크가 max_tokens 이하여야 한다"
        )

    def test_text_without_sentence_boundary_still_splits(self):
        """문장 경계 없는 텍스트(마침표 없음)도 정상 분할돼야 한다 (기존 동작 유지)."""
        large_text = " ".join(f"word{i}" for i in range(500))
        chunks = _hard_split(large_text, 100, "doc-id", "## Header")
        assert len(chunks) > 1
        assert all(c["token_count"] <= 100 for c in chunks)
