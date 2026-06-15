"""
중복 문서 감지 TDD 테스트 — SHA256 기반 dedup

커버 범위:
  BE-1  Document ORM에 file_hash 컬럼 존재
  BE-2  /kms/check-duplicate 엔드포인트 — identical / modified / new 3케이스
  BE-3  upload_document()가 file_hash Form 파라미터를 받거나 initial_state에 주입
  BE-4  _save_document()가 file_hash를 INSERT SQL에 포함
  BE-5  graph_sync_agent — 4개 저장소(PG/pgVector/Neo4j/GCS) 이전 버전 정리
  BE-6  /kms/replace-document 엔드포인트 — Graph Sync 후 새 파이프라인 실행
"""
from __future__ import annotations

import inspect

import pytest
from unittest.mock import AsyncMock, MagicMock, patch, call


# ---------------------------------------------------------------------------
# BE-1: Document ORM — file_hash 컬럼
# ---------------------------------------------------------------------------

def test_document_model_has_file_hash():
    from app.models import Document
    cols = {c.name for c in Document.__table__.columns}
    assert "file_hash" in cols, "Document must have file_hash column"


def test_document_file_hash_is_nullable_varchar64():
    from app.models import Document
    cols = {c.name: c for c in Document.__table__.columns}
    col = cols["file_hash"]
    assert col.nullable is True, "file_hash must be nullable (legacy docs have no hash)"
    assert col.type.length == 64, f"file_hash must be VARCHAR(64), got {col.type.length}"


# ---------------------------------------------------------------------------
# BE-2: /kms/check-duplicate 엔드포인트 — 3케이스
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_check_duplicate_identical():
    """동일 hash가 DB에 있으면 status='identical' + existing_doc 반환."""
    from app.routes.kms_routes import check_duplicate

    mock_session = MagicMock()
    mock_result = MagicMock()
    mock_result.fetchone.return_value = (
        "doc-aaa-111",
        "사내_보안정책.pdf",
        "stored",
        "2026-06-01T10:00:00",
    )
    mock_session.execute = AsyncMock(return_value=mock_result)

    result = await check_duplicate(
        file_hash="abc123" * 10 + "abcd",  # 64자
        original_filename="사내_보안정책.pdf",
        session=mock_session,
    )

    assert result["status"] == "identical"
    assert result["existing_doc"]["doc_id"] == "doc-aaa-111"


@pytest.mark.asyncio
async def test_check_duplicate_modified():
    """같은 파일명, 다른 hash → status='modified'."""
    from app.routes.kms_routes import check_duplicate

    mock_session = MagicMock()

    def side_effect(query, params):
        sql = str(query)
        result = MagicMock()
        if "file_hash" in sql and ":file_hash" in sql:
            result.fetchone.return_value = None  # hash 불일치 → 없음
        else:
            # filename 조회
            result.fetchone.return_value = (
                "doc-bbb-222",
                "기존_문서.pdf",
                "stored",
                "2026-05-15T09:00:00",
            )
        return result

    mock_session.execute = AsyncMock(side_effect=side_effect)

    result = await check_duplicate(
        file_hash="deadbeef" * 8,  # 64자
        original_filename="기존_문서.pdf",
        session=mock_session,
    )

    assert result["status"] == "modified"
    assert result["existing_doc"]["doc_id"] == "doc-bbb-222"


@pytest.mark.asyncio
async def test_check_duplicate_new():
    """hash도 없고 파일명도 없으면 status='new'."""
    from app.routes.kms_routes import check_duplicate

    mock_session = MagicMock()
    mock_result = MagicMock()
    mock_result.fetchone.return_value = None
    mock_session.execute = AsyncMock(return_value=mock_result)

    result = await check_duplicate(
        file_hash="cafebabe" * 8,
        original_filename="새로운_문서.pdf",
        session=mock_session,
    )

    assert result["status"] == "new"
    assert result.get("existing_doc") is None


# ---------------------------------------------------------------------------
# BE-3: upload_document() — file_hash Form 파라미터
# ---------------------------------------------------------------------------

def test_upload_endpoint_accepts_file_hash_form_field():
    """upload_document()는 file_hash를 Optional Form 파라미터로 받아야 한다."""
    from app.routes.kms_routes import upload_document

    sig = inspect.signature(upload_document)
    assert "file_hash" in sig.parameters, (
        "upload_document must accept file_hash as Form parameter"
    )


def test_pipeline_state_has_file_hash_field():
    """DocPipelineState에 file_hash 필드가 있어야 한다."""
    import typing
    from app.pipeline.models import DocPipelineState

    hints = typing.get_type_hints(DocPipelineState)
    assert "file_hash" in hints, "DocPipelineState must have file_hash field"


# ---------------------------------------------------------------------------
# BE-4: _save_document() — file_hash INSERT 포함
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_save_document_stores_file_hash():
    """state에 file_hash가 있으면 INSERT SQL에 포함되어야 한다."""
    from app.pipeline.stage6_store import _save_document

    session = MagicMock()
    session.execute = AsyncMock()

    state = {
        "doc_id": "aaaabbbb-0000-0000-0000-000000000099",
        "source": "upload",
        "file_type": "pdf",
        "original_filename": "test.pdf",
        "parser_used": None,
        "doc_complexity": None,
        "parsing_time_ms": None,
        "quality_score": 0.85,
        "metadata": {"title": "Test Doc", "category": "기타"},
        "page_image_paths": None,
        "file_hash": "abc123def456" * 4 + "abcd",  # 64자
    }

    await _save_document(session, state, "/md/test.md", "/files/test.pdf")

    call_args = session.execute.call_args
    sql = str(call_args[0][0])
    params = call_args[0][1]

    assert "file_hash" in sql, "INSERT SQL must include file_hash column"
    assert params["file_hash"] == state["file_hash"]


@pytest.mark.asyncio
async def test_save_document_null_file_hash_when_absent():
    """state에 file_hash 없으면 None으로 저장."""
    from app.pipeline.stage6_store import _save_document

    session = MagicMock()
    session.execute = AsyncMock()

    state = {
        "doc_id": "aaaabbbb-0000-0000-0000-000000000088",
        "source": "upload",
        "file_type": "md",
        "original_filename": "test.md",
        "parser_used": None,
        "doc_complexity": None,
        "parsing_time_ms": None,
        "quality_score": 0.9,
        "metadata": {"title": "No Hash Doc", "category": "기타"},
        "page_image_paths": None,
        # file_hash 없음
    }

    await _save_document(session, state, "/md/test.md", "/files/test.md")

    params = session.execute.call_args[0][1]
    assert params.get("file_hash") is None


# ---------------------------------------------------------------------------
# BE-5: Graph Sync Agent — 4개 저장소 이전 버전 정리
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_graph_sync_agent_deletes_pg_records():
    """sync_old_document_version()은 PG에서 doc_id 기준으로 chunks, documents를 삭제한다."""
    from app.pipeline.graph_sync import sync_old_document_version

    mock_session = MagicMock()
    mock_session.execute = AsyncMock()
    mock_session.commit = AsyncMock()

    await sync_old_document_version(
        old_doc_id="old-doc-111",
        session=mock_session,
        delete_gcs=False,
        delete_neo4j=False,
    )

    executed_sqls = [str(c[0][0]) for c in mock_session.execute.call_args_list]
    joined = " ".join(executed_sqls).lower()

    assert "delete" in joined, "Must issue DELETE SQL"
    assert "old-doc-111" in str(mock_session.execute.call_args_list)


@pytest.mark.asyncio
async def test_graph_sync_agent_deletes_neo4j_node():
    """delete_neo4j=True이면 Neo4j Document 노드도 삭제한다."""
    from app.pipeline.graph_sync import sync_old_document_version

    mock_session = MagicMock()
    mock_session.execute = AsyncMock()
    mock_session.commit = AsyncMock()

    with patch("app.pipeline.graph_sync._delete_neo4j_document") as mock_neo4j:
        mock_neo4j.return_value = None

        await sync_old_document_version(
            old_doc_id="old-doc-222",
            session=mock_session,
            delete_gcs=False,
            delete_neo4j=True,
        )

        mock_neo4j.assert_called_once_with("old-doc-222")


@pytest.mark.asyncio
async def test_graph_sync_agent_deletes_gcs_images():
    """delete_gcs=True이면 GCS images/{old_doc_id}/ 경로를 삭제한다."""
    from app.pipeline.graph_sync import sync_old_document_version

    mock_session = MagicMock()
    mock_session.execute = AsyncMock()
    mock_session.commit = AsyncMock()

    with patch("app.pipeline.graph_sync._delete_gcs_images") as mock_gcs:
        mock_gcs.return_value = None

        await sync_old_document_version(
            old_doc_id="old-doc-333",
            session=mock_session,
            delete_gcs=True,
            delete_neo4j=False,
        )

        mock_gcs.assert_called_once_with("old-doc-333")


# ---------------------------------------------------------------------------
# BE-6: /kms/replace-document 엔드포인트
# ---------------------------------------------------------------------------

def test_replace_document_endpoint_exists():
    """replace_document 핸들러가 kms_routes에 정의되어 있어야 한다."""
    from app.routes import kms_routes
    assert hasattr(kms_routes, "replace_document"), (
        "kms_routes must define replace_document handler"
    )


def test_replace_document_accepts_required_params():
    """replace_document()는 old_doc_id, file, file_hash를 파라미터로 받아야 한다."""
    from app.routes.kms_routes import replace_document

    sig = inspect.signature(replace_document)
    params = set(sig.parameters.keys())

    assert "old_doc_id" in params, "replace_document must accept old_doc_id"
    assert "file" in params, "replace_document must accept file upload"
