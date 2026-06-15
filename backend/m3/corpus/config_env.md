# [CONV-CFG-007] os.getenv 직접 호출 금지
- severity: Minor
- 배경(사고 이력): 2025-08 스테이징 키 프로드 배포 — `os.getenv()` 의 기본값 폴백이 누락된 프로드 키 대신 스테이징 키를 조용히 사용했고, 외부 결제 요청이 스테이징 게이트웨이로 나갔다.

## §1 규칙
서비스 코드에서 `os.getenv()` 나 `os.environ` 을 직접 읽어서는 안 된다.
환경설정은 검증 로더 `config.from_env()` 만 사용한다. 이 로더는 필수 키가 없으면 기동 시점에 실패한다 (fail fast — 잘못된 기본값으로 조용히 진행하지 않는다).

## §2 올바른 예시
```python
from common import config

settings = config.from_env()
api_key = settings.payment_api_key
```

## §3 잘못된 예시
```python
import os

api_key = os.getenv("PAYMENT_API_KEY", "stg-key-fallback")   # 조용한 폴백 (2025-08 사고 패턴)
```

## §4 예외 조항
`common/config` 모듈 내부 구현만 `os.environ` 에 접근할 수 있다. 그 외 경로는 예외 없음.
