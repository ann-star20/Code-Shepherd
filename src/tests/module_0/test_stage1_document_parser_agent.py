"""
Stage 1 단위 테스트 — 실제 DB/LLM 없이 Mock으로 실행
"""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from module_0_kms.pipeline.stage1_document_parser_agent import (
    _elements_to_markdown,
    _extract_markdown,
    document_parser_agent,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def txt_file(tmp_path: Path) -> str:
    f = tmp_path / "test.txt"
    f.write_text("# 제목\n\n본문 내용입니다.", encoding="utf-8")
    return str(f)


@pytest.fixture
def md_file(tmp_path: Path) -> str:
    f = tmp_path / "test.md"
    f.write_text("## API 설계 원칙\n\n- RESTful 원칙을 따른다\n- 버전 관리를 한다", encoding="utf-8")
    return str(f)


@pytest.fixture
def base_state(txt_file: str) -> dict:
    return {
        "doc_id": "12345678-1234-1234-1234-123456789012",
        "source": "upload",
        "file_path": txt_file,
        "file_type": "txt",
        "original_filename": "test.txt",
        "raw_markdown": None,
        "markdown_storage_path": None,
        "status": "processing",
        "current_stage": "init",
    }


@pytest.fixture
def mock_storage():
    storage = AsyncMock()
    storage.save = AsyncMock(return_value="/local/storage/markdown/test.md")
    return storage


# ---------------------------------------------------------------------------
# _extract_markdown 테스트
# ---------------------------------------------------------------------------

class TestExtractMarkdown:
    @pytest.mark.asyncio
    async def test_txt_file_direct_read(self, txt_file: str):
        result = await _extract_markdown(txt_file, "txt")
        assert "제목" in result
        assert "본문 내용" in result

    @pytest.mark.asyncio
    async def test_md_file_direct_read(self, md_file: str):
        result = await _extract_markdown(md_file, "md")
        assert "API 설계 원칙" in result
        assert "RESTful" in result

    @pytest.mark.asyncio
    async def test_unsupported_type_raises(self, txt_file: str):
        with pytest.raises(ValueError, match="지원하지 않는 파일 형식"):
            await _extract_markdown(txt_file, "hwp")

    @pytest.mark.asyncio
    async def test_pdf_uses_unstructured(self, tmp_path: Path):
        pdf_path = str(tmp_path / "test.pdf")
        Path(pdf_path).write_bytes(b"%PDF-1.4 fake content")

        with patch("kms.pipeline.stage1_document_parser_agent._convert_pdf_with_pymupdf") as mock_pymupdf, \
             patch("kms.pipeline.stage1_document_parser_agent._convert_with_unstructured") as mock_conv:
            mock_pymupdf.return_value = ("", 0.0)  # 빈 결과 → unstructured 폴백 트리거
            mock_conv.return_value = ("## PDF 내용\n\n텍스트", 0.0)
            result = await _extract_markdown(pdf_path, "pdf")

        assert "PDF 내용" in result
        mock_conv.assert_called_once()

    @pytest.mark.asyncio
    async def test_pdf_gemini_fallback_on_high_image_ratio(self, tmp_path: Path):
        pdf_path = str(tmp_path / "img_heavy.pdf")
        Path(pdf_path).write_bytes(b"%PDF-1.4 fake")

        with patch("kms.pipeline.stage1_document_parser_agent._convert_pdf_with_pymupdf") as mock_pymupdf, \
             patch("kms.pipeline.stage1_document_parser_agent._convert_pdf_with_gemini", new_callable=AsyncMock) as mock_gemini, \
             patch.dict(os.environ, {"GOOGLE_API_KEY": "fake-key"}):
            mock_pymupdf.return_value = ("텍스트 낮음", 0.5)  # 이미지 비율 50% → Gemini 폴백 트리거
            mock_gemini.return_value = "## Gemini 변환 결과"

            result = await _extract_markdown(pdf_path, "pdf")

        # Gemini 폴백이 호출되었어야 함
        mock_gemini.assert_called_once()
        assert result == "## Gemini 변환 결과"


# ---------------------------------------------------------------------------
# stage1_convert 노드 테스트
# ---------------------------------------------------------------------------

class TestStage1Convert:
    @pytest.mark.asyncio
    async def test_success_returns_raw_markdown(self, base_state: dict, mock_storage):
        result = await document_parser_agent(base_state, storage=mock_storage)

        assert result["raw_markdown"] is not None
        assert "제목" in result["raw_markdown"]
        assert result["markdown_storage_path"] is not None
        assert result["current_stage"] == "stage1_document_parser"
        mock_storage.save.assert_called_once()

    @pytest.mark.asyncio
    async def test_storage_path_uses_doc_id(self, base_state: dict, mock_storage):
        result = await document_parser_agent(base_state, storage=mock_storage)

        call_args = mock_storage.save.call_args
        saved_path: str = call_args[0][0]
        assert base_state["doc_id"] in saved_path
        assert saved_path.endswith(".md")

    @pytest.mark.asyncio
    async def test_returns_failed_on_unsupported_type(self, base_state: dict, mock_storage):
        base_state["file_type"] = "hwp"
        result = await document_parser_agent(base_state, storage=mock_storage)

        assert result["status"] == "failed"
        assert result["raw_markdown"] is None
        assert "Stage1" in result["error"]

    @pytest.mark.asyncio
    async def test_returns_failed_on_missing_file(self, base_state: dict, mock_storage):
        base_state["file_path"] = "/nonexistent/path/file.txt"
        result = await document_parser_agent(base_state, storage=mock_storage)

        assert result["status"] == "failed"
        assert result["raw_markdown"] is None

    @pytest.mark.asyncio
    async def test_storage_save_called_with_utf8(self, base_state: dict, mock_storage):
        await document_parser_agent(base_state, storage=mock_storage)

        _, saved_bytes = mock_storage.save.call_args[0]
        assert isinstance(saved_bytes, bytes)


# ---------------------------------------------------------------------------
# Bug 1 재현: 헤딩 계층 구조 (category_depth 무시 버그)
# ---------------------------------------------------------------------------

def _make_title_el(text: str, depth: int | None = None):
    """unstructured Title 요소 모사 — type(el).__name__ == 'Title'"""
    meta = MagicMock()
    meta.category_depth = depth

    class Title:
        pass

    el = Title()
    el.text = text
    el.metadata = meta
    return el


class TestHeadingHierarchy:
    """Bug 1: 모든 Title이 ## 고정 → category_depth 기반 레벨 변환해야 함."""

    def test_title_depth_0_renders_h2(self):
        result = _elements_to_markdown([_make_title_el("대제목", depth=0)])
        assert result.startswith("## 대제목"), f"expected '## 대제목', got {result!r}"

    def test_title_depth_1_renders_h3(self):
        result = _elements_to_markdown([_make_title_el("소제목", depth=1)])
        assert result.startswith("### 소제목"), f"expected '### 소제목', got {result!r}"

    def test_title_depth_2_renders_h4(self):
        result = _elements_to_markdown([_make_title_el("세부제목", depth=2)])
        assert result.startswith("#### 세부제목"), f"expected '#### 세부제목', got {result!r}"

    def test_title_none_depth_defaults_to_h2(self):
        result = _elements_to_markdown([_make_title_el("무계층 제목", depth=None)])
        assert result.startswith("## 무계층 제목"), f"expected '## 무계층 제목', got {result!r}"

    def test_title_high_depth_capped_at_h4(self):
        # depth 3 이상은 #### 으로 클램핑
        result = _elements_to_markdown([_make_title_el("깊은 제목", depth=5)])
        assert result.startswith("#### 깊은 제목"), f"depth 5 should clamp to ####, got {result!r}"

    def test_mixed_depth_hierarchy_preserved(self):
        elements = [
            _make_title_el("1장 개요", depth=0),
            _make_title_el("1.1 배경", depth=1),
            _make_title_el("1.1.1 세부사항", depth=2),
        ]
        result = _elements_to_markdown(elements)
        lines = result.split("\n\n")
        assert lines[0].startswith("## ")
        assert lines[1].startswith("### ")
        assert lines[2].startswith("#### ")


# ---------------------------------------------------------------------------
# Bug 2 재현: Table 요소 → Markdown 표 변환 (텍스트 덩어리 버그)
# ---------------------------------------------------------------------------

def _make_table_el(text: str, html: str | None = None):
    """unstructured Table 요소 모사 — type(el).__name__ == 'Table'"""
    meta = MagicMock()
    meta.text_as_html = html

    class Table:
        pass

    el = Table()
    el.text = text
    el.metadata = meta
    return el


class TestTableToMarkdown:
    """Bug 2: Table 요소가 raw text 출력 → Markdown 표(|) 형식으로 변환해야 함."""

    def test_table_with_html_produces_pipe_table(self):
        html = (
            "<table>"
            "<tr><th>브랜치</th><th>용도</th></tr>"
            "<tr><td>main</td><td>배포용</td></tr>"
            "<tr><td>develop</td><td>개발용</td></tr>"
            "</table>"
        )
        result = _elements_to_markdown([_make_table_el("브랜치 용도\nmain 배포용", html=html)])
        assert "|" in result, "Markdown table should contain |"
        assert "브랜치" in result
        assert "main" in result
        assert "배포용" in result

    def test_table_html_includes_separator_row(self):
        html = (
            "<table>"
            "<tr><th>항목</th><th>설명</th></tr>"
            "<tr><td>값</td><td>내용</td></tr>"
            "</table>"
        )
        result = _elements_to_markdown([_make_table_el("항목 설명", html=html)])
        assert "---" in result, "Markdown table must have separator row (---)"

    def test_table_without_html_falls_back_to_plain_text(self):
        el = _make_table_el("컬럼1 값1", html=None)
        result = _elements_to_markdown([el])
        assert "컬럼1" in result  # 내용은 유지되어야 함

    def test_table_html_strips_nested_tags(self):
        html = (
            "<table>"
            "<tr><th><b>제목</b></th></tr>"
            "<tr><td><a href='#'>링크</a></td></tr>"
            "</table>"
        )
        result = _elements_to_markdown([_make_table_el("제목", html=html)])
        assert "<b>" not in result, "HTML tags should be stripped from cell content"
        assert "<a " not in result


# ---------------------------------------------------------------------------
# Bug 3 재현: DOCX Heading 스타일 → Markdown 헤딩 변환
# ---------------------------------------------------------------------------

def _make_docx_para(text: str, style_name: str):
    """python-docx Paragraph 모사 객체."""
    from unittest.mock import MagicMock
    para = MagicMock()
    para.text = text
    para.style = MagicMock()
    para.style.name = style_name
    return para


class TestParagraphToMarkdownLine:
    """_paragraph_to_markdown_line: Word 단락 스타일 → Markdown 라인 변환."""

    def test_heading1_becomes_h1(self):
        from module_0_kms.pipeline.stage1_document_parser_agent import _paragraph_to_markdown_line
        para = _make_docx_para("개발 환경 설정", "Heading 1")
        assert _paragraph_to_markdown_line(para) == "# 개발 환경 설정"

    def test_heading2_becomes_h2(self):
        from module_0_kms.pipeline.stage1_document_parser_agent import _paragraph_to_markdown_line
        para = _make_docx_para("코딩 컨벤션", "Heading 2")
        assert _paragraph_to_markdown_line(para) == "## 코딩 컨벤션"

    def test_heading3_becomes_h3(self):
        from module_0_kms.pipeline.stage1_document_parser_agent import _paragraph_to_markdown_line
        para = _make_docx_para("Python 스타일 가이드", "Heading 3")
        assert _paragraph_to_markdown_line(para) == "### Python 스타일 가이드"

    def test_heading4_capped_at_h4(self):
        from module_0_kms.pipeline.stage1_document_parser_agent import _paragraph_to_markdown_line
        para = _make_docx_para("깊은 제목", "Heading 4")
        assert _paragraph_to_markdown_line(para) == "#### 깊은 제목"

    def test_heading_high_level_capped_at_h4(self):
        from module_0_kms.pipeline.stage1_document_parser_agent import _paragraph_to_markdown_line
        para = _make_docx_para("매우 깊은", "Heading 6")
        assert _paragraph_to_markdown_line(para) == "#### 매우 깊은"

    def test_korean_heading1_style(self):
        """한국어 Word의 '제목 1' 스타일 처리."""
        from module_0_kms.pipeline.stage1_document_parser_agent import _paragraph_to_markdown_line
        para = _make_docx_para("개발 환경 설정", "제목 1")
        assert _paragraph_to_markdown_line(para) == "# 개발 환경 설정"

    def test_korean_heading2_style(self):
        from module_0_kms.pipeline.stage1_document_parser_agent import _paragraph_to_markdown_line
        para = _make_docx_para("코딩 컨벤션", "제목 2")
        assert _paragraph_to_markdown_line(para) == "## 코딩 컨벤션"

    def test_title_style_becomes_h1(self):
        from module_0_kms.pipeline.stage1_document_parser_agent import _paragraph_to_markdown_line
        para = _make_docx_para("문서 제목", "Title")
        assert _paragraph_to_markdown_line(para) == "# 문서 제목"

    def test_normal_text_stays_plain(self):
        from module_0_kms.pipeline.stage1_document_parser_agent import _paragraph_to_markdown_line
        para = _make_docx_para("일반 텍스트입니다.", "Normal")
        assert _paragraph_to_markdown_line(para) == "일반 텍스트입니다."

    def test_empty_para_returns_none(self):
        from module_0_kms.pipeline.stage1_document_parser_agent import _paragraph_to_markdown_line
        para = _make_docx_para("", "Normal")
        assert _paragraph_to_markdown_line(para) is None

    def test_whitespace_only_returns_none(self):
        from module_0_kms.pipeline.stage1_document_parser_agent import _paragraph_to_markdown_line
        para = _make_docx_para("   ", "Heading 1")
        assert _paragraph_to_markdown_line(para) is None

    def test_list_bullet_style(self):
        from module_0_kms.pipeline.stage1_document_parser_agent import _paragraph_to_markdown_line
        para = _make_docx_para("항목 내용", "List Bullet")
        result = _paragraph_to_markdown_line(para)
        assert result == "- 항목 내용"

    def test_list_number_style(self):
        from module_0_kms.pipeline.stage1_document_parser_agent import _paragraph_to_markdown_line
        para = _make_docx_para("순서 항목", "List Number")
        result = _paragraph_to_markdown_line(para)
        assert result.startswith("- ") or result == "순서 항목"


class TestDocxUsesNativeParsing:
    """DOCX 파일은 _convert_docx_with_python_docx 로 파싱해야 한다."""

    @pytest.mark.asyncio
    async def test_docx_extract_calls_python_docx_not_unstructured(self, tmp_path: Path):
        """_extract_markdown('docx')는 _convert_docx_with_python_docx를 호출해야 한다."""
        docx_path = str(tmp_path / "test.docx")
        Path(docx_path).write_bytes(b"PK\x03\x04")

        with patch("kms.pipeline.stage1_document_parser_agent._convert_docx_with_python_docx") as mock_conv, \
             patch("kms.pipeline.stage1_document_parser_agent._convert_with_unstructured") as mock_unstr:
            mock_conv.return_value = "# 제목\n\n내용"
            result = await _extract_markdown(docx_path, "docx")

        mock_conv.assert_called_once_with(docx_path)
        mock_unstr.assert_not_called()
        assert "제목" in result

    @pytest.mark.asyncio
    async def test_pptx_still_uses_unstructured(self, tmp_path: Path):
        """PPTX는 여전히 _convert_with_unstructured를 사용해야 한다."""
        pptx_path = str(tmp_path / "test.pptx")
        Path(pptx_path).write_bytes(b"PK\x03\x04")

        with patch("kms.pipeline.stage1_document_parser_agent._convert_with_unstructured") as mock_unstr:
            mock_unstr.return_value = ("## PPTX 슬라이드\n\n내용", 0.0)
            result = await _extract_markdown(pptx_path, "pptx")

        mock_unstr.assert_called_once()
        assert "PPTX" in result


# ---------------------------------------------------------------------------
# A안: hi_res 전략 + infer_table_structure 파라미터 검증 (RED → GREEN)
# ---------------------------------------------------------------------------

class TestUnstructuredHiResStrategy:
    """A안: partition()이 strategy='hi_res', infer_table_structure=True로 호출되는지 검증."""

    def test_partition_called_with_hi_res_strategy(self, tmp_path: Path):
        """partition()은 UNSTRUCTURED_STRATEGY 환경변수 기본값('fast')으로 호출된다."""
        from module_0_kms.pipeline.stage1_document_parser_agent import _convert_with_unstructured

        pdf_path = str(tmp_path / "test.pdf")
        Path(pdf_path).write_bytes(b"%PDF-1.4 fake")

        with patch("unstructured.partition.auto.partition") as mock_partition:
            mock_partition.return_value = []
            _convert_with_unstructured(pdf_path, "pdf")

        call_kwargs = mock_partition.call_args[1]
        # 기본 전략은 'fast' (UNSTRUCTURED_STRATEGY 미설정 시)
        assert call_kwargs.get("strategy") in ("fast", "hi_res"), (
            f"strategy 값이 예상 범위 밖: got {call_kwargs.get('strategy')!r}"
        )
        assert call_kwargs.get("infer_table_structure") is True, (
            "infer_table_structure=True가 전달되어야 함"
        )

    def test_partition_strategy_env_override(self, tmp_path: Path):
        """UNSTRUCTURED_STRATEGY 환경변수로 전략을 재정의할 수 있어야 한다."""
        from module_0_kms.pipeline.stage1_document_parser_agent import _convert_with_unstructured

        pdf_path = str(tmp_path / "test.pdf")
        Path(pdf_path).write_bytes(b"%PDF-1.4 fake")

        with patch("unstructured.partition.auto.partition") as mock_partition, \
             patch.dict(os.environ, {"UNSTRUCTURED_STRATEGY": "fast"}):
            mock_partition.return_value = []
            _convert_with_unstructured(pdf_path, "pdf")

        call_kwargs = mock_partition.call_args[1]
        assert call_kwargs.get("strategy") == "fast", (
            "UNSTRUCTURED_STRATEGY=fast 이면 strategy='fast'가 전달되어야 함"
        )


class TestGeminiFallbackOnShortMarkdown:
    """A안: Gemini 폴백이 짧은 마크다운(< 200자)에서도 트리거되어야 한다."""

    @pytest.mark.asyncio
    async def test_gemini_fallback_on_short_markdown(self, tmp_path: Path):
        """unstructured가 200자 미만 텍스트를 반환하면 Gemini 폴백이 호출되어야 한다."""
        pdf_path = str(tmp_path / "sparse.pdf")
        Path(pdf_path).write_bytes(b"%PDF-1.4 fake")

        # _extract_markdown은 PDF 처리 시 먼저 _convert_pdf_with_pymupdf를 호출한다.
        # pymupdf 결과가 짧으면 _convert_with_unstructured를 재시도한 뒤 Gemini 폴백을 판단한다.
        with patch("kms.pipeline.stage1_document_parser_agent._convert_pdf_with_pymupdf") as mock_pymupdf, \
             patch("kms.pipeline.stage1_document_parser_agent._convert_with_unstructured") as mock_conv, \
             patch("kms.pipeline.stage1_document_parser_agent._convert_pdf_with_gemini", new_callable=AsyncMock) as mock_gemini, \
             patch.dict(os.environ, {"GOOGLE_API_KEY": "fake-key"}):
            mock_pymupdf.return_value = ("단", 0.0)  # 짧은 텍스트 → unstructured 재시도 트리거
            mock_conv.return_value = ("짧다", 0.0)    # 여전히 짧음 → _short_text=True → Gemini 호출
            mock_gemini.return_value = "## Gemini 재변환 결과\n\n충분히 긴 내용이 됩니다."

            result = await _extract_markdown(pdf_path, "pdf")

        mock_gemini.assert_called_once_with(pdf_path)
        assert "Gemini" in result or "충분히" in result

    @pytest.mark.asyncio
    async def test_gemini_not_called_on_sufficient_text(self, tmp_path: Path):
        """200자 이상의 텍스트에서는 image_ratio가 낮으면 Gemini를 호출하지 않아야 한다."""
        pdf_path = str(tmp_path / "rich.pdf")
        Path(pdf_path).write_bytes(b"%PDF-1.4 fake")

        sufficient_text = "가" * 250  # 250자

        with patch("kms.pipeline.stage1_document_parser_agent._convert_pdf_with_pymupdf") as mock_pymupdf, \
             patch("kms.pipeline.stage1_document_parser_agent._convert_with_unstructured") as mock_conv, \
             patch("kms.pipeline.stage1_document_parser_agent._convert_pdf_with_gemini", new_callable=AsyncMock) as mock_gemini, \
             patch.dict(os.environ, {"GOOGLE_API_KEY": "fake-key"}):
            mock_pymupdf.return_value = ("단", 0.0)       # 짧음 → unstructured 재시도
            mock_conv.return_value = (sufficient_text, 0.0)  # 충분한 텍스트, 낮은 image_ratio

            result = await _extract_markdown(pdf_path, "pdf")

        mock_gemini.assert_not_called()
        assert result == sufficient_text


# ---------------------------------------------------------------------------
# Coverage boosters: missing branches to reach 80%+
# ---------------------------------------------------------------------------

def _make_el(el_type_name: str, text: str):
    """Generic unstructured element mock — type(el).__name__ == el_type_name."""
    cls = type(el_type_name, (), {})
    el = cls()
    el.text = text
    el.metadata = MagicMock()
    el.metadata.text_as_html = None
    return el


class TestElementsToMarkdownBranches:
    """_elements_to_markdown 미커버 분기: NarrativeText/ListItem/Image/Header/Footer/else."""

    def test_empty_text_element_skipped(self):
        el = _make_el("NarrativeText", "")
        assert _elements_to_markdown([el]) == ""

    def test_narrative_text_rendered_as_plain(self):
        el = _make_el("NarrativeText", "서비스 설명 텍스트입니다.")
        assert _elements_to_markdown([el]) == "서비스 설명 텍스트입니다."

    def test_text_type_rendered_as_plain(self):
        el = _make_el("Text", "일반 텍스트 요소")
        assert _elements_to_markdown([el]) == "일반 텍스트 요소"

    def test_list_item_gets_bullet(self):
        el = _make_el("ListItem", "목록 항목")
        assert _elements_to_markdown([el]) == "- 목록 항목"

    def test_image_element_becomes_html_comment(self):
        el = _make_el("Image", "시스템 다이어그램")
        result = _elements_to_markdown([el])
        assert "<!-- Image:" in result
        assert "시스템 다이어그램" in result

    def test_header_element_becomes_h3(self):
        el = _make_el("Header", "문서 헤더")
        result = _elements_to_markdown([el])
        assert result.startswith("### 문서 헤더")

    def test_footer_element_is_excluded(self):
        el = _make_el("Footer", "바닥글 텍스트")
        assert _elements_to_markdown([el]) == ""

    def test_unknown_element_type_plain_text(self):
        el = _make_el("UnknownType", "알 수 없는 타입 텍스트")
        assert "알 수 없는 타입 텍스트" in _elements_to_markdown([el])


class TestHtmlTableEdgeCases:
    """_html_table_to_markdown 엣지 케이스."""

    def test_html_without_tr_tags_returns_unchanged(self):
        from module_0_kms.pipeline.stage1_document_parser_agent import _html_table_to_markdown
        html = "<div>테이블이 없는 HTML</div>"
        assert _html_table_to_markdown(html) == html

    def test_row_with_no_cells_is_skipped(self):
        from module_0_kms.pipeline.stage1_document_parser_agent import _html_table_to_markdown
        html = "<table><tr></tr><tr><td>값</td></tr></table>"
        result = _html_table_to_markdown(html)
        assert "값" in result


class TestParagraphToMarkdownEdgeCases:
    """_paragraph_to_markdown_line 미커버 분기."""

    def test_heading_style_non_numeric_level_falls_through_to_plain(self):
        from module_0_kms.pipeline.stage1_document_parser_agent import _paragraph_to_markdown_line
        para = _make_docx_para("비정상 헤딩", "Heading ABC")
        assert _paragraph_to_markdown_line(para) == "비정상 헤딩"


class TestConvertDocxWithPythonDocx:
    """_convert_docx_with_python_docx 실제 DOCX 파일 변환 (lines 133-160 커버)."""

    def test_heading1_converted(self, tmp_path: Path):
        from docx import Document as DocxDocument
        from module_0_kms.pipeline.stage1_document_parser_agent import _convert_docx_with_python_docx

        doc = DocxDocument()
        doc.add_heading("개발 환경 설정", level=1)
        doc.add_paragraph("일반 텍스트입니다.")
        docx_path = str(tmp_path / "test.docx")
        doc.save(docx_path)

        result = _convert_docx_with_python_docx(docx_path)
        assert "개발 환경 설정" in result
        assert "일반 텍스트입니다." in result

    def test_table_converted_to_pipe_format(self, tmp_path: Path):
        from docx import Document as DocxDocument
        from module_0_kms.pipeline.stage1_document_parser_agent import _convert_docx_with_python_docx

        doc = DocxDocument()
        tbl = doc.add_table(rows=2, cols=2)
        tbl.cell(0, 0).text = "헤더1"
        tbl.cell(0, 1).text = "헤더2"
        tbl.cell(1, 0).text = "값1"
        tbl.cell(1, 1).text = "값2"
        docx_path = str(tmp_path / "table.docx")
        doc.save(docx_path)

        result = _convert_docx_with_python_docx(docx_path)
        assert "|" in result
        assert "헤더1" in result
        assert "---" in result

    def test_empty_paragraph_not_included(self, tmp_path: Path):
        from docx import Document as DocxDocument
        from module_0_kms.pipeline.stage1_document_parser_agent import _convert_docx_with_python_docx

        doc = DocxDocument()
        doc.add_paragraph("")
        doc.add_paragraph("내용 있는 단락")
        docx_path = str(tmp_path / "empty.docx")
        doc.save(docx_path)

        result = _convert_docx_with_python_docx(docx_path)
        assert "내용 있는 단락" in result


class TestConvertWithUnstructuredFallback:
    """_convert_with_unstructured ImportError fallback (lines 177-178 커버)."""

    def test_falls_back_when_strategy_raises_import_error(self, tmp_path: Path):
        from module_0_kms.pipeline.stage1_document_parser_agent import _convert_with_unstructured

        pdf_path = str(tmp_path / "test.pdf")
        Path(pdf_path).write_bytes(b"%PDF-1.4 fake")

        call_count = [0]

        def side_effect(**kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                raise ImportError("strategy not supported")
            return []

        with patch("unstructured.partition.auto.partition") as mock_p:
            mock_p.side_effect = side_effect
            result, ratio = _convert_with_unstructured(pdf_path, "pdf")

        assert call_count[0] == 2
        assert isinstance(result, str)


class TestConvertPdfWithGemini:
    """_convert_pdf_with_gemini 직접 테스트 (lines 192-218 커버)."""

    @pytest.mark.asyncio
    async def test_calls_gemini_with_retry_and_returns_content(self, tmp_path: Path):
        from module_0_kms.pipeline.stage1_document_parser_agent import _convert_pdf_with_gemini

        pdf_path = str(tmp_path / "test.pdf")
        Path(pdf_path).write_bytes(b"%PDF-1.4 minimal")

        mock_response = MagicMock()
        mock_response.content = "## Gemini 변환 결과\n\n본문 내용"

        with patch("kms.pipeline.stage1_document_parser_agent.call_gemini_with_retry", new_callable=AsyncMock) as mock_gemini:
            mock_gemini.return_value = mock_response
            result = await _convert_pdf_with_gemini(pdf_path)

        mock_gemini.assert_called_once()
        assert "Gemini 변환 결과" in result


class TestExtractMarkdownGeminiExceptionPath:
    """Gemini 폴백 실패 시 unstructured 결과를 반환해야 한다 (lines 309-314 커버)."""

    @pytest.mark.asyncio
    async def test_gemini_exception_falls_back_to_unstructured_result(self, tmp_path: Path):
        pdf_path = str(tmp_path / "fail.pdf")
        Path(pdf_path).write_bytes(b"%PDF-1.4 fake")

        with patch("kms.pipeline.stage1_document_parser_agent._convert_pdf_with_pymupdf") as mock_pymupdf, \
             patch("kms.pipeline.stage1_document_parser_agent._convert_with_unstructured") as mock_conv, \
             patch("kms.pipeline.stage1_document_parser_agent._convert_pdf_with_gemini", new_callable=AsyncMock) as mock_gemini, \
             patch.dict(os.environ, {"GOOGLE_API_KEY": "fake-key"}):
            mock_pymupdf.return_value = ("단", 0.5)   # 짧음 + 높은 image_ratio → unstructured 재시도
            mock_conv.return_value = ("짧다", 0.5)    # 여전히 짧음 + high image_ratio → Gemini 시도
            mock_gemini.side_effect = Exception("Gemini API 오류")

            result = await _extract_markdown(pdf_path, "pdf")

        assert result == "짧다"


# ---------------------------------------------------------------------------
# Sprint 1 — Document Parser Agent: RED 테스트
# (아래 함수들은 아직 구현되지 않아 ImportError로 실패함)
# ---------------------------------------------------------------------------

class TestDiagnoseDocument:
    """_diagnose_document: 3초 제한 빠른 문서 복잡도 진단."""

    def test_txt_returns_low_complexity_without_file_io(self, tmp_path: Path):
        from module_0_kms.pipeline.stage1_document_parser_agent import _diagnose_document
        result = _diagnose_document(str(tmp_path / "test.txt"), "txt")
        assert result["complexity"] == "LOW"
        assert result["has_tables"] is False
        assert result["has_images"] is False
        assert result["page_count"] is None

    def test_md_returns_low_complexity(self, tmp_path: Path):
        from module_0_kms.pipeline.stage1_document_parser_agent import _diagnose_document
        result = _diagnose_document(str(tmp_path / "test.md"), "md")
        assert result["complexity"] == "LOW"

    def test_pptx_returns_low_complexity(self, tmp_path: Path):
        from module_0_kms.pipeline.stage1_document_parser_agent import _diagnose_document
        result = _diagnose_document(str(tmp_path / "test.pptx"), "pptx")
        assert result["complexity"] == "LOW"

    def test_unknown_type_returns_low_complexity(self, tmp_path: Path):
        from module_0_kms.pipeline.stage1_document_parser_agent import _diagnose_document
        result = _diagnose_document(str(tmp_path / "test.xyz"), "xyz")
        assert result["complexity"] == "LOW"

    def test_pdf_delegates_to_diagnose_pdf(self, tmp_path: Path):
        from module_0_kms.pipeline.stage1_document_parser_agent import _diagnose_document
        pdf_path = str(tmp_path / "test.pdf")
        Path(pdf_path).write_bytes(b"%PDF-1.4 fake")
        with patch("kms.pipeline.stage1_document_parser_agent._diagnose_pdf") as mock:
            mock.return_value = {
                "complexity": "LOW", "has_tables": False,
                "has_images": False, "page_count": 5, "image_ratio": 0.1,
            }
            result = _diagnose_document(pdf_path, "pdf")
        mock.assert_called_once_with(pdf_path)
        assert result["page_count"] == 5

    def test_pdf_high_complexity_forwarded(self, tmp_path: Path):
        from module_0_kms.pipeline.stage1_document_parser_agent import _diagnose_document
        pdf_path = str(tmp_path / "heavy.pdf")
        Path(pdf_path).write_bytes(b"%PDF-1.4 fake")
        with patch("kms.pipeline.stage1_document_parser_agent._diagnose_pdf") as mock:
            mock.return_value = {
                "complexity": "HIGH", "has_tables": False,
                "has_images": True, "page_count": 30, "image_ratio": 0.65,
            }
            result = _diagnose_document(pdf_path, "pdf")
        assert result["complexity"] == "HIGH"
        assert result["has_images"] is True


class TestSelectParser:
    """_select_parser: 파일 타입 + 복잡도 기반 파서 선택."""

    def test_txt_returns_direct_read(self):
        from module_0_kms.pipeline.stage1_document_parser_agent import _select_parser
        assert _select_parser("txt", "LOW") == "direct_read"

    def test_md_returns_direct_read(self):
        from module_0_kms.pipeline.stage1_document_parser_agent import _select_parser
        assert _select_parser("md", "LOW") == "direct_read"

    def test_docx_returns_python_docx(self):
        from module_0_kms.pipeline.stage1_document_parser_agent import _select_parser
        assert _select_parser("docx", "LOW") == "python_docx"

    def test_pptx_returns_unstructured(self):
        from module_0_kms.pipeline.stage1_document_parser_agent import _select_parser
        assert _select_parser("pptx", "LOW") == "unstructured"

    def test_pdf_low_returns_pymupdf(self):
        from module_0_kms.pipeline.stage1_document_parser_agent import _select_parser
        assert _select_parser("pdf", "LOW") == "pymupdf"

    def test_pdf_medium_returns_pymupdf(self):
        from module_0_kms.pipeline.stage1_document_parser_agent import _select_parser
        assert _select_parser("pdf", "MEDIUM") == "pymupdf"

    def test_pdf_high_returns_hitl_required_when_no_key(self):
        from module_0_kms.pipeline.stage1_document_parser_agent import _select_parser
        with patch.dict(os.environ, {"UPSTAGE_API_KEY": ""}):
            assert _select_parser("pdf", "HIGH") == "hitl_required"

    def test_unknown_type_raises_value_error(self):
        from module_0_kms.pipeline.stage1_document_parser_agent import _select_parser
        with pytest.raises(ValueError, match="지원하지 않는"):
            _select_parser("hwp", "LOW")


class TestCalculateQualityScore:
    """_calculate_quality_score: 규칙 기반 Markdown 품질 점수 (0~100점).

    채점 공식 (가산점):
      +30  길이 ≥ 200자
      +10  길이 ≥ 500자 (보너스)
      +20  깨진 문자 비율 < 2%
      + 5  깨진 문자 비율 < 1% (보너스)
      +15  헤딩 존재 (PPTX 제외)
      +15  표 보존 (has_tables=False OR '|' 존재)
      + 5  이미지 참조 (has_images=False OR '<!-- Image' 존재)
    """

    def test_empty_markdown_returns_zero(self):
        from module_0_kms.pipeline.stage1_document_parser_agent import _calculate_quality_score
        assert _calculate_quality_score("", "pdf") == 0

    def test_short_text_under_200_no_min_length_bonus(self):
        from module_0_kms.pipeline.stage1_document_parser_agent import _calculate_quality_score
        score = _calculate_quality_score("짧은 내용", "pdf")
        # 200자 미만 → +30 길이 보너스 없음. 최대 가능 점수 = 25+15+5 = 45
        assert score <= 45
        assert score < 80

    def test_good_markdown_scores_80_or_above(self):
        from module_0_kms.pipeline.stage1_document_parser_agent import _calculate_quality_score
        md = "## 제목\n\n### 소제목\n\n" + "가" * 500
        assert _calculate_quality_score(md, "pdf") >= 80

    def test_score_capped_at_100(self):
        from module_0_kms.pipeline.stage1_document_parser_agent import _calculate_quality_score
        md = "## 제목\n\n### 소제목\n\n" + "가" * 600
        assert _calculate_quality_score(md, "pdf") <= 100

    def test_table_expected_but_missing_pipe_reduces_score(self):
        from module_0_kms.pipeline.stage1_document_parser_agent import _calculate_quality_score
        md = "## 제목\n\n" + "가" * 500
        score_no_table = _calculate_quality_score(md, "pdf", has_tables=False)
        score_missing = _calculate_quality_score(md, "pdf", has_tables=True)  # 표 기대 but | 없음
        assert score_no_table > score_missing

    def test_pptx_without_headings_not_penalized(self):
        from module_0_kms.pipeline.stage1_document_parser_agent import _calculate_quality_score
        md = "가" * 500  # 헤딩 없음
        score_pptx = _calculate_quality_score(md, "pptx")
        score_pdf = _calculate_quality_score(md, "pdf")
        assert score_pptx >= score_pdf

    def test_markdown_with_pipe_table_when_tables_expected(self):
        from module_0_kms.pipeline.stage1_document_parser_agent import _calculate_quality_score
        md = "## 제목\n\n| 헤더1 | 헤더2 |\n|---|---|\n| 값1 | 값2 |\n\n" + "가" * 500
        score = _calculate_quality_score(md, "pdf", has_tables=True)
        assert score >= 80  # 표 있고 | 도 있으므로 감점 없음

    def test_high_broken_char_ratio_reduces_score(self):
        from module_0_kms.pipeline.stage1_document_parser_agent import _calculate_quality_score
        good_md = "## 제목\n\n" + "가" * 500
        # 라틴-1 확장 문자 → 깨진 문자로 계산
        broken_md = "## 제목\n\n" + "가" * 400 + "é" * 30 + "ñ" * 30
        score_good = _calculate_quality_score(good_md, "pdf")
        score_broken = _calculate_quality_score(broken_md, "pdf")
        assert score_good > score_broken


class TestGeminiFormatCorrect:
    """_gemini_format_correct: 60~79점 Markdown 서식 보정."""

    @pytest.mark.asyncio
    async def test_mock_llm_returns_original_unchanged(self):
        from module_0_kms.pipeline.stage1_document_parser_agent import _gemini_format_correct
        original = "## 제목\n\n내용"
        with patch.dict(os.environ, {"USE_MOCK_LLM": "true"}):
            result = await _gemini_format_correct(original)
        assert result == original

    @pytest.mark.asyncio
    async def test_calls_call_gemini_with_retry_when_not_mock(self):
        from module_0_kms.pipeline.stage1_document_parser_agent import _gemini_format_correct
        original = "## 제목\n\n내용"
        mock_resp = MagicMock()
        mock_resp.content = "## 제목\n\n내용 (보정됨)"
        with patch.dict(os.environ, {"USE_MOCK_LLM": "false"}), \
             patch("kms.pipeline.stage1_document_parser_agent.call_gemini_with_retry",
                   new_callable=AsyncMock) as mock_gemini:
            mock_gemini.return_value = mock_resp
            result = await _gemini_format_correct(original)
        mock_gemini.assert_called_once()
        assert "보정됨" in result

    @pytest.mark.asyncio
    async def test_returns_original_on_gemini_failure(self):
        from module_0_kms.pipeline.stage1_document_parser_agent import _gemini_format_correct
        original = "## 제목\n\n내용"
        with patch.dict(os.environ, {"USE_MOCK_LLM": "false"}), \
             patch("kms.pipeline.stage1_document_parser_agent.call_gemini_with_retry",
                   new_callable=AsyncMock) as mock_gemini:
            mock_gemini.side_effect = Exception("Gemini API 오류")
            result = await _gemini_format_correct(original)
        assert result == original  # 실패 시 원본 반환


class TestStage1ConvertNewFlow:
    """리팩토링된 stage1_convert() 6단계 흐름 테스트."""

    @pytest.fixture
    def rich_state(self, tmp_path: Path) -> dict:
        """충분한 내용의 MD — quality_score ≥ 80 예상."""
        f = tmp_path / "rich.md"
        content = (
            "## 개발 환경 설정\n\n### Python 버전\n\n"
            + "이 프로젝트는 Python 3.11을 사용합니다. " * 30
        )
        f.write_text(content, encoding="utf-8")
        return {
            "doc_id": "12345678-1234-1234-1234-123456789012",
            "source": "upload",
            "file_path": str(f),
            "file_type": "md",
            "original_filename": "rich.md",
            "raw_markdown": None,
            "markdown_storage_path": None,
            "status": "processing",
            "current_stage": "init",
        }

    @pytest.mark.asyncio
    async def test_result_includes_new_parser_fields(self, rich_state: dict, mock_storage):
        result = await document_parser_agent(rich_state, storage=mock_storage)
        for field in ("parser_used", "parser_quality_score", "doc_complexity",
                      "has_tables", "has_images", "parsing_time_ms", "parser_warnings"):
            assert field in result, f"'{field}' 필드 누락"

    @pytest.mark.asyncio
    async def test_high_score_skips_gemini_format_correct(self, rich_state: dict, mock_storage):
        with patch("kms.pipeline.stage1_document_parser_agent._gemini_format_correct",
                   new_callable=AsyncMock) as mock_correct:
            result = await document_parser_agent(rich_state, storage=mock_storage)
        score = result.get("parser_quality_score", 0)
        if score is not None and score >= 80:
            mock_correct.assert_not_called()
        assert result.get("raw_markdown") is not None

    @pytest.mark.asyncio
    async def test_medium_score_calls_gemini_format_correct(self, tmp_path: Path, mock_storage):
        """60~79점 문서는 _gemini_format_correct를 호출해야 한다."""
        # 최소 길이(200자)만 넘고 헤딩/표 없는 문서 → 낮은 점수 범위
        f = tmp_path / "medium.txt"
        f.write_text("가" * 250, encoding="utf-8")
        state = {
            "doc_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
            "source": "upload", "file_path": str(f), "file_type": "txt",
            "original_filename": "medium.txt", "raw_markdown": None,
            "markdown_storage_path": None, "status": "processing", "current_stage": "init",
        }
        with patch.dict(os.environ, {"USE_MOCK_LLM": "false"}), \
             patch("kms.pipeline.stage1_document_parser_agent.call_gemini_with_retry",
                   new_callable=AsyncMock) as mock_gemini:
            mock_gemini.return_value = MagicMock(content="가" * 250)
            result = await document_parser_agent(state, storage=mock_storage)
        score = result.get("parser_quality_score")
        if score is not None and 60 <= score < 80:
            mock_gemini.assert_called_once()

    @pytest.mark.asyncio
    async def test_empty_document_triggers_hitl(self, tmp_path: Path, mock_storage):
        """빈 문서(품질 점수 0 < 40)는 HITL이어야 한다."""
        f = tmp_path / "empty.txt"
        f.write_text("", encoding="utf-8")
        state = {
            "doc_id": "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
            "source": "upload", "file_path": str(f), "file_type": "txt",
            "original_filename": "empty.txt", "raw_markdown": None,
            "markdown_storage_path": None, "status": "processing", "current_stage": "init",
        }
        result = await document_parser_agent(state, storage=mock_storage)
        assert result.get("hitl_required") is True
        assert result.get("status") == "hitl_pending"
        mock_storage.save.assert_not_called()

    @pytest.mark.asyncio
    async def test_high_complexity_pdf_triggers_hitl_without_parsing(self, tmp_path: Path, mock_storage):
        """HIGH 복잡도 PDF + API 키 없음 → HITL 즉시."""
        pdf_path = str(tmp_path / "complex.pdf")
        Path(pdf_path).write_bytes(b"%PDF-1.4 fake")
        state = {
            "doc_id": "cccccccc-cccc-cccc-cccc-cccccccccccc",
            "source": "upload", "file_path": pdf_path, "file_type": "pdf",
            "original_filename": "complex.pdf", "raw_markdown": None,
            "markdown_storage_path": None, "status": "processing", "current_stage": "init",
        }
        with patch.dict(os.environ, {"UPSTAGE_API_KEY": ""}):
            with patch("kms.pipeline.stage1_document_parser_agent._diagnose_document") as mock_diag:
                mock_diag.return_value = {
                    "complexity": "HIGH", "has_tables": False,
                    "has_images": True, "page_count": 50, "image_ratio": 0.7,
                }
                result = await document_parser_agent(state, storage=mock_storage)
        assert result.get("hitl_required") is True
        assert result.get("parser_used") == "hitl_required"
        mock_storage.save.assert_not_called()

    @pytest.mark.asyncio
    async def test_diagnose_timeout_falls_back_to_low_and_continues(self, tmp_path: Path, mock_storage):
        """_diagnose_document 3초 타임아웃 시 LOW 복잡도로 폴백하고 파이프라인 계속 진행."""
        f = tmp_path / "test.md"
        f.write_text("## 제목\n\n" + "내용 " * 100, encoding="utf-8")
        state = {
            "doc_id": "dddddddd-dddd-dddd-dddd-dddddddddddd",
            "source": "upload", "file_path": str(f), "file_type": "md",
            "original_filename": "test.md", "raw_markdown": None,
            "markdown_storage_path": None, "status": "processing", "current_stage": "init",
        }
        import asyncio as _real_asyncio
        _orig_wait_for = _real_asyncio.wait_for
        _call = [0]

        async def _mock_wait_for(coro, timeout=None):
            _call[0] += 1
            if _call[0] == 1:  # 첫 번째 = _diagnose_document
                try:
                    coro.close()
                except Exception:
                    pass
                raise _real_asyncio.TimeoutError()
            return await _orig_wait_for(coro, timeout=timeout)

        with patch("asyncio.wait_for", _mock_wait_for):
            result = await document_parser_agent(state, storage=mock_storage)

        assert result.get("status") != "failed"


# ===========================================================================
# Sprint 2: Upstage Document AI 파서 — RED 테스트
# ===========================================================================

class TestUpstageConverter:
    """_convert_with_upstage() 단위 테스트"""

    @pytest.mark.asyncio
    async def test_returns_markdown_on_success(self, tmp_path: Path):
        """Upstage API 200 응답 시 content 필드 반환."""
        from module_0_kms.pipeline.stage1_document_parser_agent import _convert_with_upstage
        import httpx

        pdf_path = str(tmp_path / "scan.pdf")
        Path(pdf_path).write_bytes(b"%PDF-1.4 scanned")

        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {"content": "# 공문서 제목\n\n| 항목 | 값 |\n|---|---|\n| A | 1 |"}

        with patch("kms.pipeline.stage1_document_parser_agent.httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__ = AsyncMock(return_value=mock_client.return_value)
            mock_client.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_client.return_value.post = AsyncMock(return_value=mock_resp)

            result = await _convert_with_upstage(pdf_path)

        assert isinstance(result, str)
        assert "공문서 제목" in result
        assert "|" in result  # 표 구조 보존

    @pytest.mark.asyncio
    async def test_raises_on_http_error(self, tmp_path: Path):
        """Upstage API HTTP 오류 시 예외 전파."""
        from module_0_kms.pipeline.stage1_document_parser_agent import _convert_with_upstage
        import httpx

        pdf_path = str(tmp_path / "scan.pdf")
        Path(pdf_path).write_bytes(b"%PDF-1.4 scanned")

        with patch("kms.pipeline.stage1_document_parser_agent.httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__ = AsyncMock(return_value=mock_client.return_value)
            mock_client.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_client.return_value.post = AsyncMock(
                side_effect=httpx.HTTPError("429 Rate Limit Exceeded")
            )

            with pytest.raises(Exception):
                await _convert_with_upstage(pdf_path)

    @pytest.mark.asyncio
    async def test_empty_content_returns_empty_string(self, tmp_path: Path):
        """Upstage 응답에 content 키 없으면 빈 문자열 반환."""
        from module_0_kms.pipeline.stage1_document_parser_agent import _convert_with_upstage

        pdf_path = str(tmp_path / "scan.pdf")
        Path(pdf_path).write_bytes(b"%PDF-1.4 scanned")

        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {}  # content 없음

        with patch("kms.pipeline.stage1_document_parser_agent.httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__ = AsyncMock(return_value=mock_client.return_value)
            mock_client.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_client.return_value.post = AsyncMock(return_value=mock_resp)

            result = await _convert_with_upstage(pdf_path)

        assert result == ""


class TestUpstageDailyLimit:
    """_check_upstage_daily_limit() 단위 테스트"""

    def setup_method(self):
        """각 테스트 전 카운터 초기화."""
        from module_0_kms.pipeline import stage1_document_parser_agent as m
        m._upstage_daily_counter["date"] = None
        m._upstage_daily_counter["count"] = 0

    def test_first_call_today_is_allowed(self):
        """오늘 첫 호출은 허용."""
        from module_0_kms.pipeline.stage1_document_parser_agent import _check_upstage_daily_limit
        with patch.dict(os.environ, {"UPSTAGE_DAILY_LIMIT": "100"}):
            assert _check_upstage_daily_limit() is True

    def test_call_within_limit_increments_counter(self):
        """한도 미만 호출 시 카운터 증가."""
        from module_0_kms.pipeline import stage1_document_parser_agent as m
        with patch.dict(os.environ, {"UPSTAGE_DAILY_LIMIT": "100"}):
            m._check_upstage_daily_limit()
            assert m._upstage_daily_counter["count"] == 1

    def test_limit_exceeded_is_denied(self):
        """한도 초과 시 False 반환 (카운터 증가 없음)."""
        from module_0_kms.pipeline import stage1_document_parser_agent as m
        from datetime import date
        m._upstage_daily_counter["date"] = str(date.today())
        m._upstage_daily_counter["count"] = 100
        with patch.dict(os.environ, {"UPSTAGE_DAILY_LIMIT": "100"}):
            assert m._check_upstage_daily_limit() is False
        assert m._upstage_daily_counter["count"] == 100  # 증가 없음

    def test_counter_resets_on_new_day(self):
        """날짜가 바뀌면 카운터 리셋."""
        from module_0_kms.pipeline import stage1_document_parser_agent as m
        m._upstage_daily_counter["date"] = "2020-01-01"
        m._upstage_daily_counter["count"] = 99
        with patch.dict(os.environ, {"UPSTAGE_DAILY_LIMIT": "100"}):
            assert m._check_upstage_daily_limit() is True
        assert m._upstage_daily_counter["count"] == 1


class TestSelectParserUpstage:
    """_select_parser() — HIGH PDF Upstage 분기 테스트"""

    def test_high_pdf_with_valid_key_returns_upstage(self):
        """유효한 API 키가 있으면 HIGH PDF → 'upstage'."""
        from module_0_kms.pipeline.stage1_document_parser_agent import _select_parser
        with patch.dict(os.environ, {"UPSTAGE_API_KEY": "up_realkey123abc"}):
            assert _select_parser("pdf", "HIGH") == "upstage"

    def test_high_pdf_with_placeholder_key_returns_hitl(self):
        """플레이스홀더 키(up_xxxx)이면 HIGH PDF → 'hitl_required'."""
        from module_0_kms.pipeline.stage1_document_parser_agent import _select_parser
        with patch.dict(os.environ, {"UPSTAGE_API_KEY": "up_xxxx"}):
            assert _select_parser("pdf", "HIGH") == "hitl_required"

    def test_low_pdf_is_unaffected(self):
        """LOW PDF는 키 유무와 무관하게 pymupdf."""
        from module_0_kms.pipeline.stage1_document_parser_agent import _select_parser
        with patch.dict(os.environ, {"UPSTAGE_API_KEY": "up_realkey123abc"}):
            assert _select_parser("pdf", "LOW") == "pymupdf"


class TestDocumentParserAgentUpstage:
    """document_parser_agent() Upstage 경로 통합 테스트"""

    @pytest.mark.asyncio
    async def test_high_pdf_uses_upstage_when_limit_ok(self, tmp_path: Path, mock_storage):
        """HIGH PDF + 유효 키 + 한도 여유 → Upstage 파싱 성공."""
        from module_0_kms.pipeline.stage1_document_parser_agent import document_parser_agent

        pdf_path = str(tmp_path / "scan.pdf")
        Path(pdf_path).write_bytes(b"%PDF-1.4 scanned document")
        state = {
            "doc_id": "dddddddd-dddd-dddd-dddd-dddddddddddd",
            "source": "upload", "file_path": pdf_path, "file_type": "pdf",
            "original_filename": "scan.pdf", "raw_markdown": None,
            "markdown_storage_path": None, "status": "processing", "current_stage": "init",
        }

        with patch.dict(os.environ, {"UPSTAGE_API_KEY": "up_realkey123"}):
            with patch("kms.pipeline.stage1_document_parser_agent._diagnose_document",
                       return_value={"complexity": "HIGH", "has_tables": True,
                                     "has_images": True, "page_count": 10, "image_ratio": 0.6}):
                with patch("kms.pipeline.stage1_document_parser_agent._convert_with_upstage",
                           new=AsyncMock(return_value="# 스캔 문서\n\n## 본문\n\n내용입니다")) as mock_upstage:
                    with patch("kms.pipeline.stage1_document_parser_agent._check_upstage_daily_limit",
                               return_value=True):
                        result = await document_parser_agent(state, storage=mock_storage)

        assert result.get("hitl_required") is not True
        assert result.get("raw_markdown") is not None
        assert "스캔 문서" in result["raw_markdown"]
        assert result.get("parser_used") == "upstage"

    @pytest.mark.asyncio
    async def test_high_pdf_hitl_when_daily_limit_exceeded(self, tmp_path: Path, mock_storage):
        """HIGH PDF + 유효 키 + 일일 한도 초과 → HITL."""
        from module_0_kms.pipeline.stage1_document_parser_agent import document_parser_agent

        pdf_path = str(tmp_path / "scan.pdf")
        Path(pdf_path).write_bytes(b"%PDF-1.4 scanned document")
        state = {
            "doc_id": "eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee",
            "source": "upload", "file_path": pdf_path, "file_type": "pdf",
            "original_filename": "scan.pdf", "raw_markdown": None,
            "markdown_storage_path": None, "status": "processing", "current_stage": "init",
        }

        with patch.dict(os.environ, {"UPSTAGE_API_KEY": "up_realkey123"}):
            with patch("kms.pipeline.stage1_document_parser_agent._diagnose_document",
                       return_value={"complexity": "HIGH", "has_tables": True,
                                     "has_images": True, "page_count": 10, "image_ratio": 0.6}):
                with patch("kms.pipeline.stage1_document_parser_agent._check_upstage_daily_limit",
                           return_value=False):
                    result = await document_parser_agent(state, storage=mock_storage)

        assert result.get("hitl_required") is True
        assert result.get("status") == "hitl_pending"
        assert any("한도" in w for w in result.get("parser_warnings", []))

    @pytest.mark.asyncio
    async def test_high_pdf_hitl_when_upstage_api_fails(self, tmp_path: Path, mock_storage):
        """HIGH PDF + Upstage API 오류 → status='failed' 반환."""
        from module_0_kms.pipeline.stage1_document_parser_agent import document_parser_agent
        import httpx

        pdf_path = str(tmp_path / "scan.pdf")
        Path(pdf_path).write_bytes(b"%PDF-1.4 scanned document")
        state = {
            "doc_id": "ffffffff-ffff-ffff-ffff-ffffffffffff",
            "source": "upload", "file_path": pdf_path, "file_type": "pdf",
            "original_filename": "scan.pdf", "raw_markdown": None,
            "markdown_storage_path": None, "status": "processing", "current_stage": "init",
        }

        with patch.dict(os.environ, {"UPSTAGE_API_KEY": "up_realkey123"}):
            with patch("kms.pipeline.stage1_document_parser_agent._diagnose_document",
                       return_value={"complexity": "HIGH", "has_tables": True,
                                     "has_images": True, "page_count": 10, "image_ratio": 0.6}):
                with patch("kms.pipeline.stage1_document_parser_agent._convert_with_upstage",
                           new=AsyncMock(side_effect=httpx.HTTPError("500 Server Error"))):
                    with patch("kms.pipeline.stage1_document_parser_agent._check_upstage_daily_limit",
                               return_value=True):
                        result = await document_parser_agent(state, storage=mock_storage)

        assert result.get("status") == "failed"
        assert result.get("raw_markdown") is None
