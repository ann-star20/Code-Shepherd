"""SESSION_8D — validation/rag_eval.py TDD.

RAGAS 호출부(run_ragas)는 seam 으로 분리해 mock. 여기 단위테스트는 RAGAS·pandas
없이 돈다(가짜 retriever 결과 + 가짜 RAGAS 점수로 집계·표·정직성 검증).

핵심 검증:
  - build_samples: retriever 출력 → SingleTurn 필드(user_input/retrieved/reference)
  - 빈 검색결과(인용 없음) → has_citation=False, finalize_scores 가 정직하게 skip/0
  - finalize_scores: NaN → None(가짜 점수 금지), 빈 인용 → recall=0·나머지 skip
  - aggregate: None(미산출)은 평균에서 제외(skip), empty 카운트
  - scores_from_result: RAGAS EvaluationResult.scores(list[dict]) 파싱, NaN→None
"""
import math

from validation.rag_eval import (
    Sample,
    aggregate,
    build_samples,
    citation_correct,
    finalize_scores,
    format_report,
    scores_from_result,
)

CASE = {
    "id": "PERF-002-msg",
    "rule_id": "PERF-002",
    "query": "N+1 쿼리: 루프 안에서 DB 호출이 반복됩니다.",
    "reference_contexts": ["반복문 안에서 DB를 호출하는 N+1 은 막습니다."],
}


# ─── build_samples ────────────────────────────────────────────────────────────
def test_build_samples_maps_retriever_output_to_fields():
    """retriever 결과(content 키) → retrieved_contexts, 쿼리 → user_input, 정답 보존."""
    def fake_search(q, top_k=3):
        return [{"content": "부모 청크 A", "score": 0.9},
                {"content": "부모 청크 B", "score": 0.7}]

    samples = build_samples([CASE], search=fake_search)
    s = samples[0]
    assert s.id == "PERF-002-msg"
    assert s.rule_id == "PERF-002"
    assert s.query == CASE["query"]
    assert s.retrieved_contexts == ["부모 청크 A", "부모 청크 B"]
    assert s.reference_contexts == CASE["reference_contexts"]
    assert s.has_citation is True


def test_build_samples_empty_retrieval_marks_no_citation():
    """빈 검색결과(인용 없음) → retrieved_contexts=[], has_citation=False (정직)."""
    samples = build_samples([CASE], search=lambda q, top_k=3: [])
    assert samples[0].retrieved_contexts == []
    assert samples[0].has_citation is False


def test_build_samples_passes_top_k_to_search():
    seen = {}
    def fake_search(q, top_k=3):
        seen["top_k"] = top_k
        return []
    build_samples([CASE], search=fake_search, top_k=5)
    assert seen["top_k"] == 5


def test_build_samples_respond_fills_response_for_tier_b():
    """respond 주입 시(Tier B) 검색문맥으로 답변 생성 → sample.response."""
    def fake_respond(query, contexts):
        return f"답변({len(contexts)}개 근거)"
    samples = build_samples(
        [CASE], search=lambda q, top_k=3: [{"content": "C", "score": 0.8}],
        respond=fake_respond,
    )
    assert samples[0].response == "답변(1개 근거)"


def test_build_samples_without_respond_leaves_response_none():
    samples = build_samples([CASE], search=lambda q, top_k=3: [{"content": "C"}])
    assert samples[0].response is None


# ─── finalize_scores: 정직성 규칙 ──────────────────────────────────────────────
def test_finalize_scores_empty_citation_is_honest():
    """인용 없음: recall=0(정답 못 가져옴=진짜 miss), 나머지는 skip(None) — 가짜 점수 금지."""
    s = Sample(id="x", rule_id="R", query="q", retrieved_contexts=[],
               reference_contexts=["정답"])
    out = finalize_scores(s, raw=None)
    assert out["context_recall"] == 0.0
    assert out["context_precision"] is None
    assert out["faithfulness"] is None
    assert out["answer_relevancy"] is None


def test_finalize_scores_nan_becomes_none():
    """RAGAS 가 NaN 을 주면 None(미산출)으로 — 0 으로 둔갑시키지 않음."""
    s = Sample(id="x", rule_id="R", query="q", retrieved_contexts=["c"],
               reference_contexts=["정답"])
    out = finalize_scores(s, raw={"context_precision": float("nan"),
                                  "context_recall": 1.0})
    assert out["context_precision"] is None
    assert out["context_recall"] == 1.0


def test_finalize_scores_passes_through_real_values_when_cited():
    s = Sample(id="x", rule_id="R", query="q", retrieved_contexts=["c"],
               reference_contexts=["정답"])
    out = finalize_scores(s, raw={"context_precision": 0.5, "faithfulness": 0.8})
    assert out["context_precision"] == 0.5
    assert out["faithfulness"] == 0.8


# ─── scores_from_result: RAGAS 출력 파싱(가짜 result) ──────────────────────────
class _FakeResult:
    """ragas EvaluationResult 모사 — .scores 는 표본당 dict 리스트."""
    def __init__(self, scores):
        self.scores = scores


def test_scores_from_result_reads_per_sample_scores():
    r = _FakeResult([
        {"context_precision": 0.9, "context_recall": 1.0},
        {"context_precision": 0.2, "context_recall": 0.0},
    ])
    out = scores_from_result(r)
    assert out == [
        {"context_precision": 0.9, "context_recall": 1.0},
        {"context_precision": 0.2, "context_recall": 0.0},
    ]


def test_scores_from_result_converts_nan_to_none():
    r = _FakeResult([{"faithfulness": float("nan"), "answer_relevancy": 0.7}])
    out = scores_from_result(r)
    assert out[0]["faithfulness"] is None
    assert out[0]["answer_relevancy"] == 0.7


# ─── aggregate: 평균은 None(미산출) 제외(skip) ─────────────────────────────────
def _row(rid, scores, has_citation=True):
    return {"id": rid, "rule_id": "R", "query": "q",
            "has_citation": has_citation, "scores": scores}


def test_aggregate_mean_skips_none():
    rows = [
        _row("a", {"context_precision": 1.0, "context_recall": 1.0}),
        _row("b", {"context_precision": None, "context_recall": 0.0},
             has_citation=False),
        _row("c", {"context_precision": 0.5, "context_recall": 1.0}),
    ]
    summ = aggregate(rows)
    # precision: (1.0 + 0.5)/2 = 0.75 (None 제외), n_scored=2 n_skipped=1
    assert summ["metrics"]["context_precision"]["mean"] == 0.75
    assert summ["metrics"]["context_precision"]["n_scored"] == 2
    assert summ["metrics"]["context_precision"]["n_skipped"] == 1
    # recall: (1.0 + 0.0 + 1.0)/3
    assert abs(summ["metrics"]["context_recall"]["mean"] - (2.0 / 3.0)) < 1e-9
    assert summ["metrics"]["context_recall"]["n_scored"] == 3


def test_aggregate_all_none_metric_mean_is_none():
    rows = [_row("a", {"faithfulness": None}), _row("b", {"faithfulness": None})]
    summ = aggregate(rows)
    assert summ["metrics"]["faithfulness"]["mean"] is None
    assert summ["metrics"]["faithfulness"]["n_scored"] == 0


def test_aggregate_counts_cases_and_empty_citations():
    rows = [
        _row("a", {"context_recall": 1.0}),
        _row("b", {"context_recall": 0.0}, has_citation=False),
        _row("c", {"context_recall": 0.0}, has_citation=False),
    ]
    summ = aggregate(rows)
    assert summ["n_cases"] == 3
    assert summ["n_empty_citation"] == 2


# ─── citation_correct: 인용 라벨(doc_title)이 올바른 규칙을 가리키나 ──────────────
def test_citation_correct_matches_top1_title():
    """top1 검색결과의 doc_title 에 기대 규칙 식별자가 들어있으면 True."""
    docs = [{"doc_title": "4) N+1 쿼리 가이드 — PERF-002 (N+1 쿼리)", "score": 0.7}]
    assert citation_correct(docs, "PERF-002") is True
    assert citation_correct(docs, "PERF-001") is False


def test_citation_correct_none_when_no_docs():
    """검색결과 없음 → 라벨을 판정할 수 없음 → None(skip, 가짜 판정 금지)."""
    assert citation_correct([], "TEST-001") is None


def test_aggregate_reports_citation_label_accuracy():
    rows = [
        {"id": "a", "rule_id": "R", "query": "q", "has_citation": True,
         "scores": {}, "label_ok": True},
        {"id": "b", "rule_id": "R", "query": "q", "has_citation": True,
         "scores": {}, "label_ok": False},
        {"id": "c", "rule_id": "R", "query": "q", "has_citation": False,
         "scores": {}, "label_ok": None},
    ]
    summ = aggregate(rows)
    assert summ["citation_label"]["correct"] == 1
    assert summ["citation_label"]["judged"] == 2
    assert summ["citation_label"]["accuracy"] == 0.5


# ─── format_report ────────────────────────────────────────────────────────────
def test_format_report_includes_metrics_meta_and_skip():
    rows = [_row("a", {"context_precision": 1.0}),
            _row("b", {"context_precision": None}, has_citation=False)]
    summ = aggregate(rows)
    md = format_report(summ, meta={"judge": "gemini-2.5-flash-lite",
                                   "ragas_version": "0.4.3", "n_cases": 2})
    assert "context_precision" in md
    assert "gemini-2.5-flash-lite" in md
    assert "0.4.3" in md
    # skip(미산출) 가 표에 정직하게 드러나야 한다
    assert "skip" in md.lower() or "미산출" in md
