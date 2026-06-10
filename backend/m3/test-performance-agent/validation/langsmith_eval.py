"""8E — LangSmith 통합 평가 (Dataset·Experiment·Evaluator 래핑).

기존 채점기(validation/eval.py:evaluate_prf)를 그대로 호출. 복붙·재구현 금지.
LANGCHAIN_API_KEY 없으면 정직 skip(로컬 채점은 그대로 동작).

1커맨드:
    docker compose exec m3 sh -c \\
        'cd /app/service/test-performance-agent && \\
         RAG_ENABLED= GOOGLE_API_KEY= uv run python validation/langsmith_eval.py'
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Optional

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

if TYPE_CHECKING:
    from langsmith import Client

DATASET_8B = "m3-detection-8B"


def build_client() -> Optional["Client"]:
    """LANGCHAIN_API_KEY가 있으면 LangSmith Client 반환, 없으면 None(정직 skip)."""
    key = os.environ.get("LANGCHAIN_API_KEY", "").strip()
    if not key:
        return None
    try:
        from langsmith import Client
        return Client()
    except Exception:
        return None


def ensure_dataset(client, name: str, description: str, cases: list[dict]) -> str:
    """Dataset 없으면 생성 + examples 업로드. 이미 있으면 name만 반환(멱등).

    inputs  = {case_name, kind}
    outputs = {expected}  (evaluate_prf의 expected 형식 그대로)
    """
    if client.has_dataset(dataset_name=name):
        return name
    client.create_dataset(name, description=description)
    for case in cases:
        client.create_example(
            inputs={"case_name": case["name"], "kind": case.get("kind", "")},
            outputs={"expected": case["expected"]},
            dataset_name=name,
        )
    return name


def prf_to_langsmith_scores(scores: dict) -> list[dict]:
    """evaluate_prf() 결과 → [{key, score}, ...] LangSmith 피드백 형식."""
    overall = scores.get("overall", {})
    return [
        {"key": "precision", "score": overall.get("precision", 0.0)},
        {"key": "recall", "score": overall.get("recall", 0.0)},
        {"key": "f1", "score": overall.get("f1", 0.0)},
        {"key": "pass", "score": 1.0 if scores.get("pass") else 0.0},
    ]


def make_prf_evaluator(case_by_name: dict, results_by_name: dict):
    """케이스별 P/R/F1 채점기를 LangSmith evaluator 함수로 래핑.

    - run.outputs["outputs"]   = AgentOutput 목록 (target 함수가 반환)
    - example.inputs["case_name"] = 케이스 이름
    evaluate_prf를 그대로 호출(복붙 금지).
    """
    from validation.eval import evaluate_prf

    def evaluator(run, example) -> list:
        try:
            from langsmith.evaluation import EvaluationResult
        except ImportError:
            return []

        name = example.inputs.get("case_name")
        case = case_by_name.get(name)
        if not case:
            return [EvaluationResult(key="f1", score=None)]

        outputs = run.outputs.get("outputs", [])
        scored = evaluate_prf([
            {"name": name, "outputs": outputs, "expected": case["expected"]}
        ])
        overall = scored["overall"]
        return [
            EvaluationResult(key="f1", score=overall["f1"]),
            EvaluationResult(key="precision", score=overall["precision"]),
            EvaluationResult(key="recall", score=overall["recall"]),
        ]

    return evaluator


def run_detection_experiment(
    client,
    cases: list[dict],
    *,
    run_case_fn=None,
    experiment_prefix: str = "m3-detection-8B",
) -> dict:
    """8B 탐지 벤치마크 → LangSmith Experiment 기록. evaluate_prf 재사용(복붙 금지).

    run_case_fn: (case) → list[AgentOutput] (기본값: benchmark._run_case).
    반환: {"scores": evaluate_prf 결과, "dataset_name": str, "experiment_prefix": str}.
    """
    if run_case_fn is None:
        from validation.benchmark import _run_case
        run_case_fn = _run_case

    from validation.eval import evaluate_prf

    # 각 케이스 실행 (결과 캐시 — evaluate도 이 결과를 reuse)
    case_by_name = {c["name"]: c for c in cases}
    results_by_name: dict[str, list] = {}
    for case in cases:
        results_by_name[case["name"]] = run_case_fn(case)

    # LangSmith Dataset 업로드 (멱등)
    dataset_name = ensure_dataset(
        client, DATASET_8B, "m3 탐지 정확도 벤치마크 (8B)", cases)

    # target: Dataset example inputs → 에이전트 출력 반환 (pre-computed 결과 반환)
    def _target(inputs: dict) -> dict:
        name = inputs.get("case_name", "")
        return {"outputs": results_by_name.get(name, [])}

    evaluator = make_prf_evaluator(case_by_name, results_by_name)

    client.evaluate(
        _target,
        data=dataset_name,
        evaluators=[evaluator],
        experiment_prefix=experiment_prefix,
        blocking=True,
    )

    # 전체 aggregate score
    scored_cases = [
        {"name": c["name"], "outputs": results_by_name[c["name"]], "expected": c["expected"]}
        for c in cases
    ]
    scores = evaluate_prf(scored_cases)

    return {
        "scores": scores,
        "dataset_name": dataset_name,
        "experiment_prefix": experiment_prefix,
    }


def main() -> int:
    """8E 1커맨드 실행: 8B 탐지 벤치마크를 LangSmith에 업로드."""
    client = build_client()

    from validation.benchmark import CASES, _run_case
    from validation.eval import evaluate_prf

    # 로컬 채점은 키 유무와 무관하게 항상 실행
    print("8B 탐지 벤치마크 실행 중 ...")
    scored_cases = [
        {"name": c["name"], "outputs": _run_case(c), "expected": c["expected"]}
        for c in CASES
    ]
    local_scores = evaluate_prf(scored_cases)
    overall = local_scores["overall"]
    print(
        f"[로컬] 탐지 P={overall['precision']:.3f} R={overall['recall']:.3f} "
        f"F1={overall['f1']:.3f} ({'PASS' if local_scores['pass'] else 'FAIL'})"
    )

    if client is None:
        print("skip(LangSmith): LANGCHAIN_API_KEY 없음 — 로컬 채점만 완료")
        print("→ .env 에 LANGCHAIN_API_KEY=ls__... 추가 후 재실행하면 LangSmith에 업로드됩니다")
        return 0

    project = os.environ.get("LANGCHAIN_PROJECT", "module3-eval")
    print(f"LangSmith 업로드: project={project} ...")
    try:
        # pre-computed 결과 재활용 (run_case_fn에 캐시 주입)
        results_cache = {c["name"]: c["outputs"] for c in scored_cases}
        result = run_detection_experiment(
            client, CASES,
            run_case_fn=lambda c: results_cache[c["name"]],
            experiment_prefix=f"{project}-8B",
        )
        print(
            f"[LangSmith] Dataset={result['dataset_name']} "
            f"Experiment={result['experiment_prefix']}"
        )
        print("→ https://smith.langchain.com 에서 결과 확인")
    except Exception as e:
        print(f"LangSmith 업로드 실패 (로컬 채점은 완료): {type(e).__name__}: {e}")
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
