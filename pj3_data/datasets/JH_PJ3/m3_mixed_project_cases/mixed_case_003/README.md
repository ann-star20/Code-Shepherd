# mixed_case_003 — 리포트 서비스

## 포함 이슈

| rule_id | 함수 | 설명 |
|---------|------|------|
| PERF-002 | `generate_report` | 루프 내 DB 호출 2회 |
| TEST-001 | `summarize`, `export_csv` | 테스트 없음 → 커버리지 미달 |
| PERF-003 | `_report_cache` (전역) | dept_id마다 캐시 누적 → 메모리 무한 증가 |

## 실행

```bash
pip install pytest pytest-cov
pytest tests/ --cov=app --cov-report=term-missing
```
