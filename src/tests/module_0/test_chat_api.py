"""Tests for POST /chat — RAG 챗봇 엔드포인트.

TDD RED → GREEN:
  목표: question 임베딩 → pgVector 검색 → LLM 답변 생성 → sources + answer 포함 응답
"""

from __future__ import annotations

import pytest

import module_0_kms.chat_api as chat_api
from module_0_kms.chat_api import chat


# ---------------------------------------------------------------------------
# 헬퍼
# ---------------------------------------------------------------------------


class _AcquireCtx:
    def __init__(self, conn):
        self._conn = conn

    async def __aenter__(self):
        return self._conn

    async def __aexit__(self, *_):
        return False


class _FakePool:
    def __init__(self, conn):
        self._conn = conn

    def acquire(self):
        return _AcquireCtx(self._conn)


class _ConnSearch:
    """chunk_embeddings pgVector 검색을 흉내내는 커넥션 Mock."""

    def __init__(self, rows: list[dict] | None = None):
        self._rows = rows if rows is not None else []
        self.last_fetch_args: tuple | None = None

    async def fetch(self, query: str, *args, **_kw):
        self.last_fetch_args = args
        return self._rows


def _chunk_row(
    chunk_id: str = "chunk-001",
    content: str = "N+1 쿼리는 for 루프 안에서 DB 호출을 반복하는 패턴이다.",
    score: float = 0.92,
    doc_title: str = "N+1 쿼리 방지 가이드",
) -> dict:
    return {
        "chunk_id": chunk_id,
        "content": content,
        "score": score,
        "doc_title": doc_title,
    }


FAKE_EMBEDDING = [0.1] * 1024


# ---------------------------------------------------------------------------
# 응답 구조 검증
# ---------------------------------------------------------------------------


class TestChatResponseStructure:
    async def test_response_has_question_field(self, monkeypatch):
        """응답에 question 필드가 포함된다."""
        monkeypatch.setattr(chat_api, "_db_pool", _FakePool(_ConnSearch()))
        monkeypatch.setattr(chat_api, "_embed_question", _make_embed())
        monkeypatch.setattr(chat_api, "_generate_answer", _make_llm("답변"))
        result = await chat(_make_request("N+1 쿼리란?"))
        assert hasattr(result, "question")

    async def test_response_has_answer_field(self, monkeypatch):
        """응답에 answer 필드가 포함된다."""
        monkeypatch.setattr(chat_api, "_db_pool", _FakePool(_ConnSearch()))
        monkeypatch.setattr(chat_api, "_embed_question", _make_embed())
        monkeypatch.setattr(chat_api, "_generate_answer", _make_llm("답변"))
        result = await chat(_make_request("N+1 쿼리란?"))
        assert hasattr(result, "answer")

    async def test_response_has_sources_field(self, monkeypatch):
        """응답에 sources 필드가 포함된다."""
        monkeypatch.setattr(chat_api, "_db_pool", _FakePool(_ConnSearch()))
        monkeypatch.setattr(chat_api, "_embed_question", _make_embed())
        monkeypatch.setattr(chat_api, "_generate_answer", _make_llm("답변"))
        result = await chat(_make_request("N+1 쿼리란?"))
        assert hasattr(result, "sources")

    async def test_response_has_model_field(self, monkeypatch):
        """응답에 model 필드가 포함된다."""
        monkeypatch.setattr(chat_api, "_db_pool", _FakePool(_ConnSearch()))
        monkeypatch.setattr(chat_api, "_embed_question", _make_embed())
        monkeypatch.setattr(chat_api, "_generate_answer", _make_llm("답변"))
        result = await chat(_make_request("N+1 쿼리란?"))
        assert hasattr(result, "model")

    async def test_sources_is_list(self, monkeypatch):
        """sources 필드는 리스트 타입이다."""
        monkeypatch.setattr(chat_api, "_db_pool", _FakePool(_ConnSearch()))
        monkeypatch.setattr(chat_api, "_embed_question", _make_embed())
        monkeypatch.setattr(chat_api, "_generate_answer", _make_llm("답변"))
        result = await chat(_make_request("테스트"))
        assert isinstance(result.sources, list)


# ---------------------------------------------------------------------------
# RAG 동작 검증
# ---------------------------------------------------------------------------


class TestChatRagBehavior:
    async def test_question_echoed_in_response(self, monkeypatch):
        """question이 응답 question 필드에 그대로 반환된다."""
        monkeypatch.setattr(chat_api, "_db_pool", _FakePool(_ConnSearch()))
        monkeypatch.setattr(chat_api, "_embed_question", _make_embed())
        monkeypatch.setattr(chat_api, "_generate_answer", _make_llm("답변"))
        result = await chat(_make_request("N+1 쿼리 방지 방법은?"))
        assert result.question == "N+1 쿼리 방지 방법은?"

    async def test_llm_answer_in_response(self, monkeypatch):
        """LLM이 생성한 답변이 answer 필드에 포함된다."""
        monkeypatch.setattr(chat_api, "_db_pool", _FakePool(_ConnSearch()))
        monkeypatch.setattr(chat_api, "_embed_question", _make_embed())
        monkeypatch.setattr(chat_api, "_generate_answer", _make_llm("joinedload를 사용하세요."))
        result = await chat(_make_request("N+1 쿼리란?"))
        assert result.answer == "joinedload를 사용하세요."

    async def test_empty_pgvector_results_gives_empty_sources(self, monkeypatch):
        """pgVector 검색 결과가 0건이면 sources는 빈 리스트다."""
        monkeypatch.setattr(chat_api, "_db_pool", _FakePool(_ConnSearch(rows=[])))
        monkeypatch.setattr(chat_api, "_embed_question", _make_embed())
        monkeypatch.setattr(chat_api, "_generate_answer", _make_llm("답변 없음"))
        result = await chat(_make_request("알 수 없는 질문"))
        assert result.sources == []

    async def test_pgvector_results_appear_in_sources(self, monkeypatch):
        """pgVector 검색 결과가 있으면 sources에 포함된다."""
        rows = [_chunk_row("chunk-001"), _chunk_row("chunk-002")]
        monkeypatch.setattr(chat_api, "_db_pool", _FakePool(_ConnSearch(rows=rows)))
        monkeypatch.setattr(chat_api, "_embed_question", _make_embed())
        monkeypatch.setattr(chat_api, "_generate_answer", _make_llm("답변"))
        result = await chat(_make_request("N+1 쿼리란?"))
        assert len(result.sources) == 2

    async def test_source_item_has_chunk_id(self, monkeypatch):
        """sources 각 항목에 chunk_id가 있다."""
        monkeypatch.setattr(chat_api, "_db_pool", _FakePool(_ConnSearch([_chunk_row()])))
        monkeypatch.setattr(chat_api, "_embed_question", _make_embed())
        monkeypatch.setattr(chat_api, "_generate_answer", _make_llm("답변"))
        result = await chat(_make_request("질문"))
        assert hasattr(result.sources[0], "chunk_id")

    async def test_source_item_has_content(self, monkeypatch):
        """sources 각 항목에 content가 있다."""
        monkeypatch.setattr(chat_api, "_db_pool", _FakePool(_ConnSearch([_chunk_row()])))
        monkeypatch.setattr(chat_api, "_embed_question", _make_embed())
        monkeypatch.setattr(chat_api, "_generate_answer", _make_llm("답변"))
        result = await chat(_make_request("질문"))
        assert hasattr(result.sources[0], "content")

    async def test_source_item_has_score(self, monkeypatch):
        """sources 각 항목에 similarity score가 있다."""
        monkeypatch.setattr(chat_api, "_db_pool", _FakePool(_ConnSearch([_chunk_row()])))
        monkeypatch.setattr(chat_api, "_embed_question", _make_embed())
        monkeypatch.setattr(chat_api, "_generate_answer", _make_llm("답변"))
        result = await chat(_make_request("질문"))
        assert hasattr(result.sources[0], "score")

    async def test_source_chunk_id_value(self, monkeypatch):
        """sources[0].chunk_id가 실제 검색 결과의 chunk_id와 일치한다."""
        monkeypatch.setattr(chat_api, "_db_pool", _FakePool(_ConnSearch([_chunk_row("abc-123")])))
        monkeypatch.setattr(chat_api, "_embed_question", _make_embed())
        monkeypatch.setattr(chat_api, "_generate_answer", _make_llm("답변"))
        result = await chat(_make_request("질문"))
        assert result.sources[0].chunk_id == "abc-123"

    async def test_source_score_value(self, monkeypatch):
        """sources[0].score가 실제 검색 점수와 일치한다."""
        monkeypatch.setattr(chat_api, "_db_pool", _FakePool(_ConnSearch([_chunk_row(score=0.87)])))
        monkeypatch.setattr(chat_api, "_embed_question", _make_embed())
        monkeypatch.setattr(chat_api, "_generate_answer", _make_llm("답변"))
        result = await chat(_make_request("질문"))
        assert result.sources[0].score == pytest.approx(0.87)


# ---------------------------------------------------------------------------
# top_k / DB 쿼리 인자 검증
# ---------------------------------------------------------------------------


class TestChatDbArgs:
    async def test_default_top_k_is_5(self, monkeypatch):
        """top_k 기본값은 5이다."""
        conn = _ConnSearch()
        monkeypatch.setattr(chat_api, "_db_pool", _FakePool(conn))
        monkeypatch.setattr(chat_api, "_embed_question", _make_embed())
        monkeypatch.setattr(chat_api, "_generate_answer", _make_llm("답변"))
        await chat(_make_request("질문"))
        assert conn.last_fetch_args is not None
        assert 5 in conn.last_fetch_args

    async def test_custom_top_k_passed_to_db(self, monkeypatch):
        """top_k=3이면 DB 쿼리 인자로 3이 전달된다."""
        conn = _ConnSearch()
        monkeypatch.setattr(chat_api, "_db_pool", _FakePool(conn))
        monkeypatch.setattr(chat_api, "_embed_question", _make_embed())
        monkeypatch.setattr(chat_api, "_generate_answer", _make_llm("답변"))
        await chat(_make_request("질문", top_k=3))
        assert conn.last_fetch_args is not None
        assert 3 in conn.last_fetch_args

    async def test_embedding_passed_to_db(self, monkeypatch):
        """_embed_question 결과가 DB 쿼리 인자로 전달된다."""
        conn = _ConnSearch()
        monkeypatch.setattr(chat_api, "_db_pool", _FakePool(conn))
        monkeypatch.setattr(chat_api, "_embed_question", _make_embed(FAKE_EMBEDDING))
        monkeypatch.setattr(chat_api, "_generate_answer", _make_llm("답변"))
        await chat(_make_request("질문"))
        import json
        assert conn.last_fetch_args is not None
        # 임베딩은 JSON 문자열로 직렬화돼 DB로 전달된다
        assert json.dumps(FAKE_EMBEDDING) in conn.last_fetch_args


# ---------------------------------------------------------------------------
# 유효성 검사
# ---------------------------------------------------------------------------


class TestChatValidation:
    async def test_empty_question_raises(self, monkeypatch):
        """빈 question 문자열이면 ValueError가 발생한다."""
        monkeypatch.setattr(chat_api, "_db_pool", _FakePool(_ConnSearch()))
        monkeypatch.setattr(chat_api, "_embed_question", _make_embed())
        monkeypatch.setattr(chat_api, "_generate_answer", _make_llm("답변"))
        with pytest.raises((ValueError, Exception)):
            await chat(_make_request(""))

    async def test_model_field_is_non_empty_string(self, monkeypatch):
        """model 필드는 빈 문자열이 아닌 모델명이다."""
        monkeypatch.setattr(chat_api, "_db_pool", _FakePool(_ConnSearch()))
        monkeypatch.setattr(chat_api, "_embed_question", _make_embed())
        monkeypatch.setattr(chat_api, "_generate_answer", _make_llm("답변"))
        result = await chat(_make_request("질문"))
        assert isinstance(result.model, str) and len(result.model) > 0


# ---------------------------------------------------------------------------
# 내부 헬퍼 팩토리
# ---------------------------------------------------------------------------


def _make_request(question: str, top_k: int = 5):
    """ChatRequest 생성."""
    from module_0_kms.chat_api import ChatRequest
    return ChatRequest(question=question, top_k=top_k)


def _make_embed(embedding: list[float] | None = None):
    """_embed_question을 대체하는 async mock 팩토리."""
    _emb = embedding if embedding is not None else FAKE_EMBEDDING

    async def _fake_embed(question: str) -> list[float]:
        return _emb

    return _fake_embed


def _make_llm(answer: str):
    """_generate_answer를 대체하는 async mock 팩토리."""

    async def _fake_llm(question: str, context: str) -> str:
        return answer

    return _fake_llm


# ---------------------------------------------------------------------------
# T4: _query_pgvector()
# ---------------------------------------------------------------------------

class TestQueryPgvector:
    """_query_pgvector는 임베딩을 받아 chunk_embeddings에서 상위 k개를 반환한다."""

    def _make_pool(self, rows):
        class _Conn:
            async def fetch(self, query, *args, **_):
                return rows
        class _Pool:
            def acquire(self):
                class _Ctx:
                    async def __aenter__(self_): return _Conn()
                    async def __aexit__(self_, *_): pass
                return _Ctx()
        return _Pool()

    @pytest.fixture
    def fake_embed(self, monkeypatch):
        async def _embed(q): return [0.1] * 1024
        monkeypatch.setattr(chat_api, "_embed_question", _embed)

    async def test_returns_list_of_dicts(self, fake_embed):
        from module_0_kms.chat_api import _query_pgvector
        rows = [{"chunk_id": "c1", "content": "내용1", "score": 0.9, "doc_title": "문서A"}]
        result = await _query_pgvector("질문", self._make_pool(rows), top_k=1)
        assert isinstance(result, list)
        assert result[0]["source_type"] == "pgvector"

    async def test_returns_empty_list_when_no_rows(self, fake_embed):
        from module_0_kms.chat_api import _query_pgvector
        result = await _query_pgvector("질문", self._make_pool([]), top_k=5)
        assert result == []

    async def test_source_type_is_pgvector(self, fake_embed):
        from module_0_kms.chat_api import _query_pgvector
        rows = [{"chunk_id": "c1", "content": "텍스트", "score": 0.8, "doc_title": None}]
        result = await _query_pgvector("질문", self._make_pool(rows), top_k=1)
        assert result[0]["source_type"] == "pgvector"


# ---------------------------------------------------------------------------
# T5: _query_postgresql()
# ---------------------------------------------------------------------------

class TestQueryPostgresql:
    """_query_postgresql은 Gemini Text-to-SQL로 SQL을 생성하고 _validate_sql 검증 후 실행한다."""

    def _make_pool(self, rows):
        class _Conn:
            async def fetch(self, query, *args, **_):
                return rows
        class _Pool:
            def acquire(self):
                class _Ctx:
                    async def __aenter__(self_): return _Conn()
                    async def __aexit__(self_, *_): pass
                return _Ctx()
        return _Pool()

    @pytest.fixture
    def mock_text_to_sql(self, monkeypatch):
        """_generate_sql을 패치해 제어된 SQL을 반환한다."""
        captured = {}
        async def fake_gen(question, schema_hint=""):
            return captured.get("sql", "SELECT title FROM documents LIMIT 5")
        monkeypatch.setattr("kms.chat_api._generate_sql", fake_gen)
        return captured

    async def test_returns_list_of_dicts(self, mock_text_to_sql):
        from module_0_kms.chat_api import _query_postgresql
        rows = [{"title": "온보딩 가이드", "file_type": "pdf"}]
        result = await _query_postgresql("문서 목록", self._make_pool(rows))
        assert isinstance(result, list)

    async def test_source_type_is_postgresql(self, mock_text_to_sql):
        from module_0_kms.chat_api import _query_postgresql
        rows = [{"title": "가이드"}]
        result = await _query_postgresql("문서 몇 개야?", self._make_pool(rows))
        assert result[0]["source_type"] == "postgresql"

    async def test_invalid_sql_returns_empty(self, monkeypatch):
        """_validate_sql이 False를 반환하면 빈 리스트를 반환한다."""
        async def bad_sql(question, schema_hint=""):
            return "DROP TABLE documents"
        monkeypatch.setattr("kms.chat_api._generate_sql", bad_sql)
        from module_0_kms.chat_api import _query_postgresql
        result = await _query_postgresql("테이블 삭제해줘", self._make_pool([]))
        assert result == []

    async def test_empty_rows_returns_empty_list(self, mock_text_to_sql):
        from module_0_kms.chat_api import _query_postgresql
        result = await _query_postgresql("결과 없는 질문", self._make_pool([]))
        assert result == []

    async def test_row_fields_are_serialized(self, mock_text_to_sql):
        """각 행은 source_type 포함 dict로 변환된다."""
        from module_0_kms.chat_api import _query_postgresql
        rows = [{"title": "아키텍처 문서", "count": 3}]
        result = await _query_postgresql("문서 목록", self._make_pool(rows))
        assert result[0]["source_type"] == "postgresql"
        assert "title" in result[0] or "count" in result[0]


# ---------------------------------------------------------------------------
# T6: _query_neo4j()
# ---------------------------------------------------------------------------

class TestQueryNeo4j:
    """_query_neo4j는 고정 Cypher 템플릿으로 관계 그래프를 조회한다."""

    @pytest.fixture
    def mock_neo4j(self, monkeypatch):
        """_run_cypher를 패치해 제어된 결과를 반환한다."""
        captured = {}
        async def fake_run(cypher, params=None):
            return captured.get("records", [])
        monkeypatch.setattr("kms.chat_api._run_cypher", fake_run)
        return captured

    async def test_returns_list(self, mock_neo4j):
        from module_0_kms.chat_api import _query_neo4j
        result = await _query_neo4j("아키텍처 관련 개념")
        assert isinstance(result, list)

    async def test_source_type_is_neo4j(self, mock_neo4j):
        mock_neo4j["records"] = [{"entity": "FastAPI", "relation": "MENTIONS", "chunk": "아키텍처"}]
        from module_0_kms.chat_api import _query_neo4j
        result = await _query_neo4j("FastAPI와 연관된 개념")
        assert result[0]["source_type"] == "neo4j"

    async def test_empty_result_returns_empty_list(self, mock_neo4j):
        mock_neo4j["records"] = []
        from module_0_kms.chat_api import _query_neo4j
        result = await _query_neo4j("없는 개념")
        assert result == []

    async def test_neo4j_exception_returns_empty_list(self, monkeypatch):
        """Neo4j 연결 실패 시 예외를 삼키고 빈 리스트를 반환한다."""
        async def raise_error(cypher, params=None):
            raise ConnectionError("Neo4j 연결 실패")
        monkeypatch.setattr("kms.chat_api._run_cypher", raise_error)
        from module_0_kms.chat_api import _query_neo4j
        result = await _query_neo4j("연결 실패 케이스")
        assert result == []


# ---------------------------------------------------------------------------
# T7: _query_gcs()
# ---------------------------------------------------------------------------

class TestQueryGcs:
    """_query_gcs는 GCS에서 Markdown 파일을 읽어 Gemini로 요약한다."""

    @pytest.fixture
    def mock_gcs(self, monkeypatch):
        """_fetch_gcs_markdown과 _generate_answer를 패치한다."""
        captured = {}
        async def fake_fetch(file_name):
            return captured.get("content", "")
        async def fake_answer(question, context):
            return captured.get("summary", "[Mock GCS 요약]")
        monkeypatch.setattr("kms.chat_api._fetch_gcs_markdown", fake_fetch)
        monkeypatch.setattr("kms.chat_api._generate_answer", fake_answer)
        return captured

    async def test_returns_list(self, mock_gcs):
        from module_0_kms.chat_api import _query_gcs
        result = await _query_gcs("온보딩가이드 내용 보여줘")
        assert isinstance(result, list)

    async def test_source_type_is_gcs(self, mock_gcs):
        mock_gcs["content"] = "## 온보딩 가이드\n\n내용입니다."
        mock_gcs["summary"] = "온보딩 가이드 요약"
        from module_0_kms.chat_api import _query_gcs
        result = await _query_gcs("온보딩가이드")
        assert result[0]["source_type"] == "gcs"

    async def test_empty_content_returns_empty_list(self, mock_gcs):
        mock_gcs["content"] = ""
        from module_0_kms.chat_api import _query_gcs
        result = await _query_gcs("없는 파일")
        assert result == []

    async def test_gcs_exception_returns_empty_list(self, monkeypatch):
        """GCS 연결 실패 시 빈 리스트를 반환한다."""
        async def raise_error(file_name):
            raise ConnectionError("GCS 접근 실패")
        monkeypatch.setattr("kms.chat_api._fetch_gcs_markdown", raise_error)
        from module_0_kms.chat_api import _query_gcs
        result = await _query_gcs("연결 실패")
        assert result == []


# ---------------------------------------------------------------------------
# T8: POST /chat 라우터 통합 — Intent → Storage 라우팅
# ---------------------------------------------------------------------------

class TestChatRouting:
    """POST /chat 엔드포인트가 intent에 따라 올바른 Storage 쿼리 함수를 호출한다."""

    def _make_pool(self, rows=None):
        class _Conn:
            async def fetch(self, *a, **_): return rows or []
        class _Pool:
            def acquire(self):
                class _Ctx:
                    async def __aenter__(self_): return _Conn()
                    async def __aexit__(self_, *_): pass
                return _Ctx()
        return _Pool()

    @pytest.fixture
    def base_mocks(self, monkeypatch):
        """공통 mock — embed, generate_answer, classify_intent(semantic)."""
        monkeypatch.setattr(chat_api, "_db_pool", self._make_pool())
        monkeypatch.setattr(chat_api, "_embed_question", _make_embed())
        monkeypatch.setattr(chat_api, "_generate_answer", _make_llm("답변"))
        monkeypatch.setattr(chat_api, "_classify_intent",
                            _make_classify_mock("semantic", ["pgvector"]))

    async def test_semantic_intent_uses_pgvector(self, base_mocks, monkeypatch):
        """intent=semantic이면 _query_pgvector를 호출한다."""
        called = []
        async def fake_pgvector(q, pool, top_k=5):
            called.append("pgvector")
            return []
        monkeypatch.setattr(chat_api, "_query_pgvector", fake_pgvector)
        await chat(_make_request("N+1 쿼리 방지 방법"))
        assert "pgvector" in called

    async def test_structured_intent_uses_postgresql(self, monkeypatch):
        """intent=structured이면 _query_postgresql을 호출한다."""
        monkeypatch.setattr(chat_api, "_db_pool", self._make_pool())
        monkeypatch.setattr(chat_api, "_embed_question", _make_embed())
        monkeypatch.setattr(chat_api, "_generate_answer", _make_llm("답변"))
        monkeypatch.setattr(chat_api, "_classify_intent",
                            _make_classify_mock("structured", ["postgresql"]))
        called = []
        async def fake_pg(q, pool, schema_hint=""):
            called.append("postgresql")
            return []
        monkeypatch.setattr(chat_api, "_query_postgresql", fake_pg)
        await chat(_make_request("저장된 문서 몇 개야?"))
        assert "postgresql" in called

    async def test_graph_intent_uses_neo4j(self, monkeypatch):
        """intent=graph이면 _query_neo4j를 호출한다."""
        monkeypatch.setattr(chat_api, "_db_pool", self._make_pool())
        monkeypatch.setattr(chat_api, "_embed_question", _make_embed())
        monkeypatch.setattr(chat_api, "_generate_answer", _make_llm("답변"))
        monkeypatch.setattr(chat_api, "_classify_intent",
                            _make_classify_mock("graph", ["neo4j"]))
        called = []
        async def fake_neo(q):
            called.append("neo4j")
            return []
        monkeypatch.setattr(chat_api, "_query_neo4j", fake_neo)
        await chat(_make_request("아키텍처와 관련된 개념들"))
        assert "neo4j" in called

    async def test_file_intent_uses_gcs(self, monkeypatch):
        """intent=file이면 _query_gcs를 호출한다."""
        monkeypatch.setattr(chat_api, "_db_pool", self._make_pool())
        monkeypatch.setattr(chat_api, "_embed_question", _make_embed())
        monkeypatch.setattr(chat_api, "_generate_answer", _make_llm("답변"))
        monkeypatch.setattr(chat_api, "_classify_intent",
                            _make_classify_mock("file", ["gcs"]))
        called = []
        async def fake_gcs(q):
            called.append("gcs")
            return []
        monkeypatch.setattr(chat_api, "_query_gcs", fake_gcs)
        await chat(_make_request("온보딩가이드.md 보여줘"))
        assert "gcs" in called

    async def test_response_has_intent_field(self, base_mocks, monkeypatch):
        """응답에 intent 필드가 포함된다."""
        monkeypatch.setattr(chat_api, "_query_pgvector", _make_pgvector_mock([]))
        result = await chat(_make_request("질문"))
        assert hasattr(result, "intent")

    async def test_response_has_storages_field(self, base_mocks, monkeypatch):
        """응답에 storages 필드가 포함된다."""
        monkeypatch.setattr(chat_api, "_query_pgvector", _make_pgvector_mock([]))
        result = await chat(_make_request("질문"))
        assert hasattr(result, "storages")
        assert isinstance(result.storages, list)


def _make_pgvector_mock(results):
    async def _fake(q, pool, top_k=5):
        return results
    return _fake


# ---------------------------------------------------------------------------
# T2: ChatIntent + _classify_intent()
# ---------------------------------------------------------------------------

def _make_classify_mock(intent: str, storages: list[str], query_hint: str = ""):
    """_classify_intent를 대체하는 async mock."""
    async def _fake(question: str):
        from module_0_kms.chat_api import IntentResult
        return IntentResult(intent=intent, storages=storages, query_hint=query_hint)
    return _fake


class TestClassifyIntent:
    """_classify_intent는 질문을 분석해 intent + storages[]를 반환한다."""

    @pytest.fixture
    def mock_gemini_classify(self, monkeypatch):
        """call_gemini_with_retry를 패치하고 _USE_MOCK_LLM을 False로 설정."""
        from unittest.mock import MagicMock
        captured = {}

        async def fake_gemini(messages):
            resp = MagicMock()
            resp.content = captured.get("payload", "")
            return resp

        import module_0_kms.chat_api as m
        monkeypatch.setattr(m, "call_gemini_with_retry", fake_gemini)
        monkeypatch.setattr(m, "_USE_MOCK_LLM", False)
        return captured

    async def test_semantic_question_returns_pgvector(self, mock_gemini_classify):
        mock_gemini_classify["payload"] = (
            '{"intent":"semantic","storages":["pgvector"],"query_hint":""}'
        )
        from module_0_kms.chat_api import _classify_intent
        result = await _classify_intent("N+1 쿼리 방지 방법 설명해줘")
        assert result.intent == "semantic"
        assert "pgvector" in result.storages

    async def test_structured_question_returns_postgresql(self, mock_gemini_classify):
        mock_gemini_classify["payload"] = (
            '{"intent":"structured","storages":["postgresql"],"query_hint":"문서 개수"}'
        )
        from module_0_kms.chat_api import _classify_intent
        result = await _classify_intent("저장된 문서 몇 개야?")
        assert result.intent == "structured"
        assert "postgresql" in result.storages

    async def test_graph_question_returns_neo4j(self, mock_gemini_classify):
        mock_gemini_classify["payload"] = (
            '{"intent":"graph","storages":["neo4j"],"query_hint":"아키텍처"}'
        )
        from module_0_kms.chat_api import _classify_intent
        result = await _classify_intent("아키텍처와 연관된 개념들 뭐가 있어?")
        assert result.intent == "graph"
        assert "neo4j" in result.storages

    async def test_file_question_returns_gcs(self, mock_gemini_classify):
        mock_gemini_classify["payload"] = (
            '{"intent":"file","storages":["gcs"],"query_hint":"온보딩가이드"}'
        )
        from module_0_kms.chat_api import _classify_intent
        result = await _classify_intent("온보딩가이드 내용 보여줘")
        assert result.intent == "file"
        assert "gcs" in result.storages

    async def test_json_parse_failure_falls_back_to_semantic(self, mock_gemini_classify):
        """LLM이 잘못된 JSON을 반환하면 semantic으로 폴백한다."""
        mock_gemini_classify["payload"] = "잘못된 응답"
        from module_0_kms.chat_api import _classify_intent
        result = await _classify_intent("아무 질문")
        assert result.intent == "semantic"
        assert "pgvector" in result.storages

    async def test_mock_llm_returns_semantic(self, monkeypatch):
        """USE_MOCK_LLM=true이면 항상 semantic을 반환한다."""
        monkeypatch.setenv("USE_MOCK_LLM", "true")
        from module_0_kms.chat_api import _classify_intent
        result = await _classify_intent("뭔가 질문")
        assert result.intent == "semantic"

    async def test_result_has_required_fields(self, mock_gemini_classify):
        """IntentResult는 intent, storages, query_hint 필드를 가진다."""
        mock_gemini_classify["payload"] = (
            '{"intent":"semantic","storages":["pgvector"],"query_hint":"테스트"}'
        )
        from module_0_kms.chat_api import _classify_intent, IntentResult
        result = await _classify_intent("테스트 질문")
        assert hasattr(result, "intent")
        assert hasattr(result, "storages")
        assert hasattr(result, "query_hint")
        assert isinstance(result, IntentResult)


# ---------------------------------------------------------------------------
# T1: _validate_sql() — SQL 보안 검증
# ---------------------------------------------------------------------------

class TestValidateSql:
    """_validate_sql은 SELECT 전용 쿼리만 허용하고 위험 키워드를 차단한다."""

    def test_valid_select_passes(self):
        from module_0_kms.chat_api import _validate_sql
        assert _validate_sql("SELECT COUNT(*) FROM documents LIMIT 10") is True

    def test_valid_select_with_where_passes(self):
        from module_0_kms.chat_api import _validate_sql
        assert _validate_sql("SELECT title, file_type FROM documents WHERE file_type='pdf' LIMIT 20") is True

    def test_drop_table_blocked(self):
        from module_0_kms.chat_api import _validate_sql
        assert _validate_sql("DROP TABLE documents") is False

    def test_delete_blocked(self):
        from module_0_kms.chat_api import _validate_sql
        assert _validate_sql("DELETE FROM documents WHERE doc_id='abc'") is False

    def test_insert_blocked(self):
        from module_0_kms.chat_api import _validate_sql
        assert _validate_sql("INSERT INTO documents VALUES ('a','b')") is False

    def test_update_blocked(self):
        from module_0_kms.chat_api import _validate_sql
        assert _validate_sql("UPDATE documents SET title='x' WHERE doc_id='1'") is False

    def test_truncate_blocked(self):
        from module_0_kms.chat_api import _validate_sql
        assert _validate_sql("TRUNCATE TABLE documents") is False

    def test_select_without_limit_blocked(self):
        """LIMIT 없는 SELECT는 풀 스캔 방지를 위해 차단한다."""
        from module_0_kms.chat_api import _validate_sql
        assert _validate_sql("SELECT * FROM documents") is False

    def test_empty_string_blocked(self):
        from module_0_kms.chat_api import _validate_sql
        assert _validate_sql("") is False

    def test_case_insensitive_drop_blocked(self):
        """대소문자 혼합 위험 키워드도 차단한다."""
        from module_0_kms.chat_api import _validate_sql
        assert _validate_sql("select * from documents; Drop Table users LIMIT 10") is False


# ---------------------------------------------------------------------------
# T2: _validate_sql_v2() — sqlglot AST 기반 SQL 검증 (RED → GREEN)
# ---------------------------------------------------------------------------

class TestValidateSqlV2:
    """_validate_sql_v2는 sqlglot AST로 파싱해 keyword-split 취약점을 제거한다.

    현재 _validate_sql이 놓치는 공격:
    - UNION SELECT로 users 테이블 exfiltration
    - 세미콜론 stacked query (SELECT … LIMIT 5; SELECT user_id …)
    - 허용 테이블 외 직접 접근 (users, pr_reviews, information_schema 등)
    - 서브쿼리로 unauthorized 테이블 접근
    """

    # --- 기존 정상 쿼리 — True (GREEN) ---

    def test_valid_select_documents(self):
        from module_0_kms.chat_api import _validate_sql_v2
        assert _validate_sql_v2("SELECT COUNT(*) FROM documents LIMIT 10") is True

    def test_valid_select_chunks(self):
        from module_0_kms.chat_api import _validate_sql_v2
        assert _validate_sql_v2(
            "SELECT content FROM chunks WHERE chunk_id='abc' LIMIT 5"
        ) is True

    def test_valid_select_agent_traces(self):
        from module_0_kms.chat_api import _validate_sql_v2
        assert _validate_sql_v2("SELECT * FROM agent_traces LIMIT 20") is True

    def test_valid_select_with_join_allowed_tables(self):
        from module_0_kms.chat_api import _validate_sql_v2
        assert _validate_sql_v2(
            "SELECT d.title, c.content FROM documents d JOIN chunks c "
            "ON d.doc_id = c.doc_id LIMIT 10"
        ) is True

    def test_valid_select_with_where_and_order(self):
        from module_0_kms.chat_api import _validate_sql_v2
        assert _validate_sql_v2(
            "SELECT title, file_type FROM documents WHERE file_type='pdf' "
            "ORDER BY created_at DESC LIMIT 20"
        ) is True

    # --- 기존 차단 대상 — False (GREEN) ---

    def test_drop_blocked(self):
        from module_0_kms.chat_api import _validate_sql_v2
        assert _validate_sql_v2("DROP TABLE documents") is False

    def test_delete_blocked(self):
        from module_0_kms.chat_api import _validate_sql_v2
        assert _validate_sql_v2("DELETE FROM documents WHERE doc_id='abc'") is False

    def test_insert_blocked(self):
        from module_0_kms.chat_api import _validate_sql_v2
        assert _validate_sql_v2("INSERT INTO documents VALUES ('a', 'b')") is False

    def test_empty_blocked(self):
        from module_0_kms.chat_api import _validate_sql_v2
        assert _validate_sql_v2("") is False

    def test_select_without_limit_blocked(self):
        from module_0_kms.chat_api import _validate_sql_v2
        assert _validate_sql_v2("SELECT * FROM documents") is False

    # --- 신규 취약점 차단 (현재 _validate_sql은 True를 반환하는 버그) ---

    def test_union_select_exfiltration_blocked(self):
        """UNION SELECT로 users 테이블에서 github_id 탈취 시도 차단.

        현재 _validate_sql은 True를 반환 — 이것이 keyword-split의 핵심 취약점.
        """
        from module_0_kms.chat_api import _validate_sql_v2
        assert _validate_sql_v2(
            "SELECT doc_id FROM documents UNION SELECT github_id FROM users LIMIT 10"
        ) is False

    def test_stacked_query_semicolon_blocked(self):
        """세미콜론 뒤 두 번째 SELECT로 users 접근 차단 (stacked query).

        현재 _validate_sql은 True를 반환.
        """
        from module_0_kms.chat_api import _validate_sql_v2
        assert _validate_sql_v2(
            "SELECT title FROM documents LIMIT 5; SELECT user_id FROM users LIMIT 5"
        ) is False

    def test_unauthorized_table_users_blocked(self):
        """허용 테이블 외(users) 직접 접근 차단.

        현재 _validate_sql은 True를 반환.
        """
        from module_0_kms.chat_api import _validate_sql_v2
        assert _validate_sql_v2(
            "SELECT user_id, github_id FROM users LIMIT 10"
        ) is False

    def test_unauthorized_table_pr_reviews_blocked(self):
        """pr_reviews 테이블 접근 차단 (코드리뷰 민감 데이터).

        현재 _validate_sql은 True를 반환.
        """
        from module_0_kms.chat_api import _validate_sql_v2
        assert _validate_sql_v2("SELECT * FROM pr_reviews LIMIT 10") is False

    def test_information_schema_blocked(self):
        """information_schema.tables 접근으로 DB 구조 노출 시도 차단.

        현재 _validate_sql은 True를 반환.
        """
        from module_0_kms.chat_api import _validate_sql_v2
        assert _validate_sql_v2(
            "SELECT table_name FROM information_schema.tables LIMIT 10"
        ) is False

    def test_subquery_unauthorized_table_blocked(self):
        """서브쿼리 안에서 unauthorized 테이블 접근 시도 차단."""
        from module_0_kms.chat_api import _validate_sql_v2
        assert _validate_sql_v2(
            "SELECT title FROM documents WHERE doc_id IN "
            "(SELECT doc_id FROM pr_reviews) LIMIT 5"
        ) is False
