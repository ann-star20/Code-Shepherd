"""contracts 스키마 스모크 테스트 — 계약이 import·검증 가능함을 보증 (전 세션 공용)."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from contracts import (
    Finding,
    GapReport,
    GoldenLabel,
    ReviewInput,
    ReviewOutput,
)


def test_review_input_roundtrip():
    inp = ReviewInput(diff="--- a/x.py\n+++ b/x.py", file_paths=["x.py"], repo_meta={"pr_number": 1})
    assert inp.file_paths == ["x.py"]


def test_review_output_with_gap():
    out = ReviewOutput(
        findings=[],
        comment_md="## 지침공백",
        gap_report=GapReport(pattern_summary="규칙 없음", queries_tried=["q1"], proposed_rule_md="# 제안"),
    )
    assert out.gap_report is not None


def test_finding_requires_verdict_literal():
    with pytest.raises(ValidationError):
        Finding(
            rule_id="CONV-API-001", verdict="maybe", severity="Major",
            rule_quote="...", file="x.py", evidence_lines=[], reasoning="...",
        )


def test_golden_label_three_forms():
    assert GoldenLabel(expected="gap").expected == "gap"
    assert GoldenLabel(expected=[]).expected == []
    lbl = GoldenLabel(expected=[{"rule_id": "CONV-API-001", "verdict": "violation"}])
    assert lbl.expected[0].rule_id == "CONV-API-001"
