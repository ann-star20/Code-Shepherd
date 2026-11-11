"""YouTube API access for the background collector only."""

from __future__ import annotations

import os

import httpx

from app.video_models import VideoCandidate

_YOUTUBE_SEARCH_URL = "https://www.googleapis.com/youtube/v3/search"


async def search_candidates(query: str) -> list[VideoCandidate]:
    api_key = os.getenv("YOUTUBE_API_KEY")
    if not api_key:
        raise ValueError("YOUTUBE_API_KEY is required for collection")
    params = {
        "key": api_key,
        "q": query,
        "part": "snippet",
        "type": "video",
        "maxResults": 50,
        "relevanceLanguage": "ko",
    }
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(_YOUTUBE_SEARCH_URL, params=params)
        response.raise_for_status()
        data = response.json()
    videos: list[VideoCandidate] = []
    seen: set[str] = set()
    for item in data.get("items", []):
        video_id = item["id"]["videoId"]
        if video_id in seen:
            continue
        seen.add(video_id)
        snippet = item["snippet"]
        thumbnails = snippet.get("thumbnails", {})
        videos.append(
            {
                "video_id": video_id,
                "title": snippet.get("title", ""),
                "url": f"https://www.youtube.com/watch?v={video_id}",
                "thumbnail": thumbnails.get("medium", {}).get("url")
                or thumbnails.get("default", {}).get("url"),
                "channel_title": snippet.get("channelTitle"),
            }
        )
    return videos


async def fetch_video_metadata(video_ids: list[str]) -> list[VideoCandidate]:
    """Refresh up to 50 videos; absent/private videos are omitted."""
    if not 1 <= len(video_ids) <= 50:
        raise ValueError("videos.list requires 1..50 IDs")
    api_key = os.getenv("YOUTUBE_API_KEY")
    if not api_key:
        raise ValueError("YOUTUBE_API_KEY is required for collection")
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(
            "https://www.googleapis.com/youtube/v3/videos",
            params={
                "key": api_key,
                "id": ",".join(video_ids),
                "part": "snippet,status",
            },
        )
        response.raise_for_status()
        data = response.json()
    videos: list[VideoCandidate] = []
    for item in data.get("items", []):
        if item.get("status", {}).get("privacyStatus") != "public":
            continue
        video_id = item["id"]
        snippet = item["snippet"]
        thumbnails = snippet.get("thumbnails", {})
        videos.append(
            {
                "video_id": video_id,
                "title": snippet.get("title", ""),
                "url": f"https://www.youtube.com/watch?v={video_id}",
                "thumbnail": thumbnails.get("medium", {}).get("url")
                or thumbnails.get("default", {}).get("url"),
                "channel_title": snippet.get("channelTitle"),
            }
        )
    return videos
