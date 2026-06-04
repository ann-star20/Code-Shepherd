"""m1 테스트 픽스처."""

import os

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

# 테스트용 — compose .env 보다 우선
os.environ["GITHUB_WEBHOOK_SECRET"] = "test-webhook-secret"
os.environ["INTERNAL_SERVICE_TOKEN"] = "dev-internal-token"
os.environ["API_CORE_URL"] = "http://api-core:8000"

from shared.config import get_settings

get_settings.cache_clear()

from app.main import app  # noqa: E402


@pytest_asyncio.fixture
async def client() -> AsyncClient:
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac
