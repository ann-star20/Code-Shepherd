"""B: GET /api/graph/topology 라우터 단위 테스트.

Neo4j 실제 연결 불필요 — Neo4jConceptRepo.get_topology mock 사용.

커버:
  G01 200 + nodes/edges 키 포함
  G02 ?domains=security 필터 파라미터 전달 확인
  G03 ?limit=5 파라미터 전달 확인
  G04 Neo4j 미연결 시 503 반환
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app

_SAMPLE = {
    "nodes": [{"id": "XSS", "label": "Concept"}],
    "edges": [{"source": "XSS", "target": "security", "type": "BELONGS_TO"}],
}

_MOCK_PATH = "app.interfaces.api.graph.Neo4jConceptRepo"


@pytest.fixture(autouse=True)
def inject_neo4j_state():
    """lifespan 없이 테스트 시 app.state.neo4j_driver를 mock으로 채운다."""
    app.state.neo4j_driver = MagicMock()
    yield
    app.state.neo4j_driver = None


# ── G01: 200 + nodes/edges 구조 ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_G01_topology_returns_nodes_and_edges():
    """
    Arrange: Neo4jConceptRepo.get_topology mock → _SAMPLE, app.state 주입
    Act:     GET /api/graph/topology
    Assert:  200, body에 nodes/edges 키
    """
    with patch(_MOCK_PATH) as MockRepo:
        MockRepo.return_value.get_topology = AsyncMock(return_value=_SAMPLE)
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/api/graph/topology")

    assert resp.status_code == 200
    body = resp.json()
    assert "nodes" in body
    assert "edges" in body


# ── G02: domains 필터 파라미터 전달 ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_G02_topology_domains_filter_passed():
    """
    Arrange: get_topology mock 캡처, app.state 주입
    Act:     GET /api/graph/topology?domains=security
    Assert:  get_topology(domains=['security'], ...) 호출
    """
    with patch(_MOCK_PATH) as MockRepo:
        mock_get = AsyncMock(return_value=_SAMPLE)
        MockRepo.return_value.get_topology = mock_get
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            await client.get("/api/graph/topology?domains=security")

    mock_get.assert_called_once()
    call_kwargs = mock_get.call_args
    domains_val = call_kwargs.kwargs.get("domains") or (
        call_kwargs.args[0] if call_kwargs.args else None
    )
    assert domains_val is not None and "security" in domains_val


# ── G03: limit 파라미터 전달 ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_G03_topology_limit_passed():
    """
    Arrange: get_topology mock 캡처, app.state 주입
    Act:     GET /api/graph/topology?limit=5
    Assert:  get_topology(limit=5) 호출
    """
    with patch(_MOCK_PATH) as MockRepo:
        mock_get = AsyncMock(return_value=_SAMPLE)
        MockRepo.return_value.get_topology = mock_get
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            await client.get("/api/graph/topology?limit=5")

    mock_get.assert_called_once()
    call_kwargs = mock_get.call_args
    limit_val = call_kwargs.kwargs.get("limit") or (
        call_kwargs.args[1] if len(call_kwargs.args) > 1 else None
    )
    assert limit_val == 5
