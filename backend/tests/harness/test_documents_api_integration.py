"""통합 테스트 — POST /api/documents (실제 DB 연결).

TDD RED→GREEN:
  RED  : knowledge_document 테이블 미존재 → 500 또는 DB 오류
  GREEN: 스키마 적용 후 → 201 + PENDING 반환
"""

import os
import pytest
import asyncpg
from httpx import AsyncClient, ASGITransport


def _pg_dsn() -> str:
    return (
        f"postgresql://{os.getenv('DB_USER', 'postgres')}:{os.getenv('DB_PASSWORD', 'postgres')}"
        f"@{os.getenv('DB_HOST', 'localhost')}:{os.getenv('DB_PORT', '5432')}"
        f"/{os.getenv('DB_NAME', 'postgres')}"
    )


@pytest.fixture
async def db_with_schema():
    """실제 DB에 schema.sql 적용 후 커넥션 풀 반환."""
    from pathlib import Path

    schema_path = Path(__file__).parent.parent.parent / "scripts" / "seed" / "schema.sql"
    dsn = _pg_dsn()

    conn = await asyncpg.connect(dsn)
    try:
        sql = schema_path.read_text(encoding="utf-8")
        statements = [s.strip() for s in sql.split(";") if s.strip()]
        for stmt in statements:
            lines = [ln for ln in stmt.splitlines() if not ln.strip().startswith("--")]
            body = "\n".join(lines).strip()
            if body:
                await conn.execute(body)
    finally:
        await conn.close()

    pool = await asyncpg.create_pool(dsn, min_size=1, max_size=3)
    yield pool
    await pool.close()


@pytest.mark.anyio
async def test_post_documents_real_db_single_url(db_with_schema):
    """실제 DB에 knowledge_document 테이블이 존재할 때 POST /api/documents → 201."""
    from app.main import app

    app.state.pool = db_with_schema

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post(
            "/api/documents",
            json={"urls": ["https://docs.djangoproject.com/en/5.0/topics/security/"]},
        )

    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"
    body = resp.json()
    assert "documents" in body
    assert len(body["documents"]) == 1
    doc = body["documents"][0]
    assert doc["state"] == "PENDING"
    assert doc["doc_id"].startswith("EXT_")
    assert "djangoproject" in doc["original_url"]


@pytest.mark.anyio
async def test_post_documents_real_db_idempotent(db_with_schema):
    """동일 URL 두 번 요청 → 두 번째도 201, 같은 doc_id."""
    from app.main import app

    app.state.pool = db_with_schema
    url = "https://owasp.org/www-project-top-ten/"

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        r1 = await ac.post("/api/documents", json={"urls": [url]})
        r2 = await ac.post("/api/documents", json={"urls": [url]})

    assert r1.status_code == 201
    assert r2.status_code == 201
    assert r1.json()["documents"][0]["doc_id"] == r2.json()["documents"][0]["doc_id"]


@pytest.mark.anyio
async def test_post_documents_real_db_multiple_urls(db_with_schema):
    """URL 3개 → 201, documents 3개."""
    from app.main import app

    app.state.pool = db_with_schema
    urls = [
        "https://cheatsheetseries.owasp.org/cheatsheets/SQL_Injection_Prevention_Cheat_Sheet.html",
        "https://cheatsheetseries.owasp.org/cheatsheets/XSS_Prevention_Cheat_Sheet.html",
        "https://cheatsheetseries.owasp.org/cheatsheets/CSRF_Prevention_Cheat_Sheet.html",
    ]

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post("/api/documents", json={"urls": urls})

    assert resp.status_code == 201
    assert len(resp.json()["documents"]) == 3
    for doc in resp.json()["documents"]:
        assert doc["state"] == "PENDING"
