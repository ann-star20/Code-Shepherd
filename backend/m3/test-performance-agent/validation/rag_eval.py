"""SESSION_8D — RAG retriever 품질 평가 파이프라인 (RAGAS).

이슈 message(query) → retriever 가 가져온 사내규칙(retrieved_contexts) 가, 사람이
라벨링한 정답 규칙(reference_contexts) 과 얼마나 맞는지를 RAGAS 로 측정한다.

  - Tier A (검색 품질, LLM judge 불필요·할당량 0):
      NonLLMContextPrecisionWithReference / NonLLMContextRecall (rapidfuzz 문자열 유사도)
  - Tier B (인용 충실/관련, Gemini judge 필요·할당량 소모):
      Faithfulness / ResponseRelevancy — best-effort, 미가용 시 skip(사유)

설계 원칙(정직성):
  - RAGAS 호출부(run_ragas)는 seam — 외부 의존(ragas)은 함수 안에서 지연 import.
    그래서 이 모듈의 순수 함수(build_samples/finalize_scores/aggregate/scores_from_result)
    는 ragas·pandas 없이도 import·단위테스트된다.
  - 인용 없음(빈 검색결과): recall=0(정답을 못 가져온 진짜 miss), 나머지 지표는 skip(None).
    가짜 점수를 만들지 않는다.
  - RAGAS 가 NaN 을 주면 None(미산출)으로. 평균은 None 을 제외(skip)하고 낸다.

1커맨드 재실행: `uv run python validation/rag_eval.py`
"""
from __future__ import annotations

import json
import math
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

# 스크립트 직접 실행 시 프로젝트 루트를 sys.path 에 추가 (validation/eval.py 와 동일 패턴)
_ROOT = Path(__file__).parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def _shim_langchain_vertexai() -> None:
    """ragas 0.4.3 × langchain 1.x 비호환 우회 (ragas 가 사용 직전에만 호출).

    ragas/llms/base.py 가 모듈 로드 시 `from langchain_community.chat_models.vertexai
    import ChatVertexAI` 를 즉시 실행하는데, langchain-community 0.4.x(=langchain 1.x
    라인)에는 그 레거시 서브모듈이 없다. 우리는 Vertex 를 쓰지 않으므로(judge=Gemini,
    Tier A 는 LLM 불필요) placeholder 만 등록해 import 만 통과시킨다 — 점수에는 무영향.
    ragas 를 실제로 쓰는 경로(run_ragas/main)에서만 호출 → 단위테스트엔 영향 없음.
    """
    import types  # noqa: PLC0415
    name = "langchain_community.chat_models.vertexai"
    if name in sys.modules:
        return
    try:
        import importlib  # noqa: PLC0415
        importlib.import_module(name)
        return  # 진짜 모듈이 있으면 그대로 사용
    except Exception:
        pass
    mod = types.ModuleType(name)
    mod.ChatVertexAI = type("ChatVertexAI", (), {})  # placeholder (미사용)
    sys.modules[name] = mod


# ─── 표본(샘플) ────────────────────────────────────────────────────────────────
@dataclass
class Sample:
    """한 평가 케이스 → RAGAS SingleTurnSample 로 변환될 중간형."""
    id: str
    rule_id: str
    query: str
    retrieved_contexts: list[str]
    reference_contexts: list[str]
    response: str | None = None
    retrieved_docs: list[dict] = field(default_factory=list)  # 정성 표용 원본(title/score)
    expected_title_substr: str = ""  # 인용 라벨 정합성 판정용(예: "PERF-002")

    @property
    def has_citation(self) -> bool:
        return bool(self.retrieved_contexts)


def build_samples(cases, search, top_k: int = 3, respond=None) -> list[Sample]:
    """각 케이스의 query 로 retriever 를 돌려 표본을 만든다.

    search(query, top_k) -> [{content, doc_title, score, ...}]  (rag.retriever 형식)
    respond(query, contexts) -> str  (Tier B 답변 생성; 없으면 response=None)
    """
    samples: list[Sample] = []
    for c in cases:
        docs = list(search(c["query"], top_k))
        contexts = [d.get("content", "") for d in docs]
        resp = respond(c["query"], contexts) if respond is not None else None
        samples.append(Sample(
            id=c["id"], rule_id=c["rule_id"], query=c["query"],
            retrieved_contexts=contexts, reference_contexts=c["reference_contexts"],
            response=resp, retrieved_docs=docs,
            expected_title_substr=c.get("expected_title_substr", ""),
        ))
    return samples


def citation_correct(retrieved_docs: list[dict], expected_substr: str):
    """top1 검색결과의 doc_title 이 기대 규칙을 가리키나. 판정 불가 시 None(skip).

    검색결과 없음/기대값 없음 → None(가짜 판정 금지). 그 외 → 라벨 포함 여부 bool.
    """
    if not retrieved_docs or not expected_substr:
        return None
    title = retrieved_docs[0].get("doc_title") or ""
    return expected_substr in title


# ─── 점수 정직성 ───────────────────────────────────────────────────────────────
def _clean(v):
    """NaN/None → None(미산출), 그 외 → float. 가짜 0 으로 둔갑시키지 않는다."""
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(f) else f


def finalize_scores(
    sample: Sample, raw: dict | None,
    empty_recall_metric: str = "context_recall",
    empty_skip_metrics: tuple[str, ...] = (
        "context_precision", "faithfulness", "answer_relevancy"),
) -> dict:
    """표본 하나의 최종 점수. 인용 없음 → 정직한 skip/0 규칙 적용.

    인용 없음: recall 류 지표는 진짜 0(정답 못 가져온 miss), precision/충실/관련은 잴
    대상이 없으니 skip(None) — 가짜 점수 금지. 지표 '이름'은 호출부가 실제 쓰는 지표명
    (예: non_llm_context_recall)으로 주입해, 인용된 케이스와 같은 칼럼에 집계되게 한다.
    """
    if not sample.has_citation:
        out = {empty_recall_metric: 0.0}
        for m in empty_skip_metrics:
            out[m] = None
        return out
    raw = raw or {}
    return {k: _clean(v) for k, v in raw.items()}


def scores_from_result(result) -> list[dict]:
    """RAGAS EvaluationResult(.scores: list[dict]) → 표본당 {metric: float|None}.

    result 는 .scores(list[dict]) 만 있으면 됨 → 가짜 result 로 단위테스트 가능.
    """
    out: list[dict] = []
    for row in result.scores:
        out.append({k: _clean(v) for k, v in dict(row).items()})
    return out


# ─── 집계 ──────────────────────────────────────────────────────────────────────
def aggregate(rows: list[dict]) -> dict:
    """표본 행들(id/rule_id/query/has_citation/scores) → 지표별 평균(None 제외) + 카운트."""
    n_cases = len(rows)
    n_empty = sum(1 for r in rows if not r.get("has_citation", True))
    metric_names: list[str] = []
    for r in rows:
        for m in r["scores"]:
            if m not in metric_names:
                metric_names.append(m)

    metrics: dict[str, dict] = {}
    for m in metric_names:
        values = [r["scores"][m] for r in rows
                  if m in r["scores"] and r["scores"][m] is not None]
        mean = (sum(values) / len(values)) if values else None
        metrics[m] = {
            "mean": mean,
            "n_scored": len(values),
            "n_skipped": n_cases - len(values),
        }
    # 인용 라벨 정합성(doc_title 이 올바른 규칙을 가리키나) — 정성 약점 지표
    judged = [r for r in rows if r.get("label_ok") is not None]
    correct = sum(1 for r in judged if r["label_ok"])
    accuracy = (correct / len(judged)) if judged else None

    return {
        "n_cases": n_cases,
        "n_empty_citation": n_empty,
        "metrics": metrics,
        "citation_label": {
            "correct": correct,
            "judged": len(judged),
            "accuracy": accuracy,
        },
        "rows": rows,
    }


# ─── 리포트 ────────────────────────────────────────────────────────────────────
def _fmt(x) -> str:
    return "—(skip)" if x is None else f"{x:.3f}"


def format_report(summary: dict, meta: dict) -> str:
    """집계 결과 → 마크다운 리포트(지표 표 + 케이스 표 + 메타)."""
    lines: list[str] = []
    lines.append("# RAGAS — RAG 검색/인용 품질 리포트\n")
    lines.append("## 실행 메타 (재현용)")
    lines.append(f"- 평가셋 케이스 수: **{meta.get('n_cases', summary['n_cases'])}** "
                 f"(빈 인용 {summary['n_empty_citation']}건)")
    lines.append(f"- judge 모델: **{meta.get('judge', '—')}**")
    lines.append(f"- 임베딩(judge): {meta.get('judge_embeddings', '—')}")
    lines.append(f"- RAGAS 버전: **{meta.get('ragas_version', '—')}**")
    lines.append(f"- 검색 임베더: {meta.get('embed_model', '—')}, top_k={meta.get('top_k', '—')}")
    if meta.get("tier_b_status"):
        lines.append(f"- Tier B(faithfulness/answer_relevancy): {meta['tier_b_status']}")
    lines.append("")

    lines.append("## 지표 (평균은 미산출 skip 제외)")
    lines.append("| metric | mean | scored | skip(미산출) |")
    lines.append("|---|---|---|---|")
    for m, d in summary["metrics"].items():
        lines.append(f"| {m} | {_fmt(d['mean'])} | {d['n_scored']} | {d['n_skipped']} |")
    lines.append("")

    cl = summary.get("citation_label")
    if cl:
        lines.append("## 인용 라벨 정합성 (doc_title 이 올바른 규칙을 가리키나)")
        lines.append(f"- 정확: **{cl['correct']} / {cl['judged']}** "
                     f"(정확도 {_fmt(cl['accuracy'])}) — RAGAS 청크-단위 점수가 못 잡는 약점")
        lines.append("")

    lines.append("## 케이스별")
    metric_cols = list(summary["metrics"].keys())
    header = "| id | rule | 인용? | 라벨 | " + " | ".join(metric_cols) + " | top1 검색결과 |"
    lines.append(header)
    lines.append("|" + "---|" * (5 + len(metric_cols)))
    for r in summary["rows"]:
        cited = "○" if r.get("has_citation", True) else "✗(빈결과)"
        lab = {True: "✓", False: "✗(오라벨)", None: "—"}[r.get("label_ok")]
        cells = [_fmt(r["scores"].get(m)) for m in metric_cols]
        top1 = r.get("top1", "")
        lines.append(f"| {r['id']} | {r['rule_id']} | {cited} | {lab} | "
                     + " | ".join(cells) + f" | {top1} |")
    lines.append("")
    return "\n".join(lines)


# ─── RAGAS 호출부 (seam — 외부 의존은 여기서만) ────────────────────────────────
def run_ragas(samples: list[Sample], metrics, llm=None, embeddings=None,
              evaluate_fn=None, run_config=None) -> list[dict]:
    """표본들을 RAGAS EvaluationDataset 으로 만들어 evaluate → 표본당 점수.

    evaluate_fn 주입 가능(테스트/대체). 미주입 시 ragas.evaluate 사용(지연 import).
    """
    _shim_langchain_vertexai()
    from ragas import EvaluationDataset, evaluate  # noqa: PLC0415
    from ragas.dataset_schema import SingleTurnSample  # noqa: PLC0415

    if evaluate_fn is None:
        evaluate_fn = evaluate

    st_samples = []
    for s in samples:
        fields_ = {
            "user_input": s.query,
            "retrieved_contexts": s.retrieved_contexts,
            "reference_contexts": s.reference_contexts,
        }
        if s.response is not None:
            fields_["response"] = s.response
        st_samples.append(SingleTurnSample(**fields_))

    dataset = EvaluationDataset(samples=st_samples)
    result = evaluate_fn(dataset=dataset, metrics=metrics, llm=llm,
                         embeddings=embeddings, run_config=run_config,
                         show_progress=False)
    return scores_from_result(result)


def build_judge(model: str, api_key: str):
    """Gemini judge LLM + 임베딩(LangchainWrapper) — Tier B 용. 지연 import."""
    from langchain_google_genai import (  # noqa: PLC0415
        ChatGoogleGenerativeAI,
        GoogleGenerativeAIEmbeddings,
    )
    from ragas.embeddings import LangchainEmbeddingsWrapper  # noqa: PLC0415
    from ragas.llms import LangchainLLMWrapper  # noqa: PLC0415

    llm = LangchainLLMWrapper(ChatGoogleGenerativeAI(
        model=model, google_api_key=api_key, temperature=0.0))
    emb = LangchainEmbeddingsWrapper(GoogleGenerativeAIEmbeddings(
        model="models/embedding-001", google_api_key=api_key))
    return llm, emb


def gemini_responder(model: str, api_key: str):
    """이슈+검색문맥 → 사내 가이드 인용 답변 생성기(Tier B faithfulness/relevancy 입력)."""
    from langchain_google_genai import ChatGoogleGenerativeAI  # noqa: PLC0415

    chat = ChatGoogleGenerativeAI(model=model, google_api_key=api_key, temperature=0.0)

    def respond(query: str, contexts: list[str]) -> str:
        guide = "\n\n".join(contexts) if contexts else "(검색된 사내 가이드 없음)"
        prompt = (
            "너는 코드리뷰 봇이다. 아래 '사내 가이드'에 근거해서만 이슈에 대한 "
            "짧은 코멘트를 한국어로 작성해라. 가이드에 없는 내용은 지어내지 마라.\n\n"
            f"[이슈]\n{query}\n\n[사내 가이드]\n{guide}\n\n[코멘트]"
        )
        return chat.invoke(prompt).content

    return respond


# ════════════════════════════════════════════════════════════════════════════
# 1커맨드 라이브 실행: 평가셋 로드 → 실제 retriever → Tier A(+best-effort Tier B)
# ════════════════════════════════════════════════════════════════════════════
def _rows_from(samples: list[Sample], raw_by_id: dict,
               empty_recall_metric: str = "context_recall",
               empty_skip_metrics: tuple[str, ...] = (
                   "context_precision", "faithfulness", "answer_relevancy")) -> list[dict]:
    rows = []
    for s in samples:
        scores = finalize_scores(s, raw_by_id.get(s.id),
                                 empty_recall_metric=empty_recall_metric,
                                 empty_skip_metrics=empty_skip_metrics)
        top1 = ""
        if s.retrieved_docs:
            d0 = s.retrieved_docs[0]
            top1 = f"{(d0.get('doc_title') or '')[:30]} ({d0.get('score', 0):.2f})"
        rows.append({"id": s.id, "rule_id": s.rule_id, "query": s.query,
                     "has_citation": s.has_citation, "scores": scores, "top1": top1,
                     "label_ok": citation_correct(s.retrieved_docs, s.expected_title_substr)})
    return rows


def main() -> int:
    import importlib.metadata as _md  # noqa: PLC0415

    from rag.retriever import search_convention  # noqa: PLC0415

    evalset_path = _ROOT / "validation" / "rag_evalset.json"
    data = json.loads(evalset_path.read_text(encoding="utf-8"))
    cases = data["cases"]
    top_k = int(os.getenv("RAG_EVAL_TOP_K", "3"))

    ragas_version = _md.version("ragas")
    embed_model = os.getenv("EMBED_MODEL", "BAAI/bge-m3")
    judge_model = os.getenv("RAG_JUDGE_MODEL", "gemini-2.5-flash-lite")
    api_key = os.getenv("GOOGLE_API_KEY", "")

    print(f"[rag_eval] cases={len(cases)} top_k={top_k} ragas={ragas_version} "
          f"embed={embed_model}")

    # 검색은 1회 (Tier A·B 공유)
    samples = build_samples(cases, search=search_convention, top_k=top_k)
    cited = [s for s in samples if s.has_citation]
    print(f"[rag_eval] 검색 완료 — 인용 있음 {len(cited)} / 빈결과 {len(samples) - len(cited)}")

    meta = {
        "n_cases": len(cases), "ragas_version": ragas_version,
        "embed_model": embed_model, "top_k": top_k,
        "judge": "—(Tier A 는 LLM 불필요)", "judge_embeddings": "—",
    }

    # ── Tier A: 검색 품질 (비-LLM, 할당량 0) ──
    _shim_langchain_vertexai()
    from ragas.metrics import (  # noqa: PLC0415
        NonLLMContextPrecisionWithReference,
        NonLLMContextRecall,
    )
    raw_a = run_ragas(cited, metrics=[NonLLMContextPrecisionWithReference(),
                                      NonLLMContextRecall()])
    raw_by_id = {s.id: r for s, r in zip(cited, raw_a)}

    # ── Tier B: 인용 충실/관련 (Gemini judge, best-effort) ──
    if not api_key:
        meta["tier_b_status"] = "skip (GOOGLE_API_KEY 없음)"
    else:
        try:
            from ragas.metrics import Faithfulness, ResponseRelevancy  # noqa: PLC0415
            from ragas.run_config import RunConfig  # noqa: PLC0415

            respond = gemini_responder(judge_model, api_key)
            for s in cited:
                s.response = respond(s.query, s.retrieved_contexts)
            llm, emb = build_judge(judge_model, api_key)
            raw_b = run_ragas(
                cited, metrics=[Faithfulness(), ResponseRelevancy()],
                llm=llm, embeddings=emb,
                run_config=RunConfig(max_workers=1, timeout=120, max_retries=2),
            )
            for s, rb in zip(cited, raw_b):
                raw_by_id[s.id] = {**raw_by_id.get(s.id, {}), **rb}
            meta.update(judge=judge_model, judge_embeddings="models/embedding-001",
                        tier_b_status="ok")
        except Exception as exc:  # noqa: BLE001 — 정직하게 skip(사유)
            meta["tier_b_status"] = f"skip ({type(exc).__name__}: {str(exc)[:120]})"
            meta["judge"] = judge_model
            print(f"[rag_eval] Tier B skip — {meta['tier_b_status']}")

    # 빈 인용 케이스의 recall=0(miss)을 Tier A 와 같은 칼럼에 집계 → 전체 recall 이 정직해짐
    rows = _rows_from(
        samples, raw_by_id,
        empty_recall_metric="non_llm_context_recall",
        empty_skip_metrics=("non_llm_context_precision_with_reference",
                            "faithfulness", "answer_relevancy"),
    )
    summary = aggregate(rows)
    report = format_report(summary, meta)

    out_md = _ROOT / "validation" / "rag_eval_report.md"
    out_json = _ROOT / "validation" / "rag_eval_report.json"
    out_md.write_text(report, encoding="utf-8")
    out_json.write_text(json.dumps({"meta": meta, "summary": {
        k: v for k, v in summary.items() if k != "rows"}, "rows": rows},
        ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n" + report)
    print(f"\n[rag_eval] 저장: {out_md.name}, {out_json.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
