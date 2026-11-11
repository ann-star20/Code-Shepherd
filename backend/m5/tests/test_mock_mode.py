from unittest.mock import AsyncMock

import httpx

from app import collect_videos, graph_query, main, neo4j_client, video_store


async def test_offline_demo_graph_and_recommendations_never_connect(monkeypatch):
    monkeypatch.setenv("M5_MOCK_MODE", "true")
    monkeypatch.delenv("YOUTUBE_API_KEY", raising=False)

    def forbidden(*args, **kwargs):
        raise AssertionError("Mock mode must not connect to external services")

    monkeypatch.setattr(neo4j_client, "get_driver", forbidden)
    monkeypatch.setattr(graph_query, "get_driver", forbidden)
    monkeypatch.setattr(video_store, "get_driver", forbidden)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", forbidden)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=main.app), base_url="http://test"
    ) as client:
        graph = (await client.get("/graph/overview")).json()
        assert len(graph["concepts"]) == 16
        for entry in graph["concepts"]:
            name = entry["concept_name"]
            detail = await client.get("/graph/concept", params={"keyword": name})
            assert detail.status_code == 200
            response = await client.post("/youtube/ranked", json={"concept_name": name})
            videos = response.json()["videos"]
            assert response.status_code == 200
            assert len(videos) == 5
            assert all(v["is_mock"] and v["title"].startswith("[MOCK]") for v in videos)
            assert all(
                v["url"].startswith("https://www.youtube.com/results?search_query=")
                for v in videos
            )
        assert (
            await client.get("/graph/mechanism/parameterized_query")
        ).status_code == 200
        assert (
            await client.post("/youtube/ranked", json={"concept_name": "missing"})
        ).status_code == 404
        contextual = await client.post(
            "/youtube/ranked",
            json={
                "concept_name": "SQLi",
                "mechanism_name": "parameterized_query",
                "code_lang": "python",
                "code_framework": "django",
            },
        )
        assert "django" in contextual.json()["videos"][0]["query_used"]


async def test_mock_collector_never_writes_or_calls_youtube(monkeypatch):
    monkeypatch.setenv("M5_MOCK_MODE", "true")

    def forbidden(*args, **kwargs):
        raise AssertionError("Mock collector must not open a database")

    monkeypatch.setattr(collect_videos, "Neo4jVideoStore", forbidden)
    assert await collect_videos.run_once() == {
        "status": "mock_mode_read_only",
        "searches": 0,
    }


async def test_aura_username_supported_with_legacy_precedence(monkeypatch):
    await neo4j_client.close_driver()
    monkeypatch.setenv("NEO4J_USERNAME", "aura-user")
    monkeypatch.delenv("NEO4J_USER", raising=False)
    fake = AsyncMock()
    calls = []

    def factory(uri, **kwargs):
        calls.append(kwargs["auth"][0])
        return fake

    monkeypatch.setattr(neo4j_client.AsyncGraphDatabase, "driver", factory)
    neo4j_client.get_driver()
    await neo4j_client.close_driver()
    monkeypatch.setenv("NEO4J_USER", "legacy-user")
    neo4j_client.get_driver()
    await neo4j_client.close_driver()
    assert calls == ["aura-user", "legacy-user"]
