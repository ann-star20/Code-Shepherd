"""TDD: build_pipeline — stage6_store kwargs 전달 검증."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


def _make_mock_factory():
    """SQLAlchemy async_sessionmaker 최소 목."""
    factory = MagicMock()
    session = AsyncMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    factory.return_value = session
    return factory, session


def _make_mock_storage():
    storage = MagicMock()
    storage.upload_file = AsyncMock(return_value="gs://bucket/path")
    return storage


# ---------------------------------------------------------------------------
# 파이프라인 빌드 — 임포트 & 컴파일 성공
# ---------------------------------------------------------------------------

def test_build_pipeline_compiles_without_error():
    """build_pipeline()이 TypeError 없이 그래프를 반환해야 한다.

    오늘 수정된 버그: stage6_store 노드 등록 시 db_session_factory 누락으로
    'missing 1 required positional argument' TypeError 발생했었음.
    """
    from app.pipeline.graph import build_pipeline

    factory, _ = _make_mock_factory()
    storage = _make_mock_storage()

    # 컴파일 자체가 TypeError 없이 성공하면 통과
    pipeline = build_pipeline(db_session_factory=factory, storage=storage)
    assert pipeline is not None


# ---------------------------------------------------------------------------
# stage6_store — db_session_factory 가 fn_kwargs로 전달되는지 검증
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_stage6_store_receives_db_session_factory():
    """_wrap_with_harness가 stage6_store에 db_session_factory를 전달해야 한다."""
    from app.pipeline.graph import _wrap_with_harness
    from shared.trace import DocPipelineStage

    factory, _ = _make_mock_factory()
    storage = _make_mock_storage()

    received: dict = {}

    async def fake_stage6(state, db_session_factory=None, storage=None):
        received["db_session_factory"] = db_session_factory
        received["storage"] = storage
        return {"status": "stored"}

    node_fn = _wrap_with_harness(
        DocPipelineStage.STORE_ROUTE,
        "StoreRouteAgent",
        fake_stage6,
        factory,
        db_session_factory=factory,
        storage=storage,
    )

    state = {
        "doc_id": "00000000-0000-0000-0000-000000000001",
        "status": "processing",
    }

    async def _run(fn, st, **kw):
        return await fn(st, **kw)

    with patch("app.pipeline.graph.AgentHarness") as MockHarness:
        instance = AsyncMock()
        instance.__aenter__ = AsyncMock(return_value=instance)
        instance.__aexit__ = AsyncMock(return_value=False)
        instance.run = AsyncMock(side_effect=_run)
        MockHarness.return_value = instance

        await node_fn(state)

    assert received["db_session_factory"] is factory, (
        "stage6_store에 db_session_factory가 전달되지 않았습니다 — "
        "오늘 수정된 _wrap_with_harness kwargs 버그가 재발했을 수 있습니다."
    )
    assert received["storage"] is storage
