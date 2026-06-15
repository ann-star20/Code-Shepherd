"""
HITL 품질 지표 (Precision / Recall / False Pass / False HITL) 단위 테스트.

KMS 파이프라인에서 HITL은 "발생률 최소화" 대상이 아니라
"잘못된 지식 저장을 막는 품질 안전망"이다.
이 테스트는 golden_dataset의 expected_hitl 필드를 기준으로
파이프라인이 문제 문서를 얼마나 정확히 HITL로 분기시키는지 검증한다.
"""

from __future__ import annotations

import pytest
from dataclasses import dataclass, field
from typing import Optional


# ---------------------------------------------------------------------------
# run_eval 모듈에서 필요한 클래스·함수를 직접 import (실 의존성)
# ---------------------------------------------------------------------------

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from run_eval import GoldenEntry, PipelineResult, compute_hitl_quality_kpis


# ---------------------------------------------------------------------------
# 픽스처 헬퍼
# ---------------------------------------------------------------------------

def _golden(id: str, expected_hitl: bool) -> GoldenEntry:
    return GoldenEntry(
        id=id,
        file=f"documents/{id}.md",
        file_type="md",
        expected_title=None,
        expected_category=None,
        expected_tags=[],
        expected_entities={},
        expected_hitl=expected_hitl,
    )


def _result(golden_id: str, status: str) -> PipelineResult:
    return PipelineResult(
        doc_id=f"doc-{golden_id}",
        golden_id=golden_id,
        title=None,
        category=None,
        tags=[],
        entities={},
        status=status,
        file_type="md",
    )


# ---------------------------------------------------------------------------
# 핵심 시나리오 테스트
# ---------------------------------------------------------------------------

class TestHitlQualityKpis:
    """compute_hitl_quality_kpis() 검증."""

    def test_perfect_case_all_correct(self):
        """문제 문서 → HITL / 정상 문서 → stored. Precision=Recall=1.0."""
        goldens = [
            _golden("good_01", expected_hitl=False),
            _golden("good_02", expected_hitl=False),
            _golden("bad_01", expected_hitl=True),
            _golden("bad_02", expected_hitl=True),
        ]
        results = {
            "good_01": _result("good_01", "stored"),
            "good_02": _result("good_02", "stored"),
            "bad_01":  _result("bad_01", "hitl_pending"),
            "bad_02":  _result("bad_02", "hitl_pending"),
        }
        kpis = compute_hitl_quality_kpis(goldens, results)

        assert kpis["hitl_precision"] == 1.0
        assert kpis["hitl_recall"]    == 1.0
        assert kpis["false_pass_rate"] == 0.0
        assert kpis["false_hitl_rate"] == 0.0

    def test_false_pass_missed_problem_doc(self):
        """문제 문서가 HITL 없이 stored → False Pass Rate = 1.0, Recall = 0.0."""
        goldens = [
            _golden("bad_01", expected_hitl=True),
        ]
        results = {
            "bad_01": _result("bad_01", "stored"),  # 놓침
        }
        kpis = compute_hitl_quality_kpis(goldens, results)

        assert kpis["hitl_recall"] == 0.0
        assert kpis["false_pass_rate"] == 1.0

    def test_false_hitl_good_doc_sent_to_hitl(self):
        """정상 문서가 HITL로 분기 → False HITL Rate = 1.0, Precision = 0.0."""
        goldens = [
            _golden("good_01", expected_hitl=False),
        ]
        results = {
            "good_01": _result("good_01", "hitl_pending"),  # 과도한 HITL
        }
        kpis = compute_hitl_quality_kpis(goldens, results)

        assert kpis["false_hitl_rate"] == 1.0
        # HITL로 간 것 중 진짜 문제인 게 없으므로 Precision = 0.0
        assert kpis["hitl_precision"] == 0.0

    def test_partial_recall(self):
        """문제 문서 2개 중 1개만 HITL → Recall = 0.5."""
        goldens = [
            _golden("bad_01", expected_hitl=True),
            _golden("bad_02", expected_hitl=True),
        ]
        results = {
            "bad_01": _result("bad_01", "hitl_pending"),  # 잡음
            "bad_02": _result("bad_02", "stored"),         # 놓침
        }
        kpis = compute_hitl_quality_kpis(goldens, results)

        assert kpis["hitl_recall"] == pytest.approx(0.5)
        assert kpis["false_pass_rate"] == pytest.approx(0.5)
        assert kpis["hitl_precision"] == 1.0  # HITL로 간 1개는 진짜 문제

    def test_no_expected_hitl_entries_returns_na(self):
        """golden에 expected_hitl=True가 없으면 Recall/False Pass는 N/A."""
        goldens = [
            _golden("good_01", expected_hitl=False),
            _golden("good_02", expected_hitl=False),
        ]
        results = {
            "good_01": _result("good_01", "stored"),
            "good_02": _result("good_02", "stored"),
        }
        kpis = compute_hitl_quality_kpis(goldens, results)

        assert kpis["hitl_recall"] is None
        assert kpis["false_pass_rate"] is None

    def test_no_hitl_triggered_returns_na_precision(self):
        """파이프라인이 HITL을 한 번도 발동하지 않으면 Precision = N/A."""
        goldens = [
            _golden("good_01", expected_hitl=False),
        ]
        results = {
            "good_01": _result("good_01", "stored"),
        }
        kpis = compute_hitl_quality_kpis(goldens, results)

        assert kpis["hitl_precision"] is None

    def test_missing_result_counted_as_false_pass(self):
        """pipeline_output에 결과가 없으면 '탐지 실패'로 간주 → Recall에 반영."""
        goldens = [
            _golden("bad_01", expected_hitl=True),
        ]
        results: dict = {}  # 결과 없음

        kpis = compute_hitl_quality_kpis(goldens, results)

        assert kpis["hitl_recall"] == 0.0
        assert kpis["false_pass_rate"] == 1.0

    def test_kpis_contain_required_keys(self):
        """반환 딕셔너리에 4개 지표 키가 모두 있어야 한다."""
        goldens = [_golden("bad_01", expected_hitl=True)]
        results = {"bad_01": _result("bad_01", "hitl_pending")}

        kpis = compute_hitl_quality_kpis(goldens, results)

        for key in ("hitl_precision", "hitl_recall", "false_pass_rate", "false_hitl_rate"):
            assert key in kpis, f"누락된 키: {key}"

    def test_stored_partial_counts_as_stored(self):
        """stored_partial은 HITL 미발동으로 간주 — False Pass에 포함."""
        goldens = [
            _golden("bad_01", expected_hitl=True),
        ]
        results = {
            "bad_01": _result("bad_01", "stored_partial"),
        }
        kpis = compute_hitl_quality_kpis(goldens, results)

        assert kpis["hitl_recall"] == 0.0
        assert kpis["false_pass_rate"] == 1.0
