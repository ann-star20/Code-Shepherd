"""
Storage 추상화 레이어

환경변수 STORAGE_BACKEND 로 백엔드 전환:
  local  — 로컬 파일시스템 (개발 환경 기본값)
  gcs    — Google Cloud Storage (팀 공유 환경)
"""

from __future__ import annotations

import asyncio
import os
from abc import ABC, abstractmethod
from pathlib import Path

import aiofiles
import aiofiles.os


class Storage(ABC):
    @abstractmethod
    async def save(self, path: str, content: bytes) -> str:
        """파일을 저장하고 저장된 경로(또는 GCS URI)를 반환."""

    @abstractmethod
    async def load(self, path: str) -> bytes:
        """저장된 파일을 바이트로 반환."""

    @abstractmethod
    async def exists(self, path: str) -> bool:
        """경로에 파일이 존재하는지 확인."""


class LocalStorage(Storage):
    """로컬 파일시스템 기반 Storage (개발 환경 / GCS 미세팅 시)."""

    def __init__(self, base_dir: str | None = None) -> None:
        self.base_dir = Path(
            base_dir or os.getenv("LOCAL_STORAGE_PATH", "./data/storage")
        ).resolve()
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _resolve_path(self, path: str) -> Path:
        full_path = (self.base_dir / path).resolve()
        if full_path != self.base_dir and self.base_dir not in full_path.parents:
            raise ValueError(f"Path is outside storage base: {path}")
        return full_path

    async def save(self, path: str, content: bytes) -> str:
        full_path = self._resolve_path(path)
        await asyncio.to_thread(full_path.parent.mkdir, parents=True, exist_ok=True)
        async with aiofiles.open(full_path, "wb") as f:
            await f.write(content)
        return str(full_path)

    async def load(self, path: str) -> bytes:
        full_path = self._resolve_path(path)
        if not await aiofiles.os.path.exists(full_path):
            raise FileNotFoundError(f"저장소에 파일 없음: {path}")
        async with aiofiles.open(full_path, "rb") as f:
            return await f.read()

    async def exists(self, path: str) -> bool:
        return await aiofiles.os.path.exists(self._resolve_path(path))


class GCSStorage(Storage):
    """Google Cloud Storage 기반 Storage (팀 공유 환경)."""

    def __init__(
        self,
        bucket_name: str | None = None,
        key_path: str | None = None,
    ) -> None:
        from google.cloud import storage as gcs

        self.bucket_name = bucket_name or os.getenv("GCS_BUCKET", "tasklink-kms-storage")
        project = os.getenv("GCS_PROJECT") or os.getenv("GOOGLE_CLOUD_PROJECT")
        key_file = key_path or os.getenv("GCS_KEY_PATH", "")

        if key_file and os.path.exists(key_file):
            from google.oauth2 import service_account
            credentials = service_account.Credentials.from_service_account_file(key_file)
            self._client = gcs.Client(project=project, credentials=credentials)
        else:
            # ADC: GOOGLE_APPLICATION_CREDENTIALS 파일을 명시적으로 로드 (자동탐지 우회)
            adc_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
            if adc_path and os.path.isfile(adc_path):
                from google.oauth2.credentials import Credentials as UserCredentials
                credentials = UserCredentials.from_authorized_user_file(adc_path)
                self._client = gcs.Client(project=project, credentials=credentials)
            else:
                # Cloud Run: 메타데이터 서버 자동 인증
                self._client = gcs.Client(project=project)

        self._bucket = self._client.bucket(self.bucket_name)

    async def save(self, path: str, content: bytes) -> str:
        blob = self._bucket.blob(path)
        await asyncio.to_thread(blob.upload_from_string, content)
        return f"gs://{self.bucket_name}/{path}"

    async def load(self, path: str) -> bytes:
        blob = self._bucket.blob(path)
        exists = await asyncio.to_thread(blob.exists)
        if not exists:
            raise FileNotFoundError(f"GCS에 파일 없음: gs://{self.bucket_name}/{path}")
        return await asyncio.to_thread(blob.download_as_bytes)

    async def exists(self, path: str) -> bool:
        blob = self._bucket.blob(path)
        return await asyncio.to_thread(blob.exists)


def get_storage() -> Storage:
    """환경변수 STORAGE_BACKEND 에 따라 Storage 구현체를 반환."""
    backend = os.getenv("STORAGE_BACKEND", "local").lower()
    if backend == "local":
        return LocalStorage()
    if backend == "gcs":
        return GCSStorage()
    raise NotImplementedError(f"지원하지 않는 STORAGE_BACKEND: {backend} (local 또는 gcs)")
