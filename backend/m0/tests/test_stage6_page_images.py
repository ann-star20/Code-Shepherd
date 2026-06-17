"""TDD (RED): Stage6 — 페이지 이미지 GCS 저장 + chunk metadata 연결 검증.

테스트 대상:
    _save_page_images(doc_id, page_images, storage)
        → images/{doc_id}/page_{n}.png 경로로 GCS 저장, 경로 목록 반환
    _insert_embedding_rows(...) metadata에 page_image_path 포함
    stage6_store() 반환 storage_paths["page_images"] 포함

User Journey:
    As a KMS pipeline Stage 6, I want to upload per-page images extracted in Stage 1
    to GCS under images/{doc_id}/page_N.png, so that multimodal RAG can later fetch
    the image alongside the text chunk.

ALL TESTS SHOULD FAIL UNTIL:
    1. _save_page_images() is added to stage6_store.py
    2. _insert_embedding_rows() adds page_image_path to metadata
    3. stage6_store() calls _save_page_images and includes page_images in storage_paths
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, call, patch


PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 20

DOC_ID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"

FAKE_PAGE_IMAGES = [
    {"page_number": 1, "image_bytes": PNG_BYTES},
    {"page_number": 2, "image_bytes": PNG_BYTES},
    {"page_number": 3, "image_bytes": PNG_BYTES},
]


def _make_mock_storage() -> MagicMock:
    storage = MagicMock()
    storage.save = AsyncMock(return_value=None)
    return storage


# ---------------------------------------------------------------------------
# User Journey 1: _save_page_images — GCS 저장 경로 계약
# ---------------------------------------------------------------------------

class TestSavePageImages:
    """_save_page_images(doc_id, page_images, storage) 반환값 및 호출 계약."""

    async def test_returns_list_of_paths(self):
        """저장된 GCS 경로 목록을 반환해야 한다."""
        from app.pipeline.stage6_store import _save_page_images

        storage = _make_mock_storage()
        paths = await _save_page_images(DOC_ID, FAKE_PAGE_IMAGES, storage)

        assert isinstance(paths, list), "반환값은 list여야 합니다"
        assert len(paths) == 3, f"3개 이미지 → 3개 경로 기대, 실제: {len(paths)}"

    async def test_paths_follow_naming_convention(self):
        """경로는 images/{doc_id}/page_{n}.png 패턴이어야 한다."""
        from app.pipeline.stage6_store import _save_page_images

        storage = _make_mock_storage()
        paths = await _save_page_images(DOC_ID, FAKE_PAGE_IMAGES[:1], storage)

        expected = f"images/{DOC_ID}/page_1.png"
        assert paths[0] == expected, f"경로 패턴 불일치: 기대={expected}, 실제={paths[0]}"

    async def test_all_pages_stored_with_correct_paths(self):
        """모든 페이지가 올바른 경로로 저장되어야 한다."""
        from app.pipeline.stage6_store import _save_page_images

        storage = _make_mock_storage()
        paths = await _save_page_images(DOC_ID, FAKE_PAGE_IMAGES, storage)

        expected = [
            f"images/{DOC_ID}/page_1.png",
            f"images/{DOC_ID}/page_2.png",
            f"images/{DOC_ID}/page_3.png",
        ]
        assert paths == expected

    async def test_storage_save_called_for_each_image(self):
        """storage.save가 각 이미지마다 한 번씩 호출되어야 한다."""
        from app.pipeline.stage6_store import _save_page_images

        storage = _make_mock_storage()
        await _save_page_images(DOC_ID, FAKE_PAGE_IMAGES, storage)

        assert storage.save.call_count == 3, (
            f"storage.save 3회 기대, 실제: {storage.save.call_count}"
        )

    async def test_storage_save_called_with_correct_bytes(self):
        """storage.save에 올바른 경로와 bytes가 전달되어야 한다."""
        from app.pipeline.stage6_store import _save_page_images

        storage = _make_mock_storage()
        await _save_page_images(DOC_ID, FAKE_PAGE_IMAGES[:1], storage)

        storage.save.assert_called_once_with(
            f"images/{DOC_ID}/page_1.png",
            PNG_BYTES,
        )

    async def test_empty_page_images_returns_empty_list(self):
        """빈 page_images → 빈 경로 목록, storage.save 미호출."""
        from app.pipeline.stage6_store import _save_page_images

        storage = _make_mock_storage()
        paths = await _save_page_images(DOC_ID, [], storage)

        assert paths == []
        storage.save.assert_not_called()

    async def test_none_page_images_returns_empty_list(self):
        """page_images=None → 빈 경로 목록."""
        from app.pipeline.stage6_store import _save_page_images

        storage = _make_mock_storage()
        paths = await _save_page_images(DOC_ID, None, storage)

        assert paths == []


# ---------------------------------------------------------------------------
# User Journey 2: _insert_embedding_rows — page_image_path metadata 연결
# ---------------------------------------------------------------------------

class TestInsertEmbeddingRowsPageImagePath:
    """chunk_embeddings.metadata에 page_image_path가 포함되는지 검증."""

    def _make_session(self) -> MagicMock:
        session = MagicMock()
        session.execute = AsyncMock()
        return session

    def _make_chunk_with_page(self, page_number: int) -> dict:
        return {
            "chunk_id": "chunk-uuid-0001",
            "chunk_type": "child",
            "content": "테스트 내용",
            "page_number": page_number,
            "section_header": "1. 개요",
        }

    async def test_metadata_includes_page_image_path_when_page_number_set(self):
        """page_number가 있는 chunk는 metadata에 page_image_path가 포함되어야 한다."""
        from app.pipeline.stage6_store import _insert_embedding_rows

        session = self._make_session()
        chunk = self._make_chunk_with_page(2)
        rows = [(chunk, [0.1] * 1024)]
        metadata = {"category": "아키텍처", "team": "백엔드팀", "tags": []}

        await _insert_embedding_rows(
            session,
            rows,
            metadata,
            doc_id=DOC_ID,
        )

        assert session.execute.called, "session.execute가 호출되어야 합니다"
        call_args = session.execute.call_args
        embed_rows = call_args[0][1]  # positional 두 번째 인자
        row_metadata = json.loads(embed_rows[0]["metadata"])

        assert "page_image_path" in row_metadata, (
            "metadata에 page_image_path 키가 없습니다"
        )
        expected_path = f"images/{DOC_ID}/page_2.png"
        assert row_metadata["page_image_path"] == expected_path, (
            f"page_image_path 불일치: 기대={expected_path}, 실제={row_metadata['page_image_path']}"
        )

    async def test_metadata_page_image_path_none_when_no_page_number(self):
        """page_number가 없는 chunk는 page_image_path가 None이어야 한다."""
        from app.pipeline.stage6_store import _insert_embedding_rows

        session = self._make_session()
        chunk = {
            "chunk_id": "chunk-uuid-0002",
            "chunk_type": "child",
            "content": "내용",
            "page_number": None,
            "section_header": None,
        }
        rows = [(chunk, [0.1] * 1024)]
        metadata = {"category": "기타", "team": None, "tags": []}

        await _insert_embedding_rows(session, rows, metadata, doc_id=DOC_ID)

        call_args = session.execute.call_args
        embed_rows = call_args[0][1]
        row_metadata = json.loads(embed_rows[0]["metadata"])

        assert row_metadata.get("page_image_path") is None


# ---------------------------------------------------------------------------
# User Journey 3: stage6_store — storage_paths["page_images"] 반환
# ---------------------------------------------------------------------------

class TestStage6StorePageImagePaths:
    """stage6_store()가 storage_paths에 page_images를 포함해서 반환하는지 검증."""

    def _make_minimal_state(self, with_page_images: bool = True) -> dict:
        state = {
            "doc_id": DOC_ID,
            "file_path": "/tmp/test.pdf",
            "file_type": "pdf",
            "original_filename": "test.pdf",
            "markdown_storage_path": f"markdown/{DOC_ID}/raw.md",
            "chunks": [],
            "metadata": {"category": "아키텍처", "team": None, "tags": []},
            "neo4j_entities": [],
            "neo4j_relations": [],
        }
        if with_page_images:
            state["page_images"] = FAKE_PAGE_IMAGES
        else:
            state["page_images"] = None
        return state

    def _make_mock_factory(self):
        factory = MagicMock()
        session = MagicMock()
        session.__aenter__ = AsyncMock(return_value=session)
        session.__aexit__ = AsyncMock(return_value=False)
        session.execute = AsyncMock()
        session.commit = AsyncMock()
        session.begin = MagicMock()
        ctx = MagicMock()
        ctx.__aenter__ = AsyncMock(return_value=None)
        ctx.__aexit__ = AsyncMock(return_value=False)
        session.begin.return_value = ctx
        factory.return_value = session
        return factory, session

    async def test_storage_paths_contains_page_images_key(self):
        """반환값 storage_paths에 page_images 키가 있어야 한다."""
        from app.pipeline.stage6_store import stage6_store

        factory, _ = self._make_mock_factory()
        storage = _make_mock_storage()
        state = self._make_minimal_state(with_page_images=True)

        with (
            patch("app.pipeline.stage6_store._precompute_embeddings", new=AsyncMock(return_value=([], "bge-m3"))),
            patch("app.pipeline.stage6_store._save_document", new=AsyncMock()),
            patch("app.pipeline.stage6_store._save_chunks", new=AsyncMock()),
            patch("app.pipeline.stage6_store._insert_embedding_rows", new=AsyncMock()),
            patch("app.pipeline.stage6_store._save_to_neo4j", new=AsyncMock(return_value=True)),
            patch("app.pipeline.stage6_store._save_page_images", new=AsyncMock(
                return_value=[f"images/{DOC_ID}/page_1.png"]
            )),
            patch("aiofiles.open"),
        ):
            result = await stage6_store(state, factory, storage)

        assert "storage_paths" in result
        assert "page_images" in result["storage_paths"], (
            "storage_paths에 page_images 키가 없습니다"
        )

    async def test_storage_paths_page_images_is_list(self):
        """storage_paths['page_images']는 list여야 한다."""
        from app.pipeline.stage6_store import stage6_store

        factory, _ = self._make_mock_factory()
        storage = _make_mock_storage()
        state = self._make_minimal_state(with_page_images=True)

        expected_paths = [f"images/{DOC_ID}/page_{i}.png" for i in range(1, 4)]

        with (
            patch("app.pipeline.stage6_store._precompute_embeddings", new=AsyncMock(return_value=([], "bge-m3"))),
            patch("app.pipeline.stage6_store._save_document", new=AsyncMock()),
            patch("app.pipeline.stage6_store._save_chunks", new=AsyncMock()),
            patch("app.pipeline.stage6_store._insert_embedding_rows", new=AsyncMock()),
            patch("app.pipeline.stage6_store._save_to_neo4j", new=AsyncMock(return_value=True)),
            patch("app.pipeline.stage6_store._save_page_images", new=AsyncMock(return_value=expected_paths)),
            patch("aiofiles.open"),
        ):
            result = await stage6_store(state, factory, storage)

        page_images_paths = result["storage_paths"]["page_images"]
        assert isinstance(page_images_paths, list)
        assert page_images_paths == expected_paths

    async def test_no_page_images_in_state_returns_empty_list(self):
        """state에 page_images=None이면 storage_paths['page_images']는 []이어야 한다."""
        from app.pipeline.stage6_store import stage6_store

        factory, _ = self._make_mock_factory()
        storage = _make_mock_storage()
        state = self._make_minimal_state(with_page_images=False)

        with (
            patch("app.pipeline.stage6_store._precompute_embeddings", new=AsyncMock(return_value=([], "bge-m3"))),
            patch("app.pipeline.stage6_store._save_document", new=AsyncMock()),
            patch("app.pipeline.stage6_store._save_chunks", new=AsyncMock()),
            patch("app.pipeline.stage6_store._insert_embedding_rows", new=AsyncMock()),
            patch("app.pipeline.stage6_store._save_to_neo4j", new=AsyncMock(return_value=True)),
            patch("app.pipeline.stage6_store._save_page_images", new=AsyncMock(return_value=[])),
            patch("aiofiles.open"),
        ):
            result = await stage6_store(state, factory, storage)

        assert result["storage_paths"]["page_images"] == []
