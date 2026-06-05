"""api-core 테스트 공통 픽스처 — 각 테스트마다 독립 인메모리 DB."""

from __future__ import annotations

import os

# 테스트 전용 토큰 — .env의 실제 시크릿이 덮어쓰기 전에 고정값으로 설정
os.environ["INTERNAL_SERVICE_TOKEN"] = "dev-internal-token"

from shared.config import get_settings
get_settings.cache_clear()   # lru_cache 초기화 → 위 env var 반영

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.pool import StaticPool

from shared.db import Base, get_session
from app.main import app


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    """각 테스트마다 독립적인 aiosqlite 인메모리 DB 사용."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async_session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with async_session() as session:
        yield session

    await engine.dispose()


@pytest_asyncio.fixture
async def client(db_session) -> AsyncClient:
    """FastAPI 테스트 클라이언트 — DB 세션을 인메모리로 오버라이드."""

    async def override_get_session():
        yield db_session

    app.dependency_overrides[get_session] = override_get_session

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac

    app.dependency_overrides.clear()
