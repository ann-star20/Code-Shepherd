# [CONV-TIME-002] datetime.now() 직접 호출 금지
- severity: Major
- 배경(사고 이력): 2025-03 정산 이중집계 — 정산 서버 2대의 OS 타임존이 달라 `datetime.now()` 기준 집계 구간이 겹쳤고, 같은 거래가 두 번 집계됐다. 이후 시간 조회를 단일 유틸로 일원화했다.

## §1 규칙
서비스 코드에서 `datetime.now()` 와 `datetime.utcnow()` 를 직접 호출해서는 안 된다.
현재 시각이 필요하면 `common.timeutil.now()` 만 사용한다. 이 함수는 타임존을 UTC 로 고정하고 정산 기준 클럭과 동기화되어 있다.

## §2 올바른 예시
```python
from common.timeutil import now

window_end = now()
```

## §3 잘못된 예시
```python
from datetime import datetime

window_end = datetime.now()   # 서버 타임존에 따라 값이 달라진다 (2025-03 사고 패턴)
window_utc = datetime.utcnow()   # naive UTC — 정산 클럭과 어긋난다
```

## §4 예외 조항
예외 없음. 테스트 코드의 시간 고정도 `common.timeutil` 이 제공하는 freeze 유틸을 사용한다.
