# mixed_case_001 — 주문 서비스

## 포함 이슈

| rule_id | 함수 | 설명 |
|---------|------|------|
| PERF-001 | `find_duplicate_orders` | 이중 루프 O(n²) |
| PERF-002 | `load_orders_with_items` | 루프 내 DB 호출 2회 |
| TEST-001 | `calculate_discount`, `apply_coupon` | 테스트 없음 → 커버리지 미달 |

## 실행

```bash
pip install pytest pytest-cov
pytest tests/ --cov=app --cov-report=term-missing
```
