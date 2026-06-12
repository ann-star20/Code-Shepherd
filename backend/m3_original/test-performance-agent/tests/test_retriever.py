"""B4+B5 — rag/retriever.py TDD (B안: 쿼리 embed + pgvector 코사인 검색).

A안(Dev1 KMS API) 폐기 → B안 재작성. 고립: embedder.embed·_connect 둘 다 Mock.
- B4 정상: rows → {content,doc_title,source_url,score} 매핑, top_k, 공유 임베더(위험1),
           이슈 message 통째로(위험4)
- B5 환각방지: DB연결 없음/임베딩 실패/쿼리 예외/저score → 빈 결과 (정직성)
"""
from config import settings
from rag import embedder, retriever


class _FakeCursor:
    def __init__(self, rows, log):
        self._rows = rows
        self.log = log

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, sql, params=None):
        self.log.append((sql, params))

    def fetchall(self):
        return self._rows


class _FakeConn:
    def __init__(self, rows):
        self._rows = rows
        self.log = []
        self.closed = False

    def cursor(self):
        return _FakeCursor(self._rows, self.log)

    def close(self):
        self.closed = True


def _setup(monkeypatch, rows, embed=None):
    monkeypatch.setattr(embedder, "embed", embed or (lambda t: [[0.2] * 1024]))
    conn = _FakeConn(rows)
    monkeypatch.setattr(retriever, "_connect", lambda: conn)
    return conn


# ─── B4: 정상 검색 ────────────────────────────────────────────────────────────
def test_maps_rows_to_dicts(monkeypatch):
    _setup(monkeypatch, [("내용A", "N+1 가이드", "http://a", 0.9)])
    out = retriever.search_convention("N+1 쿼리: 루프 안 DB 호출")
    assert out == [{"content": "내용A", "doc_title": "N+1 가이드",
                    "source_url": "http://a", "score": 0.9}]


def test_low_score_filtered(monkeypatch):
    monkeypatch.setattr(settings, "RAG_SCORE_MIN", 0.5)
    _setup(monkeypatch, [("A", "t", "u", 0.9), ("B", "t", "u", 0.3)])
    out = retriever.search_convention("q")
    assert [r["content"] for r in out] == ["A"]


def test_top_k_passed_to_query(monkeypatch):
    conn = _setup(monkeypatch, [])
    retriever.search_convention("q", top_k=7)
    sql, params = conn.log[0]
    assert params[-1] == 7
    assert "LIMIT" in sql.upper()


def test_uses_shared_embedder_with_whole_message(monkeypatch):
    """위험 1(공유 임베더) + 위험 4(message 통째로)."""
    calls = []
    _setup(monkeypatch, [], embed=lambda t: calls.append(t) or [[0.1] * 1024])
    msg = "N+1 쿼리: 루프 안에서 DB 호출이 반복됩니다"
    retriever.search_convention(msg)
    assert calls == [[msg]]


def test_connection_closed(monkeypatch):
    conn = _setup(monkeypatch, [])
    retriever.search_convention("q")
    assert conn.closed


# ─── B5: 환각 방지 fallback ───────────────────────────────────────────────────
def test_no_db_url_returns_empty(monkeypatch):
    monkeypatch.setattr(embedder, "embed", lambda t: [[0.1] * 1024])
    monkeypatch.setattr(retriever, "_connect", lambda: None)
    assert retriever.search_convention("q") == []


def test_embed_failure_returns_empty(monkeypatch):
    def boom(t):
        raise RuntimeError("model load fail")

    monkeypatch.setattr(embedder, "embed", boom)
    monkeypatch.setattr(retriever, "_connect", lambda: _FakeConn([]))
    assert retriever.search_convention("q") == []


def test_query_exception_returns_empty(monkeypatch):
    class _Boom(_FakeConn):
        def cursor(self):
            raise ConnectionError("db down")

    monkeypatch.setattr(embedder, "embed", lambda t: [[0.1] * 1024])
    monkeypatch.setattr(retriever, "_connect", lambda: _Boom([]))
    assert retriever.search_convention("q") == []
