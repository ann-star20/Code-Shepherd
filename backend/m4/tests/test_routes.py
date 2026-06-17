"""계약 테스트 — /api/learn, /api/pr/{scan_id}, /api/complete (T2 라우트 + T4 JWT 인증, Mock 기반)."""

import asyncio
import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.api import routes
from app.main import app
from app.models.curriculum_plan import CurriculumPlan
from app.models.review_issue import ReviewIssue
from app.pipeline.curator_agent import GEMINI_TIMEOUT_SECONDS
from shared.auth import get_current_user
from shared.db import get_session

USER_ID = uuid.uuid4()
PR_ID = uuid.uuid4()
NOW = datetime(2026, 6, 7, 12, 0, tzinfo=UTC)


def make_issue(**overrides) -> ReviewIssue:
    defaults = dict(
        id=uuid.uuid4(),
        pull_request_id=PR_ID,
        user_id=USER_ID,
        severity="critical",
        keyword="SQL Injection",
    )
    defaults.update(overrides)
    return ReviewIssue(**defaults)


def make_plan(issue_id: uuid.UUID, **overrides) -> CurriculumPlan:
    defaults = dict(
        id=uuid.uuid4(),
        issue_id=issue_id,
        status="pending",
        llm_fallback=False,
        error_message=None,
        card_content=None,
        completed_at=None,
    )
    defaults.update(overrides)
    return CurriculumPlan(**defaults)


@pytest.fixture
def auth_override():
    app.dependency_overrides[get_current_user] = lambda: {"sub": str(USER_ID)}
    yield
    app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture
def session_override():
    fake_session = AsyncMock()
    app.dependency_overrides[get_session] = lambda: fake_session
    yield fake_session
    app.dependency_overrides.pop(get_session, None)


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


# ---------------------------------------------------------------------------
# 인증 게이트 — Bearer 토큰 없이 호출 시 401 (T4 확인 기준)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_post_learn_without_token_returns_401(client, session_override):
    resp = await client.post("/api/learn", json={})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_get_pr_without_token_returns_401(client, session_override):
    resp = await client.get(f"/api/pr/{PR_ID}")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_post_complete_without_token_returns_401(client, session_override):
    resp = await client.post("/api/complete", json={"plan_id": str(uuid.uuid4())})
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# _find_latest_pr_id — review_issue.created_at 기준 "최신 PR" 판단 (D19)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_find_latest_pr_id_queries_review_issue_not_pull_requests():
    """pull_requests.submitted_at(타 모듈 소유, raw SQL) 대신 review_issue.created_at(m4 소유,
    ORM 등록)을 기준으로 최신 PR을 찾는다 — PR은 제출됐지만 리뷰(review_issue)가 아직 끝나지
    않은 더 최근 PR이 "최신"으로 잡혀 top3 이슈가 0개가 되는 문제를 피한다."""
    fake_session = AsyncMock()
    fake_session.execute = AsyncMock(return_value=SimpleNamespace(first=lambda: (PR_ID,)))

    pr_id = await routes._find_latest_pr_id(fake_session, USER_ID)

    assert pr_id == PR_ID
    executed_stmt = fake_session.execute.call_args[0][0]
    compiled_sql = str(executed_stmt).lower()
    assert "review_issue" in compiled_sql
    assert "pull_requests" not in compiled_sql


@pytest.mark.asyncio
async def test_find_latest_pr_id_returns_none_when_user_has_no_review_issues():
    fake_session = AsyncMock()
    fake_session.execute = AsyncMock(return_value=SimpleNamespace(first=lambda: None))

    pr_id = await routes._find_latest_pr_id(fake_session, USER_ID)

    assert pr_id is None


# ---------------------------------------------------------------------------
# _find_top3_issues / _load_issues_with_plans — created_at DESC 우선, severity_rank는
# tiebreaker (D38: 같은 PR 안에서도 최신 스캔에서 insert된 이슈를 먼저 보여준다)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_find_top3_issues_orders_by_created_at_desc_before_severity_rank():
    """한 PR 안에 재스캔으로 인한 오래된 row와 최신 row가 섞여 있을 때, severity가 더 낮아도
    created_at이 더 최근인 이슈를 먼저 정렬한다 (D38) — severity_rank(CASE)는 created_at이
    동일할 때만 tiebreaker로 작동해야 한다."""
    fake_session = AsyncMock()
    fake_session.execute = AsyncMock(return_value=SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: [])))

    await routes._find_top3_issues(fake_session, PR_ID)

    executed_stmt = fake_session.execute.call_args[0][0]
    order_by_clause = str(executed_stmt).split("ORDER BY")[1]
    created_at_pos = order_by_clause.find("created_at")
    case_pos = order_by_clause.find("CASE")

    assert created_at_pos != -1
    assert case_pos != -1
    assert created_at_pos < case_pos
    assert "created_at DESC" in order_by_clause


@pytest.mark.asyncio
async def test_load_issues_with_plans_orders_by_created_at_desc_before_severity_rank():
    """GET /api/pr/{scan_id}의 이슈 표시 순서도 _find_top3_issues와 동일하게 created_at DESC
    우선, severity_rank가 tiebreaker가 되어야 한다 (D38)."""
    fake_session = AsyncMock()
    fake_session.execute = AsyncMock(return_value=SimpleNamespace(all=lambda: []))

    await routes._load_issues_with_plans(fake_session, PR_ID)

    executed_stmt = fake_session.execute.call_args[0][0]
    order_by_clause = str(executed_stmt).split("ORDER BY")[1]
    created_at_pos = order_by_clause.find("created_at")
    case_pos = order_by_clause.find("CASE")

    assert created_at_pos != -1
    assert case_pos != -1
    assert created_at_pos < case_pos
    assert "created_at DESC" in order_by_clause


# ---------------------------------------------------------------------------
# POST /api/learn
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_post_learn_no_pr_returns_404(client, auth_override, session_override):
    with patch.object(routes, "_find_latest_pr_id", new=AsyncMock(return_value=None)):
        resp = await client.post("/api/learn", json={})

    assert resp.status_code == 404
    assert resp.json()["detail"] == "제출된 PR이 없습니다. PR을 먼저 제출해 주세요."


@pytest.mark.asyncio
async def test_post_learn_new_returns_202_with_plan_ids(client, auth_override, session_override):
    issues = [make_issue() for _ in range(3)]
    plans = [make_plan(issue.id) for issue in issues]

    with (
        patch.object(routes, "_find_latest_pr_id", new=AsyncMock(return_value=PR_ID)),
        patch.object(routes, "_find_top3_issues", new=AsyncMock(return_value=issues)),
        patch.object(routes, "_find_existing_plans", new=AsyncMock(return_value=[])),
        patch.object(routes, "_create_pending_plans", new=AsyncMock(return_value=plans)),
        patch.object(routes, "_run_card_generation", new=AsyncMock()),
    ):
        resp = await client.post("/api/learn", json={})

    assert resp.status_code == 202
    body = resp.json()
    assert body["scan_id"] == str(PR_ID)
    assert sorted(body["plan_ids"]) == sorted(str(p.id) for p in plans)


@pytest.mark.asyncio
async def test_post_learn_duplicate_returns_200_with_existing_plan_ids(client, auth_override, session_override):
    issues = [make_issue() for _ in range(3)]
    existing_plans = [make_plan(issue.id, status="completed") for issue in issues]

    with (
        patch.object(routes, "_find_latest_pr_id", new=AsyncMock(return_value=PR_ID)),
        patch.object(routes, "_find_top3_issues", new=AsyncMock(return_value=issues)),
        patch.object(routes, "_find_existing_plans", new=AsyncMock(return_value=existing_plans)),
        patch.object(routes, "_create_pending_plans", new=AsyncMock()) as create_mock,
    ):
        resp = await client.post("/api/learn", json={})
        create_mock.assert_not_called()

    assert resp.status_code == 200
    body = resp.json()
    assert body["scan_id"] == str(PR_ID)
    assert sorted(body["plan_ids"]) == sorted(str(p.id) for p in existing_plans)


@pytest.mark.asyncio
async def test_post_learn_resets_failed_plans_to_pending_and_retriggers_generation(
    client, auth_override, session_override
):
    """D4 보강 — 기존 plan 중 status='failed'가 있으면 그 row를 'pending'으로 되돌리고
    review_issue를 다시 넘겨 _run_card_generation을 재트리거한다. status='failed' 기록 자체가
    영구적으로 재생성을 막아서는 안 된다 (completed/pending plan은 그대로 유지)."""
    issues = [make_issue() for _ in range(3)]
    existing_plans = [
        make_plan(issues[0].id, status="completed"),
        make_plan(issues[1].id, status="failed", error_message="Gemini 응답 시간 초과 (60s)"),
        make_plan(issues[2].id, status="pending"),
    ]

    with (
        patch.object(routes, "_find_latest_pr_id", new=AsyncMock(return_value=PR_ID)),
        patch.object(routes, "_find_top3_issues", new=AsyncMock(return_value=issues)),
        patch.object(routes, "_find_existing_plans", new=AsyncMock(return_value=existing_plans)),
        patch.object(routes, "_create_pending_plans", new=AsyncMock()) as create_mock,
        patch.object(routes, "_run_card_generation", new=AsyncMock()) as generation_mock,
    ):
        resp = await client.post("/api/learn", json={})
        create_mock.assert_not_called()

    assert resp.status_code == 200
    body = resp.json()
    assert body["scan_id"] == str(PR_ID)
    assert sorted(body["plan_ids"]) == sorted(str(p.id) for p in existing_plans)

    failed_plan = existing_plans[1]
    assert failed_plan.status == "pending"
    assert failed_plan.error_message is None

    # completed/pending plan은 그대로 유지된다
    assert existing_plans[0].status == "completed"
    assert existing_plans[2].status == "pending"

    generation_mock.assert_called_once_with([(failed_plan.id, issues[1])])


@pytest.mark.asyncio
async def test_post_learn_race_condition_returns_200_with_winner_plan_ids(client, auth_override, session_override):
    """동시 요청 race condition (T5/D5) — 사전 조회 시점엔 없었지만, INSERT 직전에 다른 요청이 먼저
    만들어버린 경우. ON CONFLICT DO NOTHING이라 IntegrityError 없이 빈 리스트가 돌아오고,
    그러면 이긴 쪽이 만든 plan을 재조회해서 그대로 반환한다 — 카드 생성도 중복 트리거하지 않는다."""
    issues = [make_issue() for _ in range(3)]
    winner_plans = [make_plan(issue.id) for issue in issues]

    with (
        patch.object(routes, "_find_latest_pr_id", new=AsyncMock(return_value=PR_ID)),
        patch.object(routes, "_find_top3_issues", new=AsyncMock(return_value=issues)),
        patch.object(routes, "_find_existing_plans", new=AsyncMock(side_effect=[[], winner_plans])),
        patch.object(routes, "_create_pending_plans", new=AsyncMock(return_value=[])),
        patch.object(routes, "_run_card_generation", new=AsyncMock()) as generation_mock,
    ):
        resp = await client.post("/api/learn", json={})
        generation_mock.assert_not_called()

    assert resp.status_code == 200
    body = resp.json()
    assert body["scan_id"] == str(PR_ID)
    assert sorted(body["plan_ids"]) == sorted(str(p.id) for p in winner_plans)


# ---------------------------------------------------------------------------
# GET /api/pr/{scan_id}
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_pr_returns_issues_with_plans(client, auth_override, session_override):
    issue_with_plan = make_issue(keyword="SQL Injection", severity="critical")
    plan = make_plan(
        issue_with_plan.id, status="completed", card_content={"explanation": "..."}, ragas_reason="low_faithfulness"
    )
    issue_without_plan = make_issue(keyword="Naming Convention", severity="low")

    rows = [(issue_with_plan, plan), (issue_without_plan, None)]

    with patch.object(routes, "_load_issues_with_plans", new=AsyncMock(return_value=rows)):
        resp = await client.get(f"/api/pr/{PR_ID}")

    assert resp.status_code == 200
    body = resp.json()
    assert len(body["issues"]) == 2

    first = body["issues"][0]
    assert first["id"] == str(issue_with_plan.id)
    assert first["keyword"] == "SQL Injection"
    assert first["plan"]["id"] == str(plan.id)
    assert first["plan"]["status"] == "completed"
    assert first["plan"]["card_content"] == {"explanation": "..."}
    assert first["plan"]["ragas_reason"] == "low_faithfulness"  # T12 — RAGAS 평가 실패 원인을 그대로 노출

    second = body["issues"][1]
    assert second["id"] == str(issue_without_plan.id)
    assert second["plan"] is None


@pytest.mark.asyncio
async def test_get_pr_exposes_curator_instruction_and_attempt_count(client, auth_override, session_override):
    """T16 — curriculum_plan.curator_instruction/attempt_count를 placeholder 없이 실제 값으로 노출한다."""
    issue_with_plan = make_issue(keyword="SQL Injection", severity="critical")
    plan = make_plan(
        issue_with_plan.id,
        status="completed",
        card_content={"explanation": "..."},
        curator_instruction={"focus": "파라미터 바인딩"},
        attempt_count=2,
    )

    with patch.object(routes, "_load_issues_with_plans", new=AsyncMock(return_value=[(issue_with_plan, plan)])):
        resp = await client.get(f"/api/pr/{PR_ID}")

    body = resp.json()
    plan_json = body["issues"][0]["plan"]
    assert plan_json["curator_instruction"] == {"focus": "파라미터 바인딩"}
    assert plan_json["attempt_count"] == 2


# ---------------------------------------------------------------------------
# POST /api/complete
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_post_complete_returns_200_with_id_and_completed_at(client, auth_override, session_override):
    plan_id = uuid.uuid4()
    completed_plan = make_plan(uuid.uuid4(), id=plan_id, status="completed", completed_at=NOW)

    with patch.object(routes, "_mark_plan_completed", new=AsyncMock(return_value=completed_plan)):
        resp = await client.post("/api/complete", json={"plan_id": str(plan_id)})

    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == str(plan_id)
    assert body["completed_at"] is not None


@pytest.mark.asyncio
async def test_post_complete_unknown_plan_returns_404(client, auth_override, session_override):
    with patch.object(routes, "_mark_plan_completed", new=AsyncMock(return_value=None)):
        resp = await client.post("/api/complete", json={"plan_id": str(uuid.uuid4())})

    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# _mark_plan_completed — 중복 완료 클릭 시에도 completed_at이 최초 1회만 기록됨 (T7/D11 idempotent)
# ---------------------------------------------------------------------------

class _FakeCompleteSession:
    def __init__(self, plan):
        self._plan = plan
        self.commit_count = 0

    async def get(self, _model, _plan_id):
        return self._plan

    async def commit(self):
        self.commit_count += 1

    async def refresh(self, _obj):
        pass


@pytest.mark.asyncio
async def test_complete_duplicate_click_is_idempotent():
    """이미 completed_at이 기록된 plan에 다시 호출해도 재커밋되지 않고 같은 값을 그대로 반환한다 (D11)."""
    plan_id = uuid.uuid4()
    plan = make_plan(uuid.uuid4(), id=plan_id, status="completed")
    session = _FakeCompleteSession(plan)

    first = await routes._mark_plan_completed(session, plan_id)
    assert first.completed_at is not None
    assert session.commit_count == 1

    second = await routes._mark_plan_completed(session, plan_id)
    assert second.completed_at == first.completed_at
    assert session.commit_count == 1  # 재커밋되지 않음 — idempotent


# ---------------------------------------------------------------------------
# _run_card_generation — 카드 생성·DB write 실패 시 plan을 'failed'로 기록 (T6 catch-all 안전망)
# ---------------------------------------------------------------------------

class _FakeCardSession:
    """`_run_card_generation`이 사용하는 session_factory()의 async context manager 더블.

    commit_exception을 지정하면 commit_fail_at번째 commit() 호출에서만 예외를 던져
    "결과 저장 commit은 실패했지만 그 이후의 'failed' 기록 commit은 성공한다"는
    DB 일시 장애 시나리오를 재현한다.
    """

    def __init__(self, plans_by_id, commit_exception=None, commit_fail_at=None, mistake_count=0, issue_history=()):
        self._plans = plans_by_id
        self.commit_count = 0
        self._commit_exception = commit_exception
        self._commit_fail_at = commit_fail_at
        self._mistake_count = mistake_count
        self._issue_history = list(issue_history)

    async def get(self, _model, plan_id):
        return self._plans.get(plan_id)

    async def execute(self, _stmt):
        """_count_user_mistakes()의 select(func.count())와 _build_developer_profile()의
        select(keyword, sub_category) 더블 — scalar_one()/all() 양쪽을 지원한다."""
        return SimpleNamespace(scalar_one=lambda: self._mistake_count, all=lambda: list(self._issue_history))

    async def commit(self):
        self.commit_count += 1
        if self._commit_exception is not None and (
            self._commit_fail_at is None or self.commit_count == self._commit_fail_at
        ):
            raise self._commit_exception

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _FakeEngine:
    async def dispose(self):
        pass


class _FakeAgentHarness:
    """AgentHarness 더블 (T17) — 생성 kwargs/run() 호출/__aexit__에 전달된 예외 타입을 기록한다.

    실제 AgentHarness.__aexit__처럼 예외를 삼키지 않는다(return False) — _generate_one이
    harness.run()의 예외를 async with 블록 안에서 잡지 않아야 __aexit__이 실제 exc_type을 받아
    agent_traces에 status='fail'로 기록할 수 있다 (§7-4). exit_exc_type으로 이를 검증한다.
    """

    last_instance: "_FakeAgentHarness | None" = None

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.run_calls: list[tuple] = []
        self.exit_exc_type = None
        type(self).last_instance = self

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        self.exit_exc_type = exc_type
        return False

    async def run(self, fn, *args, **kwargs):
        self.run_calls.append((fn, args, kwargs))
        return await fn(*args, **kwargs)


def _patch_card_generation_infra(session):
    fake_settings = SimpleNamespace(database_url="postgresql://fake")
    return (
        patch("shared.config.get_settings", return_value=fake_settings),
        patch("shared.db.create_engine_from_url", return_value=_FakeEngine()),
        patch("shared.db.create_session_factory", return_value=lambda: session),
        patch.object(routes, "PgvectorAdapter", return_value=AsyncMock()),
        patch.object(routes, "AgentHarness", _FakeAgentHarness, create=True),
    )


@pytest.mark.asyncio
async def test_run_card_generation_marks_plan_failed_on_generate_card_exception():
    """generate_card()가 예상치 못한 예외(Gemini API 오류 등)를 내면 plan이 'running'에 멈추지 않고
    'failed' + error_message로 기록된다 (T6 — build_card/fallback_card SILENT GAP에 대한 바깥쪽 안전망)."""
    plan_id = uuid.uuid4()
    issue = make_issue()
    plan = make_plan(issue.id, id=plan_id, status="pending")
    session = _FakeCardSession({plan_id: plan})

    p1, p2, p3, p4, p5 = _patch_card_generation_infra(session)
    with p1, p2, p3, p4, p5, patch.object(routes, "generate_card", new=AsyncMock(side_effect=Exception("Gemini API 오류: 429"))):
        await routes._run_card_generation([(plan_id, issue)])

    assert plan.status == "failed"
    assert plan.error_message == "Gemini API 오류: 429"


@pytest.mark.asyncio
async def test_run_card_generation_marks_plan_failed_on_db_write_exception():
    """카드 생성 자체는 성공했지만 결과를 저장하는 commit()이 실패해도(PostgreSQL 연결 끊김 등)
    plan을 'failed' + error_message로 기록한다 (T6 — DB write SILENT GAP)."""
    plan_id = uuid.uuid4()
    issue = make_issue()
    plan = make_plan(issue.id, id=plan_id, status="pending")
    generated = make_plan(issue.id, status="completed", card_content={"explanation": "..."})
    # 1번째 commit("running" 기록)은 성공, 2번째 commit(결과 저장)에서 연결이 끊기고,
    # 3번째 commit("failed" 기록)은 연결이 복구되어 성공하는 시나리오
    session = _FakeCardSession({plan_id: plan}, commit_exception=OSError("connection lost"), commit_fail_at=2)

    p1, p2, p3, p4, p5 = _patch_card_generation_infra(session)
    with p1, p2, p3, p4, p5, patch.object(routes, "generate_card", new=AsyncMock(return_value=generated)):
        await routes._run_card_generation([(plan_id, issue)])

    assert plan.status == "failed"
    assert plan.error_message == "connection lost"


@pytest.mark.asyncio
async def test_run_card_generation_passes_counted_mistake_count_to_generate_card():
    """동일 user_id+keyword로 발생한 과거 review_issue 누적 횟수(mistake_count, D18)를 집계해
    generate_card에 전달한다 — depth 결정이 항상 mistake_count=0으로 고정되는 누락을 방지."""
    plan_id = uuid.uuid4()
    issue = make_issue()
    plan = make_plan(issue.id, id=plan_id, status="pending")
    generated = make_plan(issue.id, status="completed", card_content={"explanation": "..."})
    session = _FakeCardSession({plan_id: plan}, mistake_count=3)

    p1, p2, p3, p4, p5 = _patch_card_generation_infra(session)
    with p1, p2, p3, p4, p5, patch.object(routes, "generate_card", new=AsyncMock(return_value=generated)) as generate_card_mock:
        await routes._run_card_generation([(plan_id, issue)])

    assert generate_card_mock.call_args.kwargs["mistake_count"] == 3


@pytest.mark.asyncio
async def test_run_card_generation_persists_ragas_reason_on_plan():
    """generate_card()가 반환한 ragas_reason을 pending plan에 그대로 반영한다 (T12)."""
    plan_id = uuid.uuid4()
    issue = make_issue()
    plan = make_plan(issue.id, id=plan_id, status="pending")
    generated = make_plan(
        issue.id, status="completed", card_content={"explanation": "..."}, ragas_reason="low_relevancy"
    )
    session = _FakeCardSession({plan_id: plan})

    p1, p2, p3, p4, p5 = _patch_card_generation_infra(session)
    with p1, p2, p3, p4, p5, patch.object(routes, "generate_card", new=AsyncMock(return_value=generated)):
        await routes._run_card_generation([(plan_id, issue)])

    assert plan.ragas_reason == "low_relevancy"


@pytest.mark.asyncio
async def test_run_card_generation_persists_curator_instruction_and_attempt_count_on_plan():
    """generate_card()가 반환한 curator_instruction/attempt_count를 pending plan에 그대로 반영한다 (T16)."""
    plan_id = uuid.uuid4()
    issue = make_issue()
    plan = make_plan(issue.id, id=plan_id, status="pending")
    generated = make_plan(
        issue.id,
        status="completed",
        card_content={"explanation": "..."},
        curator_instruction={"focus": "파라미터 바인딩"},
        attempt_count=2,
    )
    session = _FakeCardSession({plan_id: plan})

    p1, p2, p3, p4, p5 = _patch_card_generation_infra(session)
    with p1, p2, p3, p4, p5, patch.object(routes, "generate_card", new=AsyncMock(return_value=generated)):
        await routes._run_card_generation([(plan_id, issue)])

    assert plan.curator_instruction == {"focus": "파라미터 바인딩"}
    assert plan.attempt_count == 2


@pytest.mark.asyncio
async def test_run_card_generation_passes_developer_profile_to_generate_card():
    """이 개발자의 review_issue 이력에서 만든 DeveloperProfile(D22)을 generate_card에 전달한다 (T13) —
    최근 keyword 5개를 past_mistakes로, 2회 이상 반복된 sub_category를 weak_categories로 집계."""
    plan_id = uuid.uuid4()
    issue = make_issue()
    plan = make_plan(issue.id, id=plan_id, status="pending")
    generated = make_plan(issue.id, status="completed", card_content={"explanation": "..."})
    session = _FakeCardSession(
        {plan_id: plan},
        issue_history=[
            ("SQL Injection", "input validation"),
            ("SQL Injection", "input validation"),
            ("Hardcoded Secret", "authentication"),
        ],
    )

    p1, p2, p3, p4, p5 = _patch_card_generation_infra(session)
    with p1, p2, p3, p4, p5, patch.object(routes, "generate_card", new=AsyncMock(return_value=generated)) as generate_card_mock:
        await routes._run_card_generation([(plan_id, issue)])

    profile = generate_card_mock.call_args.kwargs["profile"]
    assert profile["past_mistakes"] == ["SQL Injection", "SQL Injection", "Hardcoded Secret"]
    assert profile["weak_categories"] == ["input validation"]


@pytest.mark.asyncio
async def test_run_card_generation_uses_empty_profile_when_issue_has_no_user():
    """issue.user_id가 None이면 DB 이력 조회 없이 빈 DeveloperProfile로 generate_card를 호출한다."""
    plan_id = uuid.uuid4()
    issue = make_issue(user_id=None)
    plan = make_plan(issue.id, id=plan_id, status="pending")
    generated = make_plan(issue.id, status="completed", card_content={"explanation": "..."})
    session = _FakeCardSession({plan_id: plan})

    p1, p2, p3, p4, p5 = _patch_card_generation_infra(session)
    with p1, p2, p3, p4, p5, patch.object(routes, "generate_card", new=AsyncMock(return_value=generated)) as generate_card_mock:
        await routes._run_card_generation([(plan_id, issue)])

    assert generate_card_mock.call_args.kwargs["profile"] == {"weak_categories": [], "past_mistakes": []}


# ---------------------------------------------------------------------------
# _run_card_generation — AgentHarness 래핑 (T17, GLOBAL_AGENT_RULE §7-2)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_card_generation_wraps_generate_card_in_agent_harness():
    """generate_card() 호출을 AgentHarness로 감싸 trace_id/agent_name/task_id/timeout을 전달하고
    (LangSmith trace + agent_traces 기록, T17), harness.run()을 통해 generate_card를 실행한다."""
    plan_id = uuid.uuid4()
    issue = make_issue()
    plan = make_plan(issue.id, id=plan_id, status="pending")
    generated = make_plan(issue.id, status="completed", card_content={"explanation": "..."})
    session = _FakeCardSession({plan_id: plan})

    p1, p2, p3, p4, p5 = _patch_card_generation_infra(session)
    with p1, p2, p3, p4, p5, patch.object(routes, "generate_card", new=AsyncMock(return_value=generated)) as generate_card_mock:
        await routes._run_card_generation([(plan_id, issue)])

    harness = _FakeAgentHarness.last_instance
    assert harness.kwargs["agent_name"] == "generate_card"
    assert harness.kwargs["task_id"] == str(plan_id)
    assert harness.kwargs["trace_id"].startswith(f"pr_{issue.pull_request_id}_generate_card_")
    assert harness.kwargs["db_session_factory"]() is session
    assert harness.kwargs["timeout"] == GEMINI_TIMEOUT_SECONDS * 6
    assert harness.run_calls[0][0] is generate_card_mock
    assert plan.status == "completed"
    assert plan.card_content == {"explanation": "..."}


@pytest.mark.asyncio
async def test_run_card_generation_lets_agent_harness_observe_timeout_and_marks_plan_failed():
    """generate_card()가 asyncio.TimeoutError를 내면 AgentHarness.__aexit__이 그 예외를 그대로
    전달받아(§7-4 — async with 블록 안에서 삼키지 않음) agent_traces에 status='fail'로 기록할 수 있고,
    plan도 'failed' + error_message로 남는다."""
    plan_id = uuid.uuid4()
    issue = make_issue()
    plan = make_plan(issue.id, id=plan_id, status="pending")
    session = _FakeCardSession({plan_id: plan})

    p1, p2, p3, p4, p5 = _patch_card_generation_infra(session)
    with p1, p2, p3, p4, p5, patch.object(
        routes, "generate_card", new=AsyncMock(side_effect=asyncio.TimeoutError("generate_card timed out"))
    ):
        await routes._run_card_generation([(plan_id, issue)])

    assert plan.status == "failed"
    assert plan.error_message == "generate_card timed out"
    assert _FakeAgentHarness.last_instance.exit_exc_type is asyncio.TimeoutError


# ---------------------------------------------------------------------------
# CORS — 프론트(Vite, http://localhost:5173)에서 m4(http://localhost:8005)로 직접
# 호출하는 구조 (FRONTEND_SPEC Section 0의 m4Api). 별도 포트 간 호출이라 브라우저가
# preflight(OPTIONS)를 보내며, Access-Control-Allow-Origin이 없으면 CORS 에러로 막힌다.
# ---------------------------------------------------------------------------


async def test_cors_preflight_allows_vite_dev_origin(client):
    response = await client.options(
        "/api/learn",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "authorization,content-type",
        },
    )

    assert response.headers.get("access-control-allow-origin") == "http://localhost:5173"
