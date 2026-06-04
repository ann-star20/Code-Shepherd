"""공용 테스트 픽스처 — 앱별 AsyncClient, 트랜잭션 롤백 DB 세션.

사용 예시 (각 서비스 conftest.py):
    from shared.testing import rollback_session, make_test_client
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from .config import get_settings

if TYPE_CHECKING:
    from fastapi import FastAPI


@pytest.fixture(scope="session")
def event_loop_policy():
    """pytest-asyncio 세션 수준 이벤트 루프 정책."""
    return asyncio.DefaultEventLoopPolicy()


def make_test_client(app: "FastAPI") -> AsyncClient:
    """ASGI 앱을 감싸는 AsyncClient 생성 (실제 네트워크 없음)."""
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


@pytest_asyncio.fixture
async def test_client(app: "FastAPI") -> AsyncGenerator[AsyncClient, None]:
    """app 픽스처가 제공된 경우 사용하는 AsyncClient 픽스처."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client


# ---------------------------------------------------------------------------
# 트랜잭션 롤백 DB 세션 픽스처
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture(scope="session")
async def test_engine():
    """테스트 세션 전체에 걸쳐 단일 엔진 사용."""
    settings = get_settings()
    engine = create_async_engine(settings.test_database_url, echo=False)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def rollback_session(test_engine) -> AsyncGenerator[AsyncSession, None]:
    """각 테스트마다 트랜잭션을 열고 테스트 종료 후 롤백.

    중첩 트랜잭션(savepoint)을 이용해 실제 DB에 변경이 남지 않도록 격리.
    """
    async with test_engine.connect() as conn:
        await conn.begin()
        # SAVEPOINT를 이용한 중첩 트랜잭션
        async with conn.begin_nested() as nested:
            session_factory = sessionmaker(
                bind=conn,
                class_=AsyncSession,
                expire_on_commit=False,
            )
            async with session_factory() as session:
                yield session
            await nested.rollback()
        await conn.rollback()
