"""
categories DB 모듈

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

import asyncpg
import logging

logger = logging.getLogger(__name__)


async def get_categories(pool: asyncpg.Pool) -> list[str]:
    """활성 카테고리 이름 목록을 반환한다."""
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT name FROM categories WHERE active = TRUE ORDER BY name"
        )
    return [row["name"] for row in rows]


async def get_valid_categories(pool: asyncpg.Pool) -> frozenset[str]:
    """활성 카테고리를 frozenset 으로 반환한다 (stage5b rule-check 용)."""
    names = await get_categories(pool)
    return frozenset(names)


async def add_category(
    pool: asyncpg.Pool,
    name: str,
    description: str = "",
) -> None:
    """새 카테고리를 추가한다. 이미 존재하면 무시한다 (ON CONFLICT DO NOTHING)."""
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO categories (name, description)
            VALUES ($1, $2)
            ON CONFLICT (name) DO NOTHING
            """,
            name.strip(),
            description.strip(),
        )
    logger.info(f"카테고리 추가/확인: '{name}'")
