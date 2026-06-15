from __future__ import annotations

from pydantic import BaseModel


class RankedRecommendRequest(BaseModel):
    concept_name: str
    mechanism_name: str | None = None
    code_id: str | None = None
    code_lang: str | None = None
    code_framework: str | None = None


class VideoResult(BaseModel):
    rank: int
    recommendation_type: str
    query_used: str
    title: str
    url: str
    thumbnail: str | None = None
    channel_title: str | None = None


class RankedRecommendResponse(BaseModel):
    concept_name: str
    videos: list[VideoResult]
