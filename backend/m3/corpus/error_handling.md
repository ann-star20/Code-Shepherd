# [CONV-ERR-006] 예외 무음 삼킴 금지
- severity: Major
- 배경(사고 이력): 2025-01 결제 실패 4시간 무음 — PG 콜백 처리의 `except: pass` 가 응답 오류를 삼켜 장애 알림이 0건이었고, 4시간 동안 결제 실패가 누적됐다.

## §1 규칙
bare `except:` 를 사용해서는 안 되며, 잡은 예외를 보고 없이 `pass` 로 삼켜서는 안 된다.
예외를 잡으면 반드시 `errors.report(err_code=..., exc=...)` 로 보고한 뒤 처리(재발생 또는 대체 동작)를 결정한다.

## §2 올바른 예시
```python
from common import errors

try:
    gateway.confirm(tx_id, amount)
except GatewayTimeout as exc:
    errors.report(err_code="PG_TIMEOUT", exc=exc)
    raise
```

## §3 잘못된 예시
```python
try:
    gateway.confirm(tx_id, amount)
except Exception:
    pass   # 실패가 어디에도 남지 않는다 (2025-01 사고 패턴)
```

## §4 예외 조항
예외 없음.
