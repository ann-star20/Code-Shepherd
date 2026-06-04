"""m1 테스트 픽스처."""

import os

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

# 테스트용 웹훅 시크릿
os.environ.setdefault("GITHUB_WEBHOOK_SECRET", "test-webhook-secret")

from app.main import app  # noqa: E402


@pytest_asyncio.fixture
async def client() -> AsyncClient:
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac
