---
source_of_truth:
  - task4.md
  - docs/PRD-arch.md
  - docs/PRD-langsmith.md
---
## L4: HITL 수정 피드백 기록 — `create_feedback()` 백엔드 연동

### SDD

**목표**: 관리자가 DRAFT 노드를 수정하고 승인할 때 수정 전/후 diff를 LangSmith 피드백으로 기록한다.

**파일**: `backend/app/usecases/record_hitl_feedback.py`

```python
from langsmith import Client
from dataclasses import dataclass

@dataclass
class HITLFeedback:
    run_id: str           # LangSmith Run ID (concept_snapshots.langsmith_run_id)
    session_id: str
    node_id: str
    before_json: dict     # 관리자 수정 전 concept_json
    after_json: dict      # 관리자 수정 후 concept_json

def record_hitl_feedback(feedback: HITLFeedback) -> None:
    """
    LangSmith에 HITL 수정 피드백 기록.
    score=0: 수정이 필요했던 출력 (품질 이슈 신호)
    comment: before/after diff JSON 문자열
    """
    client = Client()
    diff_comment = (
        f"before: {feedback.before_json}\n"
        f"after:  {feedback.after_json}"
    )
    client.create_feedback(
        run_id=feedback.run_id,
        key="hitl_correction",
        score=0,
        comment=diff_comment,
        source_info={
            "session_id": feedback.session_id,
            "node_id":    feedback.node_id,
        }
    )
```

**API 연동**: `backend/app/interfaces/api/staging.py`에 수정 감지 추가

```python
# PATCH /{session_id}/nodes/{node_id} 핸들러에서:
async def patch_node(session_id: str, node_id: str, body: PatchNodeRequest, ...):
    # 기존 concept_json 조회 (before)
    before = await get_staging_concept(conn, node_id)

    # 수정 적용
    await update_staging_concept(conn, node_id, body)

    # LangSmith 피드백 기록 (run_id 있을 때만)
    snapshot = await get_concept_snapshot(conn, node_id)
    if snapshot and snapshot.langsmith_run_id:
        record_hitl_feedback(HITLFeedback(
            run_id=snapshot.langsmith_run_id,
            session_id=session_id,
            node_id=node_id,
            before_json=before.concept_json,
            after_json=body.concept_json,
        ))
```

### TDD (AAA)

파일: `backend/tests/harness/test_hitl_feedback.py`

| ID | Arrange | Act | Assert |
|----|---------|-----|--------|
| T_L4_feedback_called | mock `langsmith.Client.create_feedback` | `record_hitl_feedback(feedback)` | `create_feedback` 1회 호출 |
| T_L4_score_zero | 임의 수정 피드백 | `record_hitl_feedback(feedback)` | `create_feedback` 호출 시 `score=0` |
| T_L4_run_id_passed | `run_id="run-abc-123"` | `record_hitl_feedback(feedback)` | `create_feedback(run_id="run-abc-123", ...)` |
| T_L4_diff_in_comment | `before={"x":1}`, `after={"x":2}` | `record_hitl_feedback(feedback)` | comment에 "before" and "after" 포함 |
| T_L4_no_run_id_skip | `snapshot.langsmith_run_id=None` | PATCH 핸들러 호출 | `create_feedback` 호출 0회 |

```python
# T_L4_feedback_called AAA 예시
@patch("app.usecases.record_hitl_feedback.Client")
def test_feedback_called_with_correct_params(mock_client_cls):
    # Arrange
    mock_client = MagicMock()
    mock_client_cls.return_value = mock_client

    feedback = HITLFeedback(
        run_id="run-abc-123",
        session_id="sid-001",
        node_id="node-001",
        before_json={"concept_domain": "security"},
        after_json={"concept_domain": "both"},
    )

    # Act
    record_hitl_feedback(feedback)

    # Assert
    mock_client.create_feedback.assert_called_once()
    kwargs = mock_client.create_feedback.call_args.kwargs
    assert kwargs["run_id"] == "run-abc-123"
    assert kwargs["score"] == 0
    assert "before" in kwargs["comment"]
    assert "after" in kwargs["comment"]
```

### COMMIT
```
test(extractor): add L4 HITL feedback record tests score run_id diff comment assertions
feat(extractor): implement record_hitl_feedback usecase and staging PATCH API integration
```