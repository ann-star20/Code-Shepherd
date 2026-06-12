# [CONV-SQL-008] 문자열 조립 SQL 금지
- severity: Major
- 배경(사고 이력): 2024-07 모의해킹 — 검색 API 의 f-string SQL 조립 한 곳이 SQL 인젝션 가능 지점으로 지적됐다.

## §1 규칙
SQL 문자열을 f-string, `%` 포맷, 문자열 연결(`+`)로 조립해서는 안 된다.
모든 SQL 실행은 사내 `db.safe_query()` 를 강제한다. `db.safe_query()` 는 파라미터 바인딩(`:이름`)만 허용하고 조립된 동적 문자열을 거부한다.

## §2 올바른 예시
```python
from common import db

rows = db.safe_query(
    "SELECT id, name FROM products WHERE category = :category",
    category=category,
)
```

## §3 잘못된 예시
```python
query = f"SELECT * FROM products WHERE name LIKE '%{keyword}%'"   # 인젝션 가능 (2024-07 지적 패턴)
cursor.execute(query)
```

## §4 예외 조항
예외 없음. 마이그레이션·관리 스크립트도 동일하게 적용한다.
