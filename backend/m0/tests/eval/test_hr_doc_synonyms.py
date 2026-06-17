"""
TDD Cycle 3: HR/법무 문서 태그 매칭 개선

문제:
  - docx_02 (취업규칙): actual 태그에 '인사정책'이 있지만 golden '근로조건', 'HR' 등과 미매칭
  - '인사정책' ↔ 'HR' 동의어 없음
  - '근로조건', '임금', '휴가', '복무', '징계', '퇴직' 등 HR 법무 용어 synonym 누락

목표:
  - 인사정책 / 인사규정 → HR 동의어 연결
  - 채용 / 채용관리 → recruitment 동의어 연결
  - 임금 / 급여 → salary 동의어 연결
  - 복무 / 복무규정 → workrule 동의어 연결
  - 징계 → discipline 동의어 연결
  - 취업규칙 → employmentrule 동의어 연결 (양방향)
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import pytest
from run_eval import _terms_match, compute_tags_metrics


# ---------------------------------------------------------------------------
# Cycle 3 RED: HR 용어 동의어 — 현재 실패해야 함
# ---------------------------------------------------------------------------

class TestHRDocumentSynonyms:
    """HR/법무 문서 태그 매칭 개선."""

    def test_인사정책_matches_hr(self):
        """인사정책(actual)이 HR(golden)과 매칭되어야 한다."""
        assert _terms_match("인사정책", "HR") is True

    def test_hr_matches_인사정책(self):
        """HR(golden)이 인사정책(actual)과 양방향 매칭되어야 한다."""
        assert _terms_match("HR", "인사정책") is True

    def test_인사규정_matches_hr(self):
        """인사규정(actual)이 HR(golden)과 매칭되어야 한다."""
        assert _terms_match("인사규정", "HR") is True

    def test_임금_matches_salary(self):
        """임금(golden)이 급여(actual)와 매칭되어야 한다."""
        assert _terms_match("임금", "급여") is True

    def test_복무_matches_복무규정(self):
        """복무(golden)가 복무규정(actual)과 매칭되어야 한다."""
        assert _terms_match("복무", "복무규정") is True

    def test_채용_matches_채용관리(self):
        """채용(golden)이 채용관리(actual)와 매칭되어야 한다."""
        assert _terms_match("채용", "채용관리") is True


class TestDocx02TagsScenario:
    """DOCX HR 문서 실패 케이스 재현 — Cycle 3 완료 후 F1 개선 확인."""

    # Golden (expected) — docx_02 취업규칙
    EXPECTED = ["취업규칙", "근로조건", "휴가", "복무", "임금", "징계", "퇴직", "HR", "채용"]
    # Actual (pipeline output) — 현재 Stage 5 출력
    ACTUAL = ["취업규칙", "근로조건", "인사정책", "온보딩", "정보보안", "교육시스템", "AI 도구 활용", "RAG"]

    def test_hr_synonym_improves_docx02_f1(self):
        """인사정책↔HR 동의어 추가 후 DOCX F1이 0.35보다 높아야 한다."""
        recall, precision = compute_tags_metrics(self.EXPECTED, self.ACTUAL)
        f1 = 2 * recall * precision / (recall + precision) if (recall + precision) > 0 else 0.0
        assert f1 > 0.35, f"DOCX F1이 0.35 이하: {f1:.3f} (HR synonym 추가 필요)"

    def test_인사정책_counted_as_hr_in_recall(self):
        """인사정책이 HR과 매칭되어 recall에 포함되어야 한다."""
        matched_hr = any(_terms_match("HR", a) for a in self.ACTUAL)
        assert matched_hr is True, "인사정책이 HR과 매칭되지 않음"
