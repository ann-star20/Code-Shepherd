"""M6 서비스 환경 변수 설정."""

from __future__ import annotations

import os


def pg_dsn() -> str:
    """asyncpg 호환 DSN (postgresql:// 형식)."""
    if url := os.getenv("DATABASE_URL"):
        return url.replace("postgresql+asyncpg://", "postgresql://")
    host = os.getenv("DB_HOST", "cloud-sql-proxy")
    port = os.getenv("DB_PORT", "5432")
    name = os.getenv("DB_NAME", "postgres")
    user = os.getenv("DB_USER", "postgres")
    pw = os.getenv("DB_PASSWORD", "postgres")
    return f"postgresql://{user}:{pw}@{host}:{port}/{name}"


REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
EMBEDDING_MODEL: str = os.getenv("EMBEDDING_MODEL", "bge-m3")
USE_REAL_LLM: bool = os.getenv("USE_MOCK_LLM", "true").lower() != "true"
GEMINI_API_KEY: str = os.getenv("GOOGLE_API_KEY", "")
GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
