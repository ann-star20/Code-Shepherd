---
source_of_truth:
  - task4.md
  - docs/PRD-langsmith.md
---
## L5: 피드백 환류 스크립트 — 수정 빈도 분석 → 데이터셋 자동 추가

### SDD

**목표**: LangSmith에 누적된 HITL 피드백 중 수정 빈도가 높은 패턴을 분석하여 `extractor_schema_eval` 데이터셋에 자동으로 추가한다.

**파일**: `scripts/feedback_loop.py`

```python
from langsmith import Client
from collections import Counter

CORRECTION_THRESHOLD = 3  # 동일 패턴 3회 이상 수정 시 데이터셋 추가

def fetch_hitl_feedbacks(project: str, limit: int = 100) -> list[dict]:
    """LangSmith에서 hitl_correction 피드백 목록 조회."""
    client = Client()
    feedbacks = client.list_feedback(
        run_ids=None,
        feedback_key=["hitl_correction"],
        limit=limit,
    )
    return [
        {
            "run_id":  fb.run_id,
            "comment": fb.comment,
            "score":   fb.score,
        }
        for fb in feedbacks if fb.score == 0
    ]

def analyze_correction_patterns(feedbacks: list[dict]) -> list[dict]:
    """
    수정 패턴 분석:
    - concept_domain 변경 (security → both 등) 집계
    - 빈도 CORRECTION_THRESHOLD 이상 → 데이터셋 추가 후보
    """
    patterns = Counter()
    for fb in feedbacks:
        comment = fb.get("comment", "")
        if "concept_domain" in comment:
            patterns["domain_correction"] += 1
        if "description_ko" in comment:
            patterns["translation_correction"] += 1
    return [
        {"pattern": k, "count": v}
        for k, v in patterns.items()
        if v >= CORRECTION_THRESHOLD
    ]

def add_to_dataset(run_id: str, dataset_name: str) -> None:
    """해당 Run의 입출력을 데이터셋에 골든 예시로 추가."""
    client = Client()
    run = client.read_run(run_id)
    dataset = client.read_dataset(dataset_name=dataset_name)
    client.create_example(
        inputs=run.inputs,
        outputs=run.outputs,
        dataset_id=dataset.id,
        metadata={"source": "hitl_feedback_loop", "run_id": run_id},
    )

def run_feedback_loop(project: str = "kg-pipeline-prod") -> dict:
    """
    전체 피드백 루프 실행.
    반환: {"analyzed": N, "added_to_dataset": M, "patterns": [...]}
    """
    feedbacks = fetch_hitl_feedbacks(project)
    patterns  = analyze_correction_patterns(feedbacks)
    added = 0
    for fb in feedbacks[:10]:   # 최대 10개 자동 추가
        add_to_dataset(fb["run_id"], "extractor_schema_eval_v1")
        added += 1
    return {"analyzed": len(feedbacks), "added_to_dataset": added, "patterns": patterns}
```

**실행 스케줄** (주 1회 cron 또는 수동):
```bash
python scripts/feedback_loop.py --project kg-pipeline-prod
```

### TDD (AAA)

파일: `backend/tests/harness/test_feedback_loop.py`

| ID | Arrange | Act | Assert |
|----|---------|-----|--------|
| T_L5_fetch_feedbacks | mock `list_feedback` → 5개 score=0 | `fetch_hitl_feedbacks("proj")` | 길이 5 반환 |
| T_L5_filter_score | mock feedbacks 중 score=1도 포함 | `fetch_hitl_feedbacks(...)` | score=0 만 반환 |
| T_L5_pattern_domain | feedbacks 4개 모두 `"concept_domain"` 포함 | `analyze_correction_patterns(feedbacks)` | `[{"pattern":"domain_correction","count":4}]` |
| T_L5_below_threshold | feedbacks 2개 (threshold=3) | `analyze_correction_patterns(feedbacks)` | 빈 리스트 `[]` |
| T_L5_add_to_dataset | mock `read_run`, `create_example` | `add_to_dataset("run-id", "dataset")` | `create_example` 1회 호출 |
| T_L5_full_loop | mock 10개 feedbacks, 2개 패턴 | `run_feedback_loop("proj")` | `added_to_dataset >= 1`, `patterns` 포함 |

```python
# T_L5_pattern_domain AAA 예시
def test_analyze_domain_correction_pattern():
    # Arrange
    feedbacks = [
        {"run_id": f"r{i}", "comment": "before: concept_domain=security after: concept_domain=both", "score": 0}
        for i in range(4)
    ]

    # Act
    patterns = analyze_correction_patterns(feedbacks)

    # Assert
    domain_patterns = [p for p in patterns if p["pattern"] == "domain_correction"]
    assert len(domain_patterns) == 1
    assert domain_patterns[0]["count"] == 4
```

### COMMIT
```
test(extractor): add L5 feedback loop fetch analyze add_to_dataset full loop tests
feat(extractor): implement feedback_loop.py with pattern analysis and auto dataset update
```
