"""trace_id 생성 유틸리티.

PRD 섹션 7 기준:
  문서 파이프라인: trc_0001_{doc_id_8hex} (문서별 고유)
  PR 리뷰 파이프라인: pr_{uuid} (요청마다 새로 생성)
  에이전트 서브태스크: {prefix}_{agent}_{4hex}

주의: new_pipeline_trace()는 doc_id를 받아야 문서별 trace가 분리된다.
doc_id 없이 호출하면 고정값(trc_0001 등)을 반환하며, 이 경우
agent_traces 테이블에서 문서 간 덮어쓰기가 발생한다.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from uuid import UUID


class DocPipelineStage(str, Enum):
    """문서 파이프라인 7단계 trace_id 접두사 — PRD 섹션 7 Trace ID 체계."""

    MARKDOWN_CONVERT = "trc_0001"
    MARKDOWN_VALIDATE = "trc_0002"
    CHUNKING = "trc_0003"
    CHUNK_VALIDATE = "trc_0004"
    METADATA_EXTRACT = "trc_0005"
    METADATA_VALIDATE = "trc_0005b"
    STORE_ROUTE = "trc_0006"


def new_pipeline_trace(stage: DocPipelineStage, doc_id: UUID | None = None) -> str:
    """문서 파이프라인 trace_id 반환.

    doc_id를 넣으면 문서별 고유 trace_id를 생성한다 (권장).
    형식: trc_0001_3a9f1c2b  (단계 접두사 + doc_id 앞 8자리)

    doc_id 없이 호출하면 고정값(trc_0001)을 반환한다.
    agent_traces.trace_id PRIMARY KEY 충돌로 이전 기록이 덮어써지므로
    운영 환경에서는 반드시 doc_id를 전달할 것.
    """
    if doc_id is None:
        return stage.value
    short = str(doc_id).replace("-", "")[:8]
    return f"{stage.value}_{short}"


def new_pr_trace() -> str:
    """PR 리뷰 요청마다 고유한 trace_id 생성.

    형식: pr_{12자리 hex}
    예시: pr_3a9f1c2b44e0
    """
    return f"pr_{uuid.uuid4().hex[:12]}"


def new_sub_trace(parent_trace_id: str, agent_name: str) -> str:
    """병렬 에이전트 각각의 서브 trace_id 생성.

    형식: {parent_trace_id}_{agent_name}_{4자리 hex}
    예시: pr_3a9f1c2b44e0_static_analysis_a1b2

    Dev2/3 asyncio.gather 실행 시 에이전트별로 구분하기 위해 사용.
    """
    suffix = uuid.uuid4().hex[:4]
    safe_name = agent_name.lower().replace(" ", "_")
    return f"{parent_trace_id}_{safe_name}_{suffix}"


def trace_metadata(trace_id: str, agent_name: str, doc_id: str | None = None) -> dict:
    """LangSmith run metadata에 추가할 공통 딕셔너리 반환.

    LangGraph config의 metadata 필드에 넣으면
    LangSmith 대시보드에서 trace_id로 검색 가능해짐.
    """
    meta: dict = {
        "trace_id": trace_id,
        "agent_name": agent_name,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    if doc_id:
        meta["doc_id"] = doc_id
    return meta
