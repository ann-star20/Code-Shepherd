"""pytest 픽스처 — DB 연결 픽스처 포함."""

import os
import pytest
import psycopg2
import asyncpg
from neo4j import GraphDatabase, AsyncGraphDatabase


def _pg_dsn() -> str:
    return (
        f"postgresql://{os.getenv('DB_USER','postgres')}:{os.getenv('DB_PASSWORD','postgres')}"
        f"@{os.getenv('DB_HOST','localhost')}:{os.getenv('DB_PORT','5433')}"
        f"/{os.getenv('DB_NAME','postgres')}"
    )


@pytest.fixture
async def asyncpg_pool():
    """asyncpg 커넥션 풀 — T06 레이스 컨디션 통합 테스트용."""
    pool = await asyncpg.create_pool(_pg_dsn(), min_size=2, max_size=5, ssl=False)
    yield pool
    await pool.close()


@pytest.fixture(params=["asyncio"])
def anyio_backend(request):
    return request.param


@pytest.fixture(scope="session")
def pg_conn():
    """psycopg2 동기 연결 — schema/UPSERT 통합 테스트용."""
    conn = psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", "5433")),
        user=os.getenv("DB_USER", "postgres"),
        password=os.getenv("DB_PASSWORD", "postgres"),
        dbname=os.getenv("DB_NAME", "postgres"),
    )
    conn.autocommit = False
    yield conn
    conn.close()


@pytest.fixture
def pg_cursor(pg_conn):
    """트랜잭션 격리 커서 — 테스트 종료 시 롤백."""
    cur = pg_conn.cursor()
    yield cur
    pg_conn.rollback()
    cur.close()


@pytest.fixture
async def async_neo4j_driver():
    """neo4j AsyncDriver — Neo4j 미실행 시 자동 skip."""
    uri = os.getenv("NEO4J_URI", "bolt://127.0.0.1:7688")
    auth = (os.getenv("NEO4J_USER", "neo4j"), os.getenv("NEO4J_PASSWORD", "pass1234!"))
    driver = AsyncGraphDatabase.driver(uri, auth=auth)
    try:
        await driver.verify_connectivity()
    except Exception:
        await driver.close()
        pytest.skip("Neo4j 미실행 — 통합 테스트 건너뜀")
    yield driver
    await driver.close()


@pytest.fixture(scope="session")
def neo4j_driver():
    """Neo4j 드라이버 — Neo4j 미실행 시 자동 skip."""
    uri = os.getenv("NEO4J_URI", "bolt://127.0.0.1:7688")
    auth = (os.getenv("NEO4J_USER", "neo4j"), os.getenv("NEO4J_PASSWORD", "pass1234!"))
    driver = GraphDatabase.driver(uri, auth=auth)
    try:
        driver.verify_connectivity()
    except Exception:
        driver.close()
        pytest.skip("Neo4j 미실행 — 통합 테스트 건너뜀")
    yield driver
    driver.close()
