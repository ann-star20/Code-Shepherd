# m1 — 오케스트레이터

**담당 범위**: GitHub PR 웹훅 수신 → HMAC 검증 → 결정적 라우팅 → 모듈 호출 → 트레이스 로깅.

## 실행법

```bash
docker compose up m1
```

## 테스트

```bash
uv run pytest tests/ --cov=app --cov-report=term-missing
```

커버리지 게이트: **≥ 80%**

## 라우팅 규칙 (결정적)

| 트리거 | 호출 모듈 |
|--------|-----------|
| `POST /triggers/pr` | m2(static) → m2(security) → m3(tests) → m3(perf) → m4(evaluate) |
| `POST /triggers/document` | m0(ingest) |

## 트레이스 로깅

각 모듈 호출마다 structlog JSON으로 기록:
```json
{
  "event": "module_call",
  "module": "m2",
  "endpoint": "/analyze/static",
  "status": 200,
  "elapsed_ms": 120,
  "trace_id": "uuid",
  "task_id": "uuid"
}
```

## 확장 지점

- `app/routers/triggers.py`: 새 트리거 타입 추가
- `app/clients/module_clients.py`: 새 모듈 클라이언트 추가
- `shared/contracts.py`: 새 DTO 추가 (계약 변경 시 전체 팀 합의 필요)
