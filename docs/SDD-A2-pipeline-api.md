# A2 SDD — Pipeline API 완성 설계

## 현재 상태 (AS-IS)

| 엔드포인트 | 상태 | 비고 |
|-----------|------|------|
| `POST /api/documents` | ✅ 구현 | URL → doc_id 생성 |
| `POST /api/documents/{doc_id}/prescan` | ✅ 구현 | framework/version 추론 |
| `POST /api/pipeline/trigger` | ✅ 구현 | Celery 큐 적재 |
| `GET /api/pipeline/logs/{session_id}` | ❌ 미구현 | 프론트 폴링 불가 |
| `GET /api/staging/{session_id}` | 확인 필요 | staging.py 경로 점검 |

## 목표 (TO-BE)

### 추가할 엔드포인트

#### `GET /api/pipeline/logs/{session_id}`

```json
{
  "session_id": "uuid",
  "doc_state": "CRAWLING",
  "logs": [
    { "ts": "2026-06-06T12:00:00Z", "agent": "Crawler", "level": "INFO", "message": "크롤링 시작" }
  ]
}
```

- `pipeline_logs` 테이블에서 `session_id` 조회
- `documents.state` JOIN → `doc_state` 실시간 반영
- 프론트엔드 2초 폴링 사용

#### `GET /api/staging/{session_id}` (경로 통일)

```json
{
  "session_id": "uuid",
  "concepts": [
    { "id": 1, "state": "DRAFT", "concept_json": { "concept_name": "XSS", ... } }
  ],
  "diff": { "draft": 3, "approved": 1, "committed": 0 }
}
```

### 프론트엔드 연동 흐름

```
[URL 입력]  POST /api/documents { urls: [...] }
             → { documents: [{ doc_id }] }

[Prescan]   POST /api/documents/{doc_id}/prescan
             → { framework, version, lang, infer_confidence }

[트리거]    POST /api/pipeline/trigger { doc_id }
             → { session_id }

[폴링]      GET /api/pipeline/logs/{session_id}  ← 2초마다
             doc_state == "EXTRACTED" → 폴링 중단, HITL 게이트 오픈

[HITL]      GET /api/staging/{session_id}
             개별 PATCH /approve, 최종 POST /commit

[완료 폴링] GET /api/pipeline/logs/{session_id}
             doc_state == "COMMITTED" → 완료
```

## TDD 구현 순서

### Step 1 — 테스트 먼저 작성

`tests/harness/test_pipeline_logs_api.py`:
- `test_logs_returns_pipeline_log_rows`
- `test_logs_includes_doc_state`
- `test_logs_empty_for_unknown_session`

### Step 2 — 엔드포인트 구현 → GREEN

`interfaces/api/pipeline.py`에 `GET /logs/{session_id}` 추가

### Step 3 — Staging 경로 확인

`staging.py` `GET /{session_id}` 경로 존재 확인 → 없으면 추가

### Step 4 — 프론트엔드 연동

`MainPage.tsx` 시뮬레이션 → 실제 `fetch()` 교체

## Mock 모드 실행 명령

```bash
# mock 모드 (Neo4j 없음, APP_MODE=mock)
docker compose -f docker-compose.yml -f docker-compose.mock.yml up postgres redis backend celery_worker

# 전체 스택
docker compose up
```
