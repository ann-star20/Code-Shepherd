---
description: Red→Green→Refactor TDD 사이클을 안내하고 테스트 파일을 먼저 작성합니다.
---

TDD 사이클로 기능을 구현합니다.

## 사용법

`/tdd [기능명]`

예: `/tdd embedding_service`
예: `/tdd context_builder`
예: `/tdd redis_cache`

---

## 실행 순서

### Step 1 — Red: 테스트 먼저 작성

1. `tests/unit/test_<기능명>.py` 파일을 생성 (구현 없이 테스트만)
2. 테스트가 실패하는지 확인: `pytest tests/unit/test_<기능명>.py -v`
3. 커밋:
   ```
   test(<기능명>): RED - <무엇을 검증하는지> 테스트 작성
   ```

### Step 2 — Green: 최소 구현으로 통과

1. 테스트를 통과시킬 최소한의 코드만 구현
2. 테스트 통과 확인: `pytest tests/unit/test_<기능명>.py -v`
3. 커밋:
   ```
   feat(<기능명>): GREEN - 테스트 통과
   ```

### Step 3 — Refactor: 코드 품질 개선

1. 동작은 유지하면서 코드 구조 개선
2. 테스트 여전히 통과 확인
3. 커밋:
   ```
   refactor(<기능명>): REFACTOR - <무엇을 개선했는지>
   ```

### Step 4 — 커버리지 확인

```bash
pytest tests/ --cov=src --cov-report=term-missing --cov-fail-under=80
```

80% 미달 시 추가 테스트 작성 후 재확인.

---

## 테스트 작성 가이드

```python
# tests/unit/test_<기능명>.py
import pytest
from unittest.mock import MagicMock, patch

# 외부 API는 반드시 모킹
@pytest.fixture
def mock_openai():
    with patch("src.services.embedding_service.openai") as mock:
        mock.embeddings.create.return_value = MagicMock(
            data=[MagicMock(embedding=[0.1] * 1536)]
        )
        yield mock

def test_<기능>_성공_케이스(mock_openai):
    # Arrange
    ...
    # Act
    result = ...
    # Assert
    assert result == expected
```
