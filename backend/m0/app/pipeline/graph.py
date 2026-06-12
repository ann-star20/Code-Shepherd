"""
KMS 문서 처리 파이프라인 — LangGraph StateGraph

7단계(Stage 1 → 5b → 6)를 순서대로 실행하며, 각 단계는 AgentHarness로 감싸져
LangSmith 추적과 PostgreSQL agent_traces 기록이 자동 처리된다.

HITL 분기:
    stage2_validate / stage4_chunk_validate / stage5b_metadata_validate에서
    hitl_required=True이면 "hitl_pending" 노드로 라우팅 → 파이프라인 종료

DB 레이어:
    asyncpg Pool 직접 사용 금지. async_sessionmaker[AsyncSession]만 사용한다.
    (개인 프로젝트와의 차이 — m0 CLAUDE.md 섹션 6 참조)

사용 예시:
    from app.pipeline.graph import build_pipeline

    pipeline = build_pipeline(db_session_factory=session_factory, storage=storage)
    result = await pipeline.ainvoke(initial_state)

⚠️  이 파일은 stage1~5b 파이프라인 파일이 모두 존재해야 import 가능하다.
    현재 구현된 파일: stage6_store.py
    구현 예정: stage1_document_parser_agent, stage2_validate_agent,
               stage3_chunk, stage4_chunk_validate,
               stage5_metadata_agent, stage5b_metadata_validate_agent
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING
from uuid import UUID

from langgraph.graph import StateGraph, END
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from shared.harness import AgentHarness
from shared.trace import DocPipelineStage, new_pipeline_trace
from app.pipeline.models import DocPipelineState
from app.pipeline.stage1_document_parser_agent import document_parser_agent
from app.pipeline.stage2_validate_agent import stage2_validate
from app.pipeline.stage3_chunk import stage3_chunk
from app.pipeline.stage4_chunk_validate import stage4_chunk_validate
from app.pipeline.stage5_metadata_agent import stage5_metadata
from app.pipeline.stage5b_metadata_validate_agent import stage5b_metadata_validate
from app.pipeline.stage6_store import stage6_store

if TYPE_CHECKING:
    from app.storage import Storage

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Harness 래핑 헬퍼
# ---------------------------------------------------------------------------

async def _overwrite_trace_as_fail(
    trace_id: str,
    factory: async_sessionmaker[AsyncSession],
    error_msg: str,
) -> None:
    """stage 함수가 예외 없이 status='failed' dict를 반환한 경우 trace를 소급 수정."""
    try:
        async with factory() as session:
            await session.execute(
                text("""
                    UPDATE agent_traces
                    SET status        = 'fail',
                        error_message = :error_message
                    WHERE trace_id = :trace_id
                """),
                {"trace_id": trace_id, "error_message": error_msg},
            )
            await session.commit()
    except Exception as e:
        logger.warning(
            "agent_traces 소급 실패 기록 오류 (무시)",
            extra={"trace_id": trace_id, "error": str(e)},
        )


def _wrap_with_harness(
    stage: DocPipelineStage,
    agent_name: str,
    fn,
    _factory: async_sessionmaker[AsyncSession],
    **fn_kwargs,
):
    """
    LangGraph 노드 함수를 AgentHarness로 감싼다.
    타임아웃 및 agent_traces 기록은 harness가 담당한다.
    fn_kwargs에 db_session_factory를 포함하면 fn에도 전달된다 (stage6_store 등).

    stage 함수가 예외 없이 {"status": "failed"} dict를 반환하는 경우(내부 try-except로
    오류를 흡수한 경우)에도 agent_traces를 소급하여 "fail"로 업데이트한다.
    """
    async def _node(state: DocPipelineState, **_) -> dict:
        trace_id = new_pipeline_trace(stage, UUID(state["doc_id"]))
        try:
            result: dict = {}
            async with AgentHarness(
                trace_id=trace_id,
                agent_name=agent_name,
                db_session_factory=_factory,
                doc_id=UUID(state["doc_id"]),
            ) as harness:
                result = await harness.run(fn, state, **fn_kwargs)
            # stage가 예외 없이 failed를 반환한 경우 trace를 소급 수정
            if isinstance(result, dict) and result.get("status") == "failed":
                error_msg = result.get("error") or f"{agent_name} 실패 (오류 메시지 없음)"
                await _overwrite_trace_as_fail(trace_id, _factory, error_msg)
            return result
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


async def _insert_hitl_queue(
    db_session_factory: async_sessionmaker[AsyncSession],
    state: DocPipelineState,
) -> None:
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
            "issues": reason_list,
            "metadata": state.get("metadata"),
            "markdown_storage_path": state.get("markdown_storage_path"),
            "category_reasoning": state.get("category_reasoning", ""),
            "category_alternatives": state.get("category_alternatives", []),
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
        async with db_session_factory() as session:
            await session.execute(
                text("""
                    INSERT INTO hitl_queue
                        (doc_id, stage, reason, quality_score, issues, status)
                    VALUES
                        (:doc_id, :stage, :reason, :quality_score, CAST(:issues AS jsonb), 'pending')
                """),
                {
                    "doc_id": str(doc_id),
                    "stage": stage,
                    "reason": reason,
                    "quality_score": quality_score,
                    "issues": json.dumps(issues, ensure_ascii=False),
                },
            )
            # HITL 발동 시점에 알려진 파싱 정보를 documents에 저장
            await session.execute(
                text("""
                    UPDATE documents
                    SET file_type         = COALESCE(file_type,         :file_type),
                        parser_used       = COALESCE(parser_used,       :parser_used),
                        original_filename = COALESCE(original_filename, :original_filename)
                    WHERE doc_id = :doc_id
                """),
                {
                    "file_type": state.get("file_type"),
                    "parser_used": state.get("parser_used"),
                    "original_filename": state.get("original_filename"),
                    "doc_id": str(doc_id),
                },
            )
            await session.commit()
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
    db_session_factory: async_sessionmaker[AsyncSession],
    storage: "Storage",
):
    """
    KMS 문서 처리 파이프라인 LangGraph를 생성·컴파일한다.

    Args:
        db_session_factory: SQLAlchemy async_sessionmaker
            (agent_traces + documents + chunks + embeddings 기록)
        storage: Storage 구현체 (GCSStorage or LocalStorage)

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
            db_session_factory,
            storage=storage,
        ),
    )
    graph.add_node(
        "stage2_validate",
        _wrap_with_harness(
            DocPipelineStage.MARKDOWN_VALIDATE,
            "MarkdownValidateAgent",
            stage2_validate,
            db_session_factory,
        ),
    )
    graph.add_node(
        "stage3_chunk",
        _wrap_with_harness(
            DocPipelineStage.CHUNKING,
            "ChunkingAgent",
            stage3_chunk,
            db_session_factory,
        ),
    )
    graph.add_node(
        "stage4_chunk_validate",
        _wrap_with_harness(
            DocPipelineStage.CHUNK_VALIDATE,
            "ChunkValidateAgent",
            stage4_chunk_validate,
            db_session_factory,
        ),
    )
    graph.add_node(
        "stage5_metadata",
        _wrap_with_harness(
            DocPipelineStage.METADATA_EXTRACT,
            "MetadataExtractAgent",
            stage5_metadata,
            db_session_factory,
        ),
    )
    graph.add_node(
        "stage5b_metadata_validate",
        _wrap_with_harness(
            DocPipelineStage.METADATA_VALIDATE,
            "MetadataValidateAgent",
            stage5b_metadata_validate,
            db_session_factory,
        ),
    )
    graph.add_node(
        "stage6_store",
        _wrap_with_harness(
            DocPipelineStage.STORE_ROUTE,
            "StoreRouteAgent",
            stage6_store,
            db_session_factory,
            db_session_factory=db_session_factory,
            storage=storage,
        ),
    )

    # hitl_pending 노드: DB INSERT 후 파이프라인 종료
    async def _hitl_with_db(state: DocPipelineState) -> dict:
        await _insert_hitl_queue(db_session_factory, state)
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
