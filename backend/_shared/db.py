"""async SQLAlchemy 엔진/세션 팩토리 및 FastAPI 의존성."""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from .config import get_settings

_settings = get_settings()
_engine = create_async_engine(
    _settings.database_url,
    echo=False,
    pool_pre_ping=True,
)
_AsyncSessionFactory = async_sessionmaker(
    _engine,
    expire_on_commit=False,
    class_=AsyncSession,
)


class Base(DeclarativeBase):
    """모든 SQLAlchemy 모델의 베이스 클래스."""


def create_engine_from_url(url: str):
    """테스트 등 외부에서 다른 DB URL을 주입할 때 사용."""
    return create_async_engine(url, echo=False, pool_pre_ping=True)


def create_session_factory(engine):
    return async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI 의존성 — 요청마다 새 세션 제공, 요청 완료 후 닫힘."""
    async with _AsyncSessionFactory() as session:
        yield session
