"""run_pipeline — URL 배치 파이프라인 오케스트레이터 (PRD §14.1).

asyncio.gather + Semaphore(GEMINI_RPM_LIMIT)로 병렬 URL 처리.
PipelineTask 프로토콜을 따르는 구현체를 주입받아 실행한다.
"""
import asyncio
from typing import Sequence

from app.usecases.interfaces.pipeline_task import PipelineTask

# Gemini 2.5 Flash RPM 한도 — 동시 실행 상한
GEMINI_RPM_LIMIT: int = 5


async def run_pipeline_batch(
    session_id: str,
    url_doc_pairs: Sequence[tuple[str, str]],
    task: PipelineTask,
    semaphore: asyncio.Semaphore | None = None,
) -> list[Exception | None]:
    """URL 목록을 Semaphore로 제한된 병렬도로 처리한다.

    Args:
        session_id:    파이프라인 트리거 단위 식별자.
        url_doc_pairs: [(url, doc_id), ...] 처리 대상 목록.
        task:          PipelineTask 구현체.
        semaphore:     None이면 GEMINI_RPM_LIMIT 기반으로 생성.

    Returns:
        각 URL 처리 결과 리스트. 성공 시 None, 실패 시 Exception 인스턴스.
    """
    if semaphore is None:
        semaphore = asyncio.Semaphore(GEMINI_RPM_LIMIT)

    async def _bounded(url: str, doc_id: str) -> None:
        async with semaphore:
            await task.execute(session_id, doc_id, url)

    results: list[Exception | None] = await asyncio.gather(
        *[_bounded(url, doc_id) for url, doc_id in url_doc_pairs],
        return_exceptions=True,
    )
    return results
