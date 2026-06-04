from dataclasses import dataclass

import aiohttp
from bs4 import BeautifulSoup


@dataclass
class CrawlResult:
    url: str
    content: str
    etag: str | None
    status_code: int


async def fetch(url: str, session: aiohttp.ClientSession) -> CrawlResult:
    async with session.get(url) as resp:
        html = await resp.text()
        etag = resp.headers.get("ETag")
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style"]):
            tag.decompose()
        content = soup.get_text(separator="\n")
        return CrawlResult(url=url, content=content, etag=etag, status_code=resp.status)


def chunk(content: str, max_chars: int = 3000) -> list[str]:
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
        chunks[-2] = chunks[-2] + "\n\n" + chunks[-1]
        chunks.pop()
    return chunks
