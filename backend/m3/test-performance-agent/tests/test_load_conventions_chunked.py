"""A1 — load_conventions_to_chunks TDD (chunks/chunk_embeddings/documents 분리 적재).

문제: 6개 사내 가이드가 DB에 2개의 과대 청크로 적재됨 → doc_title 4/6 오라벨.
해결: 가이드별로 documents(1) + parent chunk(1, NULL parent) + child chunks(N) + embeddings(N).

고립: embed·conn 모두 Mock. (옛 목업 convention_embeddings 적재 코드는 제거됨.)

주의: content split("\n\n") 기준이므로, 1 child 원하면 이중개행 없는 텍스트 사용.
      예) "# G\n\npara" → child 2개 ("# G", "para")
          "# G\npara"  → child 1개 ("# G\npara")
"""
from rag import load_conventions


class _FakeCursor:
    def __init__(self, log, return_val=None):
        self._log = log
        self._return_val = return_val

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, sql, params=None):
        self._log.append((sql, params))

    def fetchone(self):
        return self._return_val


class _FakeConn:
    """각 cursor() 호출 → return_vals 에서 순서대로 꺼낸 값을 fetchone()이 반환."""
    def __init__(self, *return_vals):
        self.log = []
        self._returns = iter(return_vals)

    def cursor(self):
        return _FakeCursor(self.log, next(self._returns, None))


def _writes(conn, table: str):
    return [(s, p) for (s, p) in conn.log if f"INSERT INTO {table}" in s]


# ─── documents ───────────────────────────────────────────────────────────────

def test_one_document_per_guide(tmp_path):
    """md 2개 → documents INSERT 2번. 1-child 콘텐츠 사용(이중개행 없음)."""
    (tmp_path / "a.md").write_text("Guide A content", encoding="utf-8")
    (tmp_path / "b.md").write_text("Guide B content", encoding="utf-8")
    # 각 guide: doc(x,) + parent(x,) + child1(x,) + embed(None) = 4 cursors
    conn = _FakeConn((1,), (10,), (100,), None, (2,), (20,), (200,), None)
    load_conventions.load_conventions_to_chunks(
        str(tmp_path), conn, embed=lambda t: [[0.1] * 1024 for _ in t])
    assert len(_writes(conn, "documents")) == 2


def test_doc_title_from_h1(tmp_path):
    """# H1 제목을 doc_title로 추출. 단일 청크 콘텐츠 사용."""
    (tmp_path / "a.md").write_text("# 커버리지 가이드\n내용", encoding="utf-8")
    conn = _FakeConn((1,), (10,), (100,), None)
    load_conventions.load_conventions_to_chunks(
        str(tmp_path), conn, embed=lambda t: [[0.0] * 1024 for _ in t])
    _, params = _writes(conn, "documents")[0]
    assert params[0] == "커버리지 가이드"


def test_source_url_is_file_path(tmp_path):
    """source_url = 'file:///conventions/{파일명}' (재적재 식별용)."""
    (tmp_path / "01_커버리지_가이드.md").write_text("content", encoding="utf-8")
    conn = _FakeConn((1,), (10,), (100,), None)
    load_conventions.load_conventions_to_chunks(
        str(tmp_path), conn, embed=lambda t: [[0.0] * 1024 for _ in t])
    _, params = _writes(conn, "documents")[0]
    assert params[1] == "file:///conventions/01_커버리지_가이드.md"


# ─── parent chunk ─────────────────────────────────────────────────────────────

def test_one_parent_chunk_per_guide(tmp_path):
    """parent chunk: parent_chunk_id = NULL, 가이드 1개 → parent INSERT 1번."""
    (tmp_path / "a.md").write_text("content only", encoding="utf-8")
    conn = _FakeConn((1,), (10,), (100,), None)
    load_conventions.load_conventions_to_chunks(
        str(tmp_path), conn, embed=lambda t: [[0.0] * 1024 for _ in t])
    parents = [(s, p) for s, p in _writes(conn, "chunks") if p and p[-1] is None]
    assert len(parents) == 1


def test_parent_section_header_uses_rule_id(tmp_path):
    """프론트매터 rule_id → parent chunk.section_header."""
    md = "---\nrule_id: PERF-002\n---\n# N+1 가이드\n내용"
    (tmp_path / "a.md").write_text(md, encoding="utf-8")
    conn = _FakeConn((1,), (10,), (100,), None)
    load_conventions.load_conventions_to_chunks(
        str(tmp_path), conn, embed=lambda t: [[0.0] * 1024 for _ in t])
    parents = [(s, p) for s, p in _writes(conn, "chunks") if p and p[-1] is None]
    _, params = parents[0]
    assert params[2] == "PERF-002"


def test_parent_section_header_fallback_to_title(tmp_path):
    """프론트매터 없음 → section_header = doc_title."""
    (tmp_path / "a.md").write_text("# 복잡도 가이드\n내용", encoding="utf-8")
    conn = _FakeConn((1,), (10,), (100,), None)
    load_conventions.load_conventions_to_chunks(
        str(tmp_path), conn, embed=lambda t: [[0.0] * 1024 for _ in t])
    parents = [(s, p) for s, p in _writes(conn, "chunks") if p and p[-1] is None]
    _, params = parents[0]
    assert params[2] == "복잡도 가이드"


# ─── child chunks ─────────────────────────────────────────────────────────────

def test_child_chunks_count_matches_paragraphs(tmp_path):
    """이중개행 기준 문단 3개 → child chunk INSERT 3번, 반환값 3."""
    (tmp_path / "a.md").write_text("p1\n\np2\n\np3", encoding="utf-8")
    # doc(1) + parent(10) + child1(100)+embed + child2(101)+embed + child3(102)+embed
    conn = _FakeConn((1,), (10,), (100,), None, (101,), None, (102,), None)
    n = load_conventions.load_conventions_to_chunks(
        str(tmp_path), conn, embed=lambda t: [[0.0] * 1024 for _ in t])
    children = [(s, p) for s, p in _writes(conn, "chunks") if p and p[-1] is not None]
    assert len(children) == 3
    assert n == 3


def test_child_chunk_carries_parent_id(tmp_path):
    """child chunk INSERT의 parent_chunk_id = 직전 parent INSERT에서 받은 id."""
    (tmp_path / "a.md").write_text("single paragraph", encoding="utf-8")
    parent_id = 42
    conn = _FakeConn((1,), (parent_id,), (100,), None)
    load_conventions.load_conventions_to_chunks(
        str(tmp_path), conn, embed=lambda t: [[0.0] * 1024 for _ in t])
    children = [(s, p) for s, p in _writes(conn, "chunks") if p and p[-1] is not None]
    _, params = children[0]
    assert params[-1] == parent_id


def test_child_section_header_same_as_parent(tmp_path):
    """child.section_header 도 rule_id(parent 와 동일 — 검색 결과 라벨 정합성)."""
    md = "---\nrule_id: TEST-001\n---\n# 커버리지\n내용"
    (tmp_path / "a.md").write_text(md, encoding="utf-8")
    conn = _FakeConn((1,), (10,), (100,), None)
    load_conventions.load_conventions_to_chunks(
        str(tmp_path), conn, embed=lambda t: [[0.0] * 1024 for _ in t])
    children = [(s, p) for s, p in _writes(conn, "chunks") if p and p[-1] is not None]
    _, params = children[0]
    assert params[2] == "TEST-001"


# ─── chunk_embeddings ─────────────────────────────────────────────────────────

def test_embedding_inserted_per_child(tmp_path):
    """child 2개 → chunk_embeddings INSERT 2번."""
    (tmp_path / "a.md").write_text("para1\n\npara2", encoding="utf-8")
    conn = _FakeConn((1,), (10,), (100,), None, (101,), None)
    load_conventions.load_conventions_to_chunks(
        str(tmp_path), conn, embed=lambda t: [[0.0] * 1024 for _ in t])
    assert len(_writes(conn, "chunk_embeddings")) == 2


def test_embedding_uses_child_id(tmp_path):
    """chunk_embeddings INSERT의 chunk_id = 직전 child chunk INSERT에서 받은 id."""
    (tmp_path / "a.md").write_text("single paragraph", encoding="utf-8")
    child_id = 99
    conn = _FakeConn((1,), (10,), (child_id,), None)
    load_conventions.load_conventions_to_chunks(
        str(tmp_path), conn, embed=lambda t: [[0.0] * 1024 for _ in t])
    _, params = _writes(conn, "chunk_embeddings")[0]
    assert params[0] == child_id


# ─── embed 호출 횟수·절대규칙 ────────────────────────────────────────────────

def test_embed_called_once_per_guide(tmp_path):
    """embed는 가이드당 1회(배치) — 가이드 2개이면 2회."""
    (tmp_path / "a.md").write_text("para1\n\npara2", encoding="utf-8")  # 2 children
    (tmp_path / "b.md").write_text("single para", encoding="utf-8")     # 1 child
    calls = {"n": 0}

    def fake_embed(texts):
        calls["n"] += 1
        return [[0.0] * 1024 for _ in texts]

    # guide a (2 children): doc+parent+child1+embed+child2+embed = 6 cursors
    # guide b (1 child):   doc+parent+child+embed = 4 cursors
    conn = _FakeConn(
        (1,), (10,), (100,), None, (101,), None,
        (2,), (20,), (200,), None,
    )
    load_conventions.load_conventions_to_chunks(str(tmp_path), conn, embed=fake_embed)
    assert calls["n"] == 2


def test_default_embedder_is_shared(tmp_path, monkeypatch):
    """embed 인자 생략 시 공유 embedder.embed 사용(절대규칙)."""
    from rag import embedder
    used = {"n": 0}
    monkeypatch.setattr(
        embedder, "embed",
        lambda t: used.__setitem__("n", used["n"] + 1) or [[0.0] * 1024 for _ in t])
    (tmp_path / "a.md").write_text("content", encoding="utf-8")
    conn = _FakeConn((1,), (10,), (100,), None)
    load_conventions.load_conventions_to_chunks(str(tmp_path), conn)
    assert used["n"] == 1


# ─── F1/9A: conventions 파일 rule_id 프론트매터 검증 ─────────────────────────

def test_all_conventions_have_rule_id_frontmatter():
    """실제 conventions/*.md 6개 모두 프론트매터 rule_id를 가진다 — SESSION F1 9A."""
    import os
    from pathlib import Path

    conv_dir = Path(os.path.dirname(__file__)).parent / "conventions"
    md_files = sorted(conv_dir.glob("*.md"))
    assert len(md_files) == 6, f"conventions 파일 수 이상: {len(md_files)}"

    for md_path in md_files:
        raw = md_path.read_text(encoding="utf-8")
        _, meta, _ = _parse_fm(raw)
        assert meta is not None and "rule_id" in meta, (
            f"{md_path.name}: 프론트매터 rule_id 없음 — 재청킹 후 인용 라벨 틀림"
        )


def _parse_fm(content: str):
    """(has_fm, meta_dict|None, body) — 테스트 헬퍼."""
    if not content.startswith("---"):
        return False, None, content
    lines = content.splitlines()
    end = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end = i
            break
    if end is None:
        return False, None, content
    import yaml
    try:
        meta = yaml.safe_load("\n".join(lines[1:end]))
    except Exception:
        return True, None, content
    body = "\n".join(lines[end + 1:]).lstrip("\n")
    return True, meta, body
