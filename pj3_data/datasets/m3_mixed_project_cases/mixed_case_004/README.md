# mixed_case_004 — 데이터 파이프라인

## 포함 이슈

| rule_id | 함수 | 설명 |
|---------|------|------|
| PERF-001 | `cross_join_records` | 이중 루프 O(n*m) |
| TEST-003 | `normalize`, `filter_outliers` | min==max/빈 리스트/경계값 테스트 없음 |
| TEST-004 | `export_csv`, `load_from_json` | 테스트 자체 없음 |

## 실행

```bash
pip install pytest pytest-cov
pytest tests/ --cov=app --cov-report=term-missing
```
