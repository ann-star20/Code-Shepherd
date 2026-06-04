"""
KMS 문서 처리 파이프라인 — LangGraph StateGraph

6단계를 순서대로 실행하며, 각 단계는 AgentHarness로 감싸져
LangSmith 추적과 PostgreSQL agent_traces 기록이 자동 처리된다.

HITL 분기:
    stage2_validate 또는 stage4_chunk_validate에서 hitl_required=True이면
    "hitl_pending" 노드로 라우팅 → 파이프라인 종료 (사람 개입 대기)

사용 예시:
    from module_0_kms.pipeline.graph import build_pipeline

    pipeline = build_pipeline(db_pool=pool, storage=storage)
    result = await pipeline.ainvoke(initial_state)
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING
from uuid import UUID

import asyncpg
from langgraph.graph import StateGraph, END

from common.harness import AgentHarness
from common.trace import DocPipelineStage, new_pipeline_trace
from module_0_kms.pipeline.models import DocPipelineState
from module_0_kms.pipeline.stage1_document_parser_agent import document_parser_agent
from module_0_kms.pipeline.stage2_validate_agent import stage2_validate
from module_0_kms.pipeline.stage3_chunk import stage3_chunk
from module_0_kms.pipeline.stage4_chunk_validate import stage4_chunk_validate
from module_0_kms.pipeline.stage5_metadata_agent import stage5_metadata
from module_0_kms.pipeline.stage5b_metadata_validate_agent import stage5b_metadata_validate
from module_0_kms.pipeline.stage6_store import stage6_store

if TYPE_CHECKING:
    from module_0_kms.storage import Storage

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Harness 래핑 헬퍼
# ---------------------------------------------------------------------------

def _wrap_with_harness(
    stage: DocPipelineStage,
    agent_name: str,
    fn,
    harness_pool: asyncpg.Pool,
    **fn_kwargs,
):
    """
    LangGraph 노드 함수를 AgentHarness로 감싼다.
    타임아웃 및 agent_traces 기록은 harness가 담당한다.
    harness_pool: AgentHarness 내부용 풀 (fn_kwargs의 db_pool과 이름 충돌 방지)
    """
    async def _node(state: DocPipelineState, **_) -> dict:
        # LangGraph 0.2.x가 config 등 내부 kwargs를 주입할 수 있으므로 **_ 로 흡수
        trace_id = new_pipeline_trace(stage, UUID(state["doc_id"]))
        try:
            async with AgentHarness(
                trace_id=trace_id,
                agent_name=agent_name,
                db_pool=harness_pool,
                doc_id=UUID(state["doc_id"]),
            ) as harness:
                return await harness.run(fn, state, **fn_kwargs)
        except Exception as e:
            logger.error(
                f"{agent_name} 실패",
                extra={"doc_id": state["doc_id"], "error": str(e)},
            )
            return {
                "status": "failed",
                "error": f"{agent_name}: {e}",
                "current_stage": stage.value,
            }

    _node.__name__ = agent_name
    return _node


# ---------------------------------------------------------------------------
# HITL 분기 라우터
# ---------------------------------------------------------------------------

def _route_after_validate(state: DocPipelineState) -> str:
    """Stage 2 완료 후 HITL 여부에 따라 다음 노드 결정."""
    if state.get("hitl_required") or state.get("status") == "hitl_pending":
        return "hitl_pending"
    if state.get("status") == "failed":
        return END
    return "stage3_chunk"


def _route_after_chunk_validate(state: DocPipelineState) -> str:
    """Stage 4 완료 후 HITL 여부에 따라 다음 노드 결정."""
    if state.get("hitl_required") or state.get("status") == "hitl_pending":
        return "hitl_pending"
    if state.get("status") == "failed":
        return END
    return "stage5_metadata"


def _route_after_metadata_validate(state: DocPipelineState) -> str:
    """Stage 5b 완료 후 HITL 여부에 따라 다음 노드 결정."""
    if state.get("hitl_required") or state.get("status") == "hitl_pending":
        return "hitl_pending"
    if state.get("status") == "failed":
        return END
    return "stage6_store"


async def _hitl_pending_node(state: DocPipelineState) -> dict:
    """HITL 대기 상태 — 파이프라인 종료. 사람이 검토 후 재개해야 한다."""
    logger.warning(
        "HITL 대기 — 파이프라인 중단",
        extra={
            "doc_id": state["doc_id"],
            "quality_score": state.get("quality_score"),
            "quality_issues": state.get("quality_issues"),
            "chunk_issues": state.get("chunk_validation_issues"),
        },
    )
    return {"status": "hitl_pending", "current_stage": "hitl_pending"}


async def _insert_hitl_queue(db_pool: asyncpg.Pool, state: DocPipelineState) -> None:
    """hitl_queue 테이블에 HITL 항목 삽입."""
    current_stage = state.get("current_stage", "")
    doc_id = UUID(state["doc_id"])

    if "stage2" in current_stage:
        stage = "stage2_validate"
        reason_list: list[str] = state.get("quality_issues") or []
        quality_score: float | None = state.get("quality_score")
        issues = {
            "quality_issues": reason_list,
            "markdown_storage_path": state.get("markdown_storage_path"),
        }
    elif "stage5b" in current_stage:
        stage = "stage5b_metadata_validate"
        reason_list = state.get("metadata_issues") or []
        quality_score = state.get("metadata_score")
        issues = {
            "metadata_issues": reason_list,
            "metadata": state.get("metadata"),
            "markdown_storage_path": state.get("markdown_storage_path"),
        }
    else:
        stage = "stage4_chunk_validate"
        reason_list = state.get("chunk_validation_issues") or []
        quality_score = None
        issues = {
            "chunk_issues": reason_list,
            "markdown_storage_path": state.get("markdown_storage_path"),
        }

    reason = ", ".join(reason_list) if reason_list else "품질 기준 미달"

    try:
        async with db_pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO hitl_queue (doc_id, stage, reason, quality_score, issues, status)
                VALUES ($1, $2, $3, $4, $5::jsonb, 'pending')
                """,
                doc_id,
                stage,
                reason,
                quality_score,
                json.dumps(issues, ensure_ascii=False),
            )
            # HITL 발동 시점에 알려진 파싱 정보를 documents에 저장
            # (stage6에 도달하지 못하는 HITL 항목도 UI에서 파서 정보를 볼 수 있도록)
            await conn.execute(
                """
                UPDATE documents
                SET file_type         = COALESCE(file_type,         $1),
                    parser_used       = COALESCE(parser_used,       $2),
                    original_filename = COALESCE(original_filename, $3)
                WHERE doc_id = $4
                """,
                state.get("file_type"),
                state.get("parser_used"),
                state.get("original_filename"),
                doc_id,
            )
        logger.info(
            "hitl_queue INSERT 완료",
            extra={"doc_id": state["doc_id"], "stage": stage},
        )
    except Exception as e:
        logger.error(
            f"hitl_queue INSERT 실패: {e}",
            extra={"doc_id": state["doc_id"]},
        )


# ---------------------------------------------------------------------------
# 파이프라인 빌더
# ---------------------------------------------------------------------------

def build_pipeline(
    db_pool: asyncpg.Pool,
    storage: "Storage",
):
    """
    KMS 문서 처리 파이프라인 LangGraph를 생성·컴파일한다.

    Args:
        db_pool: asyncpg 커넥션 풀 (agent_traces + documents + chunks + embeddings 기록)
        storage: Storage 구현체 (LocalStorage or MinIO)

    Returns:
        컴파일된 LangGraph StateGraph
    """
    graph = StateGraph(DocPipelineState)

    # --- 노드 등록 ---
    graph.add_node(
        "stage1_document_parser",
        _wrap_with_harness(
            DocPipelineStage.MARKDOWN_CONVERT,
            "DocumentParserAgent",
            document_parser_agent,
            db_pool,
            storage=storage,
        ),
    )
    graph.add_node(
        "stage2_validate",
        _wrap_with_harness(
            DocPipelineStage.MARKDOWN_VALIDATE,
            "MarkdownValidateAgent",
            stage2_validate,
            db_pool,
        ),
    )
    graph.add_node(
        "stage3_chunk",
        _wrap_with_harness(
            DocPipelineStage.CHUNKING,
            "ChunkingAgent",
            stage3_chunk,
            db_pool,
        ),
    )
    graph.add_node(
        "stage4_chunk_validate",
        _wrap_with_harness(
            DocPipelineStage.CHUNK_VALIDATE,
            "ChunkValidateAgent",
            stage4_chunk_validate,
            db_pool,
        ),
    )
    graph.add_node(
        "stage5_metadata",
        _wrap_with_harness(
            DocPipelineStage.METADATA_EXTRACT,
            "MetadataExtractAgent",
            stage5_metadata,
            db_pool,
        ),
    )
    graph.add_node(
        "stage5b_metadata_validate",
        _wrap_with_harness(
            DocPipelineStage.METADATA_VALIDATE,
            "MetadataValidateAgent",
            stage5b_metadata_validate,
            db_pool,
        ),
    )
    graph.add_node(
        "stage6_store",
        _wrap_with_harness(
            DocPipelineStage.STORE_ROUTE,
            "StoreRouteAgent",
            stage6_store,
            db_pool,
            db_pool=db_pool,
            storage=storage,
        ),
    )
    # hitl_pending 노드: DB INSERT 후 파이프라인 종료
    async def _hitl_with_db(state: DocPipelineState) -> dict:
        await _insert_hitl_queue(db_pool, state)
        return await _hitl_pending_node(state)

    graph.add_node("hitl_pending", _hitl_with_db)

    # --- 엣지 연결 ---
    graph.set_entry_point("stage1_document_parser")

    graph.add_edge("stage1_document_parser", "stage2_validate")

    graph.add_conditional_edges(
        "stage2_validate",
        _route_after_validate,
        {
            "stage3_chunk": "stage3_chunk",
            "hitl_pending": "hitl_pending",
            END: END,
        },
    )

    graph.add_edge("stage3_chunk", "stage4_chunk_validate")

    graph.add_conditional_edges(
        "stage4_chunk_validate",
        _route_after_chunk_validate,
        {
            "stage5_metadata": "stage5_metadata",
            "hitl_pending": "hitl_pending",
            END: END,
        },
    )

    graph.add_edge("stage5_metadata", "stage5b_metadata_validate")

    graph.add_conditional_edges(
        "stage5b_metadata_validate",
        _route_after_metadata_validate,
        {
            "stage6_store": "stage6_store",
            "hitl_pending": "hitl_pending",
            END: END,
        },
    )

    graph.add_edge("stage6_store", END)
    graph.add_edge("hitl_pending", END)

    return graph.compile()
