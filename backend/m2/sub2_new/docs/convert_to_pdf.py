"""
convert_to_pdf.py — docs/learning/*.md → docs/learning/pdf/*.pdf 변환 스크립트

사용법:
    python docs/convert_to_pdf.py

요구사항:
    pip install markdown fpdf2
    (맑은 고딕 폰트: C:\\Windows\\Fonts\\malgun.ttf — Windows 기본 제공)
"""

import os
import re
import markdown
from pathlib import Path
from fpdf import FPDF

LEARNING_DIR = Path(__file__).parent / "learning"
PDF_DIR = LEARNING_DIR / "pdf"
FONT_PATH = r"C:\Windows\Fonts\malgun.ttf"
FONT_BOLD_PATH = r"C:\Windows\Fonts\malgunbd.ttf"


class MarkdownPDF(FPDF):
    """맑은 고딕 + 마크다운 기본 렌더링 지원 PDF 클래스"""

    def __init__(self):
        super().__init__()
        self.add_font("Malgun", "", FONT_PATH)
        self.add_font("Malgun", "B", FONT_BOLD_PATH)
        self.set_auto_page_break(auto=True, margin=20)

    def header(self):
        pass

    def footer(self):
        self.set_y(-12)
        self.set_font("Malgun", "", 8)
        self.set_text_color(150, 150, 150)
        self.cell(0, 10, f"Dev2 학습 노트  |  {self.page_no()}", align="C")
        self.set_text_color(0, 0, 0)


EMOJI_MAP = {
    # 학습 노트 섹션 이모지
    "🏢": "[비유]", "📚": "[개념]", "🤔": "[이유]", "💡": "[팁]",
    "🔍": "[검색]", "🛠": "[도구]", "⚙": "[설정]", "🧪": "[테스트]",
    "📝": "[노트]", "📌": "[포인트]", "🚀": "[실행]", "🔗": "[링크]",
    "🎯": "[목표]", "📊": "[차트]", "🗂": "[분류]", "🏗": "[구조]",
    "🔑": "[키]", "🛡": "[보안]", "⚡": "[빠름]", "🌐": "[네트워크]",
    # 상태 이모지
    "✅": "[OK]", "❌": "[X]", "⚠": "[주의]", "⭐": "[*]",
    "☑": "[OK]", "✔": "[OK]", "✗": "[X]", "✘": "[X]",
    # 숫자/기호 이모지
    "①": "1.", "②": "2.", "③": "3.", "④": "4.", "⑤": "5.",
    "→": "->", "←": "<-", "↑": "^", "↓": "v", "↔": "<->",
    # 기타
    "📄": "[파일]", "📁": "[폴더]", "🔧": "[설정]", "💾": "[저장]",
}


def replace_emoji(text: str) -> str:
    """이모지를 한글/ASCII 텍스트로 교체, 나머지 이모지는 제거"""
    for emoji, replacement in EMOJI_MAP.items():
        text = text.replace(emoji, replacement)
    # 4바이트 이모지 (U+10000~) 제거
    text = re.sub(r'[\U00010000-\U0010ffff]', '', text)
    # BMP 이모지 범위 제거 (Variation Selector 등)
    text = re.sub(r'[️‍⃣]', '', text)
    # 나머지 특수 이모지 블록 제거
    text = re.sub(r'[☀-➿]', '', text)
    text = re.sub(r'[⬀-⯿]', '', text)
    return text


def strip_md_syntax(line: str) -> str:
    """마크다운 문법 기호를 제거하고 plain text 반환"""
    line = replace_emoji(line)
    # 인라인 코드 `` → 그대로 유지
    line = re.sub(r"`([^`]+)`", r"[\1]", line)
    # 굵게 **text** → text
    line = re.sub(r"\*\*(.+?)\*\*", r"\1", line)
    # 기울임 *text* → text
    line = re.sub(r"\*(.+?)\*", r"\1", line)
    # 링크 [text](url) → text
    line = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", line)
    # 이미지 ![alt](url) → alt
    line = re.sub(r"!\[([^\]]*)\]\([^\)]+\)", r"[\1]", line)
    return line


def render_md_to_pdf(pdf: MarkdownPDF, md_text: str):
    """마크다운 텍스트를 PDF에 렌더링"""
    lines = md_text.split("\n")
    in_code_block = False
    in_table = False
    table_rows = []

    i = 0
    while i < len(lines):
        line = lines[i]

        # ── 코드 블록 ─────────────────────────────────────
        if line.strip().startswith("```"):
            if not in_code_block:
                in_code_block = True
                lang = line.strip()[3:].strip()
                pdf.set_font("Malgun", "", 8)
                pdf.set_fill_color(240, 240, 240)
                if lang:
                    pdf.cell(0, 5, f"  [{lang}]", fill=True, new_x="LMARGIN", new_y="NEXT")
            else:
                in_code_block = False
                pdf.set_fill_color(255, 255, 255)
                pdf.ln(3)
            i += 1
            continue

        if in_code_block:
            # 코드 블록 내용 — 회색 배경
            pdf.set_font("Malgun", "", 8)
            pdf.set_fill_color(245, 245, 245)
            safe = replace_emoji(line)
            pdf.multi_cell(0, 4.5, f"  {safe}", fill=True, new_x="LMARGIN", new_y="NEXT")
            i += 1
            continue

        # ── 표 감지 ───────────────────────────────────────
        if line.strip().startswith("|"):
            table_rows.append(line)
            i += 1
            in_table = True
            continue

        if in_table and not line.strip().startswith("|"):
            # 표 렌더링
            _render_table(pdf, table_rows)
            table_rows = []
            in_table = False
            # 현재 줄 계속 처리
        elif in_table:
            i += 1
            continue

        # ── 제목 ──────────────────────────────────────────
        if line.startswith("# "):
            pdf.set_font("Malgun", "B", 16)
            pdf.set_text_color(30, 80, 160)
            pdf.ln(4)
            pdf.multi_cell(0, 9, strip_md_syntax(line[2:]), new_x="LMARGIN", new_y="NEXT")
            pdf.set_text_color(0, 0, 0)
            pdf.set_draw_color(30, 80, 160)
            pdf.set_line_width(0.5)
            pdf.line(pdf.get_x(), pdf.get_y(), pdf.get_x() + 170, pdf.get_y())
            pdf.ln(3)

        elif line.startswith("## "):
            pdf.set_font("Malgun", "B", 13)
            pdf.set_text_color(50, 50, 50)
            pdf.ln(4)
            pdf.multi_cell(0, 8, strip_md_syntax(line[3:]), new_x="LMARGIN", new_y="NEXT")
            pdf.set_text_color(0, 0, 0)
            pdf.ln(1)

        elif line.startswith("### "):
            pdf.set_font("Malgun", "B", 11)
            pdf.set_text_color(70, 70, 70)
            pdf.ln(3)
            pdf.multi_cell(0, 7, strip_md_syntax(line[4:]), new_x="LMARGIN", new_y="NEXT")
            pdf.set_text_color(0, 0, 0)

        elif line.startswith("#### "):
            pdf.set_font("Malgun", "B", 10)
            pdf.multi_cell(0, 6, strip_md_syntax(line[5:]), new_x="LMARGIN", new_y="NEXT")

        # ── 수평선 ────────────────────────────────────────
        elif line.strip() in ("---", "***", "___"):
            pdf.ln(2)
            pdf.set_draw_color(200, 200, 200)
            pdf.set_line_width(0.3)
            pdf.line(pdf.get_x(), pdf.get_y(), pdf.get_x() + 170, pdf.get_y())
            pdf.ln(3)

        # ── 인용 블록 ─────────────────────────────────────
        elif line.startswith("> "):
            pdf.set_font("Malgun", "", 9)
            pdf.set_fill_color(235, 245, 255)
            pdf.set_text_color(60, 60, 120)
            pdf.multi_cell(0, 5.5, f"  {strip_md_syntax(line[2:])}", fill=True,
                           new_x="LMARGIN", new_y="NEXT")
            pdf.set_text_color(0, 0, 0)
            pdf.set_fill_color(255, 255, 255)

        # ── 목록 ──────────────────────────────────────────
        elif re.match(r"^(\s*)([-*+]|\d+\.)\s", line):
            indent = len(line) - len(line.lstrip())
            depth = indent // 2
            prefix = "•" if not re.match(r"^\s*\d+\.", line) else re.match(r"^\s*(\d+\.)", line).group(1)
            content = re.sub(r"^(\s*)([-*+]|\d+\.)\s", "", line)
            pdf.set_font("Malgun", "", 10)
            left_margin = 15 + depth * 5
            pdf.set_x(left_margin)
            pdf.multi_cell(0, 6, f"{prefix} {strip_md_syntax(content)}",
                           new_x="LMARGIN", new_y="NEXT")

        # ── 빈 줄 ────────────────────────────────────────
        elif line.strip() == "":
            pdf.ln(2)

        # ── 일반 텍스트 ───────────────────────────────────
        else:
            pdf.set_font("Malgun", "", 10)
            pdf.multi_cell(0, 6, strip_md_syntax(line), new_x="LMARGIN", new_y="NEXT")

        i += 1

    # 마지막 표 처리
    if table_rows:
        _render_table(pdf, table_rows)


def _render_table(pdf: MarkdownPDF, rows: list[str]):
    """마크다운 표를 PDF 표로 렌더링"""
    parsed = []
    for row in rows:
        if re.match(r"^\|[-| :]+\|$", row.strip()):
            continue  # 구분선 행 스킵
        cells = [c.strip() for c in row.strip().strip("|").split("|")]
        parsed.append(cells)

    if not parsed:
        return

    col_count = max(len(r) for r in parsed)
    col_w = 165 / col_count

    for r_idx, row in enumerate(parsed):
        is_header = r_idx == 0
        pdf.set_font("Malgun", "B" if is_header else "", 8)
        pdf.set_fill_color(220, 230, 255) if is_header else pdf.set_fill_color(250, 250, 250)

        # 행 높이 계산 (긴 텍스트 대비)
        row_h = 6
        for cell in row:
            cell_text = strip_md_syntax(cell)
            approx_lines = max(1, len(cell_text) // int(col_w / 2.5))
            row_h = max(row_h, approx_lines * 5)

        for c_idx in range(col_count):
            cell_text = strip_md_syntax(row[c_idx]) if c_idx < len(row) else ""
            pdf.multi_cell(col_w, row_h, cell_text, border=1, fill=(is_header or r_idx % 2 == 0),
                           new_x="RIGHT", new_y="LAST", max_line_height=5)
        pdf.ln(row_h)

    pdf.ln(3)


def convert_all():
    """docs/learning/ 하위 모든 .md를 PDF로 변환"""
    PDF_DIR.mkdir(exist_ok=True)

    md_files = list(LEARNING_DIR.rglob("*.md"))
    # pdf 폴더 내부 md는 제외
    md_files = [f for f in md_files if "pdf" not in f.parts]

    print(f"변환 대상: {len(md_files)}개 파일".encode("utf-8").decode("utf-8", errors="replace"))
    success = 0
    failed = []

    for md_path in sorted(md_files):
        # 출력 파일명: 폴더 경로를 언더스코어로 합침
        rel = md_path.relative_to(LEARNING_DIR)
        out_name = str(rel).replace(os.sep, "_").replace("/", "_").replace(".md", ".pdf")
        out_path = PDF_DIR / out_name

        try:
            md_text = md_path.read_text(encoding="utf-8")
            # 이모지 → 텍스트 치환 (폰트 미지원 이모지는 한글/ASCII로)
            md_text = replace_emoji(md_text)

            pdf = MarkdownPDF()
            pdf.add_page()
            pdf.set_margins(15, 15, 15)

            # 파일 경로 헤더
            pdf.set_font("Malgun", "", 8)
            pdf.set_text_color(150, 150, 150)
            pdf.cell(0, 5, f"[Dev2 Learning] {rel}", new_x="LMARGIN", new_y="NEXT")
            pdf.set_text_color(0, 0, 0)
            pdf.ln(2)

            render_md_to_pdf(pdf, md_text)
            pdf.output(str(out_path))
            print(f"  OK: {rel} -> pdf/{out_name}")
            success += 1

        except Exception as e:
            print(f"  FAIL: {rel}: {e}")
            failed.append((rel, str(e)))

    print(f"\n완료: {success}/{len(md_files)} 성공")
    if failed:
        print("실패 목록:")
        for f, err in failed:
            print(f"  - {f}: {err}")
    print(f"\nPDF 저장 위치: {PDF_DIR}")


if __name__ == "__main__":
    convert_all()
