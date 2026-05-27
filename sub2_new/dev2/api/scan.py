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
import subprocess
from pathlib import Path  # mock-bandit 엔드포인트에서 사용

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

@router.post("/scan/mock-bandit")
async def run_mock_bandit_scan():
    """
    MVP 테스트용 Bandit 스캔 API.

    기존 POST /scan은 Dev1 입력 계약(TaskPayload)을 받는 정식 엔드포인트다.
    이 엔드포인트는 MVP 검증용으로:
    1. mock_vulnerable 폴더 Bandit 스캔
    2. bandit_result.json 생성
    3. generate_bandit_sql.py 실행 → insert_bandit_result.sql 생성
    4. Cloud SQL (db.py AsyncSessionLocal)로 저장

    subprocess 호출은 asyncio.to_thread()로 오프로드해 이벤트 루프 블로킹 방지.
    DB 저장은 docker exec 대신 db.py의 AsyncSessionLocal 사용 (Cloud SQL 호환).
    """
    import asyncio  # noqa: PLC0415

    from sqlalchemy import text  # noqa: PLC0415
    from dev2.db import AsyncSessionLocal  # noqa: PLC0415

    # scan.py 위치: dev2/api/scan.py
    # 프로젝트 루트: sub2_new/dev2
    project_root = Path(__file__).resolve().parents[1]

    target_dir = project_root / "mock_vulnerable"
    bandit_result = project_root / "bandit_result.json"
    sql_generator = project_root / "generate_bandit_sql.py"
    sql_file = project_root / "insert_bandit_result.sql"

    if not target_dir.exists():
        return {
            "status": "error",
            "step": "check_target",
            "message": f"스캔 대상 폴더가 없습니다: {target_dir}",
        }

    if not sql_generator.exists():
        return {
            "status": "error",
            "step": "check_sql_generator",
            "message": f"SQL 생성 파일이 없습니다: {sql_generator}",
        }

    # 1. Bandit 실행 — subprocess를 스레드풀로 오프로드 (이벤트 루프 블로킹 방지)
    bandit_process = await asyncio.to_thread(
        subprocess.run,
        ["python", "-m", "bandit", "-r", str(target_dir), "-f", "json", "-o", str(bandit_result)],
        capture_output=True,
        text=True,
        cwd=str(project_root),
    )

    # Bandit은 취약점 발견 시 returncode 1 반환 → json 생성 여부로 성공 판단
    if not bandit_result.exists():
        return {
            "status": "error",
            "step": "bandit",
            "message": "bandit_result.json 생성 실패",
            "returncode": bandit_process.returncode,
            "stderr": bandit_process.stderr,
        }

    # 2. SQL 생성 — 스레드풀 오프로드
    sql_process = await asyncio.to_thread(
        subprocess.run,
        ["python", str(sql_generator)],
        capture_output=True,
        text=True,
        cwd=str(project_root),
    )

    if sql_process.returncode != 0 or not sql_file.exists():
        return {
            "status": "error",
            "step": "generate_sql",
            "message": "insert_bandit_result.sql 생성 실패",
            "returncode": sql_process.returncode,
            "stderr": sql_process.stderr,
        }

    # 3. Cloud SQL에 저장 — db.py AsyncSessionLocal 사용 (docker exec 제거)
    sql_text = sql_file.read_text(encoding="utf-8")
    try:
        async with AsyncSessionLocal() as s:
            for statement in sql_text.split(";"):
                stmt = statement.strip()
                if stmt:
                    await s.execute(text(stmt))
            await s.commit()
    except Exception as exc:
        logger.error("run_mock_bandit_scan: Cloud SQL 저장 실패 — %s", exc)
        return {
            "status": "error",
            "step": "db_insert",
            "message": f"Cloud SQL 저장 실패: {exc}",
        }

    logger.info("run_mock_bandit_scan: 완료 (bandit_returncode=%d)", bandit_process.returncode)
    return {
        "status": "success",
        "message": "Mock Bandit scan result saved to Cloud SQL",
        "bandit_returncode": bandit_process.returncode,
    }

