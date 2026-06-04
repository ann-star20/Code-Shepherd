"""PipelineTask Protocol — BackgroundTasks/Celery 교체 가능 추상 계약 (PRD §14.1)."""
from typing import Protocol, runtime_checkable


@runtime_checkable
class PipelineTask(Protocol):
    async def execute(
        self,
        session_id: str,
        doc_id: str,
        url: str,
    ) -> None:
        """단일 URL 파이프라인 실행 (크롤→추출→스테이징 저장)."""
        ...
