from __future__ import annotations

import os

import httpx

_YOUTUBE_SEARCH_URL = "https://www.googleapis.com/youtube/v3/search"


async def search_one(query: str) -> dict | None:
    """YouTube Data API v3에서 쿼리 최상위 결과 1개를 반환한다.

    YOUTUBE_API_KEY 환경변수가 없으면 None을 반환한다.
    """
    api_key = os.getenv("YOUTUBE_API_KEY")
    if not api_key:
        return None

    params = {
        "key": api_key,
        "q": query,
        "part": "snippet",
        "type": "video",
        "maxResults": 1,
        "relevanceLanguage": "ko",
    }

    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(_YOUTUBE_SEARCH_URL, params=params)
        resp.raise_for_status()
        data = resp.json()

    items = data.get("items", [])
    if not items:
        return None

    item = items[0]
    video_id = item["id"]["videoId"]
    snippet = item["snippet"]
    thumbnail = (
        snippet.get("thumbnails", {}).get("medium", {}).get("url")
        or snippet.get("thumbnails", {}).get("default", {}).get("url")
    )

    return {
        "title": snippet.get("title", ""),
        "url": f"https://www.youtube.com/watch?v={video_id}",
        "thumbnail": thumbnail,
        "channel_title": snippet.get("channelTitle"),
    }
