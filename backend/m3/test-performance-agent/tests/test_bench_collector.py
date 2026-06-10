"""bench/collector.py TDD 테스트.

검증 핵심:
  1. percentile() — p50·p95 계산 정확성.
  2. build_stats() — {stage: [ms...]} → {stage: {p50, p95, min, max}} 집계.
  3. 측정 안 된 단계 → 결과 dict에 아예 없음 (가짜 숫자 금지).
  4. format_report_table() — 표(markdown) 형식 검증.
"""
from __future__ import annotations

import sys
import os

# bench 패키지 경로 주입 (test-performance-agent/bench/)
_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_BENCH = os.path.join(_BASE, "bench")
if _BENCH not in sys.path:
    sys.path.insert(0, _BENCH)

import pytest


# ════════════════════════════════════════════
# 1. percentile()
# ════════════════════════════════════════════

class TestPercentile:
    """collector.percentile(values, pct) 검증."""

    def test_p50_odd_list(self):
        """홀수 개 리스트 — p50은 중앙값."""
        from collector import percentile
        assert percentile([100, 200, 300], 50) == 200.0

    def test_p50_even_list(self):
        """짝수 개 리스트 — p50은 두 중앙값의 평균(또는 lower-bound)."""
        from collector import percentile
        result = percentile([100, 200, 300, 400], 50)
        # numpy-style linear: (200+300)/2 = 250 또는 conservative 200
        assert 200 <= result <= 300, f"p50 범위 벗어남: {result}"

    def test_p95_twenty_items(self):
        """20개 항목 — p95는 19번째(0-indexed 18번)에 해당하는 값 근방."""
        from collector import percentile
        values = list(range(1, 21))  # [1, 2, ..., 20]
        result = percentile(values, 95)
        assert 18 <= result <= 20, f"p95 범위 벗어남: {result}"

    def test_single_element(self):
        """1개 항목 → p50=p95=해당 값."""
        from collector import percentile
        assert percentile([42], 50) == 42.0
        assert percentile([42], 95) == 42.0

    def test_all_same_values(self):
        """모두 같은 값 → p50=p95=그 값."""
        from collector import percentile
        assert percentile([100, 100, 100], 50) == 100.0
        assert percentile([100, 100, 100], 95) == 100.0


# ════════════════════════════════════════════
# 2. build_stats()
# ════════════════════════════════════════════

class TestBuildStats:
    """collector.build_stats({stage: [ms, ...]}) → stats dict."""

    def test_single_stage_has_p50_p95_min_max(self):
        """단일 단계 → p50·p95·min·max 키가 모두 있다."""
        from collector import build_stats
        result = build_stats({"coverage": [100.0, 200.0, 300.0]})
        assert "coverage" in result
        s = result["coverage"]
        assert "p50" in s and "p95" in s and "min" in s and "max" in s

    def test_min_max_correct(self):
        """min·max 값이 올바르다."""
        from collector import build_stats
        result = build_stats({"nplus1": [50.0, 150.0, 300.0]})
        s = result["nplus1"]
        assert s["min"] == 50.0
        assert s["max"] == 300.0

    def test_missing_stage_absent(self):
        """입력에 없는 단계는 결과 dict에 없다 (가짜 0 금지)."""
        from collector import build_stats
        result = build_stats({"coverage": [100.0]})
        assert "missing_funcs" not in result, "측정 안 된 단계가 dict에 들어가면 안 된다"

    def test_empty_input_returns_empty_dict(self):
        """빈 입력 → 빈 dict."""
        from collector import build_stats
        assert build_stats({}) == {}

    def test_multiple_stages_all_present(self):
        """여러 단계 → 모두 결과 dict에 있다."""
        from collector import build_stats
        timings = {
            "coverage": [200.0, 250.0],
            "complexity": [50.0, 60.0],
            "nplus1": [30.0],
        }
        result = build_stats(timings)
        assert set(result.keys()) == {"coverage", "complexity", "nplus1"}

    def test_n_recorded_in_stats(self):
        """각 단계에 측정 횟수(n)가 기록된다."""
        from collector import build_stats
        result = build_stats({"coverage": [100.0, 200.0, 300.0]})
        assert result["coverage"]["n"] == 3


# ════════════════════════════════════════════
# 3. format_report_table()
# ════════════════════════════════════════════

class TestFormatReportTable:
    """collector.format_report_table() — markdown 표 출력 검증."""

    def _make_stats(self):
        from collector import build_stats
        return build_stats({
            "coverage": [200.0, 250.0, 210.0],
            "complexity": [50.0, 60.0, 55.0],
        })

    def test_output_is_string(self):
        """반환값이 문자열이다."""
        from collector import format_report_table
        result = format_report_table(self._make_stats(), n=3, prs=["PR#1", "PR#2", "PR#3"])
        assert isinstance(result, str)

    def test_output_contains_stage_names(self):
        """표에 단계 이름(coverage, complexity)이 포함된다."""
        from collector import format_report_table
        result = format_report_table(self._make_stats(), n=3, prs=["PR#1", "PR#2", "PR#3"])
        assert "coverage" in result
        assert "complexity" in result

    def test_output_contains_p50_p95_headers(self):
        """표 헤더에 p50·p95가 포함된다."""
        from collector import format_report_table
        result = format_report_table(self._make_stats(), n=3, prs=["PR#1"])
        assert "p50" in result.lower()
        assert "p95" in result.lower()

    def test_output_contains_n_and_prs(self):
        """표에 N(측정 횟수)·PR 목록 정보가 포함된다."""
        from collector import format_report_table
        result = format_report_table(self._make_stats(), n=3, prs=["PR#1", "PR#2", "PR#3"])
        assert "N=" in result or "n=" in result or "3" in result

    def test_rag_off_shows_off_label(self):
        """RAG 꺼진 경우 stats에 rag 없으면 표에 '(off)' 행이 나온다."""
        from collector import format_report_table
        stats = self._make_stats()
        result = format_report_table(stats, n=3, prs=["PR#1"], rag_enabled=False)
        assert "(off)" in result


# ════════════════════════════════════════════
# 4. cold/warm 구분
# ════════════════════════════════════════════

class TestColdWarmSplit:
    """cold(첫 실행)·warm(이후 실행) 구분 검증."""

    def test_split_cold_warm_returns_tuple(self):
        """split_cold_warm([run1, run2, ...]) → (cold_timings, warm_timings_list)."""
        from collector import split_cold_warm
        runs = [
            {"coverage": [200.0]},
            {"coverage": [150.0]},
            {"coverage": [140.0]},
        ]
        cold, warm = split_cold_warm(runs)
        assert cold == {"coverage": [200.0]}
        assert warm == [{"coverage": [150.0]}, {"coverage": [140.0]}]

    def test_split_single_run_warm_empty(self):
        """단 1회 실행 → cold=그 실행, warm=빈 리스트."""
        from collector import split_cold_warm
        cold, warm = split_cold_warm([{"coverage": [300.0]}])
        assert cold == {"coverage": [300.0]}
        assert warm == []

    def test_split_empty_raises_or_empty(self):
        """빈 입력 → ValueError 또는 ({}, [])."""
        from collector import split_cold_warm
        try:
            cold, warm = split_cold_warm([])
            assert cold == {} and warm == []
        except (ValueError, IndexError):
            pass  # acceptable
