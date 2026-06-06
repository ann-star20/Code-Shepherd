"""
Stage 1: Document Parser Agent (trc_0001)

지원 형식: PDF · DOCX · PPTX · TXT · MD
- TXT / MD: 직접 읽기
- DOCX / PPTX / PDF (텍스트 위주): unstructured 라이브러리
- PDF (이미지/표 복잡): Gemini Multimodal 폴백

출력:
    state["raw_markdown"]          변환된 Markdown 문자열
    state["markdown_storage_path"] 저장된 Markdown 파일 경로
    state["status"]                "processing" 유지 (검증은 Stage 2)
"""

from __future__ import annotations

import asyncio
import base64
import logging
import os
import re
import shutil
import subprocess
import tempfile
import time
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING

import httpx

if TYPE_CHECKING:
    from app.pipeline.models import DocPipelineState
    from app.storage import Storage

logger = logging.getLogger(__name__)

from langchain_core.messages import HumanMessage, SystemMessage

from app.pipeline._gemini import call_gemini_with_retry

# PDF에서 이미지 비율이 이 값 이상이면 Gemini Multimodal 폴백 사용
GEMINI_FALLBACK_IMAGE_RATIO = float(os.getenv("GEMINI_FALLBACK_IMAGE_RATIO", "0.3"))


# ---------------------------------------------------------------------------
# 내부 변환 로직
# ---------------------------------------------------------------------------

def _read_text_file(file_path: str) -> str:
    return Path(file_path).read_text(encoding="utf-8", errors="replace")


def _html_table_to_markdown(html: str) -> str:
    """HTML <table> 문자열 → Markdown 파이프 표 변환.

    BeautifulSoup(lxml)으로 파싱하여 colspan/rowspan/멀티라인 셀을 처리한다.
    - colspan=N: 내용 셀 + 빈 셀 (N-1)개로 패딩
    - rowspan=N: 해당 내용을 아래 N-1개 행에 반복 (내용 손실 방지)
    - <br> 등 인라인 태그: 공백으로 변환
    """
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "lxml")
    table = soup.find("table")
    if not table:
        return html

    rows = table.find_all("tr")
    if not rows:
        return html

    # rowspan_tracker[col] = (남은 행 수, 셀 내용)
    rowspan_tracker: dict[int, tuple[int, str]] = {}
    md_rows: list[str] = []

    for row_idx, row in enumerate(rows):
        cells = row.find_all(["td", "th"])
        row_data: list[str] = []
        cell_iter = iter(cells)
        col = 0

        while True:
            # 이 열이 위 행의 rowspan에 점유돼 있으면 내용 반복
            if col in rowspan_tracker and rowspan_tracker[col][0] > 0:
                remaining, content = rowspan_tracker[col]
                row_data.append(content)
                rowspan_tracker[col] = (remaining - 1, content)
                col += 1
                continue

            # 다음 실제 셀 가져오기
            cell = next(cell_iter, None)
            if cell is None:
                break

            # 셀 텍스트: <br>→공백, 나머지 태그 제거, 연속 공백 정리
            text = cell.get_text(separator=" ").strip()
            text = " ".join(text.split())

            colspan = int(cell.get("colspan", 1) or 1)
            rowspan = int(cell.get("rowspan", 1) or 1)

            row_data.append(text)

            # 이 셀이 rowspan > 1이면 아래 행을 위해 추적
            if rowspan > 1:
                rowspan_tracker[col] = (rowspan - 1, text)

            col += 1

            # colspan 패딩: 빈 셀 추가
            for _ in range(colspan - 1):
                row_data.append("")
                col += 1

        # 행 끝에 남아 있는 rowspan 슬롯 채우기
        while col in rowspan_tracker and rowspan_tracker[col][0] > 0:
            remaining, content = rowspan_tracker[col]
            row_data.append(content)
            rowspan_tracker[col] = (remaining - 1, content)
            col += 1

        if not row_data:
            continue

        md_rows.append("| " + " | ".join(row_data) + " |")
        if row_idx == 0:
            md_rows.append("| " + " | ".join(["---"] * len(row_data)) + " |")

    return "\n".join(md_rows) if md_rows else html


def _elements_to_markdown(elements: list) -> str:
    """unstructured Element 목록 → Markdown 문자열 변환."""
    lines: list[str] = []
    for el in elements:
        el_type = type(el).__name__
        text = el.text.strip() if el.text else ""
        if not text:
            continue

        if el_type == "Title":
            # category_depth: 0 → ##, 1 → ###, 2+ → #### (최대 ####)
            depth = getattr(el.metadata, "category_depth", None) or 0
            level = min(int(depth) + 2, 4)
            lines.append(f"{'#' * level} {text}")
        elif el_type in ("NarrativeText", "Text"):
            lines.append(text)
        elif el_type == "ListItem":
            lines.append(f"- {text}")
        elif el_type == "Table":
            html = getattr(el.metadata, "text_as_html", None)
            if html:
                lines.append(_html_table_to_markdown(html))
            else:
                lines.append(text)
        elif el_type == "Image":
            lines.append(f"<!-- Image: {text} -->")
        elif el_type == "Header":
            lines.append(f"### {text}")
        elif el_type == "Footer":
            pass  # 푸터는 제외
        else:
            lines.append(text)

    return "\n\n".join(lines)


def _paragraph_to_markdown_line(para) -> str | None:
    """python-docx Paragraph → Markdown 라인. 빈 단락은 None 반환."""
    text = para.text.strip() if para.text else ""
    if not text:
        return None

    style_name: str = (para.style.name if para.style else "") or ""

    # "Heading 1"~N (영문) / "제목 1"~N (한글 Word) → #~####
    if style_name.startswith(("Heading ", "제목 ")):
        level_token = style_name.split()[-1]
        try:
            level = min(int(level_token), 4)
            return f"{'#' * level} {text}"
        except ValueError:
            pass

    if style_name in ("Title", "제목"):
        return f"# {text}"

    if "List" in style_name:
        return f"- {text}"

    return text


def _convert_docx_with_python_docx(file_path: str) -> str:
    """python-docx로 DOCX를 Markdown으로 변환. 단락과 표를 문서 순서대로 처리한다."""
    from docx import Document
    from docx.text.paragraph import Paragraph as DocxParagraph
    from docx.table import Table as DocxTable

    doc = Document(file_path)
    blocks: list[str] = []

    for child in doc.element.body:
        tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag

        if tag == "p":
            para = DocxParagraph(child, doc)
            line = _paragraph_to_markdown_line(para)
            if line:
                blocks.append(line)

        elif tag == "tbl":
            table = DocxTable(child, doc)
            rows: list[str] = []
            for i, row in enumerate(table.rows):
                cells = [cell.text.strip() for cell in row.cells]
                rows.append("| " + " | ".join(cells) + " |")
                if i == 0:
                    rows.append("| " + " | ".join(["---"] * len(cells)) + " |")
            if rows:
                blocks.append("\n".join(rows))

    return "\n\n".join(blocks)


def _convert_with_unstructured(file_path: str, file_type: str) -> tuple[str, float]:
    """
    unstructured 라이브러리로 문서를 변환한다.
    반환: (markdown 문자열, 이미지 element 비율)

    전략 선택 기준:
    - "fast" (기본값): pdfminer 기반, 모델 다운로드 없음, 5초 이내 완료.
      이미지/표 비율이 높으면 Gemini Multimodal 폴백이 자동 처리.
    - "hi_res": YOLO 레이아웃 + OCR 기반. HuggingFace 모델 다운로드 필요 (~수십 초),
      복잡한 PDF는 90초 하네스 타임아웃 초과 → AGENT_TIMEOUT_SECONDS 를 300초 이상으로
      설정하고 운영환경에서만 사용할 것.
    """
    from unstructured.partition.auto import partition

    _strategy = os.getenv("UNSTRUCTURED_STRATEGY", "fast")
    try:
        elements = partition(
            filename=file_path,
            strategy=_strategy,
            infer_table_structure=True,
        )
    except ImportError:
        elements = partition(filename=file_path)
    total = len(elements)
    image_count = sum(1 for el in elements if type(el).__name__ == "Image")
    image_ratio = image_count / total if total > 0 else 0.0

    markdown = _elements_to_markdown(elements)
    return markdown, image_ratio


def _convert_pdf_with_pymupdf(file_path: str) -> tuple[str, float]:
    """
    PyMuPDF(fitz)로 PDF를 Markdown으로 변환한다.
    반환: (markdown 문자열, 이미지 element 비율)

    장점: 모델 다운로드 없음, C++ 기반으로 1-3초 이내 완료.
    한계: 이미지 안 텍스트(스캔본) 추출 불가 → image_ratio 높으면 Gemini 폴백 처리.
    """
    try:
        import fitz  # PyMuPDF
    except ImportError:
        logger.warning("PyMuPDF 미설치 — unstructured 로 폴백합니다. pip install pymupdf")
        return _convert_with_unstructured(file_path, "pdf")

    doc = fitz.open(file_path)
    blocks_md: list[str] = []
    total_blocks = 0
    image_blocks = 0

    for page in doc:
        blocks = page.get_text("dict", flags=fitz.TEXT_PRESERVE_WHITESPACE)["blocks"]
        for block in blocks:
            total_blocks += 1
            btype = block.get("type", 0)
            if btype == 1:  # 이미지 블록
                image_blocks += 1
                blocks_md.append("<!-- Image -->\n")
                continue
            # 텍스트 블록
            lines: list[str] = []
            for line in block.get("lines", []):
                line_text = "".join(span["text"] for span in line.get("spans", []))
                line_text = line_text.strip()
                if line_text:
                    lines.append(line_text)
            if not lines:
                continue
            text = " ".join(lines)

            # 폰트 크기 기반 제목 추정
            sizes = [span["size"] for line in block.get("lines", []) for span in line.get("spans", [])]
            avg_size = sum(sizes) / len(sizes) if sizes else 12
            if avg_size >= 18:
                blocks_md.append(f"# {text}")
            elif avg_size >= 15:
                blocks_md.append(f"## {text}")
            elif avg_size >= 13:
                blocks_md.append(f"### {text}")
            else:
                blocks_md.append(text)

    doc.close()

    image_ratio = image_blocks / total_blocks if total_blocks > 0 else 0.0
    markdown = "\n\n".join(b for b in blocks_md if b.strip())
    return markdown, image_ratio


async def _convert_pdf_with_gemini(file_path: str) -> str:
    """
    Gemini Multimodal로 PDF를 Markdown으로 변환.
    이미지·표가 많은 PDF에 대한 폴백 전략.
    """
    with open(file_path, "rb") as f:
        pdf_bytes = f.read()

    encoded = base64.b64encode(pdf_bytes).decode()

    prompt = (
        "이 PDF 문서를 Markdown 형식으로 변환해주세요.\n"
        "규칙:\n"
        "- 주요 제목은 ##, 소제목은 ###\n"
        "- 표는 Markdown 표(| 형식) 유지\n"
        "- 이미지는 <!-- Image description --> 형태로 설명 포함\n"
        "- 페이지 번호, 머리글/바닥글은 제외\n"
        "원본 구조를 최대한 보존하세요."
    )

    message = HumanMessage(
        content=[
            {"type": "text", "text": prompt},
            {
                "type": "image_url",
                "image_url": {"url": f"data:application/pdf;base64,{encoded}"},
            },
        ]
    )

    response = await call_gemini_with_retry([message])
    return response.content


# ---------------------------------------------------------------------------
# Document Parser Agent — Sprint 1 신규 함수
# ---------------------------------------------------------------------------

def _diagnose_pdf(file_path: str) -> dict:
    """PyMuPDF로 PDF 복잡도를 빠르게 스캔한다."""
    try:
        import fitz
    except ImportError:
        return {"complexity": "LOW", "has_tables": False, "has_images": False,
                "page_count": None, "image_ratio": 0.0}
    try:
        doc = fitz.open(file_path)
    except Exception:
        return {"complexity": "LOW", "has_tables": False, "has_images": False,
                "page_count": None, "image_ratio": 0.0}

    page_count = len(doc)
    total_blocks = 0
    image_blocks = 0
    table_page_count = 0
    # 테이블 감지는 최대 10페이지만 샘플링 (속도 보장)
    sample_limit = min(10, page_count)
    for i, page in enumerate(doc):
        blocks = page.get_text("dict", flags=0)["blocks"]
        for block in blocks:
            total_blocks += 1
            if block.get("type", 0) == 1:
                image_blocks += 1
        if i < sample_limit:
            try:
                if page.find_tables().tables:
                    table_page_count += 1
            except Exception:
                pass
    doc.close()
    # 샘플 기반 테이블 비율을 전체 페이지로 외삽
    if sample_limit < page_count and sample_limit > 0:
        table_page_count = int(table_page_count * page_count / sample_limit)

    has_tables = table_page_count > 0
    image_ratio = image_blocks / total_blocks if total_blocks > 0 else 0.0
    table_ratio = table_page_count / page_count if page_count > 0 else 0.0

    # 표가 하나라도 감지된 PDF는 구조화 콘텐츠 → Upstage 적합
    if image_ratio >= 0.5 or has_tables:
        complexity = "HIGH"
    elif image_ratio >= 0.3 or table_ratio >= 0.1:
        complexity = "MEDIUM"
    else:
        complexity = "LOW"

    return {
        "complexity": complexity,
        "has_tables": has_tables,
        "has_images": image_blocks > 0,
        "page_count": page_count,
        "image_ratio": image_ratio,
    }


def _diagnose_docx(file_path: str) -> dict:
    """python-docx로 DOCX를 빠르게 스캔한다."""
    try:
        from docx import Document
        doc = Document(file_path)
        return {
            "complexity": "LOW",
            "has_tables": len(doc.tables) > 0,
            "has_images": False,
            "page_count": None,
            "image_ratio": 0.0,
        }
    except Exception:
        return {"complexity": "LOW", "has_tables": False, "has_images": False,
                "page_count": None, "image_ratio": 0.0}


def _diagnose_document(file_path: str, file_type: str) -> dict:
    """
    문서 복잡도를 빠르게 진단한다 (caller가 3초 타임아웃 적용).

    Returns dict with keys:
        complexity: "LOW" | "MEDIUM" | "HIGH"
        has_tables: bool
        has_images: bool
        page_count: int | None
        image_ratio: float
    """
    if file_type in ("txt", "md", "pptx"):
        return {"complexity": "LOW", "has_tables": False, "has_images": False,
                "page_count": None, "image_ratio": 0.0}
    if file_type == "docx":
        return _diagnose_docx(file_path)
    if file_type == "pdf":
        return _diagnose_pdf(file_path)
    return {"complexity": "LOW", "has_tables": False, "has_images": False,
            "page_count": None, "image_ratio": 0.0}


# ---------------------------------------------------------------------------
# Upstage Document AI — 일일 호출 카운터 (프로세스 메모리, 날짜 기반 리셋)
# ---------------------------------------------------------------------------

_upstage_daily_counter: dict = {"date": None, "count": 0}


def _check_upstage_daily_limit() -> bool:
    """오늘의 Upstage 호출 횟수가 UPSTAGE_DAILY_LIMIT 미만인지 확인.

    True 반환 시 카운터 1 증가. False 반환 시 카운터 변경 없음.
    날짜가 바뀌면 카운터를 리셋한다.
    """
    today = str(date.today())
    limit = int(os.getenv("UPSTAGE_DAILY_LIMIT", "100"))

    if _upstage_daily_counter["date"] != today:
        _upstage_daily_counter["date"] = today
        _upstage_daily_counter["count"] = 0

    if _upstage_daily_counter["count"] >= limit:
        return False

    _upstage_daily_counter["count"] += 1
    return True


async def _convert_with_upstage(file_path: str) -> str:
    """Upstage Document AI로 PDF를 Markdown으로 변환.

    HIGH complexity PDF (스캔본, 공문서, 표 밀집 문서) 전용.
    UPSTAGE_API_KEY 환경변수 필수.
    100페이지 초과 시 분할 변환 후 결과를 이어붙임.
    """
    api_key = os.getenv("UPSTAGE_API_KEY", "")
    upstage_page_limit = 100

    try:
        import fitz as _fitz
        doc = _fitz.open(file_path)
        total_pages = len(doc)
        doc.close()
    except Exception:
        total_pages = 0

    if total_pages <= upstage_page_limit:
        return await _upstage_single_call(file_path, api_key)

    # 100페이지씩 분할해서 변환 후 합침
    import tempfile
    parts: list[str] = []
    try:
        import fitz as _fitz
        src_doc = _fitz.open(file_path)
        for start in range(0, total_pages, upstage_page_limit):
            end = min(start + upstage_page_limit, total_pages)
            chunk_doc = _fitz.open()
            chunk_doc.insert_pdf(src_doc, from_page=start, to_page=end - 1)
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
                chunk_doc.save(tmp.name)
                chunk_path = tmp.name
            chunk_doc.close()
            part_md = await _upstage_single_call(chunk_path, api_key)
            Path(chunk_path).unlink(missing_ok=True)
            if part_md:
                parts.append(part_md)
        src_doc.close()
    except Exception as exc:
        logger.error(f"Upstage 분할 변환 실패: {exc}")
    return "\n\n".join(parts)


def _normalize_korean_lists(markdown: str) -> str:
    """한국어 리스트 패턴을 '- ' 불릿으로 변환한다.

    처리 패턴 (줄 시작에서만):
    - 가. 나. 다. ... 하. (가-하 한글 자음 + 마침표)
    - (가) (나) (다) ... (하) 괄호 패턴
    - ① ~ ⑳  원문자 숫자
    - 1) 2) 3) ... 숫자 + 닫는 괄호
    """
    # ① ~ ⑳ 범위 (U+2460 ~ U+2473)
    circled_numbers = "".join(chr(0x2460 + i) for i in range(20))

    lines = markdown.split("\n")
    result_lines: list[str] = []
    for line in lines:
        # 가. ~ 하. (한글 자음 순서: 가나다라마바사아자차카타파하)
        if re.match(r"^[가나다라마바사아자차카타파하]\.\s", line):
            line = "- " + line[3:]
        # (가) ~ (하) 괄호 패턴
        elif re.match(r"^\([가나다라마바사아자차카타파하]\)\s", line):
            line = "- " + line[4:]
        # ① ~ ⑳
        elif line and line[0] in circled_numbers:
            line = "- " + line[1:].lstrip()
        # 1) 2) 3) ...
        elif re.match(r"^\d+\)\s", line):
            line = re.sub(r"^\d+\)\s+", "- ", line)
        result_lines.append(line)

    return "\n".join(result_lines)


def _normalize_heading_hierarchy(markdown: str) -> str:
    """헤딩 레벨을 정규화한다. 최소 헤딩 레벨을 h1(#)으로 시프트.

    Upstage가 모든 헤딩을 # h1으로 반환하는 경우, 이미 최소가 1이므로 변경 없음.
    반대로 최소 레벨이 ##(2) 이상이면 offset만큼 빼서 최소를 h1으로 맞춘다.
    예: ## h2, ### h3 → # h1, ## h2
    """
    lines = markdown.split("\n")
    heading_levels: list[int] = []
    for line in lines:
        m = re.match(r"^(#{1,6})\s", line)
        if m:
            heading_levels.append(len(m.group(1)))

    if not heading_levels:
        return markdown

    min_level = min(heading_levels)
    if min_level == 1:
        return markdown  # 이미 h1이 최소 레벨

    offset = min_level - 1
    result_lines: list[str] = []
    for line in lines:
        m = re.match(r"^(#{1,6})(\s.+)", line)
        if m:
            new_level = max(1, len(m.group(1)) - offset)
            result_lines.append("#" * new_level + m.group(2))
        else:
            result_lines.append(line)

    return "\n".join(result_lines)


def _strip_html_artifacts(markdown: str) -> str:
    """Upstage 출력에 남은 비-테이블 HTML 잔재를 제거한다.

    처리 순서:
    1. <figure>...</figure> 블록 전체 제거 (이미지 컨테이너)
    2. <img ...> 태그 제거 (독립 이미지)
    3. <br> / <br/> / <br /> → 개행 변환
    4. 표준 인라인/블록 태그(<span>, <em>, <strong>, <p>, <div>) 제거 — 내용 보존
    5. Upstage 고유 figure/표 참조 태그 제거 (<그림 N-N>, <표 N-N>, <목록 N> 등)
    6. HTML 엔티티 디코딩 (&nbsp;, &amp;, &lt;, &gt;, &quot;)

    <table>은 건드리지 않는다 — 표 변환은 별도 단계에서 처리.
    """
    import html

    # 1. <figure>...</figure> 전체 제거
    markdown = re.sub(r"<figure[^>]*>.*?</figure>", "", markdown, flags=re.DOTALL | re.IGNORECASE)

    # 2. <img ...> 단독 태그 제거
    markdown = re.sub(r"<img\b[^>]*/?>", "", markdown, flags=re.IGNORECASE)

    # 3. <br> 변환 → 개행
    markdown = re.sub(r"<br\s*/?>", "\n", markdown, flags=re.IGNORECASE)

    # 4. 표준 인라인/블록 태그 제거 — 내용은 보존 (<table/tr/td/th 제외)
    markdown = re.sub(
        r"</?(?:span|em|strong|b|i|u|p|div|section|article|header|footer|aside|nav|main)[^>]*>",
        "",
        markdown,
        flags=re.IGNORECASE,
    )

    # 5. Upstage 고유 참조 태그 제거: <그림 N-N>, <표 N-N>, <목록 N> 등
    # 한글을 포함하는 태그 패턴 — 표준 HTML에는 한글 태그가 없으므로 안전하게 제거
    markdown = re.sub(r"</?[가-힣][가-힣\w\s\-]*>", "", markdown)

    # 6. HTML 엔티티 디코딩 (&nbsp; → 공백, &amp; → &, 등)
    markdown = markdown.replace("&nbsp;", " ")
    markdown = html.unescape(markdown)

    return markdown


def _normalize_heading_korean_list(markdown: str) -> str:
    """헤딩으로 잘못 표시된 한국어 목록 패턴을 불릿으로 변환한다.

    Upstage가 (1), (가), 가., ① 같은 목록 패턴을 H1~H3으로 반환하는 경우
    이를 `- ` 불릿으로 변환하여 Gemini 품질 평가의 "제목 계층 잘못 적용" 오류를 제거한다.

    변환 대상 (헤딩 접두사 뒤에 목록 패턴이 오는 경우):
    - `# (N) 텍스트`  — 숫자 괄호
    - `# (가) 텍스트` — 한글 괄호
    - `# 가. 텍스트`  — 한글 자음 + 마침표
    - `# ① 텍스트`   — 원문자 숫자

    보존 대상 (변환하지 않음):
    - `# 1. 섹션명`   — 숫자+마침표 섹션 번호 (진짜 섹션 제목)
    - `# 제목 텍스트` — 일반 제목
    """
    circled_numbers = "".join(chr(0x2460 + i) for i in range(20))

    lines = markdown.split("\n")
    result: list[str] = []
    for line in lines:
        m = re.match(r"^(#{1,6})\s+(.*)", line)
        if not m:
            result.append(line)
            continue

        heading_text = m.group(2)

        # (N) 숫자 괄호 또는 (가) 한글 괄호 패턴
        if re.match(r"^\(\d+\)\s", heading_text) or re.match(
            r"^\([가나다라마바사아자차카타파하]\)\s", heading_text
        ):
            result.append("- " + heading_text)
            continue

        # 가. 나. 다. 한글 자음 + 마침표 패턴
        if re.match(r"^[가나다라마바사아자차카타파하]\.\s", heading_text):
            result.append("- " + heading_text[3:])
            continue

        # ① ~ ⑳ 원문자 숫자 패턴
        if heading_text and heading_text[0] in circled_numbers:
            result.append("- " + heading_text[1:].lstrip())
            continue

        result.append(line)

    return "\n".join(result)


def _post_process_upstage_markdown(markdown: str) -> str:
    """Upstage 응답 후처리 파이프라인.

    1. 헤딩 계층 정규화 (_normalize_heading_hierarchy)
    2. 한국어 리스트 패턴 변환 (_normalize_korean_lists)
    3. 헤딩으로 잘못 표시된 한국어 목록 패턴 변환 (_normalize_heading_korean_list)
    4. HTML 표 → Markdown 파이프 표 변환 (_html_table_to_markdown)
    5. 비-테이블 HTML 잔재 제거 (_strip_html_artifacts)
    """
    markdown = _normalize_heading_hierarchy(markdown)
    markdown = _normalize_korean_lists(markdown)
    markdown = _normalize_heading_korean_list(markdown)

    if "<table" in markdown:
        def _replace(match: re.Match) -> str:  # type: ignore[type-arg]
            converted = _html_table_to_markdown(match.group(0))
            # 변환 실패(원본 HTML 그대로 반환)면 주석으로 대체
            if "<table" in converted:
                return "<!-- 표 변환 실패 — 원본 참조 필요 -->"
            return converted

        markdown = re.sub(r"<table[^>]*>.*?</table>", _replace, markdown, flags=re.DOTALL | re.IGNORECASE)

    markdown = _strip_html_artifacts(markdown)

    return markdown


async def _upstage_single_call(file_path: str, api_key: str) -> str:
    """파일 하나를 Upstage Document Digitization API로 변환."""
    import json as _json
    with open(file_path, "rb") as f:
        pdf_bytes = f.read()

    async with httpx.AsyncClient(timeout=120.0) as client:
        response = await client.post(
            "https://api.upstage.ai/v1/document-digitization",
            headers={"Authorization": f"Bearer {api_key}"},
            files={
                "document": (os.path.basename(file_path), pdf_bytes, "application/pdf")
            },
            data={"model": "document-parse", "output_formats": _json.dumps(["markdown"])},
        )
        response.raise_for_status()
        content = response.json().get("content", {})
        if isinstance(content, dict):
            raw = content.get("markdown", "") or content.get("html", "") or content.get("text", "")
        else:
            raw = str(content) if content else ""

    # Upstage가 HTML 테이블을 반환한 경우 Markdown으로 변환
    return _post_process_upstage_markdown(raw)


PARSER_QUALITY_THRESHOLD = int(os.getenv("PARSER_QUALITY_THRESHOLD", "60"))

# PDF 파서 시도 순서 (품질 낮을 때 자동 전환)
_PDF_PARSER_SEQUENCE = ["pymupdf", "unstructured", "gemini_ocr"]


async def _parse_with_quality_loop(
    file_path: str,
    file_type: str,
) -> tuple[str, str, int]:
    """
    PDF 품질 기반 파서 자율 전환 루프 (Stage 1 Agent 핵심).

    pymupdf → unstructured → gemini_ocr 순서로 시도.
    각 결과를 _calculate_quality_score()로 관찰하고
    PARSER_QUALITY_THRESHOLD 달성 시 즉시 반환한다.
    전부 실패하면 ("", "hitl_required", 0)을 반환한다.

    gemini_ocr는 GOOGLE_API_KEY 환경변수가 있을 때만 시도한다.

    Returns:
        (markdown, parser_used, quality_score)
    """
    threshold = int(os.getenv("PARSER_QUALITY_THRESHOLD", str(PARSER_QUALITY_THRESHOLD)))
    best_md, best_parser, best_score = "", "hitl_required", 0

    for parser_name in _PDF_PARSER_SEQUENCE:
        # gemini_ocr는 API 키가 있어야 시도
        if parser_name == "gemini_ocr" and not os.getenv("GOOGLE_API_KEY", ""):
            logger.info("GOOGLE_API_KEY 없음 — gemini_ocr 건너뜀")
            break

        try:
            if parser_name == "pymupdf":
                md, _ = await asyncio.to_thread(_convert_pdf_with_pymupdf, file_path)
            elif parser_name == "unstructured":
                md, _ = await asyncio.to_thread(_convert_with_unstructured, file_path, file_type)
            else:  # gemini_ocr
                md = await _convert_pdf_with_gemini(file_path)
        except Exception as e:
            logger.warning(
                f"_parse_with_quality_loop: {parser_name} 실패 ({e}) → 다음 파서 시도",
                extra={"file_path": file_path},
            )
            continue

        score = _calculate_quality_score(md, file_type)
        logger.info(
            f"_parse_with_quality_loop: {parser_name} 품질={score}",
            extra={"file_path": file_path},
        )

        if score > best_score:
            best_md, best_parser, best_score = md, parser_name, score

        if score >= threshold:
            logger.info(f"_parse_with_quality_loop: {parser_name} 목표 달성 (score={score})")
            return md, parser_name, score

    if best_score > 0 and best_parser != "hitl_required":
        logger.warning(
            f"_parse_with_quality_loop: 모든 파서 threshold({threshold}) 미달 — HITL 등록",
            extra={"best_parser": best_parser, "best_score": best_score},
        )

    return "", "hitl_required", 0


def _select_parser(file_type: str, complexity: str) -> str:
    """
    파일 타입과 복잡도에 따라 최적 파서를 선택한다.

    Returns:
        "direct_read" | "python_docx" | "unstructured" | "pymupdf"
        | "upstage" | "hitl_required"

    Raises:
        ValueError: 지원하지 않는 파일 형식
    """
    if file_type in ("txt", "md"):
        return "direct_read"
    if file_type == "docx":
        return "python_docx"
    if file_type == "pptx":
        return "unstructured"
    if file_type == "pdf":
        if complexity == "HIGH":
            api_key = os.getenv("UPSTAGE_API_KEY", "")
            if api_key and api_key != "up_xxxx":
                return "upstage"
            return "hitl_required"
        return "pymupdf"
    raise ValueError(f"지원하지 않는 파일 형식: {file_type}")


_BROKEN_CHAR_PATTERN = re.compile(
    r"[^\x09\x0A\x0D\x20-\x7E가-힣぀-ヿ一-鿿À-ÿ]"
)


def _calculate_quality_score(
    markdown: str,
    file_type: str,
    has_tables: bool = False,
    has_images: bool = False,
    file_size_bytes: int = 0,
) -> int:
    """
    규칙 기반 Markdown 품질 점수를 계산한다 (0~100점, 가산점 방식).

    채점 기준:
        +30  길이 >= 200자
        +10  길이 >= 500자 (보너스)
        +20  깨진 문자 비율 < 2%
        + 5  깨진 문자 비율 < 1% (보너스)
        +15  헤딩 존재 (#~####, PPTX 제외)
        +15  표 보존 (has_tables=False OR '|' in markdown)
        + 5  이미지 참조 (has_images=False OR '<!-- Image' in markdown)
    """
    length = len(markdown)
    if length == 0:
        return 0

    score = 0

    if length >= 200:
        score += 30
    if length >= 500:
        score += 10

    broken = _BROKEN_CHAR_PATTERN.findall(markdown)
    broken_ratio = len(broken) / max(length, 1)
    if broken_ratio < 0.02:
        score += 20
    if broken_ratio < 0.01:
        score += 5

    if file_type != "pptx":
        if re.search(r"^#{1,4} ", markdown, re.MULTILINE):
            score += 15
    else:
        score += 15  # PPTX는 헤딩 없어도 패널티 없음

    if not has_tables or "|" in markdown:
        score += 15

    if not has_images or "<!-- Image" in markdown:
        score += 5

    return min(score, 100)


_FORMAT_CORRECT_SYSTEM = (
    "당신은 Markdown 문서 서식 교정 전문가입니다. "
    "문서의 내용(텍스트)은 절대 변경하지 말고, "
    "헤딩 계층 표 형식 리스트 구조 등 서식만 교정하세요. "
    "교정된 Markdown만 반환하고, 설명이나 주석은 포함하지 마세요."
)


async def _gemini_format_correct(markdown: str) -> str:
    """
    Gemini를 사용해 60~79점 Markdown의 서식을 보정한다.
    실패 또는 Mock LLM 환경에서는 원본 markdown을 반환한다.
    """
    if os.getenv("USE_MOCK_LLM", "true").lower() == "true":
        return markdown

    prompt = f"다음 Markdown 문서의 서식을 교정해 주세요:\n\n{markdown}"
    try:
        response = await call_gemini_with_retry([
            SystemMessage(content=_FORMAT_CORRECT_SYSTEM),
            HumanMessage(content=prompt),
        ])
        return response.content
    except Exception as e:
        logger.warning(f"Gemini 서식 보정 실패, 원본 사용: {e}")
        return markdown


def _make_hitl_result(
    parser_name: str,
    complexity: str,
    has_tables: bool,
    has_images: bool,
    page_count,
    parsing_time_ms: int,
    warnings: list,
    markdown=None,
) -> dict:
    """HITL 결과 dict를 일관된 형태로 생성한다."""
    return {
        "raw_markdown": markdown,
        "markdown_storage_path": None,
        "hitl_required": True,
        "status": "hitl_pending",
        "current_stage": "stage1_document_parser",
        "parser_used": parser_name,
        "parser_quality_score": None,
        "doc_complexity": complexity,
        "has_tables": has_tables,
        "has_images": has_images,
        "page_count": page_count,
        "parsing_time_ms": parsing_time_ms,
        "parser_warnings": warnings,
        "fallback_used": False,
        "image_refs": None,
        "image_data": None,
    }


# ---------------------------------------------------------------------------
# Stage 1 노드 함수 (Document Parser Agent)
# ---------------------------------------------------------------------------

async def document_parser_agent(
    state: "DocPipelineState",
    storage: "Storage",
) -> dict:
    """
    Document Parser Agent — 6단계 흐름:
      [1] 문서 진단 (asyncio.wait_for 3초 타임아웃)
      [2] 파서 선택 (_select_parser)
      [3] 변환 실행 (_extract_markdown, parsing_time_ms 측정)
      [4] 품질 점수 계산 (_calculate_quality_score, 규칙 기반)
      [5] 점수 기반 분기 (>= 80: 통과 / 60~79: Gemini 보정 / < 40: HITL)
      [6] GCS/로컬 저장 + state 반환
    """
    file_path = state["file_path"]
    file_type = state["file_type"].lower().lstrip(".")
    doc_id = state["doc_id"]

    logger.info("Stage 1 시작", extra={"doc_id": doc_id, "file_type": file_type})

    # [1] 문서 진단 (10초 타임아웃 — 복잡한 PDF 테이블 감지 포함)
    try:
        diagnosis = await asyncio.wait_for(
            asyncio.to_thread(_diagnose_document, file_path, file_type),
            timeout=10.0,
        )
    except asyncio.TimeoutError:
        logger.warning("문서 진단 타임아웃 — LOW 복잡도로 폴백", extra={"doc_id": doc_id})
        diagnosis = {"complexity": "LOW", "has_tables": False, "has_images": False,
                     "page_count": None, "image_ratio": 0.0}

    complexity = diagnosis["complexity"]
    has_tables = diagnosis["has_tables"]
    has_images = diagnosis["has_images"]
    page_count = diagnosis.get("page_count")

    # [2] 파서 선택
    try:
        parser_name = _select_parser(file_type, complexity)
    except ValueError as e:
        logger.error("파서 선택 실패", extra={"doc_id": doc_id, "error": str(e)})
        return {
            "raw_markdown": None,
            "markdown_storage_path": None,
            "status": "failed",
            "error": f"Stage1 변환 실패: {e}",
            "current_stage": "stage1_document_parser",
            "parser_used": None,
            "parser_quality_score": None,
            "doc_complexity": complexity,
            "has_tables": has_tables,
            "has_images": has_images,
            "page_count": page_count,
            "parsing_time_ms": 0,
            "parser_warnings": [],
            "fallback_used": False,
            "image_refs": None,
            "image_data": None,
        }

    if parser_name == "hitl_required":
        logger.warning("HIGH 복잡도 PDF — HITL 즉시", extra={"doc_id": doc_id})
        return _make_hitl_result(
            parser_name, complexity, has_tables, has_images, page_count, 0,
            ["HIGH complexity PDF: UPSTAGE_API_KEY 미설정"],
        )

    # [3] 변환 실행
    t0 = time.monotonic()

    # Upstage 경로: 일일 한도 체크 후 변환 (HIGH complexity PDF 전용)
    if parser_name == "upstage":
        if not _check_upstage_daily_limit():
            logger.warning("Upstage 일일 한도 초과 — HITL", extra={"doc_id": doc_id})
            return _make_hitl_result(
                parser_name, complexity, has_tables, has_images, page_count, 0,
                [f"Upstage 일일 한도 초과 ({os.getenv('UPSTAGE_DAILY_LIMIT', '100')}회) — 수동 처리 필요"],
            )
        try:
            markdown = await _convert_with_upstage(file_path)
            logger.info("Upstage 변환 완료", extra={"doc_id": doc_id})
        except Exception as e:
            logger.error("Upstage 변환 실패", extra={"doc_id": doc_id, "error": str(e)})
            return {
                "raw_markdown": None,
                "markdown_storage_path": None,
                "status": "failed",
                "error": f"Stage1 Upstage 변환 실패: {e}",
                "current_stage": "stage1_document_parser",
                "parser_used": parser_name,
                "parser_quality_score": None,
                "doc_complexity": complexity,
                "has_tables": has_tables,
                "has_images": has_images,
                "page_count": page_count,
                "parsing_time_ms": 0,
                "parser_warnings": [],
                "fallback_used": False,
                "image_refs": None,
                "image_data": None,
            }

    elif parser_name == "pymupdf":
        # PDF Agent 루프: 품질 관찰 → 미달 시 파서 자율 전환
        markdown, parser_name, quality_loop_score = await _parse_with_quality_loop(
            file_path, file_type
        )
        if parser_name == "hitl_required":
            parsing_time_ms = int((time.monotonic() - t0) * 1000)
            return _make_hitl_result(
                "hitl_required", complexity, has_tables, has_images, page_count,
                parsing_time_ms, ["모든 파서 품질 기준 미달"],
            )

    else:
        try:
            markdown = await _extract_markdown(file_path, file_type)
        except Exception as e:
            logger.error("Markdown 변환 실패", extra={"doc_id": doc_id, "error": str(e)})
            return {
                "raw_markdown": None,
                "markdown_storage_path": None,
                "status": "failed",
                "error": f"Stage1 변환 실패: {e}",
                "current_stage": "stage1_document_parser",
                "parser_used": parser_name,
                "parser_quality_score": None,
                "doc_complexity": complexity,
                "has_tables": has_tables,
                "has_images": has_images,
                "page_count": page_count,
                "parsing_time_ms": 0,
                "parser_warnings": [],
                "fallback_used": False,
                "image_refs": None,
                "image_data": None,
            }

    parsing_time_ms = int((time.monotonic() - t0) * 1000)
    warnings: list[str] = []

    # [4] 품질 점수 계산 (규칙 기반, LLM 없음)
    try:
        file_size_bytes = os.path.getsize(file_path)
    except Exception:
        file_size_bytes = 0

    quality_score = _calculate_quality_score(
        markdown, file_type, has_tables, has_images, file_size_bytes
    )

    # [5] 점수 기반 분기
    if quality_score < 40:
        logger.warning(
            f"품질 점수 {quality_score}/100 < 40 -> HITL",
            extra={"doc_id": doc_id},
        )
        warnings.append(f"품질 점수 미달: {quality_score}/100 (임계값 40)")
        return _make_hitl_result(
            parser_name, complexity, has_tables, has_images, page_count,
            parsing_time_ms, warnings, markdown=markdown,
        )
    elif quality_score < 60:
        logger.info(f"품질 점수 {quality_score}/100 — 경고 후 통과", extra={"doc_id": doc_id})
        warnings.append(f"품질 주의: {quality_score}/100")
    elif quality_score < 80:
        logger.info(f"품질 점수 {quality_score}/100 — Gemini 서식 보정", extra={"doc_id": doc_id})
        markdown = await _gemini_format_correct(markdown)

    # [6] 저장
    storage_path = f"markdown/{doc_id}/raw.md"
    await storage.save(storage_path, markdown.encode("utf-8"))

    # [7] 페이지 이미지 추출 (PDF / DOCX / PPTX — 멀티모달 RAG용)
    page_images: list[dict] | None = None
    if file_type == "pdf":
        try:
            page_images = await asyncio.to_thread(_extract_page_images_pdf, file_path)
        except Exception as e:
            logger.warning(f"PDF 페이지 이미지 추출 실패 (무시): {e}", extra={"doc_id": doc_id})
    elif file_type in ("docx", "pptx"):
        try:
            page_images = await asyncio.to_thread(_extract_page_images_docx, file_path)
        except Exception as e:
            logger.warning(
                f"{file_type.upper()} 페이지 이미지 추출 실패 (무시, LibreOffice 필요): {e}",
                extra={"doc_id": doc_id},
            )

    logger.info(
        "Stage 1 완료",
        extra={"doc_id": doc_id, "parser": parser_name,
               "quality_score": quality_score, "parsing_time_ms": parsing_time_ms,
               "page_images_count": len(page_images) if page_images else 0},
    )

    return {
        "raw_markdown": markdown,
        "markdown_storage_path": storage_path,
        "current_stage": "stage1_document_parser",
        "parser_used": parser_name,
        "parser_quality_score": quality_score,
        "doc_complexity": complexity,
        "has_tables": has_tables,
        "has_images": has_images,
        "page_count": page_count,
        "parsing_time_ms": parsing_time_ms,
        "parser_warnings": warnings,
        "fallback_used": False,
        "image_refs": None,
        "image_data": None,
        "page_images": page_images,
    }


async def _extract_markdown(file_path: str, file_type: str) -> str:
    """파일 형식에 따라 적절한 변환 방법을 선택."""

    if file_type in ("txt", "md"):
        # sync I/O를 스레드풀에서 실행하여 이벤트 루프 블로킹 방지
        return await asyncio.to_thread(_read_text_file, file_path)

    if file_type == "docx":
        return await asyncio.to_thread(_convert_docx_with_python_docx, file_path)

    if file_type == "pptx":
        markdown, _ = await asyncio.to_thread(
            _convert_with_unstructured, file_path, file_type
        )
        return markdown

    if file_type == "pdf":
        # 1차: PyMuPDF (빠름, 모델 다운로드 없음, 텍스트 기반 PDF에 최적)
        markdown, image_ratio = await asyncio.to_thread(_convert_pdf_with_pymupdf, file_path)

        # 텍스트가 빈약하면 unstructured fast 로 재시도
        _short_text = len(markdown.strip()) < 200
        if _short_text:
            logger.info("PyMuPDF 텍스트 부족 — unstructured fast 재시도", extra={"file_path": file_path})
            try:
                markdown, image_ratio = await asyncio.to_thread(
                    _convert_with_unstructured, file_path, file_type
                )
                _short_text = len(markdown.strip()) < 200
            except Exception as e:
                logger.warning(f"unstructured 재시도 실패: {e}", extra={"file_path": file_path})

        # 이미지 비율이 높거나 여전히 텍스트가 빈약하면 Gemini Multimodal로 재변환
        if (image_ratio >= GEMINI_FALLBACK_IMAGE_RATIO or _short_text) and os.getenv("GOOGLE_API_KEY", ""):
            logger.info(
                f"PDF 이미지 비율 {image_ratio:.1%} — Gemini Multimodal 폴백 사용",
                extra={"file_path": file_path},
            )
            try:
                return await _convert_pdf_with_gemini(file_path)
            except Exception as e:
                logger.warning(
                    f"Gemini 폴백 실패, 기존 추출 결과 사용: {e}",
                    extra={"file_path": file_path},
                )

        return markdown

    raise ValueError(f"지원하지 않는 파일 형식: {file_type}")


# ---------------------------------------------------------------------------
# 페이지 이미지 추출 (멀티모달 RAG용)
# ---------------------------------------------------------------------------

def _render_slide_to_png(slide) -> bytes:
    """python-pptx Slide에서 PNG bytes를 추출한다.

    슬라이드 내 이미지 shape이 있으면 첫 번째 이미지 blob을 반환하고,
    없으면 최소 PNG 헤더를 반환하여 경로 저장 추적만 보장한다.
    """
    for shape in slide.shapes:
        if shape.shape_type == 13:  # MSO_SHAPE_TYPE.PICTURE
            return shape.image.blob
    # 이미지 없는 슬라이드 — 경로 추적용 최소 PNG 헤더
    return b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR" + b"\x00" * 17


def _extract_page_images_pdf(file_path: str, dpi: int = 150) -> list[dict]:
    """PDF 페이지를 PNG bytes 목록으로 변환한다.

    Returns:
        [{"page_number": 1, "image_bytes": b"..."}, ...]  (1-indexed)
    """
    import fitz  # PyMuPDF

    result: list[dict] = []
    with fitz.open(file_path) as doc:
        for i, page in enumerate(doc):
            mat = fitz.Matrix(dpi / 72, dpi / 72)
            pixmap = page.get_pixmap(matrix=mat)
            result.append({
                "page_number": i + 1,
                "image_bytes": pixmap.tobytes("png"),
            })
    return result


def _extract_page_images_pptx(file_path: str) -> list[dict]:
    """PPTX 슬라이드를 PNG bytes 목록으로 변환한다.

    Returns:
        [{"page_number": 1, "image_bytes": b"..."}, ...]  (1-indexed)
    """
    import pptx

    prs = pptx.Presentation(file_path)
    result: list[dict] = []
    for i, slide in enumerate(prs.slides):
        result.append({
            "page_number": i + 1,
            "image_bytes": _render_slide_to_png(slide),
        })
    return result


def _convert_to_pdf_with_libreoffice(file_path: str) -> tuple[str, str]:
    """LibreOffice headless로 DOCX/PPTX를 PDF로 변환한다.

    Returns:
        (pdf_path, tmp_dir) — 호출자가 tmp_dir을 shutil.rmtree로 정리해야 함.
    Raises:
        RuntimeError: LibreOffice 변환 실패 시
    """
    tmp_dir = tempfile.mkdtemp()
    result = subprocess.run(
        ["libreoffice", "--headless", "--convert-to", "pdf", "--outdir", tmp_dir, file_path],
        capture_output=True,
        text=True,
        timeout=120,
    )
    if result.returncode != 0:
        raise RuntimeError(f"LibreOffice 변환 실패 (code={result.returncode}): {result.stderr}")

    pdf_name = Path(file_path).stem + ".pdf"
    pdf_path = os.path.join(tmp_dir, pdf_name)
    if not os.path.exists(pdf_path):
        raise RuntimeError(f"LibreOffice PDF 출력 파일 없음: {pdf_path}")

    return pdf_path, tmp_dir


def _extract_page_images_docx(file_path: str, dpi: int = 150) -> list[dict]:
    """DOCX/PPTX를 LibreOffice로 PDF 변환 후 페이지 이미지를 추출한다.

    LibreOffice가 없으면 RuntimeError가 전파됩니다.

    Returns:
        [{"page_number": 1, "image_bytes": b"..."}, ...]  (1-indexed)
    """
    pdf_path, tmp_dir = _convert_to_pdf_with_libreoffice(file_path)
    try:
        return _extract_page_images_pdf(pdf_path, dpi=dpi)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
