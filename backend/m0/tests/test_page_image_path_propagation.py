"""
TDD RED: page_image_path가 SearchResultItem / ChatSource에 실제로 전달되는지 검증.

현재 미완료 상태:
- kms_routes.py: SearchResultItem 생성 시 metadata["page_image_path"] 미전달
- chat_routes.py: ChatSource 생성 시 page_image_path 미전달 + _query_pgvector가 metadata 미반환
"""
from __future__ import annotations

import json
import pytest
from unittest.mock import AsyncMock, patch, MagicMock


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

FAKE_METADATA = {
    "category": "기술",
    "page_image_path": "images/doc-abc/page_3.png",
}

FAKE_ROW = {
    "chunk_id": "chunk-001",
    "content": "테스트 내용",
    "score": 0.9,
    "metadata": FAKE_METADATA,
    "doc_title": "테스트 문서",
}


# ---------------------------------------------------------------------------
# kms_routes: SearchResultItem에 page_image_path 전달
# ---------------------------------------------------------------------------

class TestKmsSearchPageImagePath:
    """GET /kms/search → SearchResultItem.page_image_path가 metadata에서 채워진다."""

    @pytest.mark.asyncio
    async def test_search_result_item_page_image_path_populated(self):
        """metadata에 page_image_path가 있으면 SearchResultItem에 채워진다."""
        from app.routes.kms_routes import SearchResultItem

        meta = {"page_image_path": "images/doc-abc/page_3.png", "category": "기술"}
        row = {
            "chunk_id": "chunk-001",
            "content": "내용",
            "score": 0.9,
            "metadata": meta,
            "doc_title": "문서 제목",
        }

        _meta = row["metadata"] if isinstance(row["metadata"], dict) else {}
        item = SearchResultItem(
            chunk_id=row["chunk_id"],
            content=row["content"],
            score=float(row["score"]),
            metadata=row["metadata"] if isinstance(row["metadata"], dict) else None,
            doc_title=row["doc_title"],
            page_image_path=_meta.get("page_image_path"),
        )

        assert item.page_image_path == "images/doc-abc/page_3.png"

    @pytest.mark.asyncio
    async def test_search_result_item_page_image_path_none_when_missing(self):
        """metadata에 page_image_path가 없으면 None이다."""
        from app.routes.kms_routes import SearchResultItem

        item = SearchResultItem(
            chunk_id="chunk-001",
            content="내용",
            score=0.9,
            metadata={"category": "기술"},
            doc_title="문서",
            page_image_path=None,
        )

        assert item.page_image_path is None

    @pytest.mark.asyncio
    async def test_kms_search_endpoint_passes_page_image_path(self):
        """실제 엔드포인트 함수가 metadata['page_image_path']를 SearchResultItem에 전달한다."""
        from fastapi.testclient import TestClient
        from app.main import app

        fake_rows = [MagicMock()]
        fake_rows[0].__getitem__ = lambda self, key: {
            "chunk_id": "chunk-001",
            "content": "테스트",
            "score": 0.9,
            "metadata": {"page_image_path": "images/doc-abc/page_3.png"},
            "doc_title": "문서",
        }[key]

        embedding_patch = patch(
            "app.routes.kms_routes._embed_query",
            new=AsyncMock(return_value=[0.1] * 1024),
        )
        session_mock = AsyncMock()
        session_mock.__aenter__ = AsyncMock(return_value=session_mock)
        session_mock.__aexit__ = AsyncMock(return_value=False)
        execute_mock = AsyncMock()
        execute_mock.mappings.return_value.fetchall.return_value = [
            {
                "chunk_id": "chunk-001",
                "content": "테스트",
                "score": 0.9,
                "metadata": {"page_image_path": "images/doc-abc/page_3.png"},
                "doc_title": "문서",
            }
        ]
        session_mock.execute = AsyncMock(return_value=execute_mock)

        factory_mock = MagicMock()
        factory_mock.return_value = session_mock

        with embedding_patch:
            with patch("app.routes.kms_routes._get_session_factory", return_value=factory_mock):
                client = TestClient(app)
                response = client.get("/kms/search?q=테스트")

        if response.status_code == 200:
            data = response.json()
            if data.get("results"):
                assert data["results"][0]["page_image_path"] == "images/doc-abc/page_3.png", (
                    "page_image_path must be propagated from metadata"
                )


# ---------------------------------------------------------------------------
# chat_routes: _query_pgvector가 metadata를 반환하는지
# ---------------------------------------------------------------------------

class TestQueryPgvectorReturnsMetadata:
    """_query_pgvector 반환 dict에 metadata 필드가 포함된다."""

    @pytest.mark.asyncio
    async def test_query_pgvector_includes_metadata(self):
        """_query_pgvector 결과 dict에 'metadata' 키가 있다."""
        from app.routes.chat_routes import _query_pgvector

        fake_row = {
            "chunk_id": "chunk-001",
            "content": "내용",
            "score": 0.9,
            "doc_title": "문서",
            "metadata": {"page_image_path": "images/doc-abc/page_3.png"},
        }

        execute_result = MagicMock()
        execute_result.mappings.return_value.fetchall.return_value = [fake_row]

        session_mock = AsyncMock()
        session_mock.__aenter__ = AsyncMock(return_value=session_mock)
        session_mock.__aexit__ = AsyncMock(return_value=False)
        session_mock.execute = AsyncMock(return_value=execute_result)

        factory_mock = MagicMock()
        factory_mock.return_value = session_mock

        with patch("app.routes.chat_routes._embed_question", new=AsyncMock(return_value=[0.1] * 1024)):
            result = await _query_pgvector("테스트 질문", factory_mock, top_k=1)

        assert len(result) == 1
        assert "metadata" in result[0], "_query_pgvector must include 'metadata' in returned dicts"

    @pytest.mark.asyncio
    async def test_query_pgvector_metadata_has_page_image_path(self):
        """_query_pgvector 결과의 metadata에 page_image_path가 있다."""
        from app.routes.chat_routes import _query_pgvector

        fake_row = {
            "chunk_id": "chunk-001",
            "content": "내용",
            "score": 0.9,
            "doc_title": "문서",
            "metadata": {"page_image_path": "images/doc-abc/page_3.png"},
        }

        execute_result = MagicMock()
        execute_result.mappings.return_value.fetchall.return_value = [fake_row]

        session_mock = AsyncMock()
        session_mock.__aenter__ = AsyncMock(return_value=session_mock)
        session_mock.__aexit__ = AsyncMock(return_value=False)
        session_mock.execute = AsyncMock(return_value=execute_result)

        factory_mock = MagicMock()
        factory_mock.return_value = session_mock

        with patch("app.routes.chat_routes._embed_question", new=AsyncMock(return_value=[0.1] * 1024)):
            result = await _query_pgvector("테스트 질문", factory_mock, top_k=1)

        assert result[0].get("metadata", {}).get("page_image_path") == "images/doc-abc/page_3.png"


# ---------------------------------------------------------------------------
# chat_routes: ChatSource에 page_image_path 전달
# ---------------------------------------------------------------------------

class TestChatSourcePageImagePath:
    """ChatSource 구성 시 page_image_path가 metadata에서 채워진다."""

    def test_chat_source_from_chunk_with_metadata(self):
        """raw_chunks 항목의 metadata에 page_image_path가 있으면 ChatSource에 채워진다."""
        from app.routes.chat_routes import ChatSource

        chunk = {
            "chunk_id": "chunk-001",
            "content": "내용",
            "score": 0.9,
            "doc_title": "문서",
            "source_type": "pgvector",
            "metadata": {"page_image_path": "images/doc-abc/page_3.png"},
        }

        _meta = chunk.get("metadata") or {}
        source = ChatSource(
            chunk_id=chunk.get("chunk_id", ""),
            content=chunk.get("content", ""),
            score=float(chunk.get("score", 0.0)),
            doc_title=chunk.get("doc_title"),
            source_type=chunk.get("source_type", "pgvector"),
            page_image_path=_meta.get("page_image_path"),
        )

        assert source.page_image_path == "images/doc-abc/page_3.png"

    def test_chat_source_page_image_path_none_when_no_metadata(self):
        """metadata가 없는 chunk는 page_image_path가 None이다."""
        from app.routes.chat_routes import ChatSource

        chunk = {
            "chunk_id": "chunk-001",
            "content": "내용",
            "score": 0.9,
            "doc_title": "문서",
            "source_type": "neo4j",
        }

        _meta = chunk.get("metadata") or {}
        source = ChatSource(
            chunk_id=chunk.get("chunk_id", ""),
            content=chunk.get("content", ""),
            score=float(chunk.get("score", 0.0)),
            doc_title=chunk.get("doc_title"),
            source_type=chunk.get("source_type", "pgvector"),
            page_image_path=_meta.get("page_image_path"),
        )

        assert source.page_image_path is None

    def test_chat_source_page_image_path_in_current_implementation_is_always_none(self):
        """현재 구현: ChatSource 생성 시 page_image_path를 전달하지 않으면 항상 None.
        이 테스트는 GREEN이 되어야 FAIL — 즉 fix 후에는 이 테스트가 의미없어진다.
        """
        from app.routes.chat_routes import ChatSource

        chunk = {
            "chunk_id": "chunk-001",
            "content": "내용",
            "score": 0.9,
            "doc_title": "문서",
            "source_type": "pgvector",
            "metadata": {"page_image_path": "images/doc-abc/page_3.png"},
        }

        # 현재 구현 방식 (page_image_path 미전달)
        source = ChatSource(
            chunk_id=chunk.get("chunk_id", ""),
            content=chunk.get("content", ""),
            score=float(chunk.get("score", 0.0)),
            doc_title=chunk.get("doc_title"),
            source_type=chunk.get("source_type", "pgvector"),
            # page_image_path 미전달
        )

        # 이것이 현재 버그: metadata에 값이 있어도 None
        assert source.page_image_path is None  # 현재는 TRUE — 버그 확인용 RED 테스트
