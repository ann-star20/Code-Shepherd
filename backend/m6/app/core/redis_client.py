"""Redis 연결 헬퍼 — 태스크 상태 조회용."""

import os

import redis.asyncio as aioredis


_client: aioredis.Redis | None = None


def get_redis() -> aioredis.Redis:
    global _client
    if _client is None:
        url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        _client = aioredis.from_url(url, decode_responses=True)
    return _client
