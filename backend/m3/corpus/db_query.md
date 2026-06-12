# [CONV-DB-004] 반복문 내 DB 쿼리 금지
- severity: Major
- 배경(사고 이력): 2025-06 대시보드 PR 1건 — 회원 목록 반복문 안의 ORM 조회(N+1)가 배포 직후 DB QPS 를 40배로 올려 읽기 복제본 커넥션이 고갈됐다.

## §1 규칙
반복문(`for`/`while`) 안에서 ORM 쿼리나 DB 호출을 실행해서는 안 된다 (N+1 패턴).
여러 건을 조회할 때는 반복문 밖에서 사내 데이터 접근 계층의 `repo.bulk_fetch()` 로 일괄 조회한다.

## §2 올바른 예시
```python
from common import repo

user_ids = [user.id for user in users]
orders_by_user = repo.bulk_fetch("orders", ids=user_ids)
```

## §3 잘못된 예시
```python
for user in users:
    orders = Order.objects.filter(user_id=user.id)   # 루프마다 쿼리 1회 — N+1 (2025-06 사고 패턴)
```

## §4 예외 조항
예외 없음. 대량 순회가 필요한 경우에도 `repo.bulk_fetch()` 의 chunk 옵션으로 일괄 처리한다.
