"""
test_severity_eval.py — LangSmith evaluate() 기반 severity 판단 정확도 평가

실행 조건:
    LANGCHAIN_API_KEY 환경변수가 설정된 경우에만 실행된다.
    CI 환경에서는 자동 스킵 (비용 통제 — CLAUDE.md §7).

실행 방법:
    # LangSmith API 키를 환경변수로 설정 후 실행
    # (USE_MOCK_LLM=false 가 되어야 실제 LLM 평가가 의미있음)
    $env:LANGCHAIN_API_KEY="ls__xxxx"
    $env:USE_MOCK_LLM="false"
    $env:ANTHROPIC_API_KEY="sk-ant-xxxx"
    pytest dev2/tests/eval/test_severity_eval.py -v -s

평가 흐름:
    1. 골든 데이터셋 (GOLDEN_DATASET) 로드
    2. LangSmith evaluate() → 케이스별로 _severity_judge_adapter() 호출
    3. severity_accuracy evaluator → 예측값 vs 정답 비교 → 0/1 점수
    4. 정확도 = 평균 점수 (목표: 70% 이상)
    5. LangSmith 대시보드에 실험 결과 자동 기록 (시계열 추이 확인 가능)

LangSmith 대시보드 접속:
    https://smith.langchain.com → Projects → dev2-{본인 GitHub ID}
    실험명: "dev2-severity-judge-{타임스탬프}"

아키텍처 메모:
    - evaluate()는 동기 함수로 내부에서 이벤트 루프를 관리한다.
    - target_function(_severity_judge_adapter)은 동기 래퍼로 작성한다.
      → asyncio.run()으로 비동기 llm_judge_node를 호출.
    - Week 5 교체 포인트: 골든 데이터셋을 LangSmith Dataset으로 업로드하면
      data=GOLDEN_DATASET 대신 data="dev2-severity-golden" (데이터셋 이름) 사용 가능.
"""

import asyncio
import os
import pytest

# ── 조건: LANGCHAIN_API_KEY 있을 때만 LangSmith 평가 실행 (비용 통제, CLAUDE.md §7) ────
# 모듈 레벨 pytestmark는 사용하지 않음 — test_mock_mode_severity_passthrough는 항상 실행
_needs_langsmith = pytest.mark.skipif(
    not os.getenv("LANGCHAIN_API_KEY"),
    reason="LANGCHAIN_API_KEY 미설정 — LangSmith 평가 스킵 (CI 환경 정상 동작)",
)


# ── Adapter: 골든 데이터셋 입력 → Dev2State → llm_judge_node 호출 ───────────────
def _severity_judge_adapter(
    message: str,
    current_severity: str,
    developer_level: str,
    similar_cases: list,
) -> dict:
    """
    LangSmith evaluate()의 target_function으로 사용되는 동기 어댑터.

    역할:
        골든 데이터셋의 "inputs" dict를 Dev2State 형식으로 변환 후
        llm_judge_node를 호출한다. LangSmith evaluate()는 동기 함수를 기대하므로
        asyncio.run()으로 비동기 노드를 래핑한다.

    Args:
        message: 이슈 메시지 (golden_dataset.inputs.message)
        current_severity: CLI 도구 판단 severity
        developer_level: 개발자 레벨
        similar_cases: 유사 이슈 목록 (RAG context)

    Returns:
        {"severity": str} — LangSmith run.outputs에 매핑됨
        evaluator에서 run.outputs.get("severity")로 접근
    """
    from dev2.nodes.llm_judge import llm_judge_node
    from dev2.schema import Dev2State

    # 평가용 최소 Dev2State — llm_judge_node가 필요한 필드만 채움
    issue = {
        "severity": current_severity,
        "line": 0,
        "file": "eval_target.py",
        "message": message,
        "rule_id": "EVAL-001",
        "suggestion": "",
        "similar_issues": similar_cases,
    }

    state = Dev2State(
        # payload: llm_judge_node가 직접 사용하지 않음 (enriched 사용)
        payload={
            "task_id": "eval-golden-001",
            "pr_id": "0",
            "pr_diff": "",
            "developer": {
                "id": "eval-dev",
                "skill_level": developer_level,
                "tech_stack": ["python"],
            },
        },
        static_raw=[],
        security_raw=[],
        enriched=[issue],   # llm_judge_node는 enriched 필드를 읽음
        final_output=[],
        skill_level=developer_level,
    )

    # asyncio.run: 동기 컨텍스트에서 비동기 노드 실행
    # Note: pytest-asyncio가 있으면 이벤트 루프 충돌 가능 → asyncio.run() 사용
    result = asyncio.run(llm_judge_node(state))

    # llm_judge_node 반환: {"enriched": [judged_issue, ...]}
    judged_issues = result.get("enriched", [])
    if not judged_issues:
        return {"severity": current_severity}  # fallback: 원래 severity 유지

    return {"severity": judged_issues[0].get("severity", current_severity)}


# ── Evaluator: 정확도 채점 함수 ────────────────────────────────────────────────
def severity_accuracy(run, example) -> dict:
    """
    LangSmith evaluator 함수 — 예측값과 정답을 비교해 0 또는 1을 반환한다.

    Args:
        run:     LangSmith Run 객체 — target_function의 반환값이 run.outputs에 담김
                 → run.outputs == {"severity": "Critical"} 형태
        example: LangSmith Example 객체 — 골든 데이터셋의 "outputs" 값이 담김
                 → example.outputs == {"expected": "Critical"} 형태

    Returns:
        {"score": 1} (정답) 또는 {"score": 0} (오답)
        여러 케이스의 score 평균 = 정확도 (0.0 ~ 1.0)
    """
    predicted = run.outputs.get("severity")      # llm_judge_node가 판단한 severity
    expected = example.outputs.get("expected")   # 골든 데이터셋의 정답

    is_correct = predicted == expected
    return {
        "key": "severity_accuracy",
        "score": int(is_correct),
        "comment": f"예측={predicted} | 정답={expected} | {'✓' if is_correct else '✗'}",
    }


# ── 메인 평가 테스트 ─────────────────────────────────────────────────────────
@_needs_langsmith
def test_severity_accuracy():
    """
    LangSmith evaluate() 기반 severity 판단 정확도 측정.

    목표 정확도: 70% 이상 (5개 중 3.5개 이상 정답)
    실험 결과: LangSmith 대시보드 → Projects → dev2-{GitHub ID} 에서 확인

    Week 5 교체 포인트:
        USE_MOCK_LLM=false + 실제 API 키 환경에서 실행해야 의미있는 정확도가 측정됨.
        Mock 모드(USE_MOCK_LLM=true)에서는 항상 CLI severity를 유지하므로
        골든 데이터셋의 "업그레이드 케이스"(Major→Critical)는 0점이 나온다.
    """
    from langsmith import evaluate
    from dev2.tests.eval.golden_dataset import GOLDEN_DATASET, DATASET_VERSION

    print(f"\n[LangSmith Eval] 골든 데이터셋 버전: {DATASET_VERSION}")
    print(f"[LangSmith Eval] 케이스 수: {len(GOLDEN_DATASET)}개")
    print(f"[LangSmith Eval] USE_MOCK_LLM={os.getenv('USE_MOCK_LLM', 'true')}")

    # ── LangSmith evaluate() 실행 ─────────────────────────────────────────────
    # experiment_prefix: LangSmith 대시보드에서 이 이름으로 실험이 그룹화됨
    # 실험명 예시: "dev2-severity-judge-20260524-abc123"
    results = evaluate(
        _severity_judge_adapter,          # target: 골든 데이터셋 inputs → severity 반환
        data=GOLDEN_DATASET,              # 입력/정답 쌍 (inputs + outputs)
        evaluators=[severity_accuracy],   # 채점 함수
        experiment_prefix="dev2-severity-judge",
        # metadata: 실험 환경 정보 (대시보드에서 필터링 가능)
        metadata={
            "dataset_version": DATASET_VERSION,
            "use_mock_llm": os.getenv("USE_MOCK_LLM", "true"),
            "model_routing": "Critical=sonnet-4-6, Major=haiku-4-5, Minor=skip",
        },
    )

    # ── 결과 집계 ─────────────────────────────────────────────────────────────
    scores: list[float] = []
    for r in results:
        eval_results = r.get("evaluation_results", {}).get("results", [])
        for eval_result in eval_results:
            if hasattr(eval_result, "score") and eval_result.score is not None:
                scores.append(float(eval_result.score))

    if not scores:
        pytest.skip("평가 결과 없음 — LangSmith API 응답 없음 (네트워크 확인)")

    accuracy = sum(scores) / len(scores)
    correct_count = int(sum(scores))
    total_count = len(scores)

    print(f"\n[LangSmith Eval] 결과: {correct_count}/{total_count} 정답")
    print(f"[LangSmith Eval] Severity 판단 정확도: {accuracy * 100:.1f}%")
    print(f"[LangSmith Eval] LangSmith 대시보드에서 시계열 추이 확인 가능")

    # ── 품질 게이팅: 70% 미달 시 머지 차단 ──────────────────────────────────
    assert accuracy >= 0.7, (
        f"Severity 판단 정확도 {accuracy * 100:.1f}% < 70% 기준 미달\n"
        f"프롬프트(dev2/prompts/severity_judge.py) 개선 또는 모델 업그레이드 필요\n"
        f"USE_MOCK_LLM=true 상태라면 false로 전환 후 재실행"
    )


# ── 추가: Mock 모드 정확도 측정 (LangSmith 없이도 실행 가능) ──────────────────
# @pytest.mark.skipif 조건이 없으므로 항상 실행됨
# Mock 모드에서는 CLI severity를 그대로 유지 → 업그레이드 케이스는 0점
def test_mock_mode_severity_passthrough():
    """
    Mock 모드(USE_MOCK_LLM=true)에서 severity passthrough 동작 검증.

    Mock은 CLI 판단을 그대로 유지하므로:
    - Minor 이슈 → Minor 유지 ✓ (정답)
    - Major → Critical 기대 케이스 → Major 유지 ✗ (Mock 한계, 실제 LLM 필요)

    이 테스트는 Mock 모드의 동작 특성을 문서화하는 역할이다.
    LangSmith API 없이도 CI에서 실행된다.
    """
    import asyncio
    from dev2.nodes.llm_judge import _get_mock_response

    # Mock 응답은 항상 입력 severity를 그대로 반환한다
    for severity in ("Critical", "Major", "Minor"):
        mock_result = _get_mock_response(severity)
        assert mock_result["severity"] == severity, (
            f"Mock 응답이 severity를 변경함: {severity} → {mock_result['severity']}"
        )
        assert "[MOCK]" in mock_result["suggestion"]

    print("\n[Mock 검증] Mock LLM이 CLI severity를 그대로 유지함을 확인")
    print("[Mock 검증] 실제 정확도 측정은 USE_MOCK_LLM=false + LANGCHAIN_API_KEY 필요")
