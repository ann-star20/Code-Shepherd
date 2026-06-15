# [CONV-PERF-009] 고비용 시간복잡도 직접 구현 금지
- severity: Major
- 배경(사고 이력): 2025-03 주문 목록 API PR 1건 — 정렬 로직에 이중 for 루프 버블소트를 직접 구현해 배포했고, 주문 건수가 10만 건을 넘은 시점에 평균 응답시간이 8초를 초과하며 SLA를 위반했다.

## §1 규칙
O(N²) 정렬·탐색을 직접 구현해서는 안 된다.
이중 for 루프 정렬, 리스트 내 반복 `in` 탐색, 버블소트·선택정렬 등의 직접 구현은 금지한다.
정렬은 `sorted()` / `list.sort()` (Python Timsort, O(N log N)), 탐색은 `set`/`dict` 변환 후 O(1) 조회로 대체한다.
대용량 데이터 정렬은 Python 계층이 아닌 DB `ORDER BY`에 위임한다.

## §2 올바른 예시
```python
# 정렬 — Timsort O(N log N)
orders_sorted = sorted(orders, key=lambda o: o.created_at, reverse=True)

# 탐색 — set 변환 후 O(1)
allowed_ids = set(allowed_list)
filtered = [item for item in items if item.id in allowed_ids]

# 대용량 정렬 — DB 위임
orders = Order.objects.filter(user_id=user_id).order_by('-created_at')
```

## §3 잘못된 예시
```python
# O(N²) 버블소트 직접 구현 (2025-03 사고 패턴)
for i in range(len(orders)):
    for j in range(len(orders) - i - 1):
        if orders[j].created_at < orders[j+1].created_at:
            orders[j], orders[j+1] = orders[j+1], orders[j]

# 리스트 선형 탐색 반복 호출 — O(N²)
for item in items:
    if item.id in allowed_list:   # allowed_list 가 list 이면 O(N)
        result.append(item)
```

## §4 예외 조항
교육·알고리즘 학습 목적의 모듈(`/examples/`, `/notebooks/`)에 한해 직접 구현을 허용하되, 프로덕션 코드 경로로 임포트되지 않아야 한다.
