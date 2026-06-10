"""
Stage 4: Chunk 검증 Agent (trc_0004)

검증 항목:
- Child 토큰 수: CHILD_MIN_TOKENS ~ CHILD_MAX_TOKENS 범위 확인
- Parent 토큰 수: PARENT_MIN_TOKENS ~ PARENT_MAX_TOKENS 범위 확인
- Parent-Child 연결: 모든 Child의 parent_chunk_id가 실제 Parent를 가리키는지 확인
- 빈 청크 탐지

임계값 초과 시 HITL 큐 등록.

출력:
    state["chunk_validation_passed"]  True/False
    state["chunk_validation_issues"]  발견된 문제 목록
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.pipeline.models import ChunkItem, DocPipelineState

logger = logging.getLogger(__name__)

# CLAUDE.md 기준 토큰 범위
PARENT_MIN = 800
PARENT_MAX = 1500
CHILD_MIN = 300
CHILD_MAX = 500


def _is_structural_issue(issue: str) -> bool:
    """Parent-Child 연결 실패 이슈인지 판별한다 (HITL 트리거 조건)."""
    return "parent_chunk_id" in issue.lower() or "연결" in issue


def _validate_chunks(chunks: list["ChunkItem"]) -> list[str]:
    """청크 목록을 검증하고 발견된 문제 목록을 반환한다. 문제 없으면 빈 리스트."""
    issues: list[str] = []

    parent_ids = {c["chunk_id"] for c in chunks if c["chunk_type"] == "parent"}

    for chunk in chunks:
        cid = chunk["chunk_id"]
        tokens = chunk["token_count"]

        if not chunk["content"].strip():
            issues.append(f"빈 청크 발견: {cid}")
            continue

        if chunk["chunk_type"] == "parent":
            if tokens < PARENT_MIN:
                issues.append(
                    f"Parent 청크 크기 미달 {cid}: {tokens} tokens (min {PARENT_MIN})"
                )
            elif tokens > PARENT_MAX * 1.2:
                issues.append(
                    f"Parent 청크 크기 초과 {cid}: {tokens} tokens (max {PARENT_MAX})"
                )

        elif chunk["chunk_type"] == "child":
            parent_id = chunk.get("parent_chunk_id")

            if parent_id is None:
                issues.append(f"Child 청크 {cid}의 parent_chunk_id가 None")
            elif parent_id not in parent_ids:
                issues.append(
                    f"Child 청크 {cid}의 parent_chunk_id {parent_id}가 존재하지 않음"
                )

            if tokens < CHILD_MIN:
                issues.append(
                    f"Child 청크 크기 미달 {cid}: {tokens} tokens (min {CHILD_MIN})"
                )
            elif tokens > CHILD_MAX * 1.2:
                issues.append(
                    f"Child 청크 크기 초과 {cid}: {tokens} tokens (max {CHILD_MAX})"
                )

    return issues


async def stage4_chunk_validate(state: "DocPipelineState") -> dict:
    """LangGraph 노드: 청크 검증."""

    chunks = state.get("chunks") or []
    doc_id = state["doc_id"]

    if not chunks:
        logger.error("Stage 4: chunks가 없음", extra={"doc_id": doc_id})
        return {
            "chunk_validation_passed": False,
            "chunk_validation_issues": ["청크 목록이 비어있음"],
            "status": "hitl_pending",
            "hitl_required": True,
            "current_stage": "stage4_chunk_validate",
        }

    issues = _validate_chunks(chunks)

    critical_issues = [i for i in issues if _is_structural_issue(i)]
    hitl_required = bool(critical_issues)

    if hitl_required:
        logger.warning(
            "Stage 4: 청크 검증 실패 — HITL 등록",
            extra={"doc_id": doc_id, "issues": critical_issues},
        )
        return {
            "chunk_validation_passed": False,
            "chunk_validation_issues": issues,
            "hitl_required": True,
            "status": "hitl_pending",
            "current_stage": "stage4_chunk_validate",
        }

    if issues:
        # 크기 경고만 있는 경우: 기록만 하고 통과
        logger.warning(
            "Stage 4: 크기 경고 있으나 통과",
            extra={"doc_id": doc_id, "warnings": issues},
        )

    logger.info(
        "Stage 4 완료",
        extra={"doc_id": doc_id, "total_chunks": len(chunks), "issues": len(issues)},
    )

    return {
        "chunk_validation_passed": True,
        "chunk_validation_issues": issues,   # 이슈 없으면 [] — None은 '검사 안 함'처럼 오해될 수 있음
        "hitl_required": False,
        "current_stage": "stage4_chunk_validate",
    }
