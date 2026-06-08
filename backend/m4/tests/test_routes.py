"""계약 테스트 — /api/learn, /api/pr/{scan_id}, /api/complete (T2 라우트 + T4 JWT 인증, Mock 기반)."""

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
    plan = make_plan(issue_with_plan.id, status="completed", card_content={"explanation": "..."})
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

    second = body["issues"][1]
    assert second["id"] == str(issue_without_plan.id)
    assert second["plan"] is None


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

    def __init__(self, plans_by_id, commit_exception=None, commit_fail_at=None):
        self._plans = plans_by_id
        self.commit_count = 0
        self._commit_exception = commit_exception
        self._commit_fail_at = commit_fail_at

    async def get(self, _model, plan_id):
        return self._plans.get(plan_id)

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


def _patch_card_generation_infra(session):
    fake_settings = SimpleNamespace(database_url="postgresql://fake")
    return (
        patch("shared.config.get_settings", return_value=fake_settings),
        patch("shared.db.create_engine_from_url", return_value=_FakeEngine()),
        patch("shared.db.create_session_factory", return_value=lambda: session),
        patch.object(routes, "PgvectorAdapter", return_value=AsyncMock()),
    )


@pytest.mark.asyncio
async def test_run_card_generation_marks_plan_failed_on_generate_card_exception():
    """generate_card()가 예상치 못한 예외(Gemini API 오류 등)를 내면 plan이 'running'에 멈추지 않고
    'failed' + error_message로 기록된다 (T6 — build_card/fallback_card SILENT GAP에 대한 바깥쪽 안전망)."""
    plan_id = uuid.uuid4()
    issue = make_issue()
    plan = make_plan(issue.id, id=plan_id, status="pending")
    session = _FakeCardSession({plan_id: plan})

    p1, p2, p3, p4 = _patch_card_generation_infra(session)
    with p1, p2, p3, p4, patch.object(routes, "generate_card", new=AsyncMock(side_effect=Exception("Gemini API 오류: 429"))):
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

    p1, p2, p3, p4 = _patch_card_generation_infra(session)
    with p1, p2, p3, p4, patch.object(routes, "generate_card", new=AsyncMock(return_value=generated)):
        await routes._run_card_generation([(plan_id, issue)])

    assert plan.status == "failed"
    assert plan.error_message == "connection lost"
