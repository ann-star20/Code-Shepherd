---
source_of_truth:
  - task4.md
  - docs/PRD-langsmith.md
---
## L3: GeminiClient @traceable 래핑 — 프로덕션 트레이싱

### SDD

**목표**: `APP_MODE=production`일 때 모든 Gemini API 호출이 LangSmith Run으로 자동 기록된다.

**파일 수정**: `backend/app/infrastructure/llm/gemini_client.py`

```python
from langsmith import traceable, get_current_run_tree

class GeminiClient(ILLMClient):

    @traceable(
        name="extractor_agent",
        tags=["extractor"],
        metadata={"model": "gemini-2.5-flash"}
    )
    async def extract_concepts(
        self, text_chunk: str, doc_id: str, metadata: dict
    ) -> list[ConceptExtractionSchema]:
        response = await self._model.generate_content_async(
            self._build_prompt(text_chunk, metadata)
        )
        # 토큰 수 메타데이터 Run에 추가
        run_tree = get_current_run_tree()
        if run_tree:
            usage = response.usage_metadata
            run_tree.extra["metadata"].update({
                "prompt_tokens":     usage.prompt_token_count,
                "completion_tokens": usage.candidates_token_count,
                "total_tokens":      usage.total_token_count,
                "doc_id":            doc_id,
                "framework":         metadata.get("framework", "unknown"),
            })
        return self._parse_response(response.text)

    def is_tracing_enabled(self) -> bool:
        return True
```

**트레이싱 범위** (PRD-lansmith §3.10.3):

| 에이전트 | LangSmith 태그 | 추적 데이터 |
|----------|---------------|------------|
| Extractor Agent | `["extractor", doc_id]` | 프롬프트·출력·토큰·지연 |
| Link Resolver Agent | `["resolver", concept_name]` | 유사도 판단 입출력 |

### TDD (AAA)

파일: `backend/tests/harness/test_gemini_tracing.py`

| ID | Arrange | Act | Assert |
|----|---------|-----|--------|
| T_L3_traceable_decorator | `GeminiClient.extract_concepts` 함수 | `hasattr(func, "__wrapped__")` 또는 langsmith 메타 확인 | `@traceable` 래핑됨 |
| T_L3_run_tree_metadata | mock `get_current_run_tree()` 반환 mock run | `extract_concepts(chunk, doc_id, meta)` | run_tree.extra["metadata"]["doc_id"] == doc_id |
| T_L3_token_recorded | mock response with `usage_metadata` | `extract_concepts(...)` | `prompt_tokens` 메타데이터 기록 |
| T_L3_is_tracing_true | `GeminiClient` 인스턴스 | `client.is_tracing_enabled()` | `True` |
| T_L3_mock_tracing_false | `MockClient` 인스턴스 | `client.is_tracing_enabled()` | `False` |

```python
# T_L3_run_tree_metadata AAA 예시
@patch("app.infrastructure.llm.gemini_client.get_current_run_tree")
async def test_run_tree_metadata_recorded(mock_get_run_tree):
    # Arrange
    mock_run = MagicMock()
    mock_run.extra = {"metadata": {}}
    mock_get_run_tree.return_value = mock_run

    client = GeminiClient.__new__(GeminiClient)
    client._model = AsyncMock()
    client._model.generate_content_async.return_value = mock_gemini_response()

    # Act
    await client.extract_concepts("chunk text", "EXT_test_abc12345", {"framework": "Django"})

    # Assert
    assert mock_run.extra["metadata"]["doc_id"] == "EXT_test_abc12345"
    assert "prompt_tokens" in mock_run.extra["metadata"]
```

### COMMIT
```
test(extractor): add L3 GeminiClient traceable decorator and run tree metadata tests
feat(extractor): add @traceable wrapping to GeminiClient with token and doc_id metadata
```