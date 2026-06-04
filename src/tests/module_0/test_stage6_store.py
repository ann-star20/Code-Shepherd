from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock

from module_0_kms.pipeline.stage6_store import (
    _save_embeddings,
    _save_chunks,
    _insert_embedding_rows,
    _get_neo4j_driver,
    _precompute_embeddings,
    _embed_text,
    _save_document,
    _save_to_neo4j,
    stage6_store,
)


# ---------------------------------------------------------------------------
# 공통 Fake 인프라
# ---------------------------------------------------------------------------

class _Conn:
    async def execute(self, *_args):
        raise AssertionError("No embedding row should be written when embedding fails")


class _TxCtx:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return False


class _FakeConn:
    def __init__(self):
        self.executes: list[str] = []

    def transaction(self):
        return _TxCtx()

    async def execute(self, query, *_):
        self.executes.append(query)

    async def executemany(self, query, _args):
        self.executes.append(query)


class _AcqCtx:
    def __init__(self, conn):
        self._c = conn

    async def __aenter__(self):
        return self._c

    async def __aexit__(self, *_):
        return False


class _FakePool:
    def __init__(self, conn):
        self._c = conn

    def acquire(self):
        return _AcqCtx(self._c)


class _FakeStorage:
    async def save(self, _path, _data):
        pass

    async def exists(self, _path):
        return False


def _make_state() -> dict:
    return {
        "doc_id": "00000000-0000-0000-0000-000000000001",
        "source": "upload",
        "file_path": "",  # 빈 문자열 → 원본 파일 저장 생략 (재처리 경로)
        "file_type": "md",
        "original_filename": "test.md",
        "raw_markdown": "# Test",
        "markdown_storage_path": "markdown/00000000-0000-0000-0000-000000000001/raw.md",
        "validated_markdown": "# Test",
        "quality_score": 1.0,
        "quality_issues": [],
        "hitl_required": False,
        "chunks": [
            {
                "chunk_id": "00000000-0000-0000-0000-000000000002",
                "doc_id": "00000000-0000-0000-0000-000000000001",
                "parent_chunk_id": None,
                "chunk_type": "child",
                "content": "searchable content",
                "token_count": 10,
                "page_number": None,
                "section_header": "Test",
            }
        ],
        "chunk_validation_passed": True,
        "chunk_validation_issues": [],
        "metadata": {
            "title": "Test Doc",
            "category": "기타",
            "team": None,
            "author": None,
            "tags": [],
            "source": "upload",
        },
        "neo4j_entities": [],
        "neo4j_relations": [],
        "stored": False,
        "neo4j_stored": None,
        "storage_paths": None,
        "status": "processing",
        "error": None,
        "current_stage": "stage5_metadata",
    }


# ---------------------------------------------------------------------------
# 기존 테스트
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_save_embeddings_fails_when_all_child_embeddings_fail(monkeypatch):
    async def fail_embed(_text: str) -> list[float]:
        raise RuntimeError("ollama unavailable")

    monkeypatch.setattr("kms.pipeline.stage6_store._embed_text", fail_embed)

    chunks = [
        {
            "chunk_id": "00000000-0000-0000-0000-000000000001",
            "chunk_type": "child",
            "content": "searchable knowledge",
            "section_header": "Intro",
        }
    ]

    with pytest.raises(RuntimeError, match="No embeddings were saved"):
        await _save_embeddings(_Conn(), chunks, {"category": "architecture"})


# ---------------------------------------------------------------------------
# 새 테스트 (RED → GREEN 목표)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_embedding_failure_prevents_document_save(monkeypatch):
    """
    임베딩 사전 계산이 트랜잭션 시작 전에 실행되어야 한다.
    Ollama 실패 시 _save_document가 호출되지 않아야 한다 (DB 트랜잭션 열리기 전에 실패).
    """
    document_saved: list[bool] = []

    async def fake_save_document(conn, state, md_path, orig_path):
        document_saved.append(True)

    async def fail_embed(_text: str) -> list[float]:
        raise RuntimeError("ollama down")

    monkeypatch.setattr("kms.pipeline.stage6_store._save_document", fake_save_document)
    monkeypatch.setattr("kms.pipeline.stage6_store._embed_text", fail_embed)

    result = await stage6_store(_make_state(), _FakePool(_FakeConn()), _FakeStorage())

    assert document_saved == [], "Ollama 실패 시 DB 트랜잭션이 열려서는 안 된다"
    assert result["stored"] is False
    assert result["status"] == "failed"


@pytest.mark.asyncio
async def test_document_saved_when_embeddings_succeed(monkeypatch):
    """
    임베딩 성공 시 _save_document가 호출되고 status='stored'가 반환되어야 한다.
    """
    document_saved: list[bool] = []

    async def fake_save_document(conn, state, md_path, orig_path):
        document_saved.append(True)

    async def fake_save_chunks(conn, chunks, doc_id):
        pass

    async def fake_embed(_text: str) -> list[float]:
        return [0.1] * 1024

    monkeypatch.setattr("kms.pipeline.stage6_store._save_document", fake_save_document)
    monkeypatch.setattr("kms.pipeline.stage6_store._save_chunks", fake_save_chunks)
    monkeypatch.setattr("kms.pipeline.stage6_store._embed_text", fake_embed)
    monkeypatch.setattr(
        "kms.pipeline.stage6_store._save_to_neo4j", AsyncMock(return_value=True)
    )

    result = await stage6_store(_make_state(), _FakePool(_FakeConn()), _FakeStorage())

    assert document_saved == [True], "임베딩 성공 시 document가 저장되어야 한다"
    assert result["stored"] is True
    assert result["status"] == "stored"


# ---------------------------------------------------------------------------
# T1: N+1 → executemany 배치 처리 (RED → GREEN)
# ---------------------------------------------------------------------------

class _BatchTrackingConn:
    """execute / executemany 호출을 분리해서 추적하는 Fake Connection."""

    def __init__(self):
        self.execute_count = 0
        self.executemany_count = 0
        self.executemany_args: list = []

    def transaction(self):
        return _TxCtx()

    async def execute(self, query: str, *_args):
        self.execute_count += 1

    async def executemany(self, query: str, args):
        self.executemany_count += 1
        self.executemany_args.append((query, list(args)))


def _make_chunks(n: int) -> list[dict]:
    """테스트용 child 청크 N개 생성."""
    import uuid
    return [
        {
            "chunk_id": str(uuid.uuid4()),
            "doc_id": "00000000-0000-0000-0000-000000000001",
            "parent_chunk_id": None,
            "chunk_type": "child",
            "content": f"content {i}",
            "token_count": 100,
            "page_number": None,
            "section_header": "Intro",
        }
        for i in range(n)
    ]


@pytest.mark.asyncio
async def test_save_chunks_uses_executemany_not_per_row_execute():
    """
    _save_chunks()는 N개 청크를 저장할 때 executemany를 1회 호출해야 한다.
    청크마다 개별 execute를 호출하면 안 된다 (N+1 → 1).
    """
    conn = _BatchTrackingConn()
    chunks = _make_chunks(5)

    await _save_chunks(conn, chunks, "00000000-0000-0000-0000-000000000001")

    assert conn.executemany_count == 1, (
        f"executemany를 1회 호출해야 하지만 {conn.executemany_count}회 호출됨"
    )
    assert conn.execute_count == 0, (
        f"청크별 execute는 0회여야 하지만 {conn.execute_count}회 호출됨 (N+1 패턴)"
    )


@pytest.mark.asyncio
async def test_save_chunks_passes_all_rows_to_executemany():
    """executemany에 전달된 rows 수가 청크 수와 일치해야 한다."""
    conn = _BatchTrackingConn()
    chunks = _make_chunks(3)

    await _save_chunks(conn, chunks, "00000000-0000-0000-0000-000000000001")

    _, rows = conn.executemany_args[0]
    assert len(rows) == 3, f"rows 3개여야 하지만 {len(rows)}개"


@pytest.mark.asyncio
async def test_insert_embedding_rows_uses_executemany_not_per_row_execute():
    """
    _insert_embedding_rows()는 N개 임베딩을 저장할 때 executemany를 1회 호출해야 한다.
    """
    conn = _BatchTrackingConn()
    chunks = _make_chunks(4)
    rows = [(c, [0.1] * 1024) for c in chunks]
    metadata = {"category": "기타", "team": None, "tags": []}

    await _insert_embedding_rows(conn, rows, metadata)

    assert conn.executemany_count == 1, (
        f"executemany를 1회 호출해야 하지만 {conn.executemany_count}회 호출됨"
    )
    assert conn.execute_count == 0, (
        f"임베딩별 execute는 0회여야 하지만 {conn.execute_count}회 호출됨 (N+1 패턴)"
    )


@pytest.mark.asyncio
async def test_insert_embedding_rows_passes_all_rows_to_executemany():
    """executemany에 전달된 rows 수가 임베딩 수와 일치해야 한다."""
    conn = _BatchTrackingConn()
    chunks = _make_chunks(4)
    rows = [(c, [0.1] * 1024) for c in chunks]
    metadata = {"category": "기타", "team": None, "tags": []}

    await _insert_embedding_rows(conn, rows, metadata)

    _, passed_rows = conn.executemany_args[0]
    assert len(passed_rows) == 4, f"rows 4개여야 하지만 {len(passed_rows)}개"


@pytest.mark.asyncio
async def test_save_chunks_empty_list_does_not_call_executemany():
    """빈 청크 목록으로 호출 시 executemany를 호출하지 않아야 한다 (불필요한 쿼리 방지)."""
    conn = _BatchTrackingConn()

    await _save_chunks(conn, [], "00000000-0000-0000-0000-000000000001")

    assert conn.executemany_count == 0, "빈 목록으로 executemany를 호출하면 안 된다"
    assert conn.execute_count == 0


# ---------------------------------------------------------------------------
# T3: Neo4j 드라이버 싱글턴 (RED → GREEN)
# ---------------------------------------------------------------------------

def test_get_neo4j_driver_returns_singleton():
    """
    _get_neo4j_driver()는 호출마다 새 드라이버를 생성하지 않고
    동일한 객체를 반환해야 한다 (싱글턴 패턴).
    """
    import module_0_kms.pipeline.stage6_store as m
    # 모듈 수준 싱글턴을 초기화된 상태로 리셋
    m._neo4j_driver = None

    from unittest.mock import MagicMock, patch

    fake_driver = MagicMock()
    with patch("kms.pipeline.stage6_store.AsyncGraphDatabase") as MockGDB:
        MockGDB.driver.return_value = fake_driver

        d1 = _get_neo4j_driver()
        d2 = _get_neo4j_driver()

    assert d1 is d2, "두 번째 호출이 새 드라이버를 생성하면 안 된다"
    assert MockGDB.driver.call_count == 1, (
        f"AsyncGraphDatabase.driver가 {MockGDB.driver.call_count}회 호출됨 — 1회만 허용"
    )


# ---------------------------------------------------------------------------
# T6: _save_document 직접 테스트 (lines 97-123 커버)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_save_document_executes_insert():
    """_save_document()가 conn.execute를 1회 호출해야 한다."""
    conn = _BatchTrackingConn()
    state = _make_state()
    await _save_document(conn, state, "markdown/test/raw.md", "originals/test/file.pdf")
    assert conn.execute_count == 1


# ---------------------------------------------------------------------------
# T6: _embed_text (httpx mock) — lines 77-84 커버
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_embed_text_returns_embedding_vector():
    """_embed_text()가 Ollama 응답에서 embedding 리스트를 반환해야 한다."""
    from unittest.mock import AsyncMock, MagicMock, patch

    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {"embedding": [0.1] * 1024}

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await _embed_text("test text")

    assert len(result) == 1024
    assert result[0] == pytest.approx(0.1)


# ---------------------------------------------------------------------------
# T6: _precompute_embeddings 부분 실패 + 차원 불일치 — lines 168, 182 커버
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_precompute_embeddings_continues_on_partial_failure(monkeypatch):
    """일부 청크 임베딩 실패 시 나머지는 계속 처리되어야 한다 (line 168 경고)."""
    call_count = [0]

    async def partial_embed(text: str) -> list[float]:
        call_count[0] += 1
        if call_count[0] == 1:
            raise RuntimeError("network error")
        return [0.1] * 1024

    monkeypatch.setattr("kms.pipeline.stage6_store._embed_text", partial_embed)

    chunks = [
        {"chunk_id": "c1", "chunk_type": "child", "content": "text1", "section_header": None},
        {"chunk_id": "c2", "chunk_type": "child", "content": "text2", "section_header": None},
    ]
    # _precompute_embeddings는 (rows, model_name) 튜플을 반환한다 (세션 40 하이브리드 임베딩 변경)
    rows, model_name = await _precompute_embeddings(chunks)
    assert len(rows) == 1
    assert isinstance(model_name, str)


@pytest.mark.asyncio
async def test_precompute_embeddings_raises_on_wrong_dimension(monkeypatch):
    """임베딩 차원이 PGVECTOR_DIMENSION과 다르면 RuntimeError를 발생시켜야 한다 (line 182)."""
    async def wrong_dim_embed(text: str) -> list[float]:
        return [0.1] * 512  # 512 ≠ 1024

    monkeypatch.setattr("kms.pipeline.stage6_store._embed_text", wrong_dim_embed)

    chunks = [{"chunk_id": "c1", "chunk_type": "child", "content": "text", "section_header": None}]

    with pytest.raises(RuntimeError, match="Embedding dimension mismatch"):
        await _precompute_embeddings(chunks)


# ---------------------------------------------------------------------------
# T6: _insert_embedding_rows 빈 rows 조기 반환 — line 201 커버
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_insert_embedding_rows_empty_does_nothing():
    """rows가 빈 리스트이면 executemany를 호출하지 않아야 한다 (early return)."""
    conn = _BatchTrackingConn()
    await _insert_embedding_rows(conn, [], {})
    assert conn.executemany_count == 0


# ---------------------------------------------------------------------------
# T6: _save_embeddings 래퍼 성공 경로 — line 239 커버
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_save_embeddings_inserts_when_embeddings_succeed(monkeypatch):
    """임베딩 성공 시 _save_embeddings이 executemany를 1회 호출해야 한다."""
    conn = _BatchTrackingConn()
    chunks = _make_chunks(2)

    async def fake_embed(text: str) -> list[float]:
        return [0.1] * 1024

    monkeypatch.setattr("kms.pipeline.stage6_store._embed_text", fake_embed)
    await _save_embeddings(conn, chunks, {"category": "기타"})
    assert conn.executemany_count == 1


# ---------------------------------------------------------------------------
# T6: _save_to_neo4j 성공/실패 — lines 253-313 커버
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_save_to_neo4j_returns_true_on_success(monkeypatch):
    """Neo4j 저장 성공 시 True를 반환해야 한다."""
    mock_session = AsyncMock()
    mock_session.run = AsyncMock()

    session_ctx = MagicMock()
    session_ctx.__aenter__ = AsyncMock(return_value=mock_session)
    session_ctx.__aexit__ = AsyncMock(return_value=False)

    mock_driver = MagicMock()
    mock_driver.session.return_value = session_ctx

    monkeypatch.setattr("kms.pipeline.stage6_store._get_neo4j_driver", lambda: mock_driver)

    state = {
        "doc_id": "00000000-0000-0000-0000-000000000001",
        "metadata": {"title": "Test", "category": "기타"},
        "chunks": [{"chunk_id": "c1", "chunk_type": "parent", "section_header": "Intro"}],
        "neo4j_entities": [{"name": "FastAPI", "type": "Technology", "description": "web fw"}],
        "neo4j_relations": [{"from_chunk_id": "c1", "entity_name": "FastAPI"}],
    }
    result = await _save_to_neo4j(state)
    assert result is True


@pytest.mark.asyncio
async def test_save_to_neo4j_returns_false_on_exception(monkeypatch):
    """Neo4j 드라이버 연결 실패 시 False를 반환하고 예외를 전파하지 않아야 한다."""
    def fail_driver():
        raise RuntimeError("Neo4j connection failed")

    monkeypatch.setattr("kms.pipeline.stage6_store._get_neo4j_driver", fail_driver)

    state = {
        "doc_id": "00000000-0000-0000-0000-000000000001",
        "metadata": {},
        "chunks": [],
        "neo4j_entities": [],
        "neo4j_relations": [],
    }
    result = await _save_to_neo4j(state)
    assert result is False


# ---------------------------------------------------------------------------
# T6: stage6_store — file_path 존재 경로 (lines 342-345 커버)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_stage6_file_path_reads_and_saves_original(monkeypatch):
    """file_path가 있으면 aiofiles로 읽어 storage.save를 호출해야 한다."""
    from unittest.mock import AsyncMock, patch

    state = _make_state()
    state["file_path"] = "/tmp/test_stage6.pdf"

    mock_file = AsyncMock()
    mock_file.read = AsyncMock(return_value=b"pdf content")
    mock_file.__aenter__ = AsyncMock(return_value=mock_file)
    mock_file.__aexit__ = AsyncMock(return_value=False)

    save_calls: list = []

    class _CapturingStorage:
        async def save(self, path, data):
            save_calls.append((path, data))

    async def fake_embed(text: str) -> list[float]:
        return [0.1] * 1024

    monkeypatch.setattr("kms.pipeline.stage6_store._save_document", AsyncMock())
    monkeypatch.setattr("kms.pipeline.stage6_store._save_chunks", AsyncMock())
    monkeypatch.setattr("kms.pipeline.stage6_store._embed_text", fake_embed)
    monkeypatch.setattr(
        "kms.pipeline.stage6_store._save_to_neo4j", AsyncMock(return_value=True)
    )

    with patch("aiofiles.open", return_value=mock_file):
        result = await stage6_store(state, _FakePool(_FakeConn()), _CapturingStorage())

    assert result["stored"] is True
    assert len(save_calls) == 1


@pytest.mark.asyncio
async def test_stage6_storage_failure_returns_failed(monkeypatch):
    """storage.save가 실패하면 status='failed'를 반환해야 한다 (lines 346-348 커버)."""
    from unittest.mock import AsyncMock, patch

    state = _make_state()
    state["file_path"] = "/tmp/test_stage6_fail.pdf"

    mock_file = AsyncMock()
    mock_file.read = AsyncMock(return_value=b"pdf content")
    mock_file.__aenter__ = AsyncMock(return_value=mock_file)
    mock_file.__aexit__ = AsyncMock(return_value=False)

    class _FailingStorage:
        async def save(self, path, data):
            raise RuntimeError("Storage write error")

    with patch("aiofiles.open", return_value=mock_file):
        result = await stage6_store(state, _FakePool(_FakeConn()), _FailingStorage())

    assert result["stored"] is False
    assert result["status"] == "failed"


# ---------------------------------------------------------------------------
# T6: stage6_store — PostgreSQL 저장 실패 경로 (lines 383-385 커버)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_stage6_postgresql_failure_returns_failed(monkeypatch):
    """DB acquire가 실패하면 status='failed'를 반환해야 한다."""
    async def fake_embed(text: str) -> list[float]:
        return [0.1] * 1024

    monkeypatch.setattr("kms.pipeline.stage6_store._embed_text", fake_embed)

    class _FailCtx:
        async def __aenter__(self):
            raise RuntimeError("DB connection failed")

        async def __aexit__(self, *_):
            return False

    class _FailPool:
        def acquire(self):
            return _FailCtx()

    state = _make_state()
    result = await stage6_store(state, _FailPool(), _FakeStorage())

    assert result["stored"] is False
    assert result["status"] == "failed"


@pytest.mark.asyncio
async def test_stage6_neo4j_failure_returns_stored_partial(monkeypatch):
    """
    Neo4j 저장 실패 시 status='stored_partial'이어야 한다.
    DB 저장(documents, chunks, embeddings)은 성공했다고 가정한다.
    """
    async def fake_save_document(conn, state, md_path, orig_path):
        pass

    async def fake_save_chunks(conn, chunks, doc_id):
        pass

    async def fake_embed(_text: str) -> list[float]:
        return [0.1] * 1024

    monkeypatch.setattr("kms.pipeline.stage6_store._save_document", fake_save_document)
    monkeypatch.setattr("kms.pipeline.stage6_store._save_chunks", fake_save_chunks)
    monkeypatch.setattr("kms.pipeline.stage6_store._embed_text", fake_embed)
    monkeypatch.setattr(
        "kms.pipeline.stage6_store._save_to_neo4j", AsyncMock(return_value=False)
    )

    result = await stage6_store(_make_state(), _FakePool(_FakeConn()), _FakeStorage())

    assert result["status"] == "stored_partial", (
        f"Neo4j 실패 시 'stored_partial'이어야 하지만 '{result['status']}'"
    )
    assert result["stored"] is True, "Neo4j 실패여도 DB 저장은 성공이므로 stored=True"
    assert result["neo4j_stored"] is False


# ---------------------------------------------------------------------------
# BUG-44: source='reprocess' + file_type='' CHECK 제약 위반 재현 테스트
# ---------------------------------------------------------------------------

def _make_reprocess_state() -> dict:
    """make_reprocess_state()가 반환하는 재처리 state와 동일한 구조."""
    return {
        "doc_id": "00000000-0000-0000-0000-000000000099",
        "source": "reprocess",   # BUG-44 원인 ①: documents_source_check 위반
        "file_path": "",
        "file_type": "",          # BUG-44 원인 ②: documents_file_type_check 위반
        "original_filename": "",
        "raw_markdown": "# 재처리 테스트",
        "markdown_storage_path": "markdown/test/raw.md",
        "validated_markdown": "# 재처리 테스트",
        "quality_score": 0.65,
        "quality_issues": ["이미지 손실"],
        "hitl_required": False,
        "chunks": [],
        "chunk_validation_passed": True,
        "chunk_validation_issues": [],
        "metadata": {"title": "재처리 문서", "category": "기타", "team": None,
                     "author": None, "tags": [], "source": "upload"},
        "neo4j_entities": [],
        "neo4j_relations": [],
        "stored": False,
        "neo4j_stored": None,
        "storage_paths": None,
        "status": "processing",
        "error": None,
        "current_stage": "reprocess_init",
        "parser_used": None,
        "doc_complexity": None,
        "parsing_time_ms": None,
    }


class TestBug44SaveDocumentReprocessConstraints:
    """BUG-44: 재처리 state에서 _save_document SQL 파라미터 검증."""

    @pytest.mark.asyncio
    async def test_file_type_param_is_none_not_empty_string(self):
        """file_type='' → SQL 파라미터로 None 전달 (빈 문자열은 file_type_check 위반)."""
        captured: list = []

        class _CapturingConn:
            async def execute(self, _query, *args):
                captured.extend(args)

        state = _make_reprocess_state()
        await _save_document(_CapturingConn(), state, "markdown/test.md", "originals/test")

        # 파라미터 순서: $1=doc_id, $2=title, $3=source, $4=category, $5=file_type
        assert len(captured) >= 5, f"SQL 파라미터가 충분히 캡처되지 않음: {captured}"
        file_type_param = captured[4]
        assert file_type_param is None, (
            f"BUG-44: file_type 파라미터가 None이어야 하지만 {repr(file_type_param)}. "
            f"빈 문자열은 documents_file_type_check 위반."
        )

    @pytest.mark.asyncio
    async def test_sql_preserves_source_on_conflict_with_reprocess(self):
        """ON CONFLICT 시 source='reprocess'는 NULLIF로 걸러져 DB 기존 값 보존."""
        sql_executed: list[str] = []

        class _CapturingConn:
            async def execute(self, query, *_args):
                sql_executed.append(query)

        state = _make_reprocess_state()
        await _save_document(_CapturingConn(), state, "markdown/test.md", "originals/test")

        assert sql_executed, "SQL이 실행되지 않음"
        sql = sql_executed[0]
        assert "NULLIF(EXCLUDED.source, 'reprocess')" in sql, (
            "BUG-44: ON CONFLICT UPDATE에 NULLIF('reprocess') 처리가 없으면 "
            "documents_source_check 제약 위반 발생."
        )

    @pytest.mark.asyncio
    async def test_stage6_store_completes_with_reprocess_state(self, monkeypatch):
        """전체 stage6_store가 재처리 state에서 예외 없이 완료되어야 한다."""
        monkeypatch.setattr(
            "kms.pipeline.stage6_store._precompute_embeddings",
            AsyncMock(return_value=([], "bge-m3")),
        )
        monkeypatch.setattr(
            "kms.pipeline.stage6_store._save_to_neo4j",
            AsyncMock(return_value=True),
        )

        class _OkConn:
            def transaction(self):
                return _TxCtx()
            async def execute(self, *_args):
                pass
            async def executemany(self, *_args):
                pass

        result = await stage6_store(
            _make_reprocess_state(),
            _FakePool(_OkConn()),
            _FakeStorage(),
        )

        assert result.get("stored") is True, (
            f"BUG-44: 재처리 state에서 stage6_store가 stored=True로 끝나야 함. "
            f"result={result}"
        )
        assert "error" not in result or result.get("error") is None, (
            f"BUG-44: 예상치 못한 에러 발생: {result.get('error')}"
        )
