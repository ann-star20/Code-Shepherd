"""run_pipeline — URL 배치 파이프라인 오케스트레이터 + 링크 리졸버 통합.

§A run_pipeline_batch:
  URL 목록 → Crawler → Extractor → staging_concepts(DRAFT)
  asyncio.Semaphore(GEMINI_RPM_LIMIT)로 병렬 URL 처리.

§B run_link_resolve:
  세션의 DRAFT staging_concepts → hybrid_resolve → 자동 사전 분류

  MERGE      (score ≥ 0.88): 기존 마스터 노드에 자동 흡수.
             staging state → COMMITTED (HITL 불필요)
  RELATED_TO (0.72 ≤ score < 0.88): 신규 노드 생성 + [:RELATED_TO] 엣지 예약.
             staging state → APPROVED (최종 커밋 대기)
  NEW        (score < 0.72): 완전 독립 신규 개념.
             staging state → DRAFT 유지 (HITL 검토 대상)
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Sequence

import asyncpg

from app.domain.models import ConceptExtractionSchema
from app.infrastructure.graph.hybrid_resolver import MergeAction
from app.infrastructure.graph.neo4j_service import GraphWriterService
from app.usecases.interfaces.pipeline_task import PipelineTask

# Gemini 2.5 Flash RPM 한도 — 동시 실행 상한
GEMINI_RPM_LIMIT: int = 5

log = logging.getLogger(__name__)


# ── §A: 크롤링·추출·스테이징 ───────────────────────────────────────────────────


async def run_pipeline_batch(
    session_id: str,
    url_doc_pairs: Sequence[tuple[str, str]],
    task: PipelineTask,
    semaphore: asyncio.Semaphore | None = None,
) -> list[Exception | None]:
    """URL 목록을 Semaphore-제한 병렬도로 처리한다.

    Args:
        session_id:    파이프라인 트리거 단위 식별자.
        url_doc_pairs: [(url, doc_id), ...] 처리 대상 목록.
        task:          PipelineTask 구현체.
        semaphore:     None이면 GEMINI_RPM_LIMIT 기반 Semaphore 생성.

    Returns:
        각 URL 처리 결과 리스트 — 성공 None, 실패 Exception 인스턴스.
    """
    if semaphore is None:
        semaphore = asyncio.Semaphore(GEMINI_RPM_LIMIT)

    async def _bounded(url: str, doc_id: str) -> None:
        async with semaphore:
            await task.execute(session_id, doc_id, url)

    results: list[Exception | None] = await asyncio.gather(
        *[_bounded(url, doc_id) for url, doc_id in url_doc_pairs],
        return_exceptions=True,
    )
    return results


# ── §B: 링크 리졸버 패스 ────────────────────────────────────────────────────────


async def run_link_resolve(
    session_id: str,
    pg_pool: asyncpg.Pool,
    writer: GraphWriterService,
) -> dict[str, int]:
    """세션의 DRAFT staging_concepts 전체에 hybrid_resolve를 적용한다.

    각 개념을 GraphWriterService.write()로 처리한 뒤 결과에 따라
    staging_concepts.state를 갱신한다.

    Args:
        session_id: 처리 대상 세션 UUID 문자열.
        pg_pool:    asyncpg 커넥션 풀.
        writer:     GraphWriterService 인스턴스.

    Returns:
        {"MERGE": n, "RELATED_TO": n, "NEW": n} — 액션별 처리 건수.
    """
    rows = await pg_pool.fetch(
        """SELECT id, concept_json
           FROM staging_concepts
           WHERE session_id = $1::uuid AND state = 'DRAFT'""",
        session_id,
    )

    summary: dict[MergeAction, int] = {
        MergeAction.MERGE: 0,
        MergeAction.RELATED_TO: 0,
        MergeAction.NEW: 0,
    }

    for row in rows:
        raw = row["concept_json"]
        data = json.loads(raw) if isinstance(raw, str) else dict(raw)
        concept = ConceptExtractionSchema(**data)

        try:
            write_result = await writer.write(concept)
        except Exception as exc:
            log.warning("[resolve] '%s' 처리 실패: %s", concept.concept_name, exc)
            continue

        action = write_result.resolve.action
        summary[action] += 1

        if action == MergeAction.MERGE:
            # 자동 흡수: staging_concepts → COMMITTED
            await pg_pool.execute(
                "UPDATE staging_concepts "
                "SET state='COMMITTED', committed_at=NOW() WHERE id=$1",
                row["id"],
            )
        elif action == MergeAction.RELATED_TO:
            # 관계 엣지 예약 완료: HITL 최종 커밋 대기
            await pg_pool.execute(
                "UPDATE staging_concepts SET state='APPROVED' WHERE id=$1",
                row["id"],
            )
        # NEW: state = DRAFT 유지 (HITL 검토 대상 — 변경 없음)

    result = {k.value: v for k, v in summary.items()}
    log.info("[resolve] session=%s result=%s", session_id, result)
    return result
