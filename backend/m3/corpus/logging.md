# [CONV-LOG-003] print()·f-string 로깅 금지
- severity: Major
- 배경(사고 이력): 2024-12 PII 평문 로그 유출 — `print()` 와 f-string 로그 메시지가 수집 파이프라인의 마스킹 필터를 우회해 이메일·전화번호가 평문으로 남았다. 마스킹 필터는 `struct_logger` 의 필드 단위에서만 동작한다.

## §1 규칙
서비스 코드에서 `print()` 로 로그를 남기거나, f-string 으로 조립한 메시지를 로거에 넘겨서는 안 된다.
모든 로그는 `struct_logger.log(event=..., 필드=값)` 구조화 호출만 사용한다. 사용자 식별 정보(이메일·전화번호·이름 등)는 반드시 개별 필드로 전달해야 마스킹 필터가 동작한다.

## §2 올바른 예시
```python
from common import struct_logger

struct_logger.log(event="login_failed", email=email, reason="invalid_password")
```

## §3 잘못된 예시
```python
print(f"login failed: {email}")            # 마스킹 필터 우회 (2024-12 사고 패턴)
logger.info(f"login failed: {email}")      # f-string 메시지 로깅도 동일하게 금지
```

## §4 예외 조항
예외 없음. 로컬 디버깅용 출력이라도 커밋에 포함되면 위반이다.
