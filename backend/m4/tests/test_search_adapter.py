"""RAG 검색 어댑터 단위 테스트 — PgvectorAdapter 빈 embedding 처리 (Mock 기반, 실 DB 없이)."""

from unittest.mock import AsyncMock

import pytest

from app.kms.search_adapter import PgvectorAdapter


@pytest.mark.asyncio
async def test_pgvector_adapter_search_with_empty_embedding_returns_empty_list():
    """curator_agent가 query_fields의 한 카테고리에 빈 문자열을 반환하면 embed_query("")가
    embedding=[]을 돌려준다 (Ollama 동작). 이 경우 PgvectorAdapter.search()가
    'CAST([] AS vector)'를 Postgres에 보내면 asyncpg.exceptions.DataError
    ("vector must have at least 1 dimension")가 발생한다 — 빈 embedding은 DB를 거치지
    않고 빈 결과로 처리해야 한다 (재생성 중 실제로 발생한 버그)."""
    session = AsyncMock()
    session.execute.side_effect = AssertionError("empty embedding should not reach the DB")
    adapter = PgvectorAdapter(session)

    results = await adapter.search(embedding=[], category="코드성능검증")

    assert results == []
