"""TDD (RED): Stage1 — 페이지 이미지 추출 함수 검증.

테스트 대상:
    _extract_page_images_pdf(file_path)  → PDF 페이지별 PNG bytes
    _extract_page_images_pptx(file_path) → PPTX 슬라이드별 PNG bytes
    stage1 진입점이 image_data 필드를 state에 담아 반환하는지

User Journey:
    As a KMS pipeline, I want to extract per-page images from PDF/PPTX during Stage 1,
    so that Stage 6 can save them to GCS and later multimodal RAG can reference them.

ALL TESTS SHOULD FAIL UNTIL _extract_page_images_pdf / _extract_page_images_pptx
ARE IMPLEMENTED IN stage1_document_parser_agent.py
"""

from __future__ import annotations

import io
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock


# ---------------------------------------------------------------------------
# User Journey 1: PDF 페이지 이미지 추출
# ---------------------------------------------------------------------------

class TestExtractPageImagesPdf:
    """_extract_page_images_pdf(file_path) — 반환값 계약 검증."""

    def _make_fake_pixmap(self, width: int = 100, height: int = 100) -> MagicMock:
        """PyMuPDF Page.get_pixmap() 반환값을 흉내 낸 mock."""
        # PNG 시그니처 + 최소 IHDR 헤더 (실제 PNG 구조가 아닌 magic bytes만 포함)
        fake_png_bytes = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
        pixmap = MagicMock()
        pixmap.tobytes.return_value = fake_png_bytes
        pixmap.width = width
        pixmap.height = height
        return pixmap

    def test_returns_list(self):
        """반환값이 list여야 한다."""
        from app.pipeline.stage1_document_parser_agent import _extract_page_images_pdf

        fake_page = MagicMock()
        fake_page.get_pixmap.return_value = self._make_fake_pixmap()

        mock_doc = MagicMock()
        mock_doc.__len__.return_value = 1
        mock_doc.__iter__.return_value = iter([fake_page])
        mock_doc.__enter__ = MagicMock(return_value=mock_doc)
        mock_doc.__exit__ = MagicMock(return_value=False)

        with patch("fitz.open", return_value=mock_doc):
            result = _extract_page_images_pdf("dummy.pdf")

        assert isinstance(result, list), "반환값이 list여야 합니다"

    def test_returns_one_entry_per_page(self):
        """페이지 수만큼 항목이 반환되어야 한다."""
        from app.pipeline.stage1_document_parser_agent import _extract_page_images_pdf

        pages = [MagicMock(), MagicMock(), MagicMock()]
        for p in pages:
            p.get_pixmap.return_value = self._make_fake_pixmap()

        mock_doc = MagicMock()
        mock_doc.__len__.return_value = 3
        mock_doc.__iter__.return_value = iter(pages)
        mock_doc.__enter__ = MagicMock(return_value=mock_doc)
        mock_doc.__exit__ = MagicMock(return_value=False)

        with patch("fitz.open", return_value=mock_doc):
            result = _extract_page_images_pdf("dummy.pdf")

        assert len(result) == 3, f"3페이지 PDF → 3개 항목 기대, 실제: {len(result)}"

    def test_each_entry_has_page_number_and_image_bytes(self):
        """각 항목은 page_number(int)와 image_bytes(bytes)를 가져야 한다."""
        from app.pipeline.stage1_document_parser_agent import _extract_page_images_pdf

        fake_page = MagicMock()
        fake_page.get_pixmap.return_value = self._make_fake_pixmap()

        mock_doc = MagicMock()
        mock_doc.__len__.return_value = 1
        mock_doc.__iter__.return_value = iter([fake_page])
        mock_doc.__enter__ = MagicMock(return_value=mock_doc)
        mock_doc.__exit__ = MagicMock(return_value=False)

        with patch("fitz.open", return_value=mock_doc):
            result = _extract_page_images_pdf("dummy.pdf")

        entry = result[0]
        assert "page_number" in entry, "page_number 키가 없습니다"
        assert "image_bytes" in entry, "image_bytes 키가 없습니다"
        assert isinstance(entry["page_number"], int), "page_number는 int여야 합니다"
        assert isinstance(entry["image_bytes"], bytes), "image_bytes는 bytes여야 합니다"

    def test_page_numbers_are_1_indexed(self):
        """페이지 번호는 1부터 시작해야 한다."""
        from app.pipeline.stage1_document_parser_agent import _extract_page_images_pdf

        pages = [MagicMock(), MagicMock()]
        for p in pages:
            p.get_pixmap.return_value = self._make_fake_pixmap()

        mock_doc = MagicMock()
        mock_doc.__len__.return_value = 2
        mock_doc.__iter__.return_value = iter(pages)
        mock_doc.__enter__ = MagicMock(return_value=mock_doc)
        mock_doc.__exit__ = MagicMock(return_value=False)

        with patch("fitz.open", return_value=mock_doc):
            result = _extract_page_images_pdf("dummy.pdf")

        page_numbers = [e["page_number"] for e in result]
        assert page_numbers == [1, 2], f"1-indexed 기대 [1,2], 실제: {page_numbers}"

    def test_image_bytes_start_with_png_signature(self):
        """image_bytes는 PNG 시그니처(\\x89PNG)로 시작해야 한다."""
        from app.pipeline.stage1_document_parser_agent import _extract_page_images_pdf

        fake_page = MagicMock()
        fake_page.get_pixmap.return_value = self._make_fake_pixmap()

        mock_doc = MagicMock()
        mock_doc.__len__.return_value = 1
        mock_doc.__iter__.return_value = iter([fake_page])
        mock_doc.__enter__ = MagicMock(return_value=mock_doc)
        mock_doc.__exit__ = MagicMock(return_value=False)

        with patch("fitz.open", return_value=mock_doc):
            result = _extract_page_images_pdf("dummy.pdf")

        assert result[0]["image_bytes"][:4] == b"\x89PNG", (
            "image_bytes가 PNG 시그니처로 시작하지 않습니다"
        )

    def test_empty_pdf_returns_empty_list(self):
        """0페이지 PDF는 빈 리스트를 반환해야 한다."""
        from app.pipeline.stage1_document_parser_agent import _extract_page_images_pdf

        mock_doc = MagicMock()
        mock_doc.__len__.return_value = 0
        mock_doc.__iter__.return_value = iter([])
        mock_doc.__enter__ = MagicMock(return_value=mock_doc)
        mock_doc.__exit__ = MagicMock(return_value=False)

        with patch("fitz.open", return_value=mock_doc):
            result = _extract_page_images_pdf("empty.pdf")

        assert result == [], f"0페이지 → 빈 리스트 기대, 실제: {result}"


# ---------------------------------------------------------------------------
# User Journey 2: PPTX 슬라이드 이미지 추출
# ---------------------------------------------------------------------------

class TestExtractPageImagesPptx:
    """_extract_page_images_pptx(file_path) — 반환값 계약 검증."""

    PNG_MAGIC = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100

    def _make_mock_presentation(self, slide_count: int = 2) -> MagicMock:
        """python-pptx Presentation을 흉내 낸 mock."""
        prs = MagicMock()
        slides = [MagicMock() for _ in range(slide_count)]
        prs.slides.__iter__ = MagicMock(return_value=iter(slides))
        prs.slides.__len__ = MagicMock(return_value=slide_count)
        return prs

    def test_returns_list(self):
        """반환값이 list여야 한다."""
        from app.pipeline.stage1_document_parser_agent import _extract_page_images_pptx

        with (
            patch("pptx.Presentation", return_value=self._make_mock_presentation(1)),
            patch(
                "app.pipeline.stage1_document_parser_agent._render_slide_to_png",
                return_value=self.PNG_MAGIC,
            ),
        ):
            result = _extract_page_images_pptx("dummy.pptx")

        assert isinstance(result, list)

    def test_returns_one_entry_per_slide(self):
        """슬라이드 수만큼 항목이 반환되어야 한다."""
        from app.pipeline.stage1_document_parser_agent import _extract_page_images_pptx

        with (
            patch("pptx.Presentation", return_value=self._make_mock_presentation(3)),
            patch(
                "app.pipeline.stage1_document_parser_agent._render_slide_to_png",
                return_value=self.PNG_MAGIC,
            ),
        ):
            result = _extract_page_images_pptx("dummy.pptx")

        assert len(result) == 3

    def test_each_entry_has_page_number_and_image_bytes(self):
        """각 항목은 page_number와 image_bytes를 가져야 한다."""
        from app.pipeline.stage1_document_parser_agent import _extract_page_images_pptx

        with (
            patch("pptx.Presentation", return_value=self._make_mock_presentation(1)),
            patch(
                "app.pipeline.stage1_document_parser_agent._render_slide_to_png",
                return_value=self.PNG_MAGIC,
            ),
        ):
            result = _extract_page_images_pptx("dummy.pptx")

        entry = result[0]
        assert "page_number" in entry
        assert "image_bytes" in entry
        assert isinstance(entry["page_number"], int)
        assert isinstance(entry["image_bytes"], bytes)

    def test_slide_numbers_are_1_indexed(self):
        """슬라이드 번호는 1부터 시작해야 한다."""
        from app.pipeline.stage1_document_parser_agent import _extract_page_images_pptx

        with (
            patch("pptx.Presentation", return_value=self._make_mock_presentation(2)),
            patch(
                "app.pipeline.stage1_document_parser_agent._render_slide_to_png",
                return_value=self.PNG_MAGIC,
            ),
        ):
            result = _extract_page_images_pptx("dummy.pptx")

        assert [e["page_number"] for e in result] == [1, 2]

    def test_empty_pptx_returns_empty_list(self):
        """슬라이드가 없는 PPTX는 빈 리스트를 반환해야 한다."""
        from app.pipeline.stage1_document_parser_agent import _extract_page_images_pptx

        with (
            patch("pptx.Presentation", return_value=self._make_mock_presentation(0)),
            patch(
                "app.pipeline.stage1_document_parser_agent._render_slide_to_png",
                return_value=self.PNG_MAGIC,
            ),
        ):
            result = _extract_page_images_pptx("dummy.pptx")

        assert result == []


# ---------------------------------------------------------------------------
# User Journey 3: stage1 진입점이 image_data를 state에 담아 반환
# ---------------------------------------------------------------------------

class TestStage1ReturnsImageData:
    """document_parser_agent()가 image_data 필드를 state에 반환하는지 검증.

    PDF / PPTX 처리 후 state["image_data"]에 페이지 이미지 목록이 들어야 한다.
    TXT / MD 는 image_data가 None이어야 한다.
    """

    PNG_MAGIC = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
    FAKE_PAGE_IMAGES = [{"page_number": 1, "image_bytes": PNG_MAGIC}]

    def _make_base_state(self, file_type: str) -> dict:
        return {
            "doc_id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
            "source": "upload",
            "file_path": f"dummy.{file_type}",
            "file_type": file_type,
            "original_filename": f"test.{file_type}",
        }

    @staticmethod
    def _make_mock_storage() -> MagicMock:
        storage = MagicMock()
        storage.save = AsyncMock(return_value=None)
        return storage

    # ---- PDF ----

    async def test_pdf_state_contains_image_data(self):
        """PDF 처리 후 state['page_images']에 페이지 이미지가 담겨야 한다."""
        from app.pipeline.stage1_document_parser_agent import document_parser_agent

        state = self._make_base_state("pdf")
        storage = self._make_mock_storage()

        # PDF는 _parse_with_quality_loop 경로를 사용하므로 해당 함수를 패치
        with (
            patch(
                "app.pipeline.stage1_document_parser_agent._parse_with_quality_loop",
                new=AsyncMock(return_value=("# Test\n" + "a" * 300, "pymupdf", 85)),
            ),
            patch(
                "app.pipeline.stage1_document_parser_agent._extract_page_images_pdf",
                return_value=self.FAKE_PAGE_IMAGES,
            ),
            patch("os.path.getsize", return_value=50000),
        ):
            result = await document_parser_agent(state, storage=storage)

        assert result.get("page_images") is not None, (
            "PDF 처리 후 page_images가 None이면 안 됩니다"
        )
        assert isinstance(result["page_images"], list)
        assert len(result["page_images"]) == 1
        assert result["page_images"][0]["page_number"] == 1

    # ---- PPTX ----

    async def test_pptx_state_contains_image_data(self):
        """PPTX 처리 후 state['page_images']에 슬라이드 이미지가 담겨야 한다."""
        from app.pipeline.stage1_document_parser_agent import document_parser_agent

        state = self._make_base_state("pptx")
        storage = self._make_mock_storage()

        # PPTX는 _extract_markdown 경로를 사용 (unstructured 파서)
        with (
            patch(
                "app.pipeline.stage1_document_parser_agent._extract_markdown",
                new=AsyncMock(return_value="Slide content " * 30),
            ),
            patch(
                "app.pipeline.stage1_document_parser_agent._extract_page_images_pptx",
                return_value=self.FAKE_PAGE_IMAGES,
            ),
            patch("os.path.getsize", return_value=20000),
        ):
            result = await document_parser_agent(state, storage=storage)

        assert result.get("page_images") is not None, (
            "PPTX 처리 후 page_images가 None이면 안 됩니다"
        )
        assert isinstance(result["page_images"], list)

    # ---- TXT (이미지 없음) ----

    async def test_txt_state_image_data_is_none(self):
        """TXT 처리 후 page_images는 None이어야 한다."""
        from app.pipeline.stage1_document_parser_agent import document_parser_agent

        state = self._make_base_state("txt")
        storage = self._make_mock_storage()

        with (
            patch(
                "app.pipeline.stage1_document_parser_agent._extract_markdown",
                new=AsyncMock(return_value="# Hello\n" + "text " * 100),
            ),
            patch("os.path.getsize", return_value=5000),
        ):
            result = await document_parser_agent(state, storage=storage)

        assert result.get("page_images") is None, (
            "TXT 파일은 page_images가 None이어야 합니다"
        )
