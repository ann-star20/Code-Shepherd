"""categories DB 모듈 — SQLAlchemy async 버전.

categories 테이블에서 카테고리 목록을 동적으로 조회하고 추가한다.
VALID_CATEGORIES 코드 상수를 대체하여 런타임 확장을 가능하게 한다.

테이블 스키마 (migrations/004_add_categories_table.sql):
    CREATE TABLE categories (
        id          SERIAL PRIMARY KEY,
        name        VARCHAR(100) NOT NULL UNIQUE,
        description TEXT         NOT NULL DEFAULT '',
        active      BOOLEAN      NOT NULL DEFAULT TRUE,
        created_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW()
    );
"""

from __future__ import annotations

import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

logger = logging.getLogger(__name__)


async def get_categories(session_factory: async_sessionmaker[AsyncSession]) -> list[str]:
    """활성 카테고리 이름 목록을 반환한다."""
    async with session_factory() as session:
        result = await session.execute(
            text("SELECT name FROM categories WHERE active = TRUE ORDER BY name")
        )
        rows = result.fetchall()
    return [row[0] for row in rows]


async def get_valid_categories(session_factory: async_sessionmaker[AsyncSession]) -> frozenset[str]:
    """활성 카테고리를 frozenset 으로 반환한다 (stage5b rule-check 용)."""
    names = await get_categories(session_factory)
    return frozenset(names)


async def add_category(
    session_factory: async_sessionmaker[AsyncSession],
    name: str,
    description: str = "",
) -> None:
    """새 카테고리를 추가한다. 이미 존재하면 무시한다 (ON CONFLICT DO NOTHING)."""
    async with session_factory() as session:
        await session.execute(
            text("""
                INSERT INTO categories (name, description)
                VALUES (:name, :description)
                ON CONFLICT (name) DO NOTHING
            """),
            {"name": name.strip(), "description": description.strip()},
        )
        await session.commit()
    logger.info(f"카테고리 추가/확인: '{name}'")
