"""RAG 검색 어댑터 단위 테스트 — PgvectorAdapter 빈 embedding 처리 (Mock 기반, 실 DB 없이)."""

from unittest.mock import AsyncMock, MagicMock

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


@pytest.mark.asyncio
async def test_pgvector_adapter_search_joins_parent_chunk_content():
    """검색 결과에 부모 chunk의 content를 parent_content로 함께 반환한다 (RAG 검색 갭 백로그 —
    Child로 정밀 검색 + Parent를 컨텍스트로 보강). chunk_embeddings는 전부 chunk_type='child'이고
    chunks.parent_chunk_id로 부모 row를 가리킨다. PgvectorAdapter.search()는 chunks를 LEFT JOIN해
    parent.content를 parent_content로 함께 SELECT해야 build_card/ragas_eval이 더 넓은 맥락을
    참고할 수 있다."""
    mock_row = {
        "content": "child text",
        "metadata": {"category": "보안"},
        "parent_content": "parent text",
        "similarity": 0.9,
    }
    mock_result = MagicMock()
    mock_result.mappings.return_value.all.return_value = [mock_row]

    session = AsyncMock()
    session.execute = AsyncMock(return_value=mock_result)
    adapter = PgvectorAdapter(session)

    results = await adapter.search(embedding=[0.1, 0.2], category="보안")

    assert results == [mock_row]
    sql_text = str(session.execute.call_args.args[0])
    assert "parent_chunk_id" in sql_text
    assert "parent_content" in sql_text
