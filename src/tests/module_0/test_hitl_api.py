"""Tests for HITL API (kms/hitl_api.py)."""

from __future__ import annotations

import datetime
from uuid import UUID

import pytest
from fastapi import BackgroundTasks, HTTPException

import module_0_kms.hitl_api as hitl_api
from module_0_kms.hitl_api import (
    _require_reviewer,
    approve_hitl,
    get_hitl_item,
    list_hitl_queue,
    reject_hitl,
)


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


def _queue_row(status: str = "pending") -> dict:
    return {
        "queue_id": "11111111-1111-1111-1111-111111111111",
        "doc_id": "22222222-2222-2222-2222-222222222222",
        "stage": "stage2_validate",
        "reason": "품질 기준 미달",
        "quality_score": 0.5,
        "issues": None,
        "status": status,
        "reviewer_id": None,
        "review_note": None,
        "created_at": "2026-05-25T00:00:00+00:00",
    }


VALID_QUEUE_ID = "11111111-1111-1111-1111-111111111111"


# ---------------------------------------------------------------------------
# _require_reviewer
# ---------------------------------------------------------------------------

class TestRequireReviewer:
    def test_senior_role_allowed(self):
        _require_reviewer("senior")  # 예외 없음

    def test_admin_role_allowed(self):
        _require_reviewer("admin")

    def test_uppercase_allowed(self):
        _require_reviewer("SENIOR")

    def test_none_raises_403(self):
        with pytest.raises(HTTPException) as exc:
            _require_reviewer(None)
        assert exc.value.status_code == 403

    def test_empty_string_raises_403(self):
        with pytest.raises(HTTPException) as exc:
            _require_reviewer("")
        assert exc.value.status_code == 403

    def test_junior_raises_403(self):
        with pytest.raises(HTTPException) as exc:
            _require_reviewer("junior")
        assert exc.value.status_code == 403

    def test_invalid_role_raises_403(self):
        with pytest.raises(HTTPException) as exc:
            _require_reviewer("developer")
        assert exc.value.status_code == 403


# ---------------------------------------------------------------------------
# list_hitl_queue
# ---------------------------------------------------------------------------

class TestListHitlQueue:
    async def test_returns_empty_items_when_no_items(self, monkeypatch):
        class Conn:
            async def fetchrow(self, *_a, **_kw):
                return {"total": 0}

            async def fetch(self, *_a, **_kw):
                return []

        monkeypatch.setattr(hitl_api, "_db_pool", _FakePool(Conn()))
        result = await list_hitl_queue(status="pending")
        assert result.items == []

    async def test_returns_items_as_hitl_queue_items(self, monkeypatch):
        class Conn:
            async def fetchrow(self, *_a, **_kw):
                return {"total": 1}

            async def fetch(self, *_a, **_kw):
                return [_queue_row()]

        monkeypatch.setattr(hitl_api, "_db_pool", _FakePool(Conn()))
        result = await list_hitl_queue(status="pending")
        assert len(result.items) == 1
        assert result.items[0].stage == "stage2_validate"
        assert result.items[0].status == "pending"

    async def test_filters_by_status(self, monkeypatch):
        executed_queries = []

        class Conn:
            async def fetchrow(self, query, *args, **_kw):
                executed_queries.append(("fetchrow", query, args))
                return {"total": 0}

            async def fetch(self, query, *args, **_kw):
                executed_queries.append(("fetch", query, args))
                return []

        monkeypatch.setattr(hitl_api, "_db_pool", _FakePool(Conn()))
        await list_hitl_queue(status="approved")
        # fetch 쿼리에 approved 상태가 파라미터로 전달됐는지 확인
        fetch_calls = [q for q in executed_queries if q[0] == "fetch"]
        assert fetch_calls
        assert "approved" in fetch_calls[0][2]


# ---------------------------------------------------------------------------
# get_hitl_item
# ---------------------------------------------------------------------------

class TestGetHitlItem:
    async def test_existing_item_returned(self, monkeypatch):
        class Conn:
            async def fetchrow(self, *_a, **_kw):
                return _queue_row()

        monkeypatch.setattr(hitl_api, "_db_pool", _FakePool(Conn()))
        result = await get_hitl_item(VALID_QUEUE_ID)
        assert result.queue_id == VALID_QUEUE_ID

    async def test_missing_item_raises_404(self, monkeypatch):
        class Conn:
            async def fetchrow(self, *_a, **_kw):
                return None

        monkeypatch.setattr(hitl_api, "_db_pool", _FakePool(Conn()))
        with pytest.raises(HTTPException) as exc:
            await get_hitl_item(VALID_QUEUE_ID)
        assert exc.value.status_code == 404


# ---------------------------------------------------------------------------
# T4: documents JOIN — parser_used / file_type / original_filename 노출
# ---------------------------------------------------------------------------

def _queue_row_with_doc_info(**overrides) -> dict:
    """documents JOIN이 포함된 hitl_queue 행 픽스처."""
    row = _queue_row()
    row.update({
        "original_filename": "테스트문서.pdf",
        "file_type": "pdf",
        "parser_used": "upstage",
    })
    row.update(overrides)
    return row


class TestHitlItemDocInfo:
    """HitlQueueItem에 documents 테이블의 파싱 맥락 필드가 포함된다."""

    async def test_get_item_returns_parser_used(self, monkeypatch):
        """get_hitl_item 응답에 parser_used 필드가 포함된다."""
        class Conn:
            async def fetchrow(self, *_a, **_kw):
                return _queue_row_with_doc_info()
        monkeypatch.setattr(hitl_api, "_db_pool", _FakePool(Conn()))
        result = await get_hitl_item(VALID_QUEUE_ID)
        assert result.parser_used == "upstage"

    async def test_get_item_returns_file_type(self, monkeypatch):
        """get_hitl_item 응답에 file_type 필드가 포함된다."""
        class Conn:
            async def fetchrow(self, *_a, **_kw):
                return _queue_row_with_doc_info()
        monkeypatch.setattr(hitl_api, "_db_pool", _FakePool(Conn()))
        result = await get_hitl_item(VALID_QUEUE_ID)
        assert result.file_type == "pdf"

    async def test_get_item_returns_original_filename(self, monkeypatch):
        """get_hitl_item 응답에 original_filename 필드가 포함된다."""
        class Conn:
            async def fetchrow(self, *_a, **_kw):
                return _queue_row_with_doc_info()
        monkeypatch.setattr(hitl_api, "_db_pool", _FakePool(Conn()))
        result = await get_hitl_item(VALID_QUEUE_ID)
        assert result.original_filename == "테스트문서.pdf"

    async def test_missing_doc_info_returns_none(self, monkeypatch):
        """documents 조인 결과가 없으면(NULL) 각 필드는 None이다."""
        class Conn:
            async def fetchrow(self, *_a, **_kw):
                return _queue_row_with_doc_info(
                    original_filename=None, file_type=None, parser_used=None
                )
        monkeypatch.setattr(hitl_api, "_db_pool", _FakePool(Conn()))
        result = await get_hitl_item(VALID_QUEUE_ID)
        assert result.parser_used is None
        assert result.file_type is None
        assert result.original_filename is None


# ---------------------------------------------------------------------------
# approve_hitl
# ---------------------------------------------------------------------------

class TestApproveHitl:
    async def test_missing_role_raises_403(self, monkeypatch):
        monkeypatch.setattr(hitl_api, "_db_pool", _FakePool(None))
        from module_0_kms.hitl_api import ApproveRequest
        body = ApproveRequest(reviewer_id="rev-01")

        with pytest.raises(HTTPException) as exc:
            await approve_hitl(VALID_QUEUE_ID, body, BackgroundTasks(), x_reviewer_role=None)
        assert exc.value.status_code == 403

    async def test_pending_item_approved_no_reprocess(self, monkeypatch):
        executes = []

        class Conn:
            async def fetchrow(self, *_a, **_kw):
                return {**_queue_row(), "issues": None}

            async def execute(self, query, *args, **_kw):
                executes.append(query)

        monkeypatch.setattr(hitl_api, "_db_pool", _FakePool(Conn()))
        from module_0_kms.hitl_api import ApproveRequest
        body = ApproveRequest(reviewer_id="rev-01", auto_reprocess=False)
        result = await approve_hitl(VALID_QUEUE_ID, body, BackgroundTasks(), x_reviewer_role="senior")
        assert result["status"] == "approved"
        assert any("approved" in q for q in executes)

    async def test_missing_item_raises_404(self, monkeypatch):
        class Conn:
            async def fetchrow(self, *_a, **_kw):
                return None

            async def execute(self, *_a, **_kw):
                pass

        monkeypatch.setattr(hitl_api, "_db_pool", _FakePool(Conn()))
        from module_0_kms.hitl_api import ApproveRequest
        body = ApproveRequest(reviewer_id="rev-01")

        with pytest.raises(HTTPException) as exc:
            await approve_hitl(VALID_QUEUE_ID, body, BackgroundTasks(), x_reviewer_role="admin")
        assert exc.value.status_code == 404

    async def test_approve_with_reprocess_adds_background_task(self, monkeypatch):
        class Conn:
            async def fetchrow(self, *_a, **_kw):
                return {**_queue_row(), "doc_id": UUID("22222222-2222-2222-2222-222222222222"), "issues": None}

            async def execute(self, *_a, **_kw):
                pass

        monkeypatch.setattr(hitl_api, "_db_pool", _FakePool(Conn()))
        from module_0_kms.hitl_api import ApproveRequest
        body = ApproveRequest(reviewer_id="rev-01", auto_reprocess=True)
        bg = BackgroundTasks()
        result = await approve_hitl(VALID_QUEUE_ID, body, bg, x_reviewer_role="senior")
        assert result["status"] == "approved"
        assert "재처리" in result["message"]
        assert len(bg.tasks) == 1


# ---------------------------------------------------------------------------
# reject_hitl
# ---------------------------------------------------------------------------

class TestRejectHitl:
    async def test_missing_role_raises_403(self, monkeypatch):
        monkeypatch.setattr(hitl_api, "_db_pool", _FakePool(None))
        from module_0_kms.hitl_api import RejectRequest
        body = RejectRequest(reviewer_id="rev-01", review_note="품질 불량")

        with pytest.raises(HTTPException) as exc:
            await reject_hitl(VALID_QUEUE_ID, body, x_reviewer_role=None)
        assert exc.value.status_code == 403

    async def test_pending_item_rejected(self, monkeypatch):
        executes = []

        class Conn:
            async def fetchrow(self, *_a, **_kw):
                return {"doc_id": UUID("22222222-2222-2222-2222-222222222222")}

            async def execute(self, query, *_a, **_kw):
                executes.append(query)

        monkeypatch.setattr(hitl_api, "_db_pool", _FakePool(Conn()))
        from module_0_kms.hitl_api import RejectRequest
        body = RejectRequest(reviewer_id="rev-01", review_note="검토 후 거부")
        result = await reject_hitl(VALID_QUEUE_ID, body, x_reviewer_role="senior")
        assert result["status"] == "rejected"
        assert any("rejected" in q for q in executes)

    async def test_missing_item_raises_404(self, monkeypatch):
        class Conn:
            async def fetchrow(self, *_a, **_kw):
                return None

            async def execute(self, *_a, **_kw):
                pass

        monkeypatch.setattr(hitl_api, "_db_pool", _FakePool(Conn()))
        from module_0_kms.hitl_api import RejectRequest
        body = RejectRequest(reviewer_id="rev-01", review_note="거부")

        with pytest.raises(HTTPException) as exc:
            await reject_hitl(VALID_QUEUE_ID, body, x_reviewer_role="admin")
        assert exc.value.status_code == 404


# ---------------------------------------------------------------------------
# reprocess_hitl
# ---------------------------------------------------------------------------

class TestReprocessHitl:
    from module_0_kms.hitl_api import reprocess_hitl

    async def test_missing_role_raises_403(self, monkeypatch):
        monkeypatch.setattr(hitl_api, "_db_pool", _FakePool(None))
        from module_0_kms.hitl_api import ReprocessRequest
        body = ReprocessRequest(reviewer_id="rev-01")

        with pytest.raises(HTTPException) as exc:
            await hitl_api.reprocess_hitl(VALID_QUEUE_ID, body, BackgroundTasks(), x_reviewer_role=None)
        assert exc.value.status_code == 403

    async def test_missing_item_raises_404(self, monkeypatch):
        class Conn:
            async def fetchrow(self, *_a, **_kw):
                return None

            async def execute(self, *_a, **_kw):
                pass

        monkeypatch.setattr(hitl_api, "_db_pool", _FakePool(Conn()))
        from module_0_kms.hitl_api import ReprocessRequest
        body = ReprocessRequest(reviewer_id="rev-01")

        with pytest.raises(HTTPException) as exc:
            await hitl_api.reprocess_hitl(VALID_QUEUE_ID, body, BackgroundTasks(), x_reviewer_role="senior")
        assert exc.value.status_code == 404

    async def test_valid_item_queues_background_task(self, monkeypatch):
        row = {
            **_queue_row(),
            "doc_id": UUID("22222222-2222-2222-2222-222222222222"),
            "issues": None,
        }
        executes = []

        class Conn:
            async def fetchrow(self, *_a, **_kw):
                return row

            async def execute(self, query, *_a, **_kw):
                executes.append(query)

        monkeypatch.setattr(hitl_api, "_db_pool", _FakePool(Conn()))
        from module_0_kms.hitl_api import ReprocessRequest
        body = ReprocessRequest(reviewer_id="rev-01", corrected_markdown="# 수정된 내용")
        bg = BackgroundTasks()
        result = await hitl_api.reprocess_hitl(VALID_QUEUE_ID, body, bg, x_reviewer_role="admin")

        assert result["status"] == "reprocessing"
        assert len(bg.tasks) == 1
        assert any("reprocessing" in q for q in executes)


# ---------------------------------------------------------------------------
# _row_to_item (JSON 파싱 처리)
# ---------------------------------------------------------------------------

class TestRowToItem:
    def test_dict_issues_preserved(self):
        from module_0_kms.hitl_api import _row_to_item
        row = {**_queue_row(), "issues": {"key": "value"}}
        item = _row_to_item(row)
        assert item.issues == {"key": "value"}

    def test_string_issues_parsed_as_json(self):
        from module_0_kms.hitl_api import _row_to_item
        row = {**_queue_row(), "issues": '{"markdown_storage_path": "/tmp/doc.md"}'}
        item = _row_to_item(row)
        assert item.issues == {"markdown_storage_path": "/tmp/doc.md"}

    def test_invalid_json_string_becomes_none(self):
        from module_0_kms.hitl_api import _row_to_item
        row = {**_queue_row(), "issues": "not valid json"}
        item = _row_to_item(row)
        assert item.issues is None

    def test_none_issues_stays_none(self):
        from module_0_kms.hitl_api import _row_to_item
        row = {**_queue_row(), "issues": None}
        item = _row_to_item(row)
        assert item.issues is None


# ---------------------------------------------------------------------------
# _reprocess_document (배경 재처리 함수)
# ---------------------------------------------------------------------------

class TestReprocessDocument:
    """_reprocess_document 내부 함수를 단계별 Mock으로 검증."""

    async def _run(
        self,
        monkeypatch,
        corrected_markdown: str | None = "# 수정된 내용",
        stage: str = "stage2_validate",
        issues: dict | None = None,
        skip_validation: bool = False,
        storage_mock=None,
        stage2_result: dict | None = None,
        stage3_result: dict | None = None,
        stage4_result: dict | None = None,
    ):
        from unittest.mock import AsyncMock, MagicMock
        import module_0_kms.hitl_api as hitl_api

        pool_mock = _FakePool(MagicMock())
        storage = storage_mock or MagicMock()

        monkeypatch.setattr(hitl_api, "_db_pool", pool_mock)
        monkeypatch.setattr(hitl_api, "_storage", storage)

        default_success = {"hitl_required": False, "status": "stored"}
        stage2 = AsyncMock(return_value=stage2_result or default_success)
        stage3 = AsyncMock(return_value=stage3_result or {"status": "ok", "chunks": []})
        stage4 = AsyncMock(return_value=stage4_result or {"hitl_required": False, "chunk_validation_passed": True})
        stage5 = AsyncMock(return_value={"metadata": {}, "neo4j_entities": [], "neo4j_relations": []})
        stage6 = AsyncMock(return_value={"status": "stored"})

        monkeypatch.setattr("kms.hitl_api.stage2_validate", stage2, raising=False)
        monkeypatch.setattr("kms.hitl_api.stage3_chunk", stage3, raising=False)
        monkeypatch.setattr("kms.hitl_api.stage4_chunk_validate", stage4, raising=False)
        monkeypatch.setattr("kms.hitl_api.stage5_metadata", stage5, raising=False)
        monkeypatch.setattr("kms.hitl_api.stage6_store", stage6, raising=False)

        return stage2, stage3, stage4, stage5, stage6

    async def test_corrected_markdown_skips_storage_load(self, monkeypatch):
        """corrected_markdown 있으면 storage.load 호출 없이 진행."""
        from module_0_kms.hitl_api import _reprocess_document
        from unittest.mock import AsyncMock, MagicMock

        class _Conn:
            async def execute(self, *_a, **_kw): pass

        storage = MagicMock()
        storage.load = AsyncMock(side_effect=AssertionError("load should not be called"))
        monkeypatch.setattr(hitl_api, "_db_pool", _FakePool(_Conn()))
        monkeypatch.setattr(hitl_api, "_storage", storage)

        try:
            await _reprocess_document(
                doc_id="eab0aff1-16ee-4033-8fb2-caf8e6a43feb",
                stage="stage2_validate",
                issues={},
                corrected_markdown="# 수정된 내용",
            )
        except Exception:
            pass  # stage 실행 중 오류는 허용 — storage.load만 호출 안 됐으면 됨

        storage.load.assert_not_called()

    async def test_no_markdown_and_no_path_aborts(self, monkeypatch):
        """corrected_markdown도 없고 markdown_path도 없으면 조기 종료."""
        from module_0_kms.hitl_api import _reprocess_document

        class _Conn:
            async def execute(self, *_a, **_kw): pass

        monkeypatch.setattr(hitl_api, "_db_pool", _FakePool(_Conn()))
        monkeypatch.setattr(hitl_api, "_storage", __import__("unittest.mock", fromlist=["MagicMock"]).MagicMock())

        await _reprocess_document(
            doc_id="eab0aff1-16ee-4033-8fb2-caf8e6a43feb",
            stage="stage2_validate",
            issues={},
            corrected_markdown=None,
        )

    async def test_storage_load_failure_aborts(self, monkeypatch):
        """storage.load 실패 시 조기 종료."""
        from module_0_kms.hitl_api import _reprocess_document
        from unittest.mock import AsyncMock, MagicMock

        class _Conn:
            async def execute(self, *_a, **_kw): pass

        storage = MagicMock()
        storage.load = AsyncMock(side_effect=FileNotFoundError("없음"))
        monkeypatch.setattr(hitl_api, "_db_pool", _FakePool(_Conn()))
        monkeypatch.setattr(hitl_api, "_storage", storage)

        await _reprocess_document(
            doc_id="eab0aff1-16ee-4033-8fb2-caf8e6a43feb",
            stage="stage2_validate",
            issues={"markdown_storage_path": "/tmp/doc.md"},
            corrected_markdown=None,
        )

    async def test_full_pipeline_success_with_corrected_markdown(self, monkeypatch):
        """corrected_markdown 제공 시 stage2~6 전체 실행 성공 경로."""
        from module_0_kms.hitl_api import _reprocess_document
        from unittest.mock import AsyncMock, MagicMock, patch

        class _Conn:
            async def execute(self, *_a, **_kw): pass

        monkeypatch.setattr(hitl_api, "_db_pool", _FakePool(_Conn()))
        monkeypatch.setattr(hitl_api, "_storage", MagicMock())

        s2_result = {"hitl_required": False, "status": "ok", "validated_markdown": "# 수정된 내용", "quality_score": 0.9}
        s3_result = {"status": "ok", "chunks": [{"chunk_id": "c1", "chunk_type": "child", "content": "내용"}]}
        s4_result = {"hitl_required": False, "chunk_validation_passed": True, "chunk_validation_issues": []}
        s5_result = {"metadata": {"title": "제목"}, "neo4j_entities": [], "neo4j_relations": []}
        s6_result = {"status": "stored", "stored": True}

        with patch("kms.pipeline.stage2_validate_agent.stage2_validate", AsyncMock(return_value=s2_result)), \
             patch("kms.pipeline.stage3_chunk.stage3_chunk", AsyncMock(return_value=s3_result)), \
             patch("kms.pipeline.stage4_chunk_validate.stage4_chunk_validate", AsyncMock(return_value=s4_result)), \
             patch("kms.pipeline.stage5_metadata_agent.stage5_metadata", AsyncMock(return_value=s5_result)), \
             patch("kms.pipeline.stage6_store.stage6_store", AsyncMock(return_value=s6_result)):
            await _reprocess_document(
                doc_id="eab0aff1-16ee-4033-8fb2-caf8e6a43feb",
                stage="stage2_validate",
                issues={},
                corrected_markdown="# 수정된 내용",
            )

    async def test_full_pipeline_skip_validation_path(self, monkeypatch):
        """skip_validation=True 시 stage3~6만 실행."""
        from module_0_kms.hitl_api import _reprocess_document
        from unittest.mock import AsyncMock, MagicMock, patch

        class _Conn:
            async def execute(self, *_a, **_kw): pass

        monkeypatch.setattr(hitl_api, "_db_pool", _FakePool(_Conn()))
        monkeypatch.setattr(hitl_api, "_storage", MagicMock())

        s3_result = {"status": "ok", "chunks": []}
        s4_result = {"hitl_required": False, "chunk_validation_passed": True, "chunk_validation_issues": []}
        s5_result = {"metadata": {}, "neo4j_entities": [], "neo4j_relations": []}
        s6_result = {"status": "stored", "stored": True}

        s2_spy = AsyncMock(return_value={})

        with patch("kms.pipeline.stage2_validate_agent.stage2_validate", s2_spy), \
             patch("kms.pipeline.stage3_chunk.stage3_chunk", AsyncMock(return_value=s3_result)), \
             patch("kms.pipeline.stage4_chunk_validate.stage4_chunk_validate", AsyncMock(return_value=s4_result)), \
             patch("kms.pipeline.stage5_metadata_agent.stage5_metadata", AsyncMock(return_value=s5_result)), \
             patch("kms.pipeline.stage6_store.stage6_store", AsyncMock(return_value=s6_result)):
            await _reprocess_document(
                doc_id="eab0aff1-16ee-4033-8fb2-caf8e6a43feb",
                stage="stage4_chunk_validate",
                issues={},
                corrected_markdown=None,
                skip_validation=True,
            )
        s2_spy.assert_not_called()

    async def test_stage2_returns_hitl_required_aborts(self, monkeypatch):
        """stage2가 hitl_required 반환 시 hitl_pending 상태 + hitl_queue INSERT 후 중단.

        BUG-40 수정 이후 _abort_reprocess_with_hitl은 reprocess_failed 대신
        hitl_pending을 설정하고 hitl_queue에 새 항목을 삽입한다.
        """
        from module_0_kms.hitl_api import _reprocess_document
        from unittest.mock import AsyncMock, MagicMock, patch

        executes = []

        class Conn:
            async def execute(self, query, *_a, **_kw):
                executes.append(query)

            async def fetchrow(self, *_a, **_kw):
                return None

        monkeypatch.setattr(hitl_api, "_db_pool", _FakePool(Conn()))
        monkeypatch.setattr(hitl_api, "_storage", MagicMock())

        s2_hitl = {"hitl_required": True, "status": "hitl_pending"}

        with patch("kms.pipeline.stage2_validate_agent.stage2_validate", AsyncMock(return_value=s2_hitl)):
            await _reprocess_document(
                doc_id="eab0aff1-16ee-4033-8fb2-caf8e6a43feb",
                stage="stage2_validate",
                issues={},
                corrected_markdown="# 내용",
            )
        # BUG-40: _abort_reprocess_with_hitl은 hitl_pending을 설정한다 (reprocess_failed 아님)
        assert any("hitl_pending" in q for q in executes), (
            f"stage2 HITL 시 hitl_pending UPDATE 없음. 실행된 쿼리: {executes}"
        )

    async def test_stage3_failed_status_stops_pipeline(self, monkeypatch):
        """stage3가 failed 반환 시 이후 단계 실행 안 함."""
        from module_0_kms.hitl_api import _reprocess_document
        from unittest.mock import AsyncMock, MagicMock, patch

        class _Conn:
            async def execute(self, *_a, **_kw): pass

        monkeypatch.setattr(hitl_api, "_db_pool", _FakePool(_Conn()))
        monkeypatch.setattr(hitl_api, "_storage", MagicMock())

        s2_ok = {"hitl_required": False, "status": "ok", "validated_markdown": "# 내용"}
        s3_fail = {"status": "failed", "error": "청킹 실패"}
        s4_spy = AsyncMock(return_value={})

        with patch("kms.pipeline.stage2_validate_agent.stage2_validate", AsyncMock(return_value=s2_ok)), \
             patch("kms.pipeline.stage3_chunk.stage3_chunk", AsyncMock(return_value=s3_fail)), \
             patch("kms.pipeline.stage4_chunk_validate.stage4_chunk_validate", s4_spy):
            await _reprocess_document(
                doc_id="eab0aff1-16ee-4033-8fb2-caf8e6a43feb",
                stage="stage2_validate",
                issues={},
                corrected_markdown="# 내용",
            )
        s4_spy.assert_not_called()

    # ------------------------------------------------------------------
    # Bug 2: 예기치 않은 예외 → _mark_reprocess_failed 미호출 (stuck)
    # ------------------------------------------------------------------

    async def test_unexpected_exception_calls_mark_failed(self, monkeypatch):
        """stage 실행 중 예기치 않은 예외 발생 시 _mark_reprocess_failed를 호출해야 한다."""
        from module_0_kms.hitl_api import _reprocess_document
        from unittest.mock import AsyncMock, MagicMock, patch

        executes = []

        class Conn:
            async def execute(self, query, *_a, **_kw):
                executes.append(query)

        monkeypatch.setattr(hitl_api, "_db_pool", _FakePool(Conn()))
        monkeypatch.setattr(hitl_api, "_storage", MagicMock())

        s2_ok = {"hitl_required": False, "status": "ok", "validated_markdown": "# 내용"}

        with patch("kms.pipeline.stage2_validate_agent.stage2_validate", AsyncMock(return_value=s2_ok)), \
             patch("kms.pipeline.stage3_chunk.stage3_chunk",
                   AsyncMock(side_effect=RuntimeError("예기치 않은 네트워크 오류"))):
            await _reprocess_document(
                doc_id="eab0aff1-16ee-4033-8fb2-caf8e6a43feb",
                stage="stage2_validate",
                issues={},
                corrected_markdown="# 내용",
            )

        assert any("reprocess_failed" in q for q in executes), (
            f"예외 발생 시 reprocess_failed 업데이트 없음. 실행된 쿼리: {executes}"
        )

    # ------------------------------------------------------------------
    # Bug 3: stage4 HITL 재트리거 → hitl_queue INSERT 누락
    # ------------------------------------------------------------------

    async def test_stage4_hitl_retrigger_inserts_hitl_queue(self, monkeypatch):
        """재처리 중 stage4가 HITL 재트리거 시 hitl_queue에 새 항목을 삽입해야 한다.

        BUG-41 수정 이후 skip_validation=False일 때만 stage4 HITL이 트리거된다.
        """
        from module_0_kms.hitl_api import _reprocess_document
        from unittest.mock import AsyncMock, MagicMock, patch

        executes = []

        class Conn:
            async def execute(self, query, *_a, **_kw):
                executes.append(query)

            async def fetchrow(self, *_a, **_kw):
                return None

        monkeypatch.setattr(hitl_api, "_db_pool", _FakePool(Conn()))
        monkeypatch.setattr(hitl_api, "_storage", MagicMock())

        s2_ok = {"hitl_required": False, "validated_markdown": "# 재처리 내용"}
        s3_result = {"status": "ok", "chunks": []}
        s4_hitl = {
            "hitl_required": True,
            "chunk_validation_passed": False,
            "status": "hitl_pending",
            "chunk_validation_issues": ["Parent-Child 연결 실패"],
        }

        # BUG-41: skip_validation=False 이어야 stage4 HITL 재트리거 경로 진입
        with patch("kms.pipeline.stage2_validate_agent.stage2_validate", AsyncMock(return_value=s2_ok)), \
             patch("kms.pipeline.stage3_chunk.stage3_chunk", AsyncMock(return_value=s3_result)), \
             patch("kms.pipeline.stage4_chunk_validate.stage4_chunk_validate",
                   AsyncMock(return_value=s4_hitl)):
            await _reprocess_document(
                doc_id="eab0aff1-16ee-4033-8fb2-caf8e6a43feb",
                stage="stage4_chunk_validate",
                issues={},
                corrected_markdown="# 재처리 내용",
                skip_validation=False,
            )

        hitl_inserts = [q for q in executes if "hitl_queue" in q.lower()]
        assert hitl_inserts, (
            f"stage4 HITL 재트리거 시 hitl_queue INSERT 없음. 실행된 쿼리: {executes}"
        )

    async def test_stage5b_hitl_retrigger_inserts_hitl_queue(self, monkeypatch):
        """재처리 중 stage5b가 HITL 재트리거 시 hitl_queue에 새 항목을 삽입해야 한다.

        BUG-41 수정 이후 skip_validation=False일 때만 stage5b HITL이 트리거된다.
        """
        from module_0_kms.hitl_api import _reprocess_document
        from unittest.mock import AsyncMock, MagicMock, patch

        executes = []

        class Conn:
            async def execute(self, query, *_a, **_kw):
                executes.append(query)

            async def fetchrow(self, *_a, **_kw):
                return None

        monkeypatch.setattr(hitl_api, "_db_pool", _FakePool(Conn()))
        monkeypatch.setattr(hitl_api, "_storage", MagicMock())

        s2_ok = {"hitl_required": False, "validated_markdown": "# 재처리 내용"}
        s3_result = {"status": "ok", "chunks": []}
        s4_ok = {"hitl_required": False, "chunk_validation_passed": True}
        s5_result = {"metadata": {"title": "제목", "category": "아키텍처"}, "neo4j_entities": [], "neo4j_relations": []}
        s5b_hitl = {
            "hitl_required": True,
            "status": "hitl_pending",
            "metadata_issues": ["카테고리 불일치"],
            "metadata_score": 0.5,
        }

        # BUG-41: skip_validation=False 이어야 stage5b HITL 재트리거 경로 진입
        with patch("kms.pipeline.stage2_validate_agent.stage2_validate", AsyncMock(return_value=s2_ok)), \
             patch("kms.pipeline.stage3_chunk.stage3_chunk", AsyncMock(return_value=s3_result)), \
             patch("kms.pipeline.stage4_chunk_validate.stage4_chunk_validate", AsyncMock(return_value=s4_ok)), \
             patch("kms.pipeline.stage5_metadata_agent.stage5_metadata", AsyncMock(return_value=s5_result)), \
             patch("kms.pipeline.stage5b_metadata_validate_agent.stage5b_metadata_validate",
                   AsyncMock(return_value=s5b_hitl)):
            await _reprocess_document(
                doc_id="eab0aff1-16ee-4033-8fb2-caf8e6a43feb",
                stage="stage4_chunk_validate",
                issues={},
                corrected_markdown="# 재처리 내용",
                skip_validation=False,
            )

        hitl_inserts = [q for q in executes if "hitl_queue" in q.lower()]
        assert hitl_inserts, (
            f"stage5b HITL 재트리거 시 hitl_queue INSERT 없음. 실행된 쿼리: {executes}"
        )


# ---------------------------------------------------------------------------
# _mark_reprocess_failed
# ---------------------------------------------------------------------------

class TestMarkReprocessFailed:
    async def test_updates_document_status(self):
        from module_0_kms.hitl_api import _mark_reprocess_failed
        executes = []

        class Conn:
            async def execute(self, query, *_a, **_kw):
                executes.append(query)

        pool = _FakePool(Conn())
        await _mark_reprocess_failed(pool, "eab0aff1-16ee-4033-8fb2-caf8e6a43feb")
        assert any("reprocess_failed" in q for q in executes)

    async def test_db_error_does_not_raise(self):
        from module_0_kms.hitl_api import _mark_reprocess_failed

        class Conn:
            async def execute(self, *_a, **_kw):
                raise Exception("DB 오류")

        # 예외가 외부로 전파되지 않아야 함
        await _mark_reprocess_failed(_FakePool(Conn()), "eab0aff1-16ee-4033-8fb2-caf8e6a43feb")


# ---------------------------------------------------------------------------
# Bug 1: _reprocess_document — 시작 시 upload_status = 'reprocessing' 미설정
# Bug 3: 마크다운 없을 때 status = 'failed' 미설정
# ---------------------------------------------------------------------------

class TestReprocessStatusTransition:

    async def test_reprocess_sets_status_reprocessing_at_start(self, monkeypatch):
        """_reprocess_document 시작 시 upload_status = 'reprocessing'이 DB에 기록돼야 한다."""
        from module_0_kms.hitl_api import _reprocess_document
        from unittest.mock import AsyncMock, MagicMock, patch

        executes = []

        class Conn:
            async def execute(self, query, *params):
                executes.append((query, params))

        monkeypatch.setattr(hitl_api, "_db_pool", _FakePool(Conn()))
        monkeypatch.setattr(hitl_api, "_storage", MagicMock())

        s3_ok = {"status": "ok", "chunks": []}
        s4_ok = {"hitl_required": False, "chunk_validation_passed": True}
        s5_ok = {"metadata": {"title": "T", "category": "아키텍처"}, "neo4j_entities": [], "neo4j_relations": []}
        s5b_ok = {"hitl_required": False, "metadata_valid": True}
        s6_ok = {"stored": True, "status": "stored"}

        s2_ok = {"hitl_required": False, "status": "ok", "validated_markdown": "# 재처리 내용", "quality_score": 0.9}

        with patch("kms.pipeline.stage2_validate_agent.stage2_validate", AsyncMock(return_value=s2_ok)), \
             patch("kms.pipeline.stage3_chunk.stage3_chunk", AsyncMock(return_value=s3_ok)), \
             patch("kms.pipeline.stage4_chunk_validate.stage4_chunk_validate", AsyncMock(return_value=s4_ok)), \
             patch("kms.pipeline.stage5_metadata_agent.stage5_metadata", AsyncMock(return_value=s5_ok)), \
             patch("kms.pipeline.stage5b_metadata_validate_agent.stage5b_metadata_validate", AsyncMock(return_value=s5b_ok)), \
             patch("kms.pipeline.stage6_store.stage6_store", AsyncMock(return_value=s6_ok)):
            await _reprocess_document(
                doc_id="eab0aff1-16ee-4033-8fb2-caf8e6a43feb",
                stage="stage2_validate",
                issues={"markdown_storage_path": "docs/test.md"},
                corrected_markdown="# 재처리 내용",
            )

        reprocessing_updates = [
            q for q, p in executes
            if "reprocessing" in q
        ]
        assert reprocessing_updates, (
            f"upload_status = 'reprocessing' 업데이트 없음. 실행된 쿼리: {[q for q, _ in executes]}"
        )

    async def test_reprocess_sets_status_failed_when_no_markdown(self, monkeypatch):
        """마크다운이 없으면 upload_status = 'reprocess_failed'가 DB에 기록돼야 한다."""
        from module_0_kms.hitl_api import _reprocess_document
        from unittest.mock import MagicMock

        executes = []

        class Conn:
            async def execute(self, query, *params):
                executes.append((query, params))

        storage_mock = MagicMock()
        storage_mock.load = MagicMock(side_effect=FileNotFoundError("없음"))

        monkeypatch.setattr(hitl_api, "_db_pool", _FakePool(Conn()))
        monkeypatch.setattr(hitl_api, "_storage", storage_mock)

        await _reprocess_document(
            doc_id="eab0aff1-16ee-4033-8fb2-caf8e6a43feb",
            stage="stage2_validate",
            issues={},  # markdown_storage_path 없음
            corrected_markdown=None,
        )

        failed_updates = [
            q for q, p in executes
            if "reprocess_failed" in q
        ]
        assert failed_updates, (
            f"마크다운 없을 때 status 실패 기록 없음. 실행된 쿼리: {[q for q, _ in executes]}"
        )


# ---------------------------------------------------------------------------
# T6: GET /hitl/queue/{id}/markdown — Markdown 내용 조회 엔드포인트
# ---------------------------------------------------------------------------

class TestGetHitlMarkdown:
    """GET /hitl/queue/{id}/markdown — GCS에서 Markdown 내용을 반환한다."""

    async def test_returns_markdown_from_issues_path(self, monkeypatch):
        """issues.markdown_storage_path 경로에서 Markdown을 로드해 반환한다."""
        import module_0_kms.hitl_api as _api
        from module_0_kms.hitl_api import get_hitl_markdown

        class Conn:
            async def fetchrow(self, *_a, **_kw):
                return {
                    "issues": {"markdown_storage_path": "markdown/doc-abc/raw.md"},
                    "doc_id": "22222222-2222-2222-2222-222222222222",
                }

        class FakeStorage:
            async def load(self, path: str):
                return "# 테스트 Markdown 내용".encode("utf-8")

        monkeypatch.setattr(_api, "_db_pool", _FakePool(Conn()))
        monkeypatch.setattr(_api, "_storage", FakeStorage())

        result = await get_hitl_markdown(VALID_QUEUE_ID)
        assert result["markdown"] == "# 테스트 Markdown 내용"
        assert result["path"] == "markdown/doc-abc/raw.md"

    async def test_missing_queue_id_raises_404(self, monkeypatch):
        """존재하지 않는 queue_id → 404."""
        import module_0_kms.hitl_api as _api
        from module_0_kms.hitl_api import get_hitl_markdown

        class Conn:
            async def fetchrow(self, *_a, **_kw):
                return None

        monkeypatch.setattr(_api, "_db_pool", _FakePool(Conn()))

        with pytest.raises(HTTPException) as exc:
            await get_hitl_markdown(VALID_QUEUE_ID)
        assert exc.value.status_code == 404

    async def test_storage_failure_raises_404(self, monkeypatch):
        """storage.load 실패 → 404."""
        import module_0_kms.hitl_api as _api
        from module_0_kms.hitl_api import get_hitl_markdown

        class Conn:
            async def fetchrow(self, *_a, **_kw):
                return {
                    "issues": {"markdown_storage_path": "markdown/doc-xyz/raw.md"},
                    "doc_id": "22222222-2222-2222-2222-222222222222",
                }

        class FailStorage:
            async def load(self, path: str):
                raise FileNotFoundError("not found")

        monkeypatch.setattr(_api, "_db_pool", _FakePool(Conn()))
        monkeypatch.setattr(_api, "_storage", FailStorage())

        with pytest.raises(HTTPException) as exc:
            await get_hitl_markdown(VALID_QUEUE_ID)
        assert exc.value.status_code == 404

    async def test_fallback_to_default_path_when_no_issues_path(self, monkeypatch):
        """issues에 markdown_storage_path 없으면 markdown/{doc_id}/raw.md 폴백."""
        import module_0_kms.hitl_api as _api
        from module_0_kms.hitl_api import get_hitl_markdown

        doc_id = "22222222-2222-2222-2222-222222222222"
        loaded_paths: list[str] = []

        class Conn:
            async def fetchrow(self, *_a, **_kw):
                return {
                    "issues": {},  # markdown_storage_path 없음
                    "doc_id": doc_id,
                }

        class FakeStorage:
            async def load(self, path: str):
                loaded_paths.append(path)
                return "# 폴백 Markdown".encode("utf-8")

        monkeypatch.setattr(_api, "_db_pool", _FakePool(Conn()))
        monkeypatch.setattr(_api, "_storage", FakeStorage())

        result = await get_hitl_markdown(VALID_QUEUE_ID)
        assert loaded_paths[0] == f"markdown/{doc_id}/raw.md"
        assert "폴백" in result["markdown"]
