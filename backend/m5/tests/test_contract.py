"""HTTP contracts: no live YouTube calls, controlled database failure."""

from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient
from neo4j.exceptions import ServiceUnavailable

from app import main
from app.graph_query import ConceptGraphResponse


@pytest.fixture
async def client():
    async with AsyncClient(
        transport=ASGITransport(app=main.app, raise_app_exceptions=False),
        base_url="http://test",
    ) as ac:
        yield ac


async def test_health_without_database(client):
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json()["service"] == "m5-graph-youtube"


async def test_extract_contract(client):
    response = await client.post(
        "/extract", json={"task_id": "t1", "doc_id": "d1", "source": "upload"}
    )
    assert response.status_code == 200
    assert response.json()["status"] == "accepted"


async def test_recommend_reads_stored_candidates_without_api_key(client, monkeypatch):
    monkeypatch.delenv("YOUTUBE_API_KEY", raising=False)
    monkeypatch.setattr(
        main,
        "fetch_concept",
        AsyncMock(return_value=ConceptGraphResponse(concept_name="SQL_Injection")),
    )

    async def candidates(concept_name, query):
        return [
            {
                "video_id": "v1",
                "title": "Stored lesson",
                "url": "https://www.youtube.com/watch?v=v1",
                "thumbnail": None,
                "channel_title": "Teacher",
            }
        ]

    monkeypatch.setattr(main, "fetch_candidates", candidates, raising=False)

    async def forbidden(*args, **kwargs):
        raise AssertionError("Serving must never search YouTube")

    monkeypatch.setattr(main, "search_one", forbidden, raising=False)
    response = await client.post(
        "/youtube/ranked", json={"concept_name": "SQL_Injection"}
    )
    assert response.status_code == 200
    assert [v["title"] for v in response.json()["videos"]] == ["Stored lesson"]


async def test_uncollected_concept_returns_empty_without_live_fallback(
    client, monkeypatch
):
    monkeypatch.delenv("YOUTUBE_API_KEY", raising=False)
    monkeypatch.setattr(
        main,
        "fetch_concept",
        AsyncMock(return_value=ConceptGraphResponse(concept_name="SQL_Injection")),
    )
    monkeypatch.setattr(
        main, "fetch_candidates", AsyncMock(return_value=[]), raising=False
    )
    response = await client.post(
        "/youtube/ranked", json={"concept_name": "SQL_Injection"}
    )
    assert response.status_code == 200
    assert response.json()["videos"] == []


@pytest.mark.parametrize(
    "path",
    [
        "/graph/overview",
        "/graph/concept?keyword=x",
        "/graph/mechanism/x",
        "/youtube/ranked",
    ],
)
async def test_database_unavailable_is_503(client, monkeypatch, path):
    monkeypatch.setenv("YOUTUBE_API_KEY", "unused")
    for name in ("fetch_concept", "fetch_overview", "fetch_mechanism"):
        monkeypatch.setattr(
            main,
            name,
            AsyncMock(side_effect=ServiceUnavailable("private connection details")),
        )
    response = (
        await client.post(path, json={"concept_name": "x"})
        if path.startswith("/youtube")
        else await client.get(path)
    )
    assert response.status_code == 503
    assert "private connection" not in response.text


async def test_unknown_concept_is_404(client, monkeypatch):
    monkeypatch.delenv("YOUTUBE_API_KEY", raising=False)
    monkeypatch.setattr(main, "fetch_concept", AsyncMock(return_value=None))
    response = await client.post("/youtube/ranked", json={"concept_name": "missing"})
    assert response.status_code == 404


async def test_real_missing_database_does_not_prevent_lifespan_or_health(
    client, monkeypatch
):
    from app.neo4j_client import close_driver

    monkeypatch.setenv("NEO4J_URI", "bolt://127.0.0.1:1")
    monkeypatch.delenv("YOUTUBE_API_KEY", raising=False)
    await close_driver()
    async with main.lifespan(main.app):
        assert (await client.get("/health")).status_code == 200
        response = await client.post(
            "/youtube/ranked", json={"concept_name": "SQL_Injection"}
        )
        assert response.status_code == 503
        assert "127.0.0.1" not in response.text
