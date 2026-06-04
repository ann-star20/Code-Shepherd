"""Tests for GET /kms/stats endpoint."""

from __future__ import annotations

import pytest

import module_0_kms.api as api
from module_0_kms.api import get_kms_stats


class _AcquireContext:
    def __init__(self, conn):
        self._conn = conn

    async def __aenter__(self):
        return self._conn

    async def __aexit__(self, *_):
        return False


class _FakePool:
    def __init__(self, conn):
        self._conn = conn

    def acquire(self):
        return _AcquireContext(self._conn)


def _overview_row(total: int = 30, success: int = 25, fail: int = 5) -> dict:
    return {"total_runs": total, "success_count": success, "fail_count": fail}


def _stage_rows() -> list[dict]:
    return [
        {"agent_name": "DocumentParserAgent", "avg_execution_ms": 3200.0, "run_count": 10},
        {"agent_name": "MarkdownValidatorAgent", "avg_execution_ms": 150.0, "run_count": 10},
        {"agent_name": "ChunkingAgent", "avg_execution_ms": 450.0, "run_count": 10},
    ]


class _ConnStats:
    def __init__(
        self,
        overview: dict | None = None,
        stages: list[dict] | None = None,
    ):
        self._overview = overview if overview is not None else _overview_row()
        self._stages = stages if stages is not None else _stage_rows()

    async def fetchrow(self, query: str, *_args, **_kw):
        return self._overview

    async def fetch(self, query: str, *_args, **_kw):
        return self._stages


# ---------------------------------------------------------------------------
# 응답 구조 검증
# ---------------------------------------------------------------------------

class TestStatsResponseStructure:
    async def test_total_runs_in_response(self, monkeypatch):
        """응답에 total_runs 필드가 포함된다."""
        monkeypatch.setattr(api, "_db_pool", _FakePool(_ConnStats()))
        result = await get_kms_stats()
        assert result.total_runs == 30

    async def test_success_count_in_response(self, monkeypatch):
        """응답에 success_count 필드가 포함된다."""
        monkeypatch.setattr(api, "_db_pool", _FakePool(_ConnStats()))
        result = await get_kms_stats()
        assert result.success_count == 25

    async def test_fail_count_in_response(self, monkeypatch):
        """응답에 fail_count 필드가 포함된다."""
        monkeypatch.setattr(api, "_db_pool", _FakePool(_ConnStats()))
        result = await get_kms_stats()
        assert result.fail_count == 5

    async def test_success_rate_in_response(self, monkeypatch):
        """응답에 success_rate 필드가 포함된다."""
        monkeypatch.setattr(api, "_db_pool", _FakePool(_ConnStats()))
        result = await get_kms_stats()
        assert hasattr(result, "success_rate")

    async def test_stage_stats_in_response(self, monkeypatch):
        """응답에 stage_stats 리스트가 포함된다."""
        monkeypatch.setattr(api, "_db_pool", _FakePool(_ConnStats()))
        result = await get_kms_stats()
        assert isinstance(result.stage_stats, list)


# ---------------------------------------------------------------------------
# 성공률 계산
# ---------------------------------------------------------------------------

class TestSuccessRateCalculation:
    async def test_success_rate_25_of_30(self, monkeypatch):
        """25/30 → success_rate ≈ 0.833"""
        monkeypatch.setattr(api, "_db_pool", _FakePool(
            _ConnStats(overview=_overview_row(total=30, success=25, fail=5))
        ))
        result = await get_kms_stats()
        assert abs(result.success_rate - 25 / 30) < 1e-6

    async def test_success_rate_all_success(self, monkeypatch):
        """100%일 때 success_rate = 1.0"""
        monkeypatch.setattr(api, "_db_pool", _FakePool(
            _ConnStats(overview=_overview_row(total=10, success=10, fail=0))
        ))
        result = await get_kms_stats()
        assert result.success_rate == pytest.approx(1.0)

    async def test_success_rate_zero_runs(self, monkeypatch):
        """실행 기록이 없으면 success_rate = 0.0 (ZeroDivisionError 방지)"""
        monkeypatch.setattr(api, "_db_pool", _FakePool(
            _ConnStats(overview=_overview_row(total=0, success=0, fail=0))
        ))
        result = await get_kms_stats()
        assert result.success_rate == 0.0

    async def test_success_rate_all_fail(self, monkeypatch):
        """모두 실패할 때 success_rate = 0.0"""
        monkeypatch.setattr(api, "_db_pool", _FakePool(
            _ConnStats(overview=_overview_row(total=5, success=0, fail=5))
        ))
        result = await get_kms_stats()
        assert result.success_rate == 0.0


# ---------------------------------------------------------------------------
# 스테이지별 통계
# ---------------------------------------------------------------------------

class TestStageStats:
    async def test_stage_stats_count(self, monkeypatch):
        """stage_stats에 3개 에이전트 항목이 포함된다."""
        monkeypatch.setattr(api, "_db_pool", _FakePool(_ConnStats()))
        result = await get_kms_stats()
        assert len(result.stage_stats) == 3

    async def test_stage_stats_agent_name(self, monkeypatch):
        """stage_stats 각 항목에 agent_name이 포함된다."""
        monkeypatch.setattr(api, "_db_pool", _FakePool(_ConnStats()))
        result = await get_kms_stats()
        names = [s.agent_name for s in result.stage_stats]
        assert "DocumentParserAgent" in names

    async def test_stage_stats_avg_execution_ms(self, monkeypatch):
        """stage_stats 항목에 avg_execution_ms가 포함된다."""
        monkeypatch.setattr(api, "_db_pool", _FakePool(_ConnStats()))
        result = await get_kms_stats()
        parser_stat = next(s for s in result.stage_stats if s.agent_name == "DocumentParserAgent")
        assert parser_stat.avg_execution_ms == pytest.approx(3200.0)

    async def test_stage_stats_run_count(self, monkeypatch):
        """stage_stats 항목에 run_count가 포함된다."""
        monkeypatch.setattr(api, "_db_pool", _FakePool(_ConnStats()))
        result = await get_kms_stats()
        parser_stat = next(s for s in result.stage_stats if s.agent_name == "DocumentParserAgent")
        assert parser_stat.run_count == 10

    async def test_empty_stage_stats_when_no_traces(self, monkeypatch):
        """agent_traces가 없으면 stage_stats는 빈 리스트를 반환한다."""
        monkeypatch.setattr(api, "_db_pool", _FakePool(_ConnStats(stages=[])))
        result = await get_kms_stats()
        assert result.stage_stats == []
