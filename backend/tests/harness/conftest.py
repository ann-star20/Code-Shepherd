"""pytest 픽스처 — DB 연결 픽스처 포함."""
import os
import pytest
import psycopg2
from neo4j import GraphDatabase


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


@pytest.fixture(scope="session")
def neo4j_driver():
    """Neo4j 드라이버 — Tag Node MERGE 통합 테스트용."""
    uri = os.getenv("NEO4J_URI", "bolt://127.0.0.1:7687")
    auth = (
        os.getenv("NEO4J_USER", "neo4j"),
        os.getenv("NEO4J_PASSWORD", "pass1234!"),
    )
    driver = GraphDatabase.driver(uri, auth=auth)
    yield driver
    driver.close()
