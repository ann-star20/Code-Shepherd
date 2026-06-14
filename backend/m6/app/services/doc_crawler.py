"""외부 문서 크롤러 — URL에서 텍스트 추출 스텁."""

import httpx


async def fetch_text(url: str) -> str:
    """URL에서 원시 텍스트 추출 (스텁 — HTML 파싱 미구현)."""
    # TODO: BeautifulSoup 또는 trafilatura로 본문 추출
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.get(url)
        response.raise_for_status()
    return response.text
