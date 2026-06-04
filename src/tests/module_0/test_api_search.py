from __future__ import annotations

import pytest

import module_0_kms.api as api


class _AcquireContext:
    def __init__(self, conn):
        self.conn = conn

    async def __aenter__(self):
        return self.conn

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _FakePool:
    def __init__(self, conn):
        self.conn = conn

    def acquire(self):
        return _AcquireContext(self.conn)


@pytest.mark.asyncio
async def test_search_includes_partial_stores(monkeypatch):
    captured = {}

    async def fake_embed(_text: str) -> list[float]:
        return [0.1, 0.2, 0.3]

    class Conn:
        async def fetch(self, query, *params):
            captured["query"] = query
            captured["params"] = params
            return []

    monkeypatch.setattr(api, "_db_pool", _FakePool(Conn()))
    monkeypatch.setattr(api, "_embed_query", fake_embed)

    await api.search_kms(q="architecture", limit=5)

    assert "stored_partial" in captured["query"]
    assert "stored" in captured["query"]
