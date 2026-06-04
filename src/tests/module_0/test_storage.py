from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch, AsyncMock

from module_0_kms.storage import LocalStorage, GCSStorage, get_storage


@pytest.mark.asyncio
async def test_local_storage_rejects_paths_outside_base_dir(tmp_path):
    storage = LocalStorage(str(tmp_path / "storage"))

    with pytest.raises(ValueError, match="outside storage base"):
        await storage.save("../escape.txt", b"nope")

    assert not (tmp_path / "escape.txt").exists()


@pytest.mark.asyncio
async def test_save_and_load_roundtrip(tmp_path):
    storage = LocalStorage(str(tmp_path / "storage"))
    content = b"Hello, KMS!"
    await storage.save("docs/test.txt", content)
    loaded = await storage.load("docs/test.txt")
    assert loaded == content


@pytest.mark.asyncio
async def test_load_missing_file_raises(tmp_path):
    storage = LocalStorage(str(tmp_path / "storage"))
    with pytest.raises(FileNotFoundError):
        await storage.load("nonexistent.txt")


@pytest.mark.asyncio
async def test_exists_returns_true_for_saved_file(tmp_path):
    storage = LocalStorage(str(tmp_path / "storage"))
    await storage.save("file.md", b"content")
    assert await storage.exists("file.md") is True


@pytest.mark.asyncio
async def test_exists_returns_false_for_missing_file(tmp_path):
    storage = LocalStorage(str(tmp_path / "storage"))
    assert await storage.exists("missing.md") is False


@pytest.mark.asyncio
async def test_save_creates_subdirectories(tmp_path):
    storage = LocalStorage(str(tmp_path / "storage"))
    await storage.save("deep/nested/path/file.md", b"content")
    assert await storage.exists("deep/nested/path/file.md") is True


def test_get_storage_returns_local_storage(monkeypatch):
    monkeypatch.setenv("STORAGE_BACKEND", "local")
    storage = get_storage()
    assert isinstance(storage, LocalStorage)


def test_get_storage_raises_for_unknown_backend(monkeypatch):
    monkeypatch.setenv("STORAGE_BACKEND", "s3")
    with pytest.raises(NotImplementedError, match="s3"):
        get_storage()


# ──────────────────────────────────────────────
# GCSStorage Mock 테스트 (실제 GCS 연결 없음)
# ──────────────────────────────────────────────

def _make_gcs_storage(mock_client: MagicMock, bucket_name: str = "test-bucket") -> GCSStorage:
    """GCSStorage를 Mock client로 생성하는 헬퍼."""
    with patch("google.cloud.storage.Client", return_value=mock_client):
        with patch.dict("os.environ", {
            "GCS_BUCKET": bucket_name,
            "GCS_PROJECT": "test-project",
            "STORAGE_BACKEND": "gcs",
        }):
            storage = GCSStorage(bucket_name=bucket_name)
    return storage


def test_gcs_storage_save_returns_gs_uri():
    mock_client = MagicMock()
    mock_bucket = MagicMock()
    mock_blob = MagicMock()
    mock_client.bucket.return_value = mock_bucket
    mock_bucket.blob.return_value = mock_blob

    storage = _make_gcs_storage(mock_client, "my-bucket")
    storage._bucket = mock_bucket

    import asyncio
    result = asyncio.get_event_loop().run_until_complete(
        storage.save("docs/test.pdf", b"pdf-content")
    )

    assert result == "gs://my-bucket/docs/test.pdf"
    mock_bucket.blob.assert_called_once_with("docs/test.pdf")
    mock_blob.upload_from_string.assert_called_once_with(b"pdf-content")


def test_gcs_storage_load_returns_bytes():
    mock_client = MagicMock()
    mock_bucket = MagicMock()
    mock_blob = MagicMock()
    mock_blob.exists.return_value = True
    mock_blob.download_as_bytes.return_value = b"file-bytes"
    mock_client.bucket.return_value = mock_bucket
    mock_bucket.blob.return_value = mock_blob

    storage = _make_gcs_storage(mock_client)
    storage._bucket = mock_bucket

    import asyncio
    result = asyncio.get_event_loop().run_until_complete(
        storage.load("docs/test.pdf")
    )

    assert result == b"file-bytes"


def test_gcs_storage_load_raises_when_file_missing():
    mock_client = MagicMock()
    mock_bucket = MagicMock()
    mock_blob = MagicMock()
    mock_blob.exists.return_value = False
    mock_client.bucket.return_value = mock_bucket
    mock_bucket.blob.return_value = mock_blob

    storage = _make_gcs_storage(mock_client)
    storage._bucket = mock_bucket

    import asyncio
    with pytest.raises(FileNotFoundError, match="GCS에 파일 없음"):
        asyncio.get_event_loop().run_until_complete(
            storage.load("missing.pdf")
        )


def test_gcs_storage_exists_true_when_blob_exists():
    mock_client = MagicMock()
    mock_bucket = MagicMock()
    mock_blob = MagicMock()
    mock_blob.exists.return_value = True
    mock_client.bucket.return_value = mock_bucket
    mock_bucket.blob.return_value = mock_blob

    storage = _make_gcs_storage(mock_client)
    storage._bucket = mock_bucket

    import asyncio
    result = asyncio.get_event_loop().run_until_complete(
        storage.exists("docs/file.md")
    )
    assert result is True


def test_gcs_storage_exists_false_when_blob_missing():
    mock_client = MagicMock()
    mock_bucket = MagicMock()
    mock_blob = MagicMock()
    mock_blob.exists.return_value = False
    mock_client.bucket.return_value = mock_bucket
    mock_bucket.blob.return_value = mock_blob

    storage = _make_gcs_storage(mock_client)
    storage._bucket = mock_bucket

    import asyncio
    result = asyncio.get_event_loop().run_until_complete(
        storage.exists("missing.md")
    )
    assert result is False


def test_get_storage_returns_gcs_storage(monkeypatch):
    mock_client = MagicMock()
    mock_bucket = MagicMock()
    mock_client.bucket.return_value = mock_bucket

    monkeypatch.setenv("STORAGE_BACKEND", "gcs")
    monkeypatch.setenv("GCS_BUCKET", "test-bucket")
    monkeypatch.setenv("GCS_PROJECT", "test-project")

    with patch("google.cloud.storage.Client", return_value=mock_client):
        storage = get_storage()

    assert isinstance(storage, GCSStorage)
