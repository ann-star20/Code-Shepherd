"""외부 문서 수집 요청/응답 스키마."""

from typing import Literal

from pydantic import BaseModel, HttpUrl


class IngestRequest(BaseModel):
    url: HttpUrl
    title: str | None = None
    tags: list[str] = []


class IngestStatus(BaseModel):
    task_id: str
    status: Literal["pending", "running", "success", "failed"]
    message: str | None = None
    error: str | None = None
