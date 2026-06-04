"""
graph.py HITL 분기 조건 단위 테스트

_route_after_validate, _route_after_chunk_validate, _route_after_metadata_validate,
_hitl_pending_node, _wrap_with_harness, build_pipeline, _insert_hitl_queue의
핵심 분기 로직을 검증한다.
"""
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from langgraph.graph import END

from common.trace import DocPipelineStage
from module_0_kms.pipeline.graph import (
    _route_after_validate,
    _route_after_chunk_validate,
    _route_after_metadata_validate,
    _hitl_pending_node,
    _wrap_with_harness,
    build_pipeline,
    _insert_hitl_queue,
)


# ---------------------------------------------------------------------------
# _route_after_validate
# ---------------------------------------------------------------------------

class TestRouteAfterValidate:
    def test_routes_to_hitl_when_hitl_required(self):
        state = {"hitl_required": True, "status": "processing"}
        assert _route_after_validate(state) == "hitl_pending"

    def test_routes_to_hitl_when_status_hitl_pending(self):
        state = {"hitl_required": False, "status": "hitl_pending"}
        assert _route_after_validate(state) == "hitl_pending"

    def test_routes_to_end_on_failed(self):
        state = {"hitl_required": False, "status": "failed"}
        assert _route_after_validate(state) == END

    def test_routes_to_stage3_on_success(self):
        state = {"hitl_required": False, "status": "validated"}
        assert _route_after_validate(state) == "stage3_chunk"

    def test_hitl_required_takes_priority_over_failed(self):
        # hitl_required=True인 경우 status=failed보다 우선
        state = {"hitl_required": True, "status": "failed"}
        assert _route_after_validate(state) == "hitl_pending"


# ---------------------------------------------------------------------------
# _route_after_chunk_validate
# ---------------------------------------------------------------------------

class TestRouteAfterChunkValidate:
    def test_routes_to_hitl_when_hitl_required(self):
        state = {"hitl_required": True, "status": "processing"}
        assert _route_after_chunk_validate(state) == "hitl_pending"

    def test_routes_to_hitl_when_status_hitl_pending(self):
        state = {"hitl_required": False, "status": "hitl_pending"}
        assert _route_after_chunk_validate(state) == "hitl_pending"

    def test_routes_to_end_on_failed(self):
        state = {"hitl_required": False, "status": "failed"}
        assert _route_after_chunk_validate(state) == END

    def test_routes_to_stage5_on_success(self):
        state = {"hitl_required": False, "status": "chunk_validated"}
        assert _route_after_chunk_validate(state) == "stage5_metadata"


# ---------------------------------------------------------------------------
# _insert_hitl_queue — stage2 vs stage4 분기 (BUG-1 회귀 방지)
# ---------------------------------------------------------------------------

class TestInsertHitlQueue:
    @pytest.fixture
    def mock_pool(self):
        conn = AsyncMock()
        conn.execute = AsyncMock()
        pool = MagicMock()
        pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
        pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)
        return pool, conn

    @pytest.mark.asyncio
    async def test_stage2_hitl_records_stage2_validate(self, mock_pool):
        pool, conn = mock_pool
        state = {
            "doc_id": "00000000-0000-0000-0000-000000000001",
            "current_stage": "stage2_validate",
            "quality_score": 0.5,
            "quality_issues": ["표 구조 손실", "이미지 참조 누락"],
            "markdown_storage_path": "markdown/doc1/raw.md",
            "chunk_validation_issues": None,
        }

        await _insert_hitl_queue(pool, state)

        # execute가 2번 호출됨: [0] hitl_queue INSERT, [1] documents UPDATE
        insert_call = conn.execute.call_args_list[0]
        assert insert_call[0][2] == "stage2_validate"
        issues = json.loads(insert_call[0][5])
        assert "quality_issues" in issues

    @pytest.mark.asyncio
    async def test_stage4_hitl_records_stage4_not_stage2(self, mock_pool):
        """BUG-1 회귀 테스트 — stage4_chunk_validate HITL이 stage2로 잘못 기록되지 않아야 함."""
        pool, conn = mock_pool
        state = {
            "doc_id": "00000000-0000-0000-0000-000000000002",
            "current_stage": "stage4_chunk_validate",
            "quality_score": None,
            "quality_issues": None,
            "markdown_storage_path": "markdown/doc2/raw.md",
            "chunk_validation_issues": ["parent-child 연결 실패"],
        }

        await _insert_hitl_queue(pool, state)

        insert_call = conn.execute.call_args_list[0]
        stage_recorded = insert_call[0][2]
        assert stage_recorded == "stage4_chunk_validate", (
            f"BUG-1 재발: stage4 HITL이 '{stage_recorded}'로 기록됨"
        )
        issues = json.loads(insert_call[0][5])
        assert "chunk_issues" in issues

    @pytest.mark.asyncio
    async def test_stage5b_hitl_stores_markdown_storage_path(self, mock_pool):
        """Bug 2 회귀 테스트 — stage5b HITL issues에 markdown_storage_path가 포함돼야 재처리 가능."""
        pool, conn = mock_pool
        state = {
            "doc_id": "00000000-0000-0000-0000-000000000004",
            "current_stage": "stage5b_metadata_validate",
            "metadata_issues": ["카테고리 불일치"],
            "metadata_score": 0.4,
            "metadata": {"title": "제목", "category": "기타"},
            "markdown_storage_path": "markdown/doc4/raw.md",
            "quality_issues": None,
            "chunk_validation_issues": None,
        }

        await _insert_hitl_queue(pool, state)

        insert_call = conn.execute.call_args_list[0]
        issues = json.loads(insert_call[0][5])
        assert "markdown_storage_path" in issues, (
            f"Bug 2: stage5b HITL issues에 markdown_storage_path 없음 → 재처리 시 마크다운 로드 불가. issues={issues}"
        )
        assert issues["markdown_storage_path"] == "markdown/doc4/raw.md"

    @pytest.mark.asyncio
    async def test_db_failure_does_not_raise(self, mock_pool):
        """hitl_queue INSERT 실패 시 예외가 상위로 전파되지 않아야 함."""
        pool, conn = mock_pool
        conn.execute.side_effect = Exception("DB 연결 끊김")
        state = {
            "doc_id": "00000000-0000-0000-0000-000000000003",
            "current_stage": "stage2_validate",
            "quality_score": 0.3,
            "quality_issues": [],
            "markdown_storage_path": None,
            "chunk_validation_issues": None,
        }

        # 예외 없이 완료되어야 함
        await _insert_hitl_queue(pool, state)


# ---------------------------------------------------------------------------
# T6: _route_after_metadata_validate
# ---------------------------------------------------------------------------

class TestRouteAfterMetadataValidate:
    def test_routes_to_hitl_when_hitl_required(self):
        state = {"hitl_required": True, "status": "processing"}
        assert _route_after_metadata_validate(state) == "hitl_pending"

    def test_routes_to_hitl_when_status_hitl_pending(self):
        state = {"hitl_required": False, "status": "hitl_pending"}
        assert _route_after_metadata_validate(state) == "hitl_pending"

    def test_routes_to_end_on_failed(self):
        state = {"hitl_required": False, "status": "failed"}
        assert _route_after_metadata_validate(state) == END

    def test_routes_to_stage6_on_success(self):
        state = {"hitl_required": False, "status": "metadata_validated"}
        assert _route_after_metadata_validate(state) == "stage6_store"

    def test_hitl_required_takes_priority_over_failed(self):
        state = {"hitl_required": True, "status": "failed"}
        assert _route_after_metadata_validate(state) == "hitl_pending"


# ---------------------------------------------------------------------------
# T6: _hitl_pending_node
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_hitl_pending_node_returns_hitl_status():
    state = {
        "doc_id": "00000000-0000-0000-0000-000000000001",
        "quality_score": 0.7,
        "quality_issues": ["표 손실"],
        "chunk_validation_issues": None,
    }
    result = await _hitl_pending_node(state)
    assert result == {"status": "hitl_pending", "current_stage": "hitl_pending"}


# ---------------------------------------------------------------------------
# T6: _wrap_with_harness 오류 경로
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_wrap_with_harness_returns_failed_on_exception():
    """AgentHarness가 예외를 발생시키면 status='failed' dict를 반환해야 한다."""
    async def dummy_fn(state):
        return {"status": "success"}

    mock_harness_cls = MagicMock()
    mock_harness_instance = MagicMock()
    mock_harness_instance.__aenter__ = AsyncMock(
        side_effect=RuntimeError("harness failed")
    )
    mock_harness_instance.__aexit__ = AsyncMock(return_value=False)
    mock_harness_cls.return_value = mock_harness_instance

    mock_pool = MagicMock()

    with patch("kms.pipeline.graph.AgentHarness", mock_harness_cls):
        node_fn = _wrap_with_harness(
            DocPipelineStage.MARKDOWN_CONVERT,
            "TestAgent",
            dummy_fn,
            mock_pool,
        )
        state = {"doc_id": "00000000-0000-0000-0000-000000000001"}
        result = await node_fn(state)

    assert result["status"] == "failed"
    assert "TestAgent" in result["error"]
    assert result["current_stage"] == DocPipelineStage.MARKDOWN_CONVERT.value


# ---------------------------------------------------------------------------
# T6: build_pipeline 컴파일
# ---------------------------------------------------------------------------

def test_build_pipeline_returns_compiled_graph():
    """build_pipeline()이 예외 없이 컴파일된 그래프를 반환해야 한다."""
    mock_pool = MagicMock()
    mock_storage = MagicMock()

    compiled = build_pipeline(mock_pool, mock_storage)
    assert compiled is not None
