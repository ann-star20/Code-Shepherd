"""7A — rag/retriever.py TDD (chunks/chunk_embeddings parent-child small-to-big).

목업 convention_embeddings → 진짜 chunk_embeddings + chunks(parent-child)로 교체.
정밀 매칭은 child(=chunk_embeddings)로, 인용 본문은 그 child의 parent로(없으면 child fallback).

고립: embedder.embed·_connect 둘 다 Mock. SQL은 한 번에 join(부모/문서)해 raw 컬럼을
반환하고, parent→child fallback·title 선택·score 컷은 retriever 가 파이썬에서 한다
(→ ①②를 mock 으로 검증 가능).

SQL SELECT 컬럼 순서(=_row 순서):
  0 parent_content  1 child_content  2 parent_section_header
  3 child_section_header  4 doc_title(documents.title)  5 source_url  6 score
"""
from config import settings
from rag import embedder, retriever, store


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


def _row(score=0.9, *, parent_content=None, child_content="child 본문",
         parent_sh=None, child_sh=None, doc_title=None, source_url=None):
    """SQL SELECT 컬럼 순서대로의 한 행(부모 컬럼은 LEFT JOIN 미스 시 None)."""
    return (parent_content, child_content, parent_sh, child_sh,
            doc_title, source_url, score)


# ─── small-to-big: child 매칭 → 부모 본문 인용 ─────────────────────────────────
def test_child_match_returns_parent_body(monkeypatch):
    """① child 로 매칭하되 인용 본문은 부모 청크 본문."""
    _setup(monkeypatch, [_row(
        parent_content="부모: N+1은 루프 밖 IN/JOIN 으로 일괄 조회한다.",
        child_content="child 조각",
        parent_sh="DB 접근 규칙",
        child_sh="N+1 예시",
        source_url="http://wiki/db",
    )])
    out = retriever.search_convention("N+1 쿼리")
    assert out == [{
        "content": "부모: N+1은 루프 밖 IN/JOIN 으로 일괄 조회한다.",
        "doc_title": "DB 접근 규칙",
        "source_url": "http://wiki/db",
        "score": 0.9,
    }]


def test_no_parent_falls_back_to_child_body(monkeypatch):
    """② 부모 없으면(parent_chunk_id NULL) child 본문으로 fallback."""
    _setup(monkeypatch, [_row(
        parent_content=None,
        child_content="child: 매직넘버 금지",
        child_sh="네이밍 규칙",
        source_url="http://wiki/style",
    )])
    out = retriever.search_convention("매직넘버")
    assert out[0]["content"] == "child: 매직넘버 금지"
    assert out[0]["doc_title"] == "네이밍 규칙"


def test_doc_title_falls_back_to_document_title(monkeypatch):
    """section_header 없으면 documents.title 로 매핑."""
    _setup(monkeypatch, [_row(
        parent_content="부모 본문",
        parent_sh=None,
        child_sh=None,
        doc_title="백엔드 컨벤션 v2",
    )])
    out = retriever.search_convention("q")
    assert out[0]["doc_title"] == "백엔드 컨벤션 v2"


def test_no_fake_link_when_source_url_null(monkeypatch):
    """source_url 없으면 빈 문자열(가짜 링크 금지)."""
    _setup(monkeypatch, [_row(parent_content="부모", source_url=None)])
    out = retriever.search_convention("q")
    assert out[0]["source_url"] == ""


def test_multiple_children_preserve_order_and_map(monkeypatch):
    """여러 child(부모 있음 + 부모 없음 섞임) → 순서 유지, 각각 매핑."""
    _setup(monkeypatch, [
        _row(score=0.95, parent_content="부모1", parent_sh="규칙1"),
        _row(score=0.80, parent_content=None, child_content="child2", child_sh="규칙2"),
    ])
    out = retriever.search_convention("q", top_k=2)
    assert [r["content"] for r in out] == ["부모1", "child2"]
    assert [r["doc_title"] for r in out] == ["규칙1", "규칙2"]


def test_low_score_filtered(monkeypatch):
    """score < RAG_SCORE_MIN 제거(환각 방지 유지)."""
    monkeypatch.setattr(settings, "RAG_SCORE_MIN", 0.5)
    _setup(monkeypatch, [
        _row(score=0.9, parent_content="A"),
        _row(score=0.3, parent_content="B"),
    ])
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


def test_query_param_bound_on_chunk_tables(monkeypatch):
    """SQL 은 진짜 chunk 테이블을 파라미터 바인딩으로만 검색(f-string SQL 금지)."""
    conn = _setup(monkeypatch, [])
    retriever.search_convention("q")
    sql, params = conn.log[0]
    qlit = store.to_vector_literal([0.2] * 1024)
    # 벡터는 파라미터로만 전달 — SQL 본문에 직접 박히지 않음
    assert qlit in params
    assert qlit not in sql
    assert "%s::vector" in sql
    # 목업 표 폐기 + 진짜 parent-child 표 사용
    assert "convention_embeddings" not in sql
    assert "chunk_embeddings" in sql
    assert "parent_chunk_id" in sql


def test_connection_closed(monkeypatch):
    conn = _setup(monkeypatch, [])
    retriever.search_convention("q")
    assert conn.closed


# ─── 환각 방지 fallback ───────────────────────────────────────────────────────
def test_empty_rows_returns_empty(monkeypatch):
    _setup(monkeypatch, [])
    assert retriever.search_convention("q") == []


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


def test_empty_embedding_returns_empty(monkeypatch):
    monkeypatch.setattr(embedder, "embed", lambda t: [])
    monkeypatch.setattr(retriever, "_connect", lambda: _FakeConn([]))
    assert retriever.search_convention("q") == []


def test_query_exception_returns_empty(monkeypatch):
    class _Boom(_FakeConn):
        def cursor(self):
            raise ConnectionError("db down")

    monkeypatch.setattr(embedder, "embed", lambda t: [[0.1] * 1024])
    monkeypatch.setattr(retriever, "_connect", lambda: _Boom([]))
    assert retriever.search_convention("q") == []
