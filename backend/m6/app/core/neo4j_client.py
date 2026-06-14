"""Neo4j async 드라이버 래퍼 — m6 전용."""

import os

from neo4j import AsyncGraphDatabase, AsyncDriver


_driver: AsyncDriver | None = None


def get_driver() -> AsyncDriver:
    global _driver
    if _driver is None:
        uri = os.getenv("NEO4J_URI", "bolt://localhost:7688")
        user = os.getenv("NEO4J_USER", "neo4j")
        password = os.getenv("NEO4J_PASSWORD", "codeshepherd")
        _driver = AsyncGraphDatabase.driver(uri, auth=(user, password))
    return _driver


async def close_driver() -> None:
    global _driver
    if _driver is not None:
        await _driver.close()
        _driver = None


def get_database() -> str:
    return os.getenv("NEO4J_DATABASE", "neo4j")
