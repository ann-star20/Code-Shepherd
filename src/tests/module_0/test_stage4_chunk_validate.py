"""Tests for Stage 4: Chunk 검증 (stage4_chunk_validate)."""

from __future__ import annotations

import pytest

from module_0_kms.pipeline.stage4_chunk_validate import _validate_chunks, stage4_chunk_validate


def _parent(cid: str, tokens: int = 500, content: str = "부모 내용") -> dict:
    return {
        "chunk_id": cid,
        "chunk_type": "parent",
        "content": content,
        "token_count": tokens,
        "parent_chunk_id": None,
    }


def _child(cid: str, parent_id: str, tokens: int = 300, content: str = "자식 내용") -> dict:
    return {
        "chunk_id": cid,
        "chunk_type": "child",
        "content": content,
        "token_count": tokens,
        "parent_chunk_id": parent_id,
    }


def _state(chunks: list) -> dict:
    return {"doc_id": "doc-s4-001", "chunks": chunks}


# ---------------------------------------------------------------------------
# _validate_chunks 순수 함수
# ---------------------------------------------------------------------------

class TestValidateChunks:
    def test_valid_parent_child_pair_no_issues(self):
        chunks = [_parent("p1"), _child("c1", "p1")]
        assert _validate_chunks(chunks) == []

    def test_empty_child_content_reported(self):
        chunks = [_parent("p1"), _child("c1", "p1", content="   ")]
        issues = _validate_chunks(chunks)
        assert any("c1" in i for i in issues)

    def test_empty_parent_content_reported(self):
        chunks = [_parent("p1", content=""), _child("c1", "p1")]
        issues = _validate_chunks(chunks)
        assert any("p1" in i for i in issues)

    def test_child_missing_parent_id_reported(self):
        chunk = _child("c1", "p1")
        chunk["parent_chunk_id"] = None
        issues = _validate_chunks([_parent("p1"), chunk])
        assert any("parent_chunk_id" in i.lower() and "c1" in i for i in issues)

    def test_child_referencing_nonexistent_parent_reported(self):
        chunk = _child("c1", "ghost_parent")
        issues = _validate_chunks([_parent("p1"), chunk])
        assert any("ghost_parent" in i for i in issues)

    def test_oversized_parent_reported(self):
        chunks = [_parent("p1", tokens=2000)]
        issues = _validate_chunks(chunks)
        assert any("p1" in i and "초과" in i for i in issues)

    def test_oversized_child_reported(self):
        chunks = [_parent("p1"), _child("c1", "p1", tokens=700)]
        issues = _validate_chunks(chunks)
        assert any("c1" in i and "초과" in i for i in issues)

    def test_undersized_child_reported(self):
        """Child 토큰 수가 CHILD_MIN(300) 미만이면 이슈를 보고해야 한다."""
        chunks = [_parent("p1"), _child("c1", "p1", tokens=50)]
        issues = _validate_chunks(chunks)
        assert any("c1" in i and "미달" in i for i in issues), (
            f"50 tokens child에 대한 미달 이슈가 없음. 실제 이슈: {issues}"
        )

    def test_boundary_child_min_exact_passes(self):
        """정확히 CHILD_MIN(300) 토큰이면 이슈 없음."""
        chunks = [_parent("p1"), _child("c1", "p1", tokens=300)]
        issues = _validate_chunks(chunks)
        assert not any("c1" in i and "미달" in i for i in issues)

    def test_normal_sized_parent_no_issue(self):
        chunks = [_parent("p1", tokens=1000)]
        assert _validate_chunks(chunks) == []

    def test_multiple_children_valid(self):
        chunks = [_parent("p1"), _child("c1", "p1"), _child("c2", "p1")]
        assert _validate_chunks(chunks) == []


# ---------------------------------------------------------------------------
# stage4_chunk_validate 노드 함수
# ---------------------------------------------------------------------------

class TestStage4Node:
    async def test_empty_chunks_triggers_hitl(self):
        result = await stage4_chunk_validate(_state([]))
        assert result["chunk_validation_passed"] is False
        assert result["hitl_required"] is True
        assert result["status"] == "hitl_pending"

    async def test_none_chunks_triggers_hitl(self):
        result = await stage4_chunk_validate({"doc_id": "doc-001", "chunks": None})
        assert result["hitl_required"] is True

    async def test_valid_chunks_pass(self):
        chunks = [_parent("p1"), _child("c1", "p1")]
        result = await stage4_chunk_validate(_state(chunks))
        assert result["chunk_validation_passed"] is True
        assert result["hitl_required"] is False

    async def test_missing_parent_id_triggers_hitl(self):
        c = _child("c1", "p1")
        c["parent_chunk_id"] = None
        result = await stage4_chunk_validate(_state([_parent("p1"), c]))
        assert result["hitl_required"] is True
        assert result["chunk_validation_passed"] is False

    async def test_nonexistent_parent_triggers_hitl(self):
        result = await stage4_chunk_validate(_state([_child("c1", "missing_p")]))
        assert result["hitl_required"] is True

    async def test_size_warning_only_still_passes(self):
        chunks = [_parent("p1", tokens=2000), _child("c1", "p1")]
        result = await stage4_chunk_validate(_state(chunks))
        # 크기 초과는 HITL 아님 — 경고만
        assert result["chunk_validation_passed"] is True
        assert result["hitl_required"] is False
        assert result["chunk_validation_issues"]  # 경고는 있음

    async def test_undersized_child_is_warning_not_hitl(self):
        """Child 토큰 미달은 경고로 기록되지만 HITL을 트리거하지 않는다."""
        chunks = [_parent("p1"), _child("c1", "p1", tokens=50)]
        result = await stage4_chunk_validate(_state(chunks))
        assert result["chunk_validation_passed"] is True
        assert result["hitl_required"] is False
        assert result["chunk_validation_issues"], "50 tokens child에 대한 경고가 있어야 함"

    async def test_passed_sets_no_status_field(self):
        chunks = [_parent("p1"), _child("c1", "p1")]
        result = await stage4_chunk_validate(_state(chunks))
        # 성공 경로에는 status 필드 없음
        assert "status" not in result

    async def test_current_stage_always_set(self):
        result = await stage4_chunk_validate(_state([]))
        assert result["current_stage"] == "stage4_chunk_validate"
