"""
scan.py — POST /scan 엔드포인트

Dev1 Orchestrator 또는 GitHub Webhook이 PR 분석을 요청하는 진입점.

설계:
    - 202 Accepted: 무거운 LLM 분석을 즉시 실행하지 않고 BackgroundTasks로 등록.
      클라이언트는 분석 완료를 기다리지 않아도 됨.
    - BackgroundTasks: FastAPI 내장 비동기 후처리. 응답 전송 후 run_dev2() 실행.

CQRS 분리:
    쓰기(트리거): POST /scan → BackgroundTasks → run_dev2 (LangGraph 파이프라인)
    읽기(조회):  GET /insights/* (insights.py)

CLAUDE.md §5-B: TaskPayload = Dev1 → Dev2 입력 계약 (Pydantic 검증)
CLAUDE.md §6:   BackgroundTasks → 응답 반환 후 run_dev2 실행 (타임아웃 분리)
"""

import logging

from fastapi import APIRouter, BackgroundTasks

from dev2.graph import run_dev2
from dev2.schema import Dev2State, TaskPayload

logger = logging.getLogger(__name__)

router = APIRouter(tags=["scan"])


def _payload_to_state(payload: TaskPayload) -> Dev2State:
    """
    TaskPayload (Dev1 → Dev2 입력 계약) 를 Dev2State로 변환한다.

    TaskPayload.developer → Dev2State.developer_id / skill_level / tech_stack
    TaskPayload.context  → Dev2State.architecture_docs / coding_conventions / previous_pr_issues

    [CLAUDE.md §11] PRReviewState 필드 명세 준수.

    Args:
        payload: Pydantic 검증 완료된 Dev1 입력

    Returns:
        Dev2State — run_dev2()에 전달할 LangGraph 초기 State
    """
    return {
        # PRReviewState 필드 (Dev1이 채움)
        "task_id": payload.task_id,
        "pr_id": payload.pr_id,
        "pr_diff": payload.pr_diff,
        "developer_id": payload.developer.id,
        "skill_level": payload.developer.skill_level,
        "tech_stack": payload.developer.tech_stack,
        "architecture_docs": payload.context.architecture_docs,
        "coding_conventions": payload.context.coding_conventions,
        "previous_pr_issues": payload.context.previous_pr_issues,
        # Dev2 전용 필드 초기값
        "static_raw": [],
        "security_raw": [],
        "enriched": [],
        "final_output": [],
    }


@router.post("/scan", status_code=202)
async def trigger_scan(payload: TaskPayload, background_tasks: BackgroundTasks):
    """
    PR 분석 트리거 (비동기 접수).

    동작 흐름:
        1. FastAPI가 요청 바디를 TaskPayload(Pydantic)로 자동 파싱·검증
        2. BackgroundTasks에 run_dev2 등록 (즉시 실행 안 함)
        3. 202 Accepted + 접수증 즉시 반환
        4. 응답 전송 후 → run_dev2(state) 실행 (LangGraph 5노드 파이프라인)

    왜 202인가:
        LLM 분석은 수 초~수십 초가 걸린다. 200(처리 완료)을 기다리면
        클라이언트 HTTP 타임아웃에 걸릴 수 있어 202(접수 완료)로 분리한다.

    Args:
        payload: TaskPayload — Dev1 → Dev2 입력 계약 (CLAUDE.md §5-B)
        background_tasks: FastAPI BackgroundTasks — 응답 후 실행 작업 등록

    Returns:
        {"status": "accepted", "task_id": str} — 접수증 (결과 아님)
    """
    initial_state = _payload_to_state(payload)

    # BackgroundTasks에 등록 — 응답 전송 후 자동 실행
    background_tasks.add_task(run_dev2, initial_state)

    logger.info(
        "POST /scan: 접수 완료 (task_id=%s, pr_id=%s, developer=%s)",
        payload.task_id, payload.pr_id, payload.developer.id,
    )

    return {"status": "accepted", "task_id": payload.task_id}
