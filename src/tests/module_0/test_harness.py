"""
AgentHarness.run() — LangSmith trace_metadata 주입 테스트

수정 전 harness.run()은 trace_metadata를 import만 하고 실제로 사용하지 않아
LangSmith에 trace_id/agent_name 없이 Run이 올라간다.

이 테스트들은 harness.run()이 fn의 config 파라미터에
trace_metadata를 주입하는지 검증한다.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import pytest

# conftest.py가 asyncpg mock을 주입하므로 import는 항상 성공
from common.harness import AgentHarness


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _make_pool() -> MagicMock:
    pool = MagicMock()
    conn = MagicMock()
    conn.execute = AsyncMock()
    pool.acquire = MagicMock()
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)
    return pool


async def _fn_with_config(state: dict, config: dict | None = None) -> dict:
    """LangGraph ainvoke 시그니처 모사."""
    return {"received_config": config}


async def _fn_without_config(state: dict) -> dict:
    """config 파라미터 없는 일반 async 함수."""
    return {"ok": True}


async def _fn_with_varkw(state: dict, **kwargs) -> dict:
    """**kwargs로 config를 받는 함수."""
    return {"received_config": kwargs.get("config")}


# ---------------------------------------------------------------------------
# trace_id / agent_name 주입
# ---------------------------------------------------------------------------

class TestTraceMetadataInjection:

    @pytest.mark.asyncio
    async def test_run_injects_trace_id_into_config(self):
        """fn이 config를 받으면 config['metadata']['trace_id']가 주입돼야 한다."""
        harness = AgentHarness(
            trace_id="trc_0001_abcd1234",
            agent_name="MarkdownConverterAgent",
            db_pool=_make_pool(),
        )
        harness._started_at = __import__("datetime").datetime.now(
            __import__("datetime").timezone.utc
        )

        result = await harness.run(_fn_with_config, {"input": "test"})

        config = result["received_config"]
        assert config is not None, "config이 None — run()이 config를 주입하지 않았음"
        assert "metadata" in config, "config에 metadata 키가 없음"
        assert config["metadata"]["trace_id"] == "trc_0001_abcd1234"

    @pytest.mark.asyncio
    async def test_run_injects_agent_name_into_config(self):
        """config['metadata']['agent_name']이 주입돼야 한다."""
        harness = AgentHarness(
            trace_id="trc_0002_abcd1234",
            agent_name="ChunkingAgent",
            db_pool=_make_pool(),
        )
        harness._started_at = __import__("datetime").datetime.now(
            __import__("datetime").timezone.utc
        )

        result = await harness.run(_fn_with_config, {})

        assert result["received_config"]["metadata"]["agent_name"] == "ChunkingAgent"

    @pytest.mark.asyncio
    async def test_run_injects_doc_id_when_set(self):
        """doc_id가 있으면 config['metadata']['doc_id']가 주입돼야 한다."""
        doc_id = UUID("12345678-1234-5678-1234-567812345678")
        harness = AgentHarness(
            trace_id="trc_0003_12345678",
            agent_name="MetadataAgent",
            db_pool=_make_pool(),
            doc_id=doc_id,
        )
        harness._started_at = __import__("datetime").datetime.now(
            __import__("datetime").timezone.utc
        )

        result = await harness.run(_fn_with_config, {})

        assert result["received_config"]["metadata"]["doc_id"] == str(doc_id)


# ---------------------------------------------------------------------------
# 기존 config/metadata 보존
# ---------------------------------------------------------------------------

class TestExistingConfigPreservation:

    @pytest.mark.asyncio
    async def test_run_preserves_existing_config_keys(self):
        """호출자가 넘긴 config의 기존 키가 유지돼야 한다."""
        harness = AgentHarness(
            trace_id="trc_0001_aabbccdd",
            agent_name="TestAgent",
            db_pool=_make_pool(),
        )
        harness._started_at = __import__("datetime").datetime.now(
            __import__("datetime").timezone.utc
        )

        existing_config = {"recursion_limit": 10, "tags": ["test"]}
        result = await harness.run(_fn_with_config, {}, config=existing_config)

        config = result["received_config"]
        assert config["recursion_limit"] == 10
        assert config["tags"] == ["test"]

    @pytest.mark.asyncio
    async def test_run_does_not_overwrite_existing_metadata_keys(self):
        """호출자가 넘긴 metadata 키가 harness 주입값보다 우선해야 한다."""
        harness = AgentHarness(
            trace_id="trc_0001_aabbccdd",
            agent_name="TestAgent",
            db_pool=_make_pool(),
        )
        harness._started_at = __import__("datetime").datetime.now(
            __import__("datetime").timezone.utc
        )

        user_config = {"metadata": {"custom_key": "user_value", "trace_id": "user_override"}}
        result = await harness.run(_fn_with_config, {}, config=user_config)

        meta = result["received_config"]["metadata"]
        assert meta["custom_key"] == "user_value"
        assert meta["trace_id"] == "user_override", "사용자 override가 harness 주입값에 덮어써지면 안 됨"


# ---------------------------------------------------------------------------
# config 없는 함수는 영향 없음
# ---------------------------------------------------------------------------

class TestNoConfigInjectionWhenNotAccepted:

    @pytest.mark.asyncio
    async def test_run_does_not_break_fn_without_config_param(self):
        """config 파라미터가 없는 fn은 정상 실행돼야 한다."""
        harness = AgentHarness(
            trace_id="trc_0001_aabbccdd",
            agent_name="TestAgent",
            db_pool=_make_pool(),
        )
        harness._started_at = __import__("datetime").datetime.now(
            __import__("datetime").timezone.utc
        )

        result = await harness.run(_fn_without_config, {"input": "data"})
        assert result == {"ok": True}

    @pytest.mark.asyncio
    async def test_run_injects_config_when_fn_has_varkw(self):
        """**kwargs를 받는 fn에도 config가 주입돼야 한다."""
        harness = AgentHarness(
            trace_id="trc_0001_aabbccdd",
            agent_name="TestAgent",
            db_pool=_make_pool(),
        )
        harness._started_at = __import__("datetime").datetime.now(
            __import__("datetime").timezone.utc
        )

        result = await harness.run(_fn_with_varkw, {})

        config = result["received_config"]
        assert config is not None
        assert config["metadata"]["trace_id"] == "trc_0001_aabbccdd"
