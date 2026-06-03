"""
api/aggregate.py — POST /aggregate 엔드포인트 (파이프라인 2 트리거)

M0(Orchestrator)가 M2+M3 분석 결과를 묶어 전송하면 취합·코멘트·알림
파이프라인을 비동기로 실행한다. 202 Accepted를 즉시 반환한다.
"""

from fastapi import APIRouter, BackgroundTasks

from dev2.aggregate_graph import run_aggregate
from dev2.schema import AggregatePayload

router = APIRouter()


@router.post("/aggregate", status_code=202, tags=["aggregate"])
async def trigger_aggregate(payload: AggregatePayload, background_tasks: BackgroundTasks):
    """
    M0가 M2+M3 결과를 묶어 전송 → 취합·코멘트·알림 파이프라인 비동기 실행.

    202 즉시 반환 (BackgroundTasks).
    """
    background_tasks.add_task(run_aggregate, payload.model_dump())
    return {"status": "accepted", "task_id": payload.task_id}
