---
source_of_truth:
  - task4.md
  - docs/PRD-langsmith.md 
  - docs/PRD-qa.md
---
## L2: Pre-Eval 실행 스크립트 — 스키마 이탈률 0% 게이트

### SDD

**목표**: 프롬프트 후보를 LangSmith 데이터셋으로 평가하여 스키마 이탈률 0%를 달성한 버전만 승인.

**파일**: `scripts/run_pre_eval.py`

```python
from langsmith import Client
from langsmith.evaluation import evaluate
from app.infrastructure.llm.gemini_client import GeminiClient
from app.domain.models import ConceptExtractionSchema
import json

def schema_compliance_evaluator(run, example) -> dict:
    """스키마 이탈 여부 평가 — 이탈 시 score=0, 통과 시 score=1."""
    try:
        output = run.outputs.get("concepts", [])
        for concept in output:
            ConceptExtractionSchema(**concept)  # Pydantic 검증
        return {"key": "schema_compliance", "score": 1}
    except Exception as e:
        return {"key": "schema_compliance", "score": 0, "comment": str(e)}

def domain_accuracy_evaluator(run, example) -> dict:
    """concept_domain 분류 정확도 평가."""
    expected = example.outputs.get("concepts", [{}])[0].get("concept_domain")
    actual   = (run.outputs.get("concepts", [{}]) or [{}])[0].get("concept_domain")
    return {
        "key": "domain_accuracy",
        "score": 1 if expected == actual else 0
    }

def run_pre_eval(prompt_version: str) -> dict:
    """
    반환:
      {"schema_compliance": 1.0, "domain_accuracy": 0.97, "passed": True}
    schema_compliance < 1.0 → passed=False (이탈률 0% 미달성)
    domain_accuracy < 0.95  → passed=False
    """
    client = Client()
    results = evaluate(
        target=lambda inputs: gemini_extract(inputs["text_chunk"]),
        data="extractor_schema_eval_v1",
        evaluators=[schema_compliance_evaluator, domain_accuracy_evaluator],
        experiment_prefix=f"pre_eval_{prompt_version}",
        client=client,
    )
    schema_score = results.to_pandas()["schema_compliance"].mean()
    domain_score = results.to_pandas()["domain_accuracy"].mean()
    passed = schema_score == 1.0 and domain_score >= 0.95
    return {
        "schema_compliance": schema_score,
        "domain_accuracy": domain_score,
        "passed": passed,
    }
```

**CI 게이트** (`.github/workflows/ci.yml`에 추가):
```yaml
- name: LangSmith Pre-Eval Gate
  if: github.event_name == 'push' && github.ref == 'refs/heads/main'
  run: |
    python scripts/run_pre_eval.py --version ${{ github.sha }}
  env:
    LANGCHAIN_API_KEY: ${{ secrets.LANGCHAIN_API_KEY }}
    GEMINI_API_KEY: ${{ secrets.GEMINI_API_KEY }}
```

### TDD (AAA)

파일: `backend/tests/harness/test_pre_eval.py`

| ID | Arrange | Act | Assert |
|----|---------|-----|--------|
| T_L2_compliance_pass | 유효한 ConceptExtractionSchema JSON | `schema_compliance_evaluator(run, example)` | `score == 1` |
| T_L2_compliance_fail | 필수 필드(`concept_domain`) 누락 JSON | `schema_compliance_evaluator(run, example)` | `score == 0` |
| T_L2_domain_match | expected `"security"`, actual `"security"` | `domain_accuracy_evaluator(run, example)` | `score == 1` |
| T_L2_domain_mismatch | expected `"security"`, actual `"performance"` | `domain_accuracy_evaluator(run, example)` | `score == 0` |
| T_L2_passed_flag | `schema_compliance=1.0`, `domain_accuracy=0.97` | `run_pre_eval(...)` mock 결과 | `passed == True` |
| T_L2_failed_schema | `schema_compliance=0.95` | `run_pre_eval(...)` mock 결과 | `passed == False` |

```python
# T_L2_compliance_fail AAA 예시
def test_schema_compliance_fail_on_missing_field():
    # Arrange — concept_domain 누락
    bad_output = {"concept_name": "XSS", "description_ko": "설명"}
    mock_run = MagicMock()
    mock_run.outputs = {"concepts": [bad_output]}
    mock_example = MagicMock()

    # Act
    result = schema_compliance_evaluator(mock_run, mock_example)

    # Assert
    assert result["score"] == 0
    assert "comment" in result
```

### COMMIT
```
test(extractor): add L2 pre-eval schema compliance and domain accuracy evaluator tests
feat(extractor): implement run_pre_eval.py with langsmith evaluate and CI gate
chore(infra): add LangSmith pre-eval gate step to github actions workflow
```
