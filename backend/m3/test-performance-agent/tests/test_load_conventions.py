"""B3 — rag/load_conventions.py TDD (문서 → 청크 → embed → INSERT).

고립: embed·conn 둘 다 Mock. 절대규칙(위험 1) 검증 = 기본 임베더가
공유 embedder.embed 인지 확인.

+ load_from_dir: conventions/*.md → records → embed_and_store 얇은 래퍼.
"""
from rag import load_conventions


class _FakeCursor:
    def __init__(self, log):
        self.log = log

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, sql, params=None):
        self.log.append((sql, params))


class _FakeConn:
    def __init__(self):
        self.log = []

    def cursor(self):
        return _FakeCursor(self.log)


def _inserts(conn):
    return [(s, p) for (s, p) in conn.log if "INSERT INTO convention_embeddings" in s]


# ─── 1) 문단 청크별로 INSERT, 임베딩은 배치 1회 ───────────────────────────────
def test_embed_and_store_inserts_chunk_rows():
    calls = {"embed": 0}

    def fake_embed(texts):
        calls["embed"] += 1
        return [[0.1] * 1024 for _ in texts]

    conn = _FakeConn()
    records = [{"doc_title": "N+1 가이드", "source_url": "http://x",
                "content": "문단1 내용\n\n문단2 내용"}]
    n = load_conventions.embed_and_store(records, conn, embed=fake_embed)

    assert n == 2                       # 청크 2개
    assert len(_inserts(conn)) == 2     # INSERT 2번
    assert calls["embed"] == 1          # 임베딩은 배치로 1회


# ─── 2) INSERT 파라미터에 제목·내용·벡터가 들어간다 ──────────────────────────
def test_insert_params_carry_fields():
    conn = _FakeConn()
    records = [{"doc_title": "복잡도", "source_url": "u", "content": "한 청크"}]
    load_conventions.embed_and_store(
        records, conn, embed=lambda t: [[0.5] * 1024 for _ in t])
    sql, params = _inserts(conn)[0]
    assert params[0] == "복잡도"        # doc_title
    assert params[1] == "u"             # source_url
    assert params[2] == "한 청크"       # content


# ─── 3) 빈 내용 → INSERT·임베딩 없음, 0 반환 ──────────────────────────────────
def test_empty_content_no_insert():
    conn = _FakeConn()
    calls = {"embed": 0}
    n = load_conventions.embed_and_store(
        [{"doc_title": "t", "source_url": "", "content": "   "}],
        conn, embed=lambda t: (calls.__setitem__("embed", calls["embed"] + 1) or []))
    assert n == 0
    assert _inserts(conn) == []
    assert calls["embed"] == 0


# ─── 4) 절대규칙: 기본 임베더 = 공유 embedder.embed ───────────────────────────
def test_default_embedder_is_shared_embed(monkeypatch):
    from rag import embedder
    used = {"n": 0}

    def spy(texts):
        used["n"] += 1
        return [[0.0] * 1024 for _ in texts]

    monkeypatch.setattr(embedder, "embed", spy)
    conn = _FakeConn()
    # embed 인자 생략 → 내부에서 embedder.embed 사용해야
    load_conventions.embed_and_store(
        [{"doc_title": "t", "source_url": "", "content": "c"}], conn)
    assert used["n"] == 1


# ─── 5) load_from_dir: .md 읽어 청크별 INSERT (.txt 무시) ─────────────────────
def test_load_from_dir_reads_md_and_inserts(tmp_path):
    (tmp_path / "a.md").write_text("# 제목A\n\n본문1\n\n본문2", encoding="utf-8")
    (tmp_path / "b.md").write_text("# 제목B\n\n본문", encoding="utf-8")
    (tmp_path / "ignore.txt").write_text("# 무시\n\n내용", encoding="utf-8")
    conn = _FakeConn()
    n = load_conventions.load_from_dir(
        str(tmp_path), conn, embed=lambda t: [[0.1] * 1024 for _ in t])
    # 빈 줄 기준 청크: a.md=[H1,본문1,본문2]=3, b.md=[H1,본문]=2 → 5. .txt 제외.
    assert n == 5
    assert len(_inserts(conn)) == 5


# ─── 6) doc_title은 첫 H1(# ...)에서 추출 ─────────────────────────────────────
def test_doc_title_from_h1(tmp_path):
    (tmp_path / "x.md").write_text("# 커버리지 가이드\n\n내용", encoding="utf-8")
    conn = _FakeConn()
    load_conventions.load_from_dir(
        str(tmp_path), conn, embed=lambda t: [[0.0] * 1024 for _ in t])
    _, params = _inserts(conn)[0]
    assert params[0] == "커버리지 가이드"


# ─── 7) load_from_dir도 기본 공유 임베더 사용(절대규칙) ──────────────────────
def test_load_from_dir_uses_shared_embedder(tmp_path, monkeypatch):
    from rag import embedder
    used = {"n": 0}
    monkeypatch.setattr(
        embedder, "embed",
        lambda t: used.__setitem__("n", 1) or [[0.0] * 1024 for _ in t])
    (tmp_path / "x.md").write_text("# T\n\nc", encoding="utf-8")
    load_conventions.load_from_dir(str(tmp_path), _FakeConn())
    assert used["n"] == 1
