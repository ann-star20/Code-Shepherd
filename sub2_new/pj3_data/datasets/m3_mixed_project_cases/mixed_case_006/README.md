# mixed_case_006 — 대시보드 분석 서비스

## 포함 이슈

| rule_id | 함수 | 설명 |
|---------|------|------|
| PERF-001 | `rank_users` | 이중 루프 O(n²) |
| PERF-002 | `load_metrics` | 루프 내 DB 호출 |
| TEST-004 | `export_pdf`, `archive_dashboard` | 테스트 자체 없음 |
| PERF-003 | `_event_log` (전역) | 모든 액션마다 리스트 누적 → 메모리 무한 증가 |

## 실행

```bash
pip install pytest pytest-cov
pytest tests/ --cov=app --cov-report=term-missing
```
