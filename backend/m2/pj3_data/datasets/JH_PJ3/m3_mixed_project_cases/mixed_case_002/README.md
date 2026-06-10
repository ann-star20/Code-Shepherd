# mixed_case_002 — 유저 프로필 서비스

## 포함 이슈

| rule_id | 함수 | 설명 |
|---------|------|------|
| TEST-003 | `get_profile`, `update_bio` | None/경계값 테스트 없음 |
| TEST-004 | `update_avatar`, `delete_account` | 테스트 자체 없음 |
| PERF-003 | `_request_log` (전역) | 요청마다 리스트 누적 → 메모리 무한 증가 |

## 실행

```bash
pip install pytest pytest-cov
pytest tests/ --cov=app --cov-report=term-missing
```
