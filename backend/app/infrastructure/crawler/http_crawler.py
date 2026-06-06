"""HTTP 크롤러 — 섹션 기반 청크 분할.

청크 전략:
  - 전체 텍스트 < SINGLE_CHUNK_LIMIT → 청크 없이 1개로 반환 (LLM 1회 호출)
  - 이상     → HTML h1/h2/h3 헤딩 기준으로 섹션 분할
  - 섹션이 여전히 크면 → 단락 단위 재분할 (SECTION_MAX_CHARS 기준)
"""

from __future__ import annotations

from dataclasses import dataclass

import aiohttp
from bs4 import BeautifulSoup, Tag

SINGLE_CHUNK_LIMIT = 80_000   # 이하면 전체를 LLM 1회에 처리
SECTION_MAX_CHARS  = 12_000   # 섹션 하나가 이 크기 초과 시 단락 재분할
HEADING_TAGS       = {"h1", "h2", "h3"}


@dataclass
class CrawlResult:
    url: str
    content: str        # 전체 텍스트 (fallback용)
    html: str           # 원본 HTML (섹션 분할용)
    etag: str | None
    status_code: int


async def fetch(url: str, session: aiohttp.ClientSession) -> CrawlResult:
    async with session.get(url) as resp:
        html = await resp.text()
        etag = resp.headers.get("ETag")
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style", "nav", "footer"]):
            tag.decompose()
        content = soup.get_text(separator="\n")
        return CrawlResult(
            url=url,
            content=content,
            html=html,
            etag=etag,
            status_code=resp.status,
        )


def smart_chunk(result: CrawlResult) -> list[str]:
    """전체 크기에 따라 단일 청크 or 섹션 분할을 자동 선택한다."""
    text = result.content.strip()
    if len(text) <= SINGLE_CHUNK_LIMIT:
        return [text]
    return chunk_by_sections(result.html) or [text]


def chunk_by_sections(html: str) -> list[str]:
    """HTML h1/h2/h3 헤딩 기준으로 섹션을 분리한다.

    각 섹션 = 헤딩 텍스트 + 다음 헤딩 전까지의 본문.
    섹션이 SECTION_MAX_CHARS 초과 시 단락 단위로 재분할.
    """
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "footer"]):
        tag.decompose()

    body = soup.find("body") or soup
    sections: list[str] = []
    current_heading = ""
    current_parts: list[str] = []

    for elem in body.descendants:
        if not isinstance(elem, Tag):
            continue
        if elem.name in HEADING_TAGS:
            if current_parts:
                _flush_section(current_heading, current_parts, sections)
            current_heading = elem.get_text(separator=" ", strip=True)
            current_parts = []
        elif elem.name in {"p", "pre", "code", "li", "blockquote"}:
            text = elem.get_text(separator=" ", strip=True)
            if text:
                current_parts.append(text)

    if current_parts:
        _flush_section(current_heading, current_parts, sections)

    return sections


def _flush_section(heading: str, parts: list[str], out: list[str]) -> None:
    """섹션 텍스트를 조합하고 크기 초과 시 단락 단위로 재분할한다."""
    prefix = f"## {heading}\n\n" if heading else ""
    full   = (prefix + "\n".join(parts)).strip()

    if len(full) <= SECTION_MAX_CHARS:
        out.append(full)
        return

    sub = prefix
    for part in parts:
        if len(sub) + len(part) > SECTION_MAX_CHARS and sub.strip():
            out.append(sub.strip())
            sub = part + "\n"
        else:
            sub += part + "\n"
    if sub.strip():
        out.append(sub.strip())


# ── 하위 호환 (tasks.py의 chunk() 호출 유지) ────────────────────────────────

def chunk(content: str, max_chars: int = 3000) -> list[str]:
    """단락 기반 고정 크기 분할 — 하위 호환용. smart_chunk 권장."""
    paragraphs = content.split("\n\n")
    chunks: list[str] = []
    current = ""
    for para in paragraphs:
        if len(current) + len(para) + 2 <= max_chars:
            current = (current + "\n\n" + para).lstrip("\n")
        else:
            if current:
                chunks.append(current)
            current = para
    if current:
        chunks.append(current)
    if len(chunks) >= 2 and len(chunks[-1]) < 500:
        chunks[-2] += "\n\n" + chunks[-1]
        chunks.pop()
    return chunks
