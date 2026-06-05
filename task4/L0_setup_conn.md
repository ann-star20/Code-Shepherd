---
source_of_truth:
  - task4.md
  - docs/PRD-langsmith.md
---
## L0: LangSmith 환경 설정 및 연결 검증

### SDD

**목표**: `APP_MODE=production` 전환 시 LangSmith SDK가 정상 연결되고 트레이싱이 활성화됨을 검증.

**환경변수 추가** (`.env.prod`):
```bash
LANGCHAIN_TRACING_V2=true
LANGCHAIN_ENDPOINT=https://api.smith.langchain.com
LANGCHAIN_API_KEY=ls__your_key_here
LANGCHAIN_PROJECT=kg-pipeline-prod
```

**연결 확인 스크립트**: `scripts/check_langsmith.py`
```python
from langsmith import Client

def check_connection() -> bool:
    """LangSmith 연결 상태 확인."""
    try:
        client = Client()
        projects = list(client.list_projects())
        return any(p.name == "kg-pipeline-prod" for p in projects)
    except Exception as e:
        print(f"LangSmith 연결 실패: {e}")
        return False
```

**`APP_MODE` 분기 확인** (`factory.py` 기존 코드):
```python
# APP_MODE=development → MockClient (LANGCHAIN_TRACING_V2=false 강제)
# APP_MODE=production  → GeminiClient (LANGCHAIN_TRACING_V2=true)
```

### TDD (AAA)

파일: `backend/tests/harness/test_langsmith_connection.py`

| ID | Arrange | Act | Assert |
|----|---------|-----|--------|
| T_L0_dev_tracing_off | `APP_MODE=development`, MockClient 생성 | `client.is_tracing_enabled()` | `False` |
| T_L0_prod_tracing_on | `APP_MODE=production`, GeminiClient mock | `client.is_tracing_enabled()` | `True` |
| T_L0_env_flag | `LANGCHAIN_TRACING_V2=false` | `os.environ.get(...)` | `"false"` (dev 모드 강제 확인) |
| T_L0_connection_script | `check_connection()` with mock Client | 함수 호출 | 프로젝트 이름 매칭 시 `True` 반환 |

```python
# T_L0_dev_tracing_off AAA 예시
def test_dev_mode_tracing_disabled():
    # Arrange
    from app.infrastructure.llm.mock_client import MockClient
    client = MockClient()

    # Act
    result = client.is_tracing_enabled()

    # Assert
    assert result is False
```

### COMMIT
```
chore(infra): add LangSmith env vars to env.prod and env.local docs
test(extractor): add L0 langsmith connection and APP_MODE tracing flag tests
feat(extractor): add check_langsmith.py connection verification script
```