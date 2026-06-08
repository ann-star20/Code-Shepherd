"""B2 — rag/store.py TDD (convention_embeddings DDL + ensure 함수).

위험 2(스키마 강결합) 대응: 테이블·차원을 한 모듈에 집중.
실제 DB 없이 고립: conn/cursor를 가짜로 주입해 실행된 SQL만 검증.
"""
from rag import store


class _FakeCursor:
    def __init__(self, log: list):
        self.log = log

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, sql, params=None):
        self.log.append(sql)


class _FakeConn:
    def __init__(self):
        self.log: list = []

    def cursor(self):
        return _FakeCursor(self.log)


# ─── 1) 확장 + 테이블 DDL이 실행된다 ─────────────────────────────────────────
def test_ensure_executes_extension_and_table():
    conn = _FakeConn()
    store.ensure_convention_table(conn)
    sql = "\n".join(conn.log)
    assert "CREATE EXTENSION IF NOT EXISTS vector" in sql
    assert "convention_embeddings" in sql


# ─── 2) 차원이 설정값(1024)과 일치 ────────────────────────────────────────────
def test_ddl_uses_configured_dimension():
    from config import settings
    assert f"vector({settings.EMBED_DIM})" in store.CONVENTION_DDL
    assert "vector(1024)" in store.CONVENTION_DDL  # BGE-M3


# ─── 3) 멱등(IF NOT EXISTS)이라 재실행 안전 ───────────────────────────────────
def test_ddl_is_idempotent():
    assert "CREATE TABLE IF NOT EXISTS convention_embeddings" in store.CONVENTION_DDL
