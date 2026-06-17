"""eval.harness 골든 로더·지표 4종·실행기록(runs) 단위 테스트 — 가짜 review_fn, LLM 호출 없음.

지표 정의 (브리프 §4.2):
- 탐지율: 위반 PR 중 올바른 rule_id 를 violation 으로 잡은 비율
- 오탐: 정상 PR(expected: [])에 낸 violation 건수
- 환각률: 인용 검증 실패 건수 / 전체 Finding 인용 수
- 지침공백 정확도: gap PR 를 gap 으로 보고한 비율
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from contracts import Finding, GapReport, ReviewOutput
from eval.harness import (
    build_corpus_index,
    compute_metrics,
    load_failed_ids,
    load_golden_cases,
    render_report,
    run_cases,
    save_run,
)

RULE_API = """# [CONV-API-001] async 함수 내 동기 HTTP 금지
- severity: Major

## §1 규칙
async 함수 안에서 동기 requests 호출을 금지한다. 반드시 httpx.AsyncClient 를 사용한다.
"""

RULE_LOG = """# [CONV-LOG-003] print 로깅 금지
- severity: Major

## §1 규칙
print() 로깅을 금지한다. struct_logger.log(event=...) 만 사용한다.
"""

DIFF_VIOLATION = """diff --git a/app/api.py b/app/api.py
--- a/app/api.py
+++ b/app/api.py
@@ -1,4 +1,6 @@
 async def fetch_user(uid):
-    return cache.get(uid)
+    resp = requests.get(f"https://api.internal/users/{uid}")
+    return resp.json()
"""

DIFF_NORMAL = """diff --git a/scripts/backfill.py b/scripts/backfill.py
--- a/scripts/backfill.py
+++ b/scripts/backfill.py
@@ -1,2 +1,3 @@
+import requests
+resp = requests.get(url)
"""

DIFF_GAP = """diff --git a/app/cache.py b/app/cache.py
--- a/app/cache.py
+++ b/app/cache.py
@@ -1,2 +1,3 @@
+TTL = 60 * 60 * 24
"""


def _write_pr(golden: Path, pr_id: str, diff: str, label_yaml: str, files: dict[str, str] | None = None) -> None:
    d = golden / pr_id
    d.mkdir(parents=True)
    (d / "diff.patch").write_text(diff, encoding="utf-8")
    (d / "label.yaml").write_text(label_yaml, encoding="utf-8")
    for rel, content in (files or {}).items():
        p = d / "files" / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")


@pytest.fixture()
def env(tmp_path: Path):
    """tmp 코퍼스(규칙 2개) + tmp 골든셋(위반2·정상1·gap1) 환경."""
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "external_api.md").write_text(RULE_API, encoding="utf-8")
    (corpus / "logging.md").write_text(RULE_LOG, encoding="utf-8")

    golden = tmp_path / "golden"
    _write_pr(
        golden, "pr_001", DIFF_VIOLATION,
        "expected: [{rule_id: CONV-API-001, verdict: violation}]\n",
        files={"app/api.py": "async def fetch_user(uid): ...\n"},
    )
    _write_pr(golden, "pr_002", DIFF_NORMAL, "expected: []\n")
    _write_pr(golden, "pr_003", DIFF_GAP, "expected: gap\n")
    _write_pr(
        golden, "pr_004", DIFF_VIOLATION,
        "expected: [{rule_id: CONV-API-001, verdict: violation}]\n",
    )
    return {
        "corpus_idx": build_corpus_index(corpus),
        "cases": load_golden_cases(golden),
    }


def _finding(rule_id="CONV-API-001", verdict="violation",
             quote="동기 requests 호출을 금지한다",
             evidence=('+    resp = requests.get(f"https://api.internal/users/{uid}")',)) -> Finding:
    return Finding(
        rule_id=rule_id, verdict=verdict, severity="Major", rule_quote=quote,
        file="app/api.py", evidence_lines=list(evidence), reasoning="r",
    )


def _out(findings=(), gap: GapReport | None = None) -> ReviewOutput:
    return ReviewOutput(findings=list(findings), comment_md="(comment)", gap_report=gap)


def _gap() -> GapReport:
    return GapReport(pattern_summary="규칙 없음", queries_tried=["q"], proposed_rule_md="# 제안")


def _review_fn(mapping):
    """pr_id → ReviewOutput | Exception 매핑으로 만든 가짜 파이프라인."""
    def fn(case):
        val = mapping[case.pr_id]
        if isinstance(val, Exception):
            raise val
        return val
    return fn


# ── 골든 로더 ──────────────────────────────────────────────────────────

def test_load_golden_cases(env):
    cases = {c.pr_id: c for c in env["cases"]}
    assert set(cases) == {"pr_001", "pr_002", "pr_003", "pr_004"}
    assert cases["pr_001"].category == "violation"
    assert cases["pr_002"].category == "normal"
    assert cases["pr_003"].category == "gap"
    # file_paths 는 diff 의 '+++ b/...' 에서 파싱
    assert cases["pr_001"].file_paths == ["app/api.py"]
    # files/ 전문 로드 (repo_meta 로 전달될 재료)
    assert "app/api.py" in cases["pr_001"].files


# ── 지표 4종 ──────────────────────────────────────────────────────────

def test_detection_hit_and_miss(env):
    # pr_001: 정답 rule 적중 / pr_004: 다른(실존) rule 만 지적 → 탐지 실패
    results = run_cases(env["cases"], env["corpus_idx"], _review_fn({
        "pr_001": _out([_finding()]),
        "pr_002": _out(),
        "pr_003": _out(gap=_gap()),
        "pr_004": _out([_finding(rule_id="CONV-LOG-003",
                                 quote="print() 로깅을 금지한다",
                                 evidence=("resp = requests.get",))]),
    }))
    m = compute_metrics(results)
    assert m["detection"] == {"hit": 1, "total": 2}
    by_id = {r["pr_id"]: r for r in results}
    assert by_id["pr_001"]["pass"] is True
    assert by_id["pr_004"]["pass"] is False
    assert by_id["pr_004"]["missing"] == ["CONV-API-001"]


def test_false_positive_counted_on_normal_pr(env):
    results = run_cases(env["cases"], env["corpus_idx"], _review_fn({
        "pr_001": _out([_finding()]),
        "pr_002": _out([_finding(quote="동기 requests 호출을 금지한다",
                                 evidence=("resp = requests.get(url)",))]),  # 정상 PR에 violation → 오탐
        "pr_003": _out(gap=_gap()),
        "pr_004": _out([_finding()]),
    }))
    m = compute_metrics(results)
    assert m["false_positive"] == {"count": 1, "normal_prs": 1, "prs_with_fp": 1}
    assert {r["pr_id"]: r["pass"] for r in results}["pr_002"] is False


def test_gap_accuracy_and_false_gap(env):
    # pr_003(gap)을 gap 으로 보고 → 적중. pr_002(정상)에 gap 보고 → 해당 PR fail.
    results = run_cases(env["cases"], env["corpus_idx"], _review_fn({
        "pr_001": _out([_finding()]),
        "pr_002": _out(gap=_gap()),
        "pr_003": _out(gap=_gap()),
        "pr_004": _out([_finding()]),
    }))
    m = compute_metrics(results)
    assert m["gap"] == {"hit": 1, "total": 1}
    by_id = {r["pr_id"]: r for r in results}
    assert by_id["pr_002"]["pass"] is False
    assert by_id["pr_003"]["pass"] is True


def test_hallucination_rate(env):
    # pr_001 에 인용 2건 — 1건은 날조 인용문 → 환각 1/2, PR fail
    results = run_cases(env["cases"], env["corpus_idx"], _review_fn({
        "pr_001": _out([
            _finding(),
            _finding(rule_id="CONV-LOG-003", quote="존재하지 않는 날조 인용문이다"),
        ]),
        "pr_002": _out(),
        "pr_003": _out(gap=_gap()),
        "pr_004": _out([_finding()]),
    }))
    m = compute_metrics(results)
    assert m["hallucination"]["bad"] == 1
    assert m["hallucination"]["checked"] == 3  # pr_001 2건 + pr_004 1건 (전 PR Finding 합)
    assert {r["pr_id"]: r["pass"] for r in results}["pr_001"] is False


def test_extra_violation_detected_but_not_pass(env):
    # 정답 rule 적중 + 기대에 없는 rule 추가 지적 → 탐지율엔 hit, PASS 는 fail
    results = run_cases(env["cases"], env["corpus_idx"], _review_fn({
        "pr_001": _out([
            _finding(),
            _finding(rule_id="CONV-LOG-003", quote="print() 로깅을 금지한다",
                     evidence=("resp = requests.get",)),
        ]),
        "pr_002": _out(),
        "pr_003": _out(gap=_gap()),
        "pr_004": _out([_finding()]),
    }))
    m = compute_metrics(results)
    assert m["detection"] == {"hit": 2, "total": 2}
    by_id = {r["pr_id"]: r for r in results}
    assert by_id["pr_001"]["pass"] is False
    assert by_id["pr_001"]["extra"] == ["CONV-LOG-003"]


def test_pipeline_error_marked_failed(env):
    results = run_cases(env["cases"], env["corpus_idx"], _review_fn({
        "pr_001": RuntimeError("boom"),
        "pr_002": _out(),
        "pr_003": _out(gap=_gap()),
        "pr_004": _out([_finding()]),
    }))
    by_id = {r["pr_id"]: r for r in results}
    assert by_id["pr_001"]["status"] == "error"
    assert by_id["pr_001"]["pass"] is False
    m = compute_metrics(results)
    assert m["detection"] == {"hit": 1, "total": 2}  # 에러 PR 는 탐지 실패로 집계
    assert m["errors"] == 1


# ── 실행 기록(runs) + --failed 선택 ────────────────────────────────────

def test_save_run_then_failed_selection_and_merge(env, tmp_path):
    runs = tmp_path / "runs"
    ok = {
        "pr_001": _out([_finding()]),
        "pr_002": _out(),
        "pr_003": _out(gap=_gap()),
        "pr_004": _out([_finding()]),
    }
    # 1) 전체 실행 — pr_004 만 실패(탐지 누락)
    first = dict(ok, pr_004=_out())
    results = run_cases(env["cases"], env["corpus_idx"], _review_fn(first))
    save_run(results, runs)
    assert load_failed_ids(runs) == ["pr_004"]
    assert (runs / "latest.json").exists()

    # 2) 부분 재실행(--failed 흐름) — pr_004 수정 후 통과 → latest 에 병합
    retry_cases = [c for c in env["cases"] if c.pr_id == "pr_004"]
    retry = run_cases(retry_cases, env["corpus_idx"], _review_fn(ok))
    save_run(retry, runs, partial=True)
    assert load_failed_ids(runs) == []

    latest = json.loads((runs / "latest.json").read_text(encoding="utf-8"))
    assert {r["pr_id"] for r in latest["results"]} == {"pr_001", "pr_002", "pr_003", "pr_004"}
    assert latest["metrics"]["detection"] == {"hit": 2, "total": 2}


# ── 리포트 ─────────────────────────────────────────────────────────────

def test_render_report_smoke(env):
    results = run_cases(env["cases"], env["corpus_idx"], _review_fn({
        "pr_001": _out([_finding()]),
        "pr_002": _out(),
        "pr_003": _out(gap=_gap()),
        "pr_004": _out([_finding()]),
    }))
    text = render_report(results, compute_metrics(results))
    for token in ("탐지율", "오탐", "환각", "지침공백", "pr_001", "pr_004", "PASS"):
        assert token in text
