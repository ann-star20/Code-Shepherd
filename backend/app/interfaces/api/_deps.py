"""공통 FastAPI 의존성."""

import asyncpg
from fastapi import Request


async def get_conn(request: Request) -> asyncpg.Connection:
    """요청별 asyncpg 연결 — lifespan pool에서 획득."""
    async with request.app.state.pool.acquire() as conn:
        yield conn
