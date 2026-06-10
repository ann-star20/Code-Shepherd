"""8E — validation/langsmith_eval.py TDD.

LangSmith Client·네트워크·실 탐지기 모두 Mock. 단위테스트만.
TDD seam:
  - build_client(): LANGCHAIN_API_KEY 환경변수 + langsmith 모듈 가용성
  - ensure_dataset(): Client.has_dataset / create_dataset / create_example 호출
  - prf_to_langsmith_scores(): 순수 함수
  - make_prf_evaluator(): evaluate_prf 재사용 검증 (복붙 금지)
  - run_detection_experiment(): run_case_fn 주입, client.evaluate 호출 검증
"""
from unittest.mock import MagicMock, call, patch

import pytest

from validation import langsmith_eval


# ─── build_client ─────────────────────────────────────────────────────────────

def test_build_client_returns_none_without_key(monkeypatch):
    monkeypatch.delenv("LANGCHAIN_API_KEY", raising=False)
    assert langsmith_eval.build_client() is None


def test_build_client_returns_none_when_empty_key(monkeypatch):
    monkeypatch.setenv("LANGCHAIN_API_KEY", "   ")
    assert langsmith_eval.build_client() is None


def test_build_client_returns_none_on_import_error(monkeypatch):
    monkeypatch.setenv("LANGCHAIN_API_KEY", "ls__fake")
    with patch.dict("sys.modules", {"langsmith": None}):
        result = langsmith_eval.build_client()
    assert result is None


# ─── ensure_dataset ───────────────────────────────────────────────────────────

def _fake_client(exists=False):
    client = MagicMock()
    client.has_dataset.return_value = exists
    return client


def test_ensure_dataset_creates_when_missing():
    client = _fake_client(exists=False)
    cases = [
        {"name": "pos_a", "kind": "positive", "expected": {"x": 1}},
        {"name": "neg_b", "kind": "negative", "expected": {"x": 0}},
    ]
    name = langsmith_eval.ensure_dataset(client, "ds-test", "desc", cases)
    assert name == "ds-test"
    client.create_dataset.assert_called_once_with("ds-test", description="desc")
    assert client.create_example.call_count == 2


def test_ensure_dataset_skips_when_existing():
    client = _fake_client(exists=True)
    name = langsmith_eval.ensure_dataset(client, "ds-test", "desc", [])
    assert name == "ds-test"
    client.create_dataset.assert_not_called()
    client.create_example.assert_not_called()


def test_ensure_dataset_example_inputs_have_case_name():
    client = _fake_client(exists=False)
    cases = [{"name": "case1", "kind": "positive", "expected": {}}]
    langsmith_eval.ensure_dataset(client, "ds", "d", cases)
    call_kwargs = client.create_example.call_args
    inputs = call_kwargs.kwargs.get("inputs") or call_kwargs[1].get("inputs", {})
    assert inputs.get("case_name") == "case1"


def test_ensure_dataset_example_outputs_have_expected():
    client = _fake_client(exists=False)
    expected = {"test_verification": {"expected_issues": []}}
    cases = [{"name": "c", "kind": "neg", "expected": expected}]
    langsmith_eval.ensure_dataset(client, "ds", "d", cases)
    call_kwargs = client.create_example.call_args
    outputs = call_kwargs.kwargs.get("outputs") or call_kwargs[1].get("outputs", {})
    assert outputs.get("expected") == expected


# ─── prf_to_langsmith_scores ──────────────────────────────────────────────────

def test_prf_to_langsmith_scores_keys():
    scores = {
        "overall": {"precision": 0.8, "recall": 0.9, "f1": 0.85},
        "pass": True,
    }
    result = langsmith_eval.prf_to_langsmith_scores(scores)
    keys = {r["key"] for r in result}
    assert keys == {"precision", "recall", "f1", "pass"}


def test_prf_to_langsmith_scores_values():
    scores = {
        "overall": {"precision": 0.75, "recall": 0.60, "f1": 0.67},
        "pass": False,
    }
    result = langsmith_eval.prf_to_langsmith_scores(scores)
    by_key = {r["key"]: r["score"] for r in result}
    assert by_key["precision"] == pytest.approx(0.75)
    assert by_key["recall"] == pytest.approx(0.60)
    assert by_key["f1"] == pytest.approx(0.67)
    assert by_key["pass"] == 0.0


def test_prf_to_langsmith_scores_pass_true_is_1():
    scores = {"overall": {"precision": 1.0, "recall": 1.0, "f1": 1.0}, "pass": True}
    result = langsmith_eval.prf_to_langsmith_scores(scores)
    by_key = {r["key"]: r["score"] for r in result}
    assert by_key["pass"] == 1.0


# ─── make_prf_evaluator ───────────────────────────────────────────────────────

def _make_agent_output(rule_id: str, file: str, agent: str = "test_verification"):
    """AgentOutput·Issue Pydantic 모델을 Mock으로 대체."""
    issue = MagicMock()
    issue.rule_id = rule_id
    issue.file = file
    out = MagicMock()
    out.agent = agent
    out.issues = [issue]
    return out


def _make_run(outputs: dict):
    run = MagicMock()
    run.outputs = outputs
    return run


def _make_example(case_name: str, expected: dict):
    ex = MagicMock()
    ex.inputs = {"case_name": case_name}
    ex.outputs = {"expected": expected}
    return ex


def _make_expected(rule_id: str, file: str, agent: str = "test_verification") -> dict:
    key = "test_verification" if agent == "test_verification" else "performance"
    return {key: {"expected_issues": [{"rule_id": rule_id, "file": file}]}}


def test_make_prf_evaluator_returns_list_of_results():
    case = {
        "name": "c1",
        "expected": _make_expected("TEST-001", "(전체)"),
    }
    case_by_name = {"c1": case}
    agent_out = _make_agent_output("TEST-001", "(전체)")
    results_by_name = {"c1": [agent_out]}
    evaluator = langsmith_eval.make_prf_evaluator(case_by_name, results_by_name)
    run = _make_run({"outputs": [agent_out]})
    example = _make_example("c1", case["expected"])

    try:
        results = evaluator(run, example)
    except ImportError:
        pytest.skip("langsmith.evaluation not available")

    assert isinstance(results, list)
    assert len(results) > 0


def test_make_prf_evaluator_f1_score_correct():
    """TP=1 → precision=recall=f1=1.0."""
    case = {"name": "c1", "expected": _make_expected("TEST-001", "(전체)")}
    case_by_name = {"c1": case}
    agent_out = _make_agent_output("TEST-001", "(전체)")
    results_by_name = {"c1": [agent_out]}
    evaluator = langsmith_eval.make_prf_evaluator(case_by_name, results_by_name)
    run = _make_run({"outputs": [agent_out]})
    example = _make_example("c1", case["expected"])

    try:
        results = evaluator(run, example)
    except ImportError:
        pytest.skip("langsmith.evaluation not available")

    f1_result = next((r for r in results if r.key == "f1"), None)
    assert f1_result is not None
    assert f1_result.score == pytest.approx(1.0)


def test_make_prf_evaluator_unknown_case_returns_none_score():
    evaluator = langsmith_eval.make_prf_evaluator({}, {})
    run = _make_run({"outputs": []})
    example = _make_example("unknown", {})

    try:
        results = evaluator(run, example)
    except ImportError:
        pytest.skip("langsmith.evaluation not available")

    assert any(r.score is None for r in results)


# ─── run_detection_experiment ─────────────────────────────────────────────────

def _make_cases(n: int = 2) -> list[dict]:
    return [
        {"name": f"case_{i}", "kind": "positive",
         "expected": _make_expected("TEST-001", f"f{i}.py")}
        for i in range(n)
    ]


def test_run_detection_calls_run_case_fn_per_case():
    client = _fake_client(exists=True)
    client.evaluate.return_value = MagicMock()
    cases = _make_cases(3)
    call_log = []

    def fake_runner(case):
        call_log.append(case["name"])
        return []

    langsmith_eval.run_detection_experiment(client, cases, run_case_fn=fake_runner)
    assert len(call_log) == 3
    assert set(call_log) == {"case_0", "case_1", "case_2"}


def test_run_detection_calls_client_evaluate():
    client = _fake_client(exists=True)
    client.evaluate.return_value = MagicMock()
    cases = _make_cases(2)

    langsmith_eval.run_detection_experiment(
        client, cases, run_case_fn=lambda c: [])

    client.evaluate.assert_called_once()
    kwargs = client.evaluate.call_args
    # data 인자 = dataset name
    data_arg = kwargs[1].get("data") or (kwargs[0][1] if len(kwargs[0]) > 1 else None)
    assert data_arg == langsmith_eval.DATASET_8B


def test_run_detection_returns_scores():
    client = _fake_client(exists=True)
    client.evaluate.return_value = MagicMock()
    cases = _make_cases(1)

    result = langsmith_eval.run_detection_experiment(
        client, cases, run_case_fn=lambda c: [])

    assert "scores" in result
    assert "overall" in result["scores"]


def test_run_detection_experiment_prefix_passed():
    client = _fake_client(exists=True)
    client.evaluate.return_value = MagicMock()
    cases = _make_cases(1)

    langsmith_eval.run_detection_experiment(
        client, cases, run_case_fn=lambda c: [],
        experiment_prefix="test-prefix-8B")

    call_kwargs = client.evaluate.call_args[1]
    assert call_kwargs.get("experiment_prefix") == "test-prefix-8B"
