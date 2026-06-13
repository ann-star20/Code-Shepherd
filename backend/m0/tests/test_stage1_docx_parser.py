"""
test_stage1_docx_parser.py — _paragraph_to_markdown_line / _calculate_quality_score 단위 테스트

버그 재현:
  Bug 1: 코드 블록 미감지 — Code/Preformatted 스타일, 모노스페이스 폰트 단락이 평문으로 출력
  Bug 2: 헤딩 outline level 미적용 — 커스텀 스타일명의 Heading이 #로 변환 안 됨
  Bug 3: run 사이 공백 소실 — para.text 단순 concat으로 "ClassNameAttribute" 병합 발생
  Bug 4: 이모지를 깨진 문자로 오판 — _BROKEN_CHAR_PATTERN이 이모지 범위 미포함
"""

from unittest.mock import MagicMock, PropertyMock
import pytest

from app.pipeline.stage1_document_parser_agent import (
    _paragraph_to_markdown_line,
    _calculate_quality_score,
)


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


# ---------------------------------------------------------------------------
# Bug 4: 이모지를 깨진 문자로 오판
# ---------------------------------------------------------------------------

class TestEmojiNotBrokenChar:
    """_calculate_quality_score 가 이모지를 broken char로 계산하지 않아야 한다."""

    EMOJI_HEAVY_MD = (
        "# Django Clickjacking 보안\n\n"
        "| 상태 | 설명 |\n"
        "| --- | --- |\n"
        "| 🟢 허용 | 공개 위젯 뷰 |\n"
        "| 🔴 차단 | 기본 미들웨어 적용 |\n"
        "| 🟡 경고 | 커스텀 헤더 필요 |\n"
        "| ⚠ 주의 | X-Frame-Options 설정 확인 |\n"
        "| 🖥 데스크톱 | 전체 지원 |\n"
        "| 📊 통계 | 클릭재킹 공격 비율 |\n"
        "| ★ 추천 | SAMEORIGIN 옵션 |\n\n"
        "이모지가 포함된 표는 정상 마크다운입니다.\n" * 10
    )

    def test_emoji_does_not_lower_broken_ratio(self):
        """이모지가 포함된 마크다운의 broken_ratio가 2% 미만이어야 한다."""
        score = _calculate_quality_score(self.EMOJI_HEAVY_MD, "docx", has_tables=True)
        # broken_ratio < 0.02 → +20점 획득 확인
        # 헤딩+표+길이 보너스까지 합산해 60점 이상이어야 함
        assert score >= 60, (
            f"이모지로 인해 품질 점수 과소 산정: {score} (기대 >= 60)"
        )

    def test_emoji_only_paragraph_not_broken(self):
        """이모지만으로 구성된 단락도 broken char로 처리하지 않는다."""
        emoji_line = "🔴 🟡 🟢 ⚠ 🖥 📊 ★ 🔵"
        md = "# 제목\n\n" + emoji_line + "\n\n" + ("본문 내용입니다.\n" * 20)
        score = _calculate_quality_score(md, "docx")
        assert score >= 50, f"이모지 단락으로 품질 과소 산정: {score}"

    def test_misc_symbols_not_broken(self):
        """U+2600-U+27BF 범위 (⚠ ★ 등 Misc Symbols/Dingbats)도 정상 처리된다."""
        md = "# 제목\n\n⚠ 경고 메시지\n★ 별점 5개\n☑ 완료\n\n" + ("내용 " * 50)
        score = _calculate_quality_score(md, "docx")
        assert score >= 50, f"Misc Symbols가 broken char로 처리됨: {score}"

    def test_pure_ascii_korean_still_high_score(self):
        """이모지 없는 일반 문서는 여전히 높은 점수를 받는다."""
        md = "# 제목\n\n## 소제목\n\n본문 내용입니다. " * 30
        score = _calculate_quality_score(md, "docx")
        assert score >= 75, f"일반 문서 점수가 낮아짐 (regression): {score}"


# ---------------------------------------------------------------------------
# Bug 5: DOCX 표 빈 행 필터링
# ---------------------------------------------------------------------------

from unittest.mock import patch, MagicMock as MM

from app.pipeline.stage1_document_parser_agent import _convert_docx_with_python_docx


def _make_docx_table(rows_data: list[list[str]]):
    """python-docx Document + Table 목업을 반환한다."""
    doc = MM()
    table = MM()

    mock_rows = []
    for row_data in rows_data:
        row = MM()
        cells = []
        for cell_text in row_data:
            cell = MM()
            cell.text = cell_text
            cell._tc = object()  # 고유 identity
            cells.append(cell)
        row.cells = cells
        mock_rows.append(row)

    table.rows = mock_rows

    # body element: 표 하나만 포함
    tbl_elem = MM()
    tbl_elem.tag = "tbl"

    doc.element = MM()
    doc.element.body = [tbl_elem]

    return doc, table, tbl_elem


class TestDocxTableEmptyRowFiltering:
    def test_all_empty_row_is_excluded(self):
        """모든 셀이 빈 행은 Markdown 표에서 제외되어야 한다."""
        rows_data = [
            ["번호", "기법", "예시"],          # 헤더
            ["1", "Query Parameterization", "cursor.execute(sql)"],
            ["2", "", ""],                    # 빈 행
            ["3", "Input Validation", "isdigit()"],
            ["", "", ""],                     # 완전 빈 행
        ]
        from docx import Document
        import io, struct

        # 실제 python-docx 객체 없이 _convert_docx_with_python_docx를 직접 호출하기 어려우므로
        # _build_table_markdown 헬퍼 함수를 별도 추출·테스트한다
        from app.pipeline.stage1_document_parser_agent import _table_rows_to_markdown
        result = _table_rows_to_markdown(rows_data)
        assert result is not None

        # 완전 빈 행("", "", "")은 결과에 포함되면 안 된다
        lines = [l for l in result.split("\n") if l.strip()]
        empty_data_lines = [l for l in lines if l.strip("| ").replace("|", "").strip() == ""]
        assert len(empty_data_lines) == 0, (
            f"완전 빈 행이 포함됨:\n{result}"
        )

    def test_partial_empty_row_is_kept(self):
        """일부 셀만 비어있는 행은 유지되어야 한다."""
        rows_data = [
            ["번호", "기법", "예시"],
            ["2", "", "QuerySet API"],   # 중간 셀만 비어있음
        ]
        from app.pipeline.stage1_document_parser_agent import _table_rows_to_markdown
        result = _table_rows_to_markdown(rows_data)
        assert result is not None
        assert "QuerySet API" in result, f"부분 빈 행이 제거됨: {result}"

    def test_header_row_never_excluded(self):
        """헤더 행(첫 번째 행)은 비어있어도 제외하지 않는다."""
        rows_data = [
            ["번호", "기법", "예시"],
            ["", "", ""],
        ]
        from app.pipeline.stage1_document_parser_agent import _table_rows_to_markdown
        result = _table_rows_to_markdown(rows_data)
        assert result is not None
        assert "번호" in result, f"헤더 행이 제거됨: {result}"


# ---------------------------------------------------------------------------
# Bug 6: DOCX 텍스트 박스 내용 미추출
# ---------------------------------------------------------------------------

from app.pipeline.stage1_document_parser_agent import _extract_textbox_lines_from_para


def _make_txbx_para_elem(textbox_texts: list[str], anchor_text: str = ""):
    """w:txbxContent를 포함하는 최소 w:p lxml 요소를 생성한다.

    실제 DOCX는 drawing > anchor > graphic > ... > wps:txbx > w:txbxContent
    경로를 사용하지만, iter()는 깊이 무관하게 탐색하므로
    w:p > w:txbxContent 단순 구조로도 동일하게 동작한다.
    """
    from lxml import etree
    W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"

    para = etree.Element(f"{{{W}}}p")

    if anchor_text:
        r = etree.SubElement(para, f"{{{W}}}r")
        t = etree.SubElement(r, f"{{{W}}}t")
        t.text = anchor_text

    txbx_content = etree.SubElement(para, f"{{{W}}}txbxContent")
    for text in textbox_texts:
        p = etree.SubElement(txbx_content, f"{{{W}}}p")
        r = etree.SubElement(p, f"{{{W}}}r")
        t_elem = etree.SubElement(r, f"{{{W}}}t")
        t_elem.text = text

    return para


class TestTextBoxExtraction:
    def test_single_textbox_text_extracted(self):
        """텍스트 박스 안의 단일 텍스트가 추출된다."""
        elem = _make_txbx_para_elem(["🛒 Django 공식 문서 예시"])
        result = _extract_textbox_lines_from_para(elem)
        assert "Django 공식 문서 예시" in " ".join(result), (
            f"텍스트 박스 내용 미추출: {result}"
        )

    def test_multiline_textbox_all_lines_extracted(self):
        """텍스트 박스 안에 여러 단락이 있으면 모두 추출된다."""
        lines = [
            "온라인 쇼핑몰에 로그인된 사용자가",
            "'지금 구매' 버튼을 클릭할 수 있는 페이지가 있습니다.",
            "공격자는 자신의 사이트에 iframe을 올려서 버튼을 숨깁니다.",
        ]
        elem = _make_txbx_para_elem(lines)
        result = _extract_textbox_lines_from_para(elem)
        assert len(result) == 3, f"단락 수 불일치: {result}"
        assert result[0] == lines[0]
        assert result[2] == lines[2]

    def test_no_textbox_returns_empty_list(self):
        """텍스트 박스가 없는 일반 단락은 빈 리스트를 반환한다."""
        from lxml import etree
        W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
        para = etree.Element(f"{{{W}}}p")
        r = etree.SubElement(para, f"{{{W}}}r")
        t = etree.SubElement(r, f"{{{W}}}t")
        t.text = "일반 단락 텍스트"
        result = _extract_textbox_lines_from_para(para)
        assert result == [], f"일반 단락에서 텍스트 박스 오탐: {result}"

    def test_empty_textbox_lines_excluded(self):
        """텍스트 박스 안의 완전 빈 단락은 결과에서 제외된다."""
        elem = _make_txbx_para_elem(["내용 있음", "", "   "])
        result = _extract_textbox_lines_from_para(elem)
        assert len(result) == 1, f"빈 단락이 포함됨: {result}"
        assert result[0] == "내용 있음"

    def test_deeply_nested_textbox_extracted(self):
        """실제 DOCX처럼 drawing > anchor > ... 깊이 중첩돼도 추출된다."""
        from lxml import etree
        W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
        WP = "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"

        para = etree.Element(f"{{{W}}}p")
        r = etree.SubElement(para, f"{{{W}}}r")
        drawing = etree.SubElement(r, f"{{{W}}}drawing")
        anchor = etree.SubElement(drawing, f"{{{WP}}}anchor")
        # anchor 아래 여러 레이어 후 txbxContent
        txbx_content = etree.SubElement(anchor, f"{{{W}}}txbxContent")
        p = etree.SubElement(txbx_content, f"{{{W}}}p")
        r2 = etree.SubElement(p, f"{{{W}}}r")
        t = etree.SubElement(r2, f"{{{W}}}t")
        t.text = "중첩 텍스트 박스"

        result = _extract_textbox_lines_from_para(para)
        assert "중첩 텍스트 박스" in result, f"깊은 중첩 텍스트 박스 미추출: {result}"
