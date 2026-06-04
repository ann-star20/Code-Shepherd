"""G2 테스트 — HttpCrawler fetch + chunk.

T_crawl_returns_text:      fetch → HTML <p>Hello</p> → "Hello" in content
T_crawl_strips_script:     <script>alert(1)</script> 제거
T_crawl_captures_etag:     ETag 헤더 보존
T_chunk_splits:            10000자 → chunks >= 3, 각 <= 3500자
T_chunk_merges_short_tail: 마지막 단락 200자 → 병합 후 >= 500자
"""

import pytest
from unittest.mock import AsyncMock, MagicMock

from app.infrastructure.crawler.http_crawler import CrawlResult, fetch, chunk


# ── T_crawl_returns_text ──────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_T_crawl_returns_text():
    """Arrange: aiohttp mock → 200 + <p>Hello</p>.
    Act: fetch(url, session).
    Assert: "Hello" in result.content.
    """
    html = "<html><body><p>Hello</p></body></html>"
    mock_response = MagicMock()
    mock_response.status = 200
    mock_response.headers = {}
    mock_response.text = AsyncMock(return_value=html)

    mock_session = MagicMock()
    mock_session.get = MagicMock(
        return_value=AsyncMock(
            __aenter__=AsyncMock(return_value=mock_response),
            __aexit__=AsyncMock(return_value=False),
        )
    )

    result = await fetch("https://example.com/", mock_session)

    assert isinstance(result, CrawlResult)
    assert "Hello" in result.content
    assert result.status_code == 200


# ── T_crawl_strips_script ─────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_T_crawl_strips_script():
    """Arrange: HTML with <script>alert(1)</script>.
    Act: fetch(url, session).
    Assert: "alert" not in result.content.
    """
    html = "<html><body><p>Safe</p><script>alert(1)</script></body></html>"
    mock_response = MagicMock()
    mock_response.status = 200
    mock_response.headers = {}
    mock_response.text = AsyncMock(return_value=html)

    mock_session = MagicMock()
    mock_session.get = MagicMock(
        return_value=AsyncMock(
            __aenter__=AsyncMock(return_value=mock_response),
            __aexit__=AsyncMock(return_value=False),
        )
    )

    result = await fetch("https://example.com/", mock_session)

    assert "alert" not in result.content


# ── T_crawl_captures_etag ─────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_T_crawl_captures_etag():
    """Arrange: response header ETag: "abc123".
    Act: fetch(url, session).
    Assert: result.etag == "abc123".
    """
    html = "<html><body><p>Content</p></body></html>"
    mock_response = MagicMock()
    mock_response.status = 200
    mock_response.headers = {"ETag": "abc123"}
    mock_response.text = AsyncMock(return_value=html)

    mock_session = MagicMock()
    mock_session.get = MagicMock(
        return_value=AsyncMock(
            __aenter__=AsyncMock(return_value=mock_response),
            __aexit__=AsyncMock(return_value=False),
        )
    )

    result = await fetch("https://example.com/", mock_session)

    assert result.etag == "abc123"


# ── T_chunk_splits ────────────────────────────────────────────────────────────


def test_T_chunk_splits():
    """Arrange: 10000자 콘텐츠 (단락 구분 포함).
    Act: chunk(content, 3000).
    Assert: len(chunks) >= 3, 각 chunk <= 3500자.
    """
    paragraph = "가" * 600
    content = "\n\n".join([paragraph] * 15)

    chunks = chunk(content, max_chars=3000)

    assert len(chunks) >= 3, f"청크 수 {len(chunks)} < 3"
    for i, c in enumerate(chunks):
        assert len(c) <= 3500, f"청크[{i}] {len(c)}자 > 3500자"


# ── T_chunk_merges_short_tail ─────────────────────────────────────────────────


def test_T_chunk_merges_short_tail():
    """Arrange: 주 단락들 + 마지막 단락 200자.
    Act: chunk(content, 3000).
    Assert: 마지막 chunk >= 500자 (짧은 꼬리 병합됨).
    """
    main_paragraph = "나" * 800
    short_tail = "다" * 200
    content = "\n\n".join([main_paragraph] * 5 + [short_tail])

    chunks = chunk(content, max_chars=3000)

    assert len(chunks[-1]) >= 500, f"마지막 청크 {len(chunks[-1])}자 < 500자 (병합 실패)"
