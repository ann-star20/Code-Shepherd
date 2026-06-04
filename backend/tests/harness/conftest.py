"""pytest 픽스처 — A1 단계에서는 인프라 의존 없음."""
import pytest


# ── 향후 추가될 픽스처 placeholder ──────────────────────────────────────────
# Phase C (DB 스키마) 단계에서 db_session, neo4j_session 추가
# Phase D (파이프라인) 단계에서 run_sync_pipeline_task 추가

import pytest

@pytest.fixture(params=["asyncio"])
def anyio_backend(request):
    return request.param
