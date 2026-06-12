"""G6: PipelineTaskImpl — Crawler → Extractor → StagingDraft 단일 파이프라인."""

import aiohttp
import asyncpg

from app.infrastructure.crawler.http_crawler import fetch, chunk
from app.infrastructure.llm.interface import ILLMClient
from app.usecases.extract_concepts import extract_concepts
from app.usecases.write_staging_draft import write_staging_draft


class PipelineTaskImpl:
    """PipelineTask Protocol 구현체."""

    def __init__(self, llm: ILLMClient, pool: asyncpg.Pool) -> None:
        self._llm = llm
        self._pool = pool

    async def execute(self, session_id: str, doc_id: str, url: str) -> None:
        async with aiohttp.ClientSession() as session:
            crawl_result = await fetch(url, session)
        print(
            f"크롤링 완료: {len(crawl_result.content)}자, {len(crawl_result.links)}개 링크"
        )
        chunks = chunk(crawl_result.content)
        concepts = await extract_concepts(doc_id, chunks, self._llm)
        print(f"chunks 완료: {len(chunks)}자")
        print(f"chunks 추출 완료: {chunks}")
        print(f"concepts 추출 완료: {len(concepts)}개")
        print(concepts)

        async with self._pool.acquire() as conn:
            await write_staging_draft(session_id, doc_id, concepts, conn)
