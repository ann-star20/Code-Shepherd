# mixed_case_005 — 알림 서비스

## 포함 이슈

| rule_id | 함수 | 설명 |
|---------|------|------|
| PERF-002 | `send_bulk_notification` | 루프 내 DB 호출 |
| PERF-003 | `_sent_log` (전역) | 알림마다 리스트 누적 → 메모리 무한 증가 |
| TEST-001 | `retry_failed`, `get_sent_count` | 테스트 없음 → 커버리지 미달 |
| TEST-003 | `format_message` | None/빈 문자열 엣지케이스 없음 |

## 실행

```bash
pip install pytest pytest-cov
pytest tests/ --cov=app --cov-report=term-missing
```
