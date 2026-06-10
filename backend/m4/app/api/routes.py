"""T2 누락 라우트 + T4 JWT 인증 — POST /api/learn, GET /api/pr/{scan_id}, POST /api/complete (D2/D4/D11/D19)."""

import asyncio
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import case, func, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.kms.search_adapter import PgvectorAdapter
from app.models.curriculum_plan import CurriculumPlan
from app.models.review_issue import ReviewIssue
from app.pipeline.learn_pipeline import generate_card
from shared.auth import get_current_user
from shared.db import get_session

router = APIRouter(prefix="/api", tags=["learning"])

PR_NOT_FOUND_DETAIL = "제출된 PR이 없습니다. PR을 먼저 제출해 주세요."
PLAN_NOT_FOUND_DETAIL = "curriculum_plan을 찾을 수 없습니다."

# severity는 TEXT 컬럼이라 알파벳 순으로는 critical > high > low > medium이 되어버림
# → CASE로 숫자 우선순위를 매겨 critical, high, medium, low 순으로 정렬한다 (D19 top 3 선정 기준)
_SEVERITY_RANK = case(
    (ReviewIssue.severity == "critical", 1),
    (ReviewIssue.severity == "high", 2),
    (ReviewIssue.severity == "medium", 3),
    (ReviewIssue.severity == "low", 4),
    else_=5,
)


class CompleteRequest(BaseModel):
    plan_id: uuid.UUID


def _parse_user_id(payload: dict) -> uuid.UUID:
    return uuid.UUID(payload["sub"])


# pull_requests는 m4 Base.metadata에 등록되어 있지 않은 타 모듈 소유 테이블이라
# ORM select(PullRequest) 대신 파라미터 바인딩된 raw SQL로 조회한다 (review_issue의 cross-module FK 이슈와 동일 구조)
async def _find_latest_pr_id(session: AsyncSession, user_id: uuid.UUID) -> uuid.UUID | None:
    result = await session.execute(
        text("SELECT id FROM pull_requests WHERE user_id = :user_id ORDER BY submitted_at DESC LIMIT 1"),
        {"user_id": user_id},
    )
    row = result.first()
    return row[0] if row else None


async def _find_top3_issues(session: AsyncSession, pr_id: uuid.UUID) -> list[ReviewIssue]:
    result = await session.execute(
        select(ReviewIssue)
        .where(ReviewIssue.pull_request_id == pr_id)
        .order_by(_SEVERITY_RANK, ReviewIssue.created_at)
        .limit(3)
    )
    return list(result.scalars().all())


async def _find_existing_plans(session: AsyncSession, issue_ids: list[uuid.UUID]) -> list[CurriculumPlan]:
    if not issue_ids:
        return []
    result = await session.execute(select(CurriculumPlan).where(CurriculumPlan.issue_id.in_(issue_ids)))
    return list(result.scalars().all())


async def _create_pending_plans(session: AsyncSession, issues: list[ReviewIssue]) -> list[CurriculumPlan]:
    """ON CONFLICT DO NOTHING으로 동시 요청 시에도 IntegrityError 없이 생성한다 (D5/T5 race condition 처리).

    RETURNING은 실제로 INSERT된 row만 돌려주고 충돌로 스킵된 row는 포함하지 않는다 —
    그래서 빈 리스트가 반환되면 "동시 요청에 져서 내가 만든 게 하나도 없다"는 뜻이고,
    호출부는 그 신호로 동시 요청이 만든 plan을 재조회해서 그대로 돌려주면 된다.
    """
    if not issues:
        return []
    values = [{"id": uuid.uuid4(), "issue_id": issue.id, "status": "pending"} for issue in issues]
    stmt = (
        pg_insert(CurriculumPlan)
        .values(values)
        .on_conflict_do_nothing(index_elements=[CurriculumPlan.issue_id])
        .returning(CurriculumPlan)
    )
    result = await session.execute(stmt)
    plans = list(result.scalars().all())
    await session.commit()
    return plans


async def _count_user_mistakes(session: AsyncSession, *, user_id: uuid.UUID | None, keyword: str) -> int:
    """이 개발자가 같은 keyword로 발생시킨 review_issue 누적 횟수 — depth 결정(D18)의 mistake_count."""
    if user_id is None:
        return 0
    result = await session.execute(
        select(func.count())
        .select_from(ReviewIssue)
        .where(ReviewIssue.user_id == user_id, ReviewIssue.keyword == keyword)
    )
    return result.scalar_one()


async def _run_card_generation(plan_issue_pairs: list[tuple[uuid.UUID, ReviewIssue]]) -> None:
    """BackgroundTask — pending 상태로 미리 만들어둔 plan row를 generate_card 결과로 갱신한다 (D2: "202 즉시 응답 후 비동기 생성").

    generate_card()는 새 CurriculumPlan 인스턴스를 반환할 뿐 기존 row를 갱신하지 않으므로
    (이미 검증된 계약이라 변경하지 않음), 여기서 결과 필드를 pending row에 합성해 커밋한다.
    """
    from shared.config import get_settings
    from shared.db import create_engine_from_url, create_session_factory

    settings = get_settings()
    engine = create_engine_from_url(settings.database_url)
    session_factory = create_session_factory(engine)

    async def _generate_one(plan_id: uuid.UUID, issue: ReviewIssue) -> None:
        async with session_factory() as session:
            adapter = PgvectorAdapter(session)
            plan = await session.get(CurriculumPlan, plan_id)
            if plan is None:
                return
            try:
                plan.status = "running"
                await session.commit()

                mistake_count = await _count_user_mistakes(session, user_id=issue.user_id, keyword=issue.keyword)
                generated = await generate_card(issue, adapter, mistake_count=mistake_count)
                plan.status = generated.status
                plan.llm_fallback = generated.llm_fallback
                plan.error_message = generated.error_message
                plan.card_content = generated.card_content
                await session.commit()
            except Exception as exc:
                plan.status = "failed"
                plan.error_message = str(exc)
                await session.commit()

    await asyncio.gather(*[_generate_one(plan_id, issue) for plan_id, issue in plan_issue_pairs])
    await engine.dispose()


@router.post("/learn", status_code=status.HTTP_202_ACCEPTED)
async def post_learn(
    background_tasks: BackgroundTasks,
    payload: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """D2/D19 — 사용자의 최신 PR에서 severity 상위 3개 이슈를 골라 학습 카드 생성을 시작한다."""
    user_id = _parse_user_id(payload)

    pr_id = await _find_latest_pr_id(session, user_id)
    if pr_id is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=PR_NOT_FOUND_DETAIL)

    issues = await _find_top3_issues(session, pr_id)
    issue_ids = [issue.id for issue in issues]
    existing_plans = await _find_existing_plans(session, issue_ids)

    if existing_plans:
        # D4 — 동일 PR에 대한 재요청은 새로 만들지 않고 기존 plan을 그대로 반환
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={"scan_id": str(pr_id), "plan_ids": [str(plan.id) for plan in existing_plans]},
        )

    plans = await _create_pending_plans(session, issues)
    if not plans:
        # D5/T5 race condition — 사전 조회 후 INSERT 사이에 동시 요청이 먼저 만들어버린 경우.
        # ON CONFLICT DO NOTHING이라 에러 없이 빈 리스트만 돌아오므로, 이긴 쪽이 만든 plan을
        # 재조회해서 그대로 반환한다 (카드 생성도 중복 트리거하지 않음).
        plans = await _find_existing_plans(session, issue_ids)
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={"scan_id": str(pr_id), "plan_ids": [str(plan.id) for plan in plans]},
        )

    background_tasks.add_task(_run_card_generation, list(zip((plan.id for plan in plans), issues)))

    return {"scan_id": pr_id, "plan_ids": [plan.id for plan in plans]}


async def _load_issues_with_plans(
    session: AsyncSession, scan_id: uuid.UUID
) -> list[tuple[ReviewIssue, CurriculumPlan]]:
    result = await session.execute(
        select(ReviewIssue, CurriculumPlan)
        .join(CurriculumPlan, CurriculumPlan.issue_id == ReviewIssue.id)
        .where(ReviewIssue.pull_request_id == scan_id)
        .order_by(_SEVERITY_RANK, ReviewIssue.created_at)
    )
    return [(issue, plan) for issue, plan in result.all()]


def _plan_json(plan: CurriculumPlan | None) -> dict | None:
    if plan is None:
        return None
    return {
        "id": str(plan.id),
        "status": plan.status,
        "llm_fallback": plan.llm_fallback,
        "error_message": plan.error_message,
        "card_content": plan.card_content,
        # ragas_reason/attempt_count/curator_instruction: Phase 2(T12/T13/T14/T16) 전까지는
        # curriculum_plan에 컬럼 자체가 없음 — ragas_eval.reason의 "Phase 1엔 항상 None" 전례를 따라 placeholder 반환
        "ragas_reason": None,
        "attempt_count": None,
        "curator_instruction": None,
    }


@router.get("/pr/{scan_id}")
async def get_pr(
    scan_id: uuid.UUID,
    payload: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """D2 — scan_id(=pull_requests.id) 기준으로 이슈와 학습 카드 진행 상태를 함께 반환한다 (프론트 polling 대상)."""
    rows = await _load_issues_with_plans(session, scan_id)
    return {
        "issues": [
            {
                "id": str(issue.id),
                "keyword": issue.keyword,
                "severity": issue.severity,
                "plan": _plan_json(plan),
            }
            for issue, plan in rows
        ]
    }


async def _mark_plan_completed(session: AsyncSession, plan_id: uuid.UUID) -> CurriculumPlan | None:
    """D11 — 카드 학습 완료 시각을 기록한다. 이미 기록돼 있으면 그대로 반환(idempotent, 중복 호출 대비)."""
    plan = await session.get(CurriculumPlan, plan_id)
    if plan is None:
        return None
    if plan.completed_at is None:
        plan.completed_at = datetime.now(UTC)
        await session.commit()
        await session.refresh(plan)
    return plan


@router.post("/complete")
async def post_complete(
    body: CompleteRequest,
    payload: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """D11 — 학습 카드 페이지 진입 시 호출되는 학습 완료 기록 엔드포인트."""
    plan = await _mark_plan_completed(session, body.plan_id)
    if plan is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=PLAN_NOT_FOUND_DETAIL)
    return {"id": str(plan.id), "completed_at": plan.completed_at}
