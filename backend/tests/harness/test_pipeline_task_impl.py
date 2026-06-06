"""G6: PipelineTaskImpl 통합 테스트 — domains: list[str] 스키마."""

import uuid
from unittest.mock import patch

import aiohttp
import pytest

from app.domain.models import ConceptExtractionSchema
from app.infrastructure.llm.interface import ILLMClient
from app.usecases.interfaces.pipeline_task import PipelineTask
from app.usecases.pipeline_task_impl import PipelineTaskImpl


class _FakeResp:
    def __init__(self, html: str):
        self.status = 200
        self.headers = {}
        self._html = html

    async def text(self):
        return self._html

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass


class _FakeSession:
    def __init__(self, html: str):
        self._html = html

    def get(self, url, **kwargs):
        return _FakeResp(self._html)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass


class _ErrorSession:
    def get(self, url, **kwargs):
        class _Err:
            async def __aenter__(self_):
                raise aiohttp.ClientError("network error")
            async def __aexit__(self_, *args):
                pass
        return _Err()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass


_XSS = dict(
    concept_name="XSS",
    domains=["security"],
    severity="HIGH",
    description_ko="크로스 사이트 스크립팅",
)


class _MockLLM(ILLMClient):
    async def extract_concepts(self, text_chunk, doc_id, metadata):
        return [ConceptExtractionSchema(**_XSS)]

    def is_tracing_enabled(self):
        return False


async def _insert_doc(conn, doc_id: str) -> None:
    await conn.execute(
        "INSERT INTO documents (doc_id, source_prefix, original_url, content_hash) "
        "VALUES ($1,'EXT','https://example.com/pipeline-impl-test','abcd1234') "
        "ON CONFLICT DO NOTHING",
        doc_id,
    )


async def _cleanup(conn, session_id: str, doc_id: str) -> None:
    await conn.execute("DELETE FROM staging_concepts WHERE session_id=$1::uuid", session_id)
    await conn.execute("DELETE FROM documents WHERE doc_id=$1", doc_id)


def test_impl_protocol():
    impl = PipelineTaskImpl(llm=_MockLLM(), pool=None)  # type: ignore[arg-type]
    assert isinstance(impl, PipelineTask)


@pytest.mark.anyio
async def test_impl_writes_draft(asyncpg_pool):
    """execute() 성공 시 staging_concepts에 DRAFT 행 ≥ 1."""
    session_id = str(uuid.uuid4())
    doc_id = f"EXT_impl_{uuid.uuid4().hex[:8]}"

    async with asyncpg_pool.acquire() as conn:
        await _insert_doc(conn, doc_id)

    try:
        impl = PipelineTaskImpl(llm=_MockLLM(), pool=asyncpg_pool)
        with patch("aiohttp.ClientSession", return_value=_FakeSession("<p>Hello</p>")):
            await impl.execute(session_id, doc_id, "https://example.com/")

        async with asyncpg_pool.acquire() as conn:
            count = await conn.fetchval(
                "SELECT count(*) FROM staging_concepts "
                "WHERE session_id=$1::uuid AND state='DRAFT'",
                session_id,
            )
        assert count >= 1
    finally:
        async with asyncpg_pool.acquire() as conn:
            await _cleanup(conn, session_id, doc_id)


@pytest.mark.anyio
async def test_impl_crawl_error(asyncpg_pool):
    """fetch → ClientError 시 staging 행 0, 예외 전파."""
    session_id = str(uuid.uuid4())
    doc_id = f"EXT_impl_{uuid.uuid4().hex[:8]}"

    async with asyncpg_pool.acquire() as conn:
        await _insert_doc(conn, doc_id)

    try:
        impl = PipelineTaskImpl(llm=_MockLLM(), pool=asyncpg_pool)
        with pytest.raises(aiohttp.ClientError):
            with patch("aiohttp.ClientSession", return_value=_ErrorSession()):
                await impl.execute(session_id, doc_id, "https://example.com/")

        async with asyncpg_pool.acquire() as conn:
            count = await conn.fetchval(
                "SELECT count(*) FROM staging_concepts WHERE session_id=$1::uuid",
                session_id,
            )
        assert count == 0
    finally:
        async with asyncpg_pool.acquire() as conn:
            await _cleanup(conn, session_id, doc_id)
