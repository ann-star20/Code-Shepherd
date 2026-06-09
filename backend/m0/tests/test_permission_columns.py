"""
Tests for RBAC permission metadata columns.

Verifies:
1. Document ORM model has department_id, user_id, permission_level, visibility columns
2. Chunk ORM model has department_id, permission_level columns (no user_id)
3. DocPipelineState carries optional permission fields
4. _save_document() stores permission fields from state
5. _save_document() defaults to permission_level='public', visibility='all' when absent
6. upload endpoint accepts department_id, user_id, permission_level, visibility as Form params
"""
from __future__ import annotations

import inspect

import pytest
from unittest.mock import AsyncMock, MagicMock


# ---------------------------------------------------------------------------
# 1. ORM 모델 — Document 컬럼 존재
# ---------------------------------------------------------------------------

def test_document_model_has_permission_columns():
    from app.models import Document
    cols = {c.name for c in Document.__table__.columns}
    assert "department_id" in cols, "Document must have department_id"
    assert "user_id" in cols, "Document must have user_id"
    assert "permission_level" in cols, "Document must have permission_level"
    assert "visibility" in cols, "Document must have visibility"


def test_document_permission_defaults():
    from app.models import Document
    cols = {c.name: c for c in Document.__table__.columns}

    assert cols["department_id"].nullable is True
    assert cols["user_id"].nullable is True
    # server_default or default — either is acceptable
    perm_default = (
        cols["permission_level"].default.arg
        if cols["permission_level"].default is not None
        else cols["permission_level"].server_default.arg
    )
    vis_default = (
        cols["visibility"].default.arg
        if cols["visibility"].default is not None
        else cols["visibility"].server_default.arg
    )
    assert perm_default == "public", f"Expected 'public', got {perm_default!r}"
    assert vis_default == "all", f"Expected 'all', got {vis_default!r}"


# ---------------------------------------------------------------------------
# 2. ORM 모델 — Chunk 컬럼 존재 (user_id 없어야 함)
# ---------------------------------------------------------------------------

def test_chunk_model_has_permission_columns():
    from app.models import Chunk
    cols = {c.name for c in Chunk.__table__.columns}
    assert "department_id" in cols, "Chunk must have department_id"
    assert "permission_level" in cols, "Chunk must have permission_level"
    assert "user_id" not in cols, "Chunk must NOT have user_id (owner-level, not chunk-level)"


def test_chunk_permission_defaults():
    from app.models import Chunk
    cols = {c.name: c for c in Chunk.__table__.columns}

    assert cols["department_id"].nullable is True
    perm_default = (
        cols["permission_level"].default.arg
        if cols["permission_level"].default is not None
        else cols["permission_level"].server_default.arg
    )
    assert perm_default == "public", f"Expected 'public', got {perm_default!r}"


# ---------------------------------------------------------------------------
# 3. DocPipelineState 권한 필드 존재
# ---------------------------------------------------------------------------

def test_pipeline_state_has_permission_fields():
    import typing
    from app.pipeline.models import DocPipelineState

    hints = typing.get_type_hints(DocPipelineState)
    assert "department_id" in hints, "DocPipelineState must have department_id"
    assert "user_id" in hints, "DocPipelineState must have user_id"
    assert "permission_level" in hints, "DocPipelineState must have permission_level"
    assert "visibility" in hints, "DocPipelineState must have visibility"


# ---------------------------------------------------------------------------
# 4. _save_document() 권한 필드를 INSERT에 포함
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_save_document_stores_permission_fields():
    """state에 권한 필드가 있으면 INSERT SQL에 포함되어야 한다."""
    from app.pipeline.stage6_store import _save_document

    session = MagicMock()
    session.execute = AsyncMock()

    state = {
        "doc_id": "aaaabbbb-0000-0000-0000-000000000001",
        "source": "upload",
        "file_type": "md",
        "original_filename": "test.md",
        "parser_used": None,
        "doc_complexity": None,
        "parsing_time_ms": None,
        "quality_score": 0.9,
        "metadata": {"title": "Test Doc", "category": "기타"},
        "page_image_paths": None,
        "department_id": "backend_team",
        "user_id": "user-abc-123",
        "permission_level": "team",
        "visibility": "department",
    }

    await _save_document(session, state, "/md/test.md", "/files/test.md")

    call_args = session.execute.call_args
    sql = str(call_args[0][0])
    params = call_args[0][1]

    assert "department_id" in sql, "INSERT SQL must include department_id column"
    assert "user_id" in sql, "INSERT SQL must include user_id column"
    assert "permission_level" in sql, "INSERT SQL must include permission_level column"
    assert "visibility" in sql, "INSERT SQL must include visibility column"

    assert params["department_id"] == "backend_team"
    assert params["user_id"] == "user-abc-123"
    assert params["permission_level"] == "team"
    assert params["visibility"] == "department"


# ---------------------------------------------------------------------------
# 5. _save_document() 권한 필드 없으면 기본값 적용
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_save_document_defaults_when_no_permission_fields():
    """state에 권한 필드가 없으면 'public' / 'all' / None으로 기본값 처리."""
    from app.pipeline.stage6_store import _save_document

    session = MagicMock()
    session.execute = AsyncMock()

    state = {
        "doc_id": "aaaabbbb-0000-0000-0000-000000000002",
        "source": "upload",
        "file_type": "md",
        "original_filename": "test2.md",
        "parser_used": None,
        "doc_complexity": None,
        "parsing_time_ms": None,
        "quality_score": 0.85,
        "metadata": {"title": "Test2", "category": "보안"},
        "page_image_paths": None,
        # permission 필드 없음
    }

    await _save_document(session, state, "/md/test2.md", "/files/test2.md")

    call_args = session.execute.call_args
    params = call_args[0][1]

    assert params.get("permission_level") == "public"
    assert params.get("visibility") == "all"
    assert params.get("department_id") is None
    assert params.get("user_id") is None


# ---------------------------------------------------------------------------
# 6. 업로드 엔드포인트 Form 파라미터 확인
# ---------------------------------------------------------------------------

def test_upload_endpoint_accepts_permission_form_fields():
    """upload_document()는 department_id, user_id, permission_level, visibility를 Form으로 받아야 한다."""
    from app.routes.kms_routes import upload_document

    sig = inspect.signature(upload_document)
    param_names = set(sig.parameters.keys())

    assert "department_id" in param_names, "upload_document must accept department_id"
    assert "user_id" in param_names, "upload_document must accept user_id"
    assert "permission_level" in param_names, "upload_document must accept permission_level"
    assert "visibility" in param_names, "upload_document must accept visibility"
