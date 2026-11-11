import httpx
import pytest

from app import youtube_client


async def test_batch_search_requests_50_and_deduplicates_ids(monkeypatch):
    monkeypatch.setenv("YOUTUBE_API_KEY", "test-key")
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "items": [
                    {
                        "id": {"videoId": "a"},
                        "snippet": {
                            "title": "A",
                            "channelTitle": "T",
                            "thumbnails": {},
                        },
                    },
                    {
                        "id": {"videoId": "a"},
                        "snippet": {"title": "duplicate", "thumbnails": {}},
                    },
                    {
                        "id": {"videoId": "b"},
                        "snippet": {
                            "title": "B",
                            "thumbnails": {
                                "default": {"url": "https://example.test/b.jpg"}
                            },
                        },
                    },
                ]
            },
        )

    original = httpx.AsyncClient
    monkeypatch.setattr(
        youtube_client.httpx,
        "AsyncClient",
        lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs),
    )
    videos = await youtube_client.search_candidates("SQL Injection")
    assert [v["video_id"] for v in videos] == ["a", "b"]
    assert requests[0].url.params["maxResults"] == "50"
    assert videos[1]["thumbnail"] == "https://example.test/b.jpg"


async def test_missing_key_fails_before_network(monkeypatch):
    monkeypatch.delenv("YOUTUBE_API_KEY", raising=False)
    with pytest.raises(ValueError):
        await youtube_client.search_candidates("test")


async def test_metadata_refresh_excludes_private_and_missing_videos(monkeypatch):
    monkeypatch.setenv("YOUTUBE_API_KEY", "test-key")

    def handler(request):
        assert request.url.path.endswith("/videos")
        assert request.url.params["id"] == "a,b,deleted"
        return httpx.Response(
            200,
            json={
                "items": [
                    {
                        "id": "a",
                        "snippet": {"title": "Updated", "thumbnails": {}},
                        "status": {"privacyStatus": "public"},
                    },
                    {
                        "id": "b",
                        "snippet": {"title": "Private", "thumbnails": {}},
                        "status": {"privacyStatus": "private"},
                    },
                ]
            },
        )

    original = httpx.AsyncClient
    monkeypatch.setattr(
        youtube_client.httpx,
        "AsyncClient",
        lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs),
    )
    videos = await youtube_client.fetch_video_metadata(["a", "b", "deleted"])
    assert [v["video_id"] for v in videos] == ["a"]
    assert videos[0]["title"] == "Updated"
