"""TDD (RED): Stage1 — LibreOffice DOCX/PPTX 페이지 이미지 추출.

테스트 대상:
    _convert_to_pdf_with_libreoffice(file_path) → (pdf_path, tmp_dir)
    _extract_page_images_docx(file_path)         → list[dict]
    document_parser_agent DOCX 처리 후 state["page_images"] 포함 여부

User Journey:
    As a KMS pipeline, I want to extract per-page images from DOCX/PPTX during Stage 1
    via LibreOffice conversion, so that SplitView can show the original document on the left.

ALL TESTS SHOULD FAIL UNTIL _convert_to_pdf_with_libreoffice / _extract_page_images_docx
ARE IMPLEMENTED IN stage1_document_parser_agent.py
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, call, patch


PNG_MAGIC = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
FAKE_PAGE_IMAGES = [
    {"page_number": 1, "image_bytes": PNG_MAGIC},
    {"page_number": 2, "image_bytes": PNG_MAGIC},
]


# ---------------------------------------------------------------------------
# User Journey 1: _convert_to_pdf_with_libreoffice 함수 계약
# ---------------------------------------------------------------------------

class TestConvertToPdfWithLibreoffice:
    """LibreOffice headless 변환 함수 — 반환값 및 예외 계약."""

    def test_function_exists(self):
        """_convert_to_pdf_with_libreoffice 함수가 존재해야 한다."""
        from app.pipeline.stage1_document_parser_agent import _convert_to_pdf_with_libreoffice
        assert callable(_convert_to_pdf_with_libreoffice)

    def test_returns_tuple_of_pdf_path_and_tmp_dir(self):
        """성공 시 (pdf_path: str, tmp_dir: str) 튜플을 반환해야 한다."""
        from app.pipeline.stage1_document_parser_agent import _convert_to_pdf_with_libreoffice

        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stderr = ""

        with (
            patch("subprocess.run", return_value=mock_proc),
            patch("tempfile.mkdtemp", return_value="/tmp/lo_test"),
            patch("os.path.exists", return_value=True),
        ):
            result = _convert_to_pdf_with_libreoffice("/docs/test.docx")

        assert isinstance(result, tuple), "반환값이 tuple이어야 합니다"
        assert len(result) == 2, "반환 tuple 길이는 2여야 합니다"
        pdf_path, tmp_dir = result
        assert isinstance(pdf_path, str), "pdf_path는 str이어야 합니다"
        assert isinstance(tmp_dir, str), "tmp_dir는 str이어야 합니다"
        assert pdf_path.endswith(".pdf"), "pdf_path는 .pdf로 끝나야 합니다"

    def test_pdf_path_uses_original_stem(self):
        """PDF 파일명은 원본 파일의 stem을 사용해야 한다."""
        from app.pipeline.stage1_document_parser_agent import _convert_to_pdf_with_libreoffice

        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stderr = ""

        with (
            patch("subprocess.run", return_value=mock_proc),
            patch("tempfile.mkdtemp", return_value="/tmp/lo_test"),
            patch("os.path.exists", return_value=True),
        ):
            pdf_path, _ = _convert_to_pdf_with_libreoffice("/docs/my_report.docx")

        assert "my_report" in pdf_path, f"PDF 경로에 원본 파일명 stem이 없습니다: {pdf_path}"

    def test_raises_runtime_error_on_nonzero_exit(self):
        """LibreOffice 변환 실패 시 RuntimeError를 발생시켜야 한다."""
        from app.pipeline.stage1_document_parser_agent import _convert_to_pdf_with_libreoffice
        import pytest

        mock_proc = MagicMock()
        mock_proc.returncode = 1
        mock_proc.stderr = "Error: file not found"

        with (
            patch("subprocess.run", return_value=mock_proc),
            patch("tempfile.mkdtemp", return_value="/tmp/lo_test"),
        ):
            with pytest.raises(RuntimeError, match="LibreOffice"):
                _convert_to_pdf_with_libreoffice("/docs/missing.docx")

    def test_calls_libreoffice_headless_with_convert_to_pdf(self):
        """subprocess.run이 libreoffice --headless --convert-to pdf를 호출해야 한다."""
        from app.pipeline.stage1_document_parser_agent import _convert_to_pdf_with_libreoffice

        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stderr = ""

        with (
            patch("subprocess.run", return_value=mock_proc) as mock_run,
            patch("tempfile.mkdtemp", return_value="/tmp/lo_test"),
            patch("os.path.exists", return_value=True),
        ):
            _convert_to_pdf_with_libreoffice("/docs/test.docx")

        args = mock_run.call_args[0][0]
        assert "libreoffice" in args[0], "libreoffice 명령어가 사용되어야 합니다"
        assert "--headless" in args, "--headless 플래그가 필요합니다"
        assert "--convert-to" in args, "--convert-to 플래그가 필요합니다"
        assert "pdf" in args, "pdf 변환 대상이 필요합니다"


# ---------------------------------------------------------------------------
# User Journey 2: _extract_page_images_docx 함수 계약
# ---------------------------------------------------------------------------

class TestExtractPageImagesDocx:
    """_extract_page_images_docx(file_path) — LibreOffice 경유 DOCX 이미지 추출."""

    def test_function_exists(self):
        """_extract_page_images_docx 함수가 존재해야 한다."""
        from app.pipeline.stage1_document_parser_agent import _extract_page_images_docx
        assert callable(_extract_page_images_docx)

    def test_returns_list(self):
        """반환값이 list여야 한다."""
        from app.pipeline.stage1_document_parser_agent import _extract_page_images_docx

        with (
            patch(
                "app.pipeline.stage1_document_parser_agent._convert_to_pdf_with_libreoffice",
                return_value=("/tmp/test.pdf", "/tmp/tmpdir"),
            ),
            patch(
                "app.pipeline.stage1_document_parser_agent._extract_page_images_pdf",
                return_value=FAKE_PAGE_IMAGES,
            ),
            patch("shutil.rmtree"),
        ):
            result = _extract_page_images_docx("test.docx")

        assert isinstance(result, list), "반환값이 list여야 합니다"

    def test_delegates_to_pdf_extractor(self):
        """LibreOffice로 PDF 변환 후 _extract_page_images_pdf에 위임해야 한다."""
        from app.pipeline.stage1_document_parser_agent import _extract_page_images_docx

        with (
            patch(
                "app.pipeline.stage1_document_parser_agent._convert_to_pdf_with_libreoffice",
                return_value=("/tmp/test.pdf", "/tmp/tmpdir"),
            ) as mock_lo,
            patch(
                "app.pipeline.stage1_document_parser_agent._extract_page_images_pdf",
                return_value=FAKE_PAGE_IMAGES,
            ) as mock_pdf,
            patch("shutil.rmtree"),
        ):
            result = _extract_page_images_docx("test.docx")

        mock_lo.assert_called_once_with("test.docx")
        assert mock_pdf.call_args[0][0] == "/tmp/test.pdf", "pdf_path가 올바르게 전달되어야 합니다"

    def test_cleans_up_tmp_dir_after_extraction(self):
        """변환 완료 후 tmp_dir을 삭제해야 한다."""
        from app.pipeline.stage1_document_parser_agent import _extract_page_images_docx

        with (
            patch(
                "app.pipeline.stage1_document_parser_agent._convert_to_pdf_with_libreoffice",
                return_value=("/tmp/test.pdf", "/tmp/tmpdir_cleanup"),
            ),
            patch(
                "app.pipeline.stage1_document_parser_agent._extract_page_images_pdf",
                return_value=FAKE_PAGE_IMAGES,
            ),
            patch("shutil.rmtree") as mock_rmtree,
        ):
            _extract_page_images_docx("test.docx")

        mock_rmtree.assert_called_once()
        args = mock_rmtree.call_args[0]
        assert "/tmp/tmpdir_cleanup" in args[0], "tmp_dir이 삭제되어야 합니다"

    def test_cleans_up_tmp_dir_even_on_error(self):
        """PDF 추출 중 오류가 발생해도 tmp_dir을 삭제해야 한다."""
        from app.pipeline.stage1_document_parser_agent import _extract_page_images_docx
        import pytest

        with (
            patch(
                "app.pipeline.stage1_document_parser_agent._convert_to_pdf_with_libreoffice",
                return_value=("/tmp/test.pdf", "/tmp/tmpdir_err"),
            ),
            patch(
                "app.pipeline.stage1_document_parser_agent._extract_page_images_pdf",
                side_effect=RuntimeError("PDF 추출 실패"),
            ),
            patch("shutil.rmtree") as mock_rmtree,
        ):
            with pytest.raises(RuntimeError):
                _extract_page_images_docx("test.docx")

        mock_rmtree.assert_called_once()

    def test_returns_correct_page_count(self):
        """추출된 페이지 수가 PDF 변환 결과와 일치해야 한다."""
        from app.pipeline.stage1_document_parser_agent import _extract_page_images_docx

        three_pages = [
            {"page_number": i + 1, "image_bytes": PNG_MAGIC}
            for i in range(3)
        ]

        with (
            patch(
                "app.pipeline.stage1_document_parser_agent._convert_to_pdf_with_libreoffice",
                return_value=("/tmp/test.pdf", "/tmp/tmpdir"),
            ),
            patch(
                "app.pipeline.stage1_document_parser_agent._extract_page_images_pdf",
                return_value=three_pages,
            ),
            patch("shutil.rmtree"),
        ):
            result = _extract_page_images_docx("test.docx")

        assert len(result) == 3


# ---------------------------------------------------------------------------
# User Journey 3: document_parser_agent DOCX 처리 시 page_images 포함
# ---------------------------------------------------------------------------

class TestStage1DocxPageImages:
    """document_parser_agent()가 DOCX 처리 후 page_images를 state에 반환."""

    PNG_MAGIC = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100

    def _make_base_state(self) -> dict:
        return {
            "doc_id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
            "source": "upload",
            "file_path": "dummy.docx",
            "file_type": "docx",
            "original_filename": "test.docx",
        }

    @staticmethod
    def _make_mock_storage() -> MagicMock:
        storage = MagicMock()
        storage.save = AsyncMock(return_value=None)
        return storage

    async def test_docx_state_contains_page_images(self):
        """DOCX 처리 후 state['page_images']에 페이지 이미지가 담겨야 한다."""
        from app.pipeline.stage1_document_parser_agent import document_parser_agent

        state = self._make_base_state()
        storage = self._make_mock_storage()
        fake_images = [{"page_number": 1, "image_bytes": self.PNG_MAGIC}]

        with (
            patch(
                "app.pipeline.stage1_document_parser_agent._extract_markdown",
                new=AsyncMock(return_value="# 제목\n\n" + "내용 " * 100),
            ),
            patch(
                "app.pipeline.stage1_document_parser_agent._extract_page_images_docx",
                return_value=fake_images,
            ),
            patch("os.path.getsize", return_value=30000),
        ):
            result = await document_parser_agent(state, storage=storage)

        paths = result.get("page_image_paths")
        assert paths is not None, "DOCX 처리 후 page_image_paths가 None이면 안 됩니다"
        assert isinstance(paths, list)
        assert len(paths) >= 1

    async def test_pptx_uses_libreoffice_extractor(self):
        """PPTX 처리 시 _extract_page_images_docx가 호출되어야 한다."""
        from app.pipeline.stage1_document_parser_agent import document_parser_agent

        state = {
            "doc_id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
            "source": "upload",
            "file_path": "dummy.pptx",
            "file_type": "pptx",
            "original_filename": "test.pptx",
        }
        storage = self._make_mock_storage()
        fake_images = [{"page_number": 1, "image_bytes": self.PNG_MAGIC}]

        with (
            patch(
                "app.pipeline.stage1_document_parser_agent._extract_markdown",
                new=AsyncMock(return_value="Slide content " * 30),
            ),
            patch(
                "app.pipeline.stage1_document_parser_agent._extract_page_images_docx",
                return_value=fake_images,
            ) as mock_extractor,
            patch("os.path.getsize", return_value=20000),
        ):
            result = await document_parser_agent(state, storage=storage)

        mock_extractor.assert_called_once_with("dummy.pptx")
        assert result.get("page_image_paths") is not None
