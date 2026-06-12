"""
test_insights.py — FastAPI 엔드포인트 테스트

Task 6: POST /scan + Insights API 3종 + PATCH /issues/{id}/dismiss

테스트 목표:
    1. POST /scan → 202 Accepted (BackgroundTasks 비동기 접수)
    2. GET /insights/developer/{id} → 200 + "developer_id" 키 포함
    3. GET /insights/team → 200 + "top_issues" 키 포함
    4. GET /insights/trends → 200 + "trends" 키 포함
    5. PATCH /issues/{id}/dismiss → 200 + is_false_positive=True

Mock 전략:
    - run_dev2: LangGraph 파이프라인 스킵 (scan 접수 검증에 불필요)
    - AsyncSessionLocal: PostgreSQL 연결 스킵 (insights/dismiss DB 쿼리)

httpx 사용법 (httpx 0.20+ / 0.27.0):
    - app=app 직접 전달 방식은 0.20에서 deprecated → ASGITransport 사용
    - ASGITransport: 실제 HTTP 소켓 없이 ASGI 앱을 in-process로 호출
    - base_url="http://test": 가짜 베이스 주소 (실제 접속 안 함)

CLAUDE.md §13: Mock 기반 단위 테스트 (실제 DB/LLM 없이 통과)
"""

import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import patch, AsyncMock, MagicMock

from dev2.main import app


# ── DB Mock 헬퍼 ──────────────────────────────────────────────────────────────

def _mock_db_ctx(rows: list[dict] | None = None):
    """
    AsyncSessionLocal() → async with 패턴을 Mock으로 대체한다.

    사용법:
        with patch("dev2.api.insights.AsyncSessionLocal", return_value=_mock_db_ctx()):
            ...

    AsyncSessionLocal()가 반환하는 컨텍스트 매니저를 모사:
        async with AsyncSessionLocal() as s:   # s = mock_session
            await s.execute(...)               # mock_result 반환
            r.mappings().all()                 # rows 반환

    Args:
        rows: 쿼리 결과로 반환할 dict 목록. None이면 빈 리스트.

    Returns:
        AsyncMock — __aenter__/__aexit__ 지원하는 컨텍스트 매니저 Mock
    """
    rows = rows or []

    # SQLAlchemy 결과 객체 모사 (r.mappings().all() → rows)
    mock_result = MagicMock()
    mock_result.mappings.return_value.all.return_value = rows

    # 세션 객체 모사 (await s.execute(...) → mock_result)
    mock_session = AsyncMock()
    mock_session.execute.return_value = mock_result

    # async with 컨텍스트 매니저 모사 (as s → mock_session)
    mock_cm = AsyncMock()
    mock_cm.__aenter__.return_value = mock_session
    mock_cm.__aexit__.return_value = False  # 예외 전파 허용

    return mock_cm


# ── 테스트 1: POST /scan → 202 Accepted ───────────────────────────────────────

@pytest.mark.asyncio
async def test_scan_accepted():
    """
    POST /scan이 202 Accepted를 반환하는지 확인.

    흐름:
        클라이언트 → POST /scan → trigger_scan() → BackgroundTasks에 run_dev2 등록
        → 202 + {"status": "accepted", "task_id": ...} 즉시 반환
        → run_dev2는 응답 전송 후 background에서 실행 (Mock이므로 즉시 완료)

    Mock:
        run_dev2 — LangGraph 파이프라인 전체 스킵.
        "patch where it's used" 원칙: dev2.api.scan.run_dev2 (임포트된 위치)
    """
    with patch("dev2.api.scan.run_dev2", new_callable=AsyncMock, return_value=[]):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            r = await client.post("/scan", json={
                "task_id": "uuid-001",
                "pr_id": "1",
                "pr_diff": "+++ b/a.py\n+query = sql + user",
                "developer": {
                    "id": "dev-001",
                    "skill_level": "junior",
                    "tech_stack": ["python"]
                }
            })

    assert r.status_code == 202
    body = r.json()
    assert body["status"] == "accepted"
    assert body["task_id"] == "uuid-001"


# ── 테스트 2: GET /insights/developer/{id} → 200 ──────────────────────────────

@pytest.mark.asyncio
async def test_developer_insights():
    """
    GET /insights/developer/{id}가 200과 developer_id 키를 반환하는지 확인.

    Mock:
        AsyncSessionLocal — PostgreSQL 연결 스킵.
        빈 rows 반환 → {"developer_id": "dev-001", "issues": []}
    """
    # lazy import 패턴: dev2.api.insights 내부에서 "from dev2.db import AsyncSessionLocal"
    # → patch 대상은 "dev2.db.AsyncSessionLocal" (임포트 원본 위치)
    with patch("dev2.db.AsyncSessionLocal", return_value=_mock_db_ctx()):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            r = await client.get("/insights/developer/dev-001")

    assert r.status_code == 200
    body = r.json()
    assert "developer_id" in body
    assert body["developer_id"] == "dev-001"


# ── 테스트 3: GET /insights/team → 200 ────────────────────────────────────────

@pytest.mark.asyncio
async def test_team_insights():
    """
    GET /insights/team이 200과 top_issues 키를 반환하는지 확인.

    Mock:
        AsyncSessionLocal — 이번 달 Top 5 이슈 집계 쿼리 스킵.
    """
    with patch("dev2.db.AsyncSessionLocal", return_value=_mock_db_ctx()):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            r = await client.get("/insights/team")

    assert r.status_code == 200
    assert "top_issues" in r.json()


# ── 테스트 4: GET /insights/trends → 200 ──────────────────────────────────────

@pytest.mark.asyncio
async def test_trends():
    """
    GET /insights/trends가 200과 trends 키를 반환하는지 확인.

    Mock:
        AsyncSessionLocal — 주간 Critical 추이 집계 쿼리 스킵.
    """
    with patch("dev2.db.AsyncSessionLocal", return_value=_mock_db_ctx()):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            r = await client.get("/insights/trends")

    assert r.status_code == 200
    assert "trends" in r.json()


# ── 테스트 5: PATCH /issues/{id}/dismiss → 200 ───────────────────────────────

@pytest.mark.asyncio
async def test_dismiss_issue():
    """
    PATCH /issues/{id}/dismiss가 200과 is_false_positive=True를 반환하는지 확인.

    흐름:
        클라이언트 → PATCH /issues/1/dismiss → dismiss_issue(1)
        → UPDATE scan_issues SET is_false_positive=true WHERE id=1
        → {"issue_id": 1, "is_false_positive": True}

    Mock:
        dev2.db.AsyncSessionLocal — lazy import 원본 위치에서 패치.
        issues.py가 함수 내부에서 `from dev2.db import AsyncSessionLocal`을 하므로
        "dev2.db.AsyncSessionLocal"을 패치하면 전체 적용된다.
    """
    with patch("dev2.db.AsyncSessionLocal", return_value=_mock_db_ctx()):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            r = await client.patch("/issues/1/dismiss")

    assert r.status_code == 200
    body = r.json()
    assert body["is_false_positive"] is True
    assert body["issue_id"] == 1


# ── 예외 처리 경로 테스트 (커버리지 보완) ─────────────────────────────────────

@pytest.mark.asyncio
async def test_developer_insights_db_error():
    """DB 오류 시 빈 issues 반환 (예외 삼키지 않음)."""
    with patch("dev2.db.AsyncSessionLocal", side_effect=Exception("DB down")):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            r = await client.get("/insights/developer/dev-001")
    assert r.status_code == 200
    assert r.json()["issues"] == []


@pytest.mark.asyncio
async def test_team_insights_db_error():
    """DB 오류 시 빈 top_issues 반환."""
    with patch("dev2.db.AsyncSessionLocal", side_effect=Exception("DB down")):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            r = await client.get("/insights/team")
    assert r.status_code == 200
    assert r.json()["top_issues"] == []


@pytest.mark.asyncio
async def test_trends_db_error():
    """DB 오류 시 빈 trends 반환."""
    with patch("dev2.db.AsyncSessionLocal", side_effect=Exception("DB down")):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            r = await client.get("/insights/trends")
    assert r.status_code == 200
    assert r.json()["trends"] == []
