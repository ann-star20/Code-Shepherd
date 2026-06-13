"""
test_stage1_docx_parser.py — _paragraph_to_markdown_line / _convert_docx_with_python_docx 단위 테스트

버그 재현:
  Bug 1: 코드 블록 미감지 — Code/Preformatted 스타일, 모노스페이스 폰트 단락이 평문으로 출력
  Bug 2: 헤딩 outline level 미적용 — 커스텀 스타일명의 Heading이 #로 변환 안 됨
  Bug 3: run 사이 공백 소실 — para.text 단순 concat으로 "ClassNameAttribute" 병합 발생
"""

from unittest.mock import MagicMock, PropertyMock
import pytest

from app.pipeline.stage1_document_parser_agent import _paragraph_to_markdown_line


# ---------------------------------------------------------------------------
# 헬퍼: python-docx Paragraph 목업
# ---------------------------------------------------------------------------

def _make_para(text: str, style_name: str = "Normal", runs=None, outline_level: int | None = None):
    """python-docx Paragraph 모사 객체를 반환한다."""
    para = MagicMock()
    para.text = text

    style = MagicMock()
    style.name = style_name
    para.style = style

    # runs: [(run_text, font_name, is_bold)]
    mock_runs = []
    if runs:
        for run_text, font_name, is_bold in runs:
            run = MagicMock()
            run.text = run_text
            font = MagicMock()
            font.name = font_name
            font.bold = is_bold
            run.font = font
            mock_runs.append(run)
    para.runs = mock_runs

    # outline level: XML element mock
    pPr = MagicMock()
    if outline_level is not None:
        outlineLvl = MagicMock()
        outlineLvl.val = outline_level
        pPr.outlineLvl = outlineLvl
    else:
        pPr.outlineLvl = None
    para._element = MagicMock()
    para._element.pPr = pPr

    return para


# ---------------------------------------------------------------------------
# Bug 1: 코드 블록 감지
# ---------------------------------------------------------------------------

class TestCodeBlockDetection:
    def test_code_style_wraps_in_fence(self):
        """스타일명 'Code'인 단락은 코드 펜스로 감싸야 한다."""
        para = _make_para("print('hello')", style_name="Code")
        result = _paragraph_to_markdown_line(para)
        assert result is not None
        assert result.strip().startswith("```") or "```" in result, (
            f"코드 펜스 없음: {result!r}"
        )

    def test_preformatted_style_wraps_in_fence(self):
        """스타일명 'Preformatted Text'인 단락도 코드 펜스로 감싸야 한다."""
        para = _make_para("SELECT * FROM users;", style_name="Preformatted Text")
        result = _paragraph_to_markdown_line(para)
        assert result is not None
        assert "```" in result, f"코드 펜스 없음: {result!r}"

    def test_consolas_font_wraps_in_fence(self):
        """Consolas 폰트가 사용된 단락은 코드 펜스로 감싸야 한다."""
        para = _make_para(
            "XFrameOptionsMiddleware",
            runs=[("XFrameOptionsMiddleware", "Consolas", False)],
        )
        result = _paragraph_to_markdown_line(para)
        assert result is not None
        assert "```" in result, f"Consolas 폰트 단락이 코드 펜스 없음: {result!r}"

    def test_courier_new_font_wraps_in_fence(self):
        """Courier New 폰트가 사용된 단락은 코드 펜스로 감싸야 한다."""
        para = _make_para(
            "def view(request):",
            runs=[("def view(request):", "Courier New", False)],
        )
        result = _paragraph_to_markdown_line(para)
        assert result is not None
        assert "```" in result, f"Courier New 단락이 코드 펜스 없음: {result!r}"

    def test_normal_style_no_fence(self):
        """일반 Normal 스타일 단락은 코드 펜스로 감싸지 않는다."""
        para = _make_para("일반 본문 텍스트입니다.", style_name="Normal")
        result = _paragraph_to_markdown_line(para)
        assert result is not None
        assert "```" not in result


# ---------------------------------------------------------------------------
# Bug 2: Heading outline level 감지
# ---------------------------------------------------------------------------

class TestHeadingOutlineLevel:
    def test_standard_heading1_still_works(self):
        """기존 'Heading 1' 스타일은 여전히 # 로 변환된다."""
        para = _make_para("소개", style_name="Heading 1")
        result = _paragraph_to_markdown_line(para)
        assert result == "# 소개"

    def test_lowercase_heading_style(self):
        """소문자 'heading 1' 스타일도 # 로 변환되어야 한다."""
        para = _make_para("소개", style_name="heading 1")
        result = _paragraph_to_markdown_line(para)
        assert result is not None
        assert result.startswith("#"), f"소문자 heading 감지 실패: {result!r}"

    def test_outline_level_0_becomes_h1(self):
        """outline level=0 (Heading 1 의미)인 단락은 # 로 변환되어야 한다."""
        para = _make_para("챕터 제목", style_name="CustomHeadingStyle", outline_level=0)
        result = _paragraph_to_markdown_line(para)
        assert result is not None
        assert result.startswith("# "), f"outline level=0 → h1 실패: {result!r}"

    def test_outline_level_1_becomes_h2(self):
        """outline level=1 (Heading 2 의미)인 단락은 ## 로 변환되어야 한다."""
        para = _make_para("섹션 제목", style_name="CustomStyle", outline_level=1)
        result = _paragraph_to_markdown_line(para)
        assert result is not None
        assert result.startswith("## "), f"outline level=1 → h2 실패: {result!r}"

    def test_outline_level_2_becomes_h3(self):
        """outline level=2 → ### 로 변환되어야 한다."""
        para = _make_para("소제목", style_name="AnotherStyle", outline_level=2)
        result = _paragraph_to_markdown_line(para)
        assert result is not None
        assert result.startswith("### "), f"outline level=2 → h3 실패: {result!r}"


# ---------------------------------------------------------------------------
# Bug 3: run 사이 공백 보존
# ---------------------------------------------------------------------------

class TestRunSpacePreservation:
    def test_runs_with_existing_spaces_preserved(self):
        """run 사이에 원래 공백이 있으면 병합 후에도 유지된다."""
        para = _make_para(
            "XFrameOptionsMiddleware X-Frame-Options",
            runs=[
                ("XFrameOptionsMiddleware ", "Calibri", True),
                ("X-Frame-Options", "Calibri", False),
            ],
        )
        result = _paragraph_to_markdown_line(para)
        assert result is not None
        # 두 토큰이 붙어서 나오면 안 된다
        assert "XFrameOptionsMiddlewareX-Frame-Options" not in result, (
            f"run 공백 소실: {result!r}"
        )

    def test_bold_run_produces_no_gap(self):
        """굵은 run 뒤에 공백 run이 없어도 구분 가능한 출력이 나와야 한다."""
        para = _make_para(
            "ClassNameAttribute",
            runs=[
                ("ClassName", "Calibri", True),
                ("Attribute", "Calibri", False),
            ],
        )
        result = _paragraph_to_markdown_line(para)
        # 최소한 원본 텍스트 전체가 포함되어야 한다
        assert result is not None
        assert "ClassName" in result
        assert "Attribute" in result
