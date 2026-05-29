# Dev2 팀 연동 가이드

**작성일**: 2026-05-29
**대상**: Dev1, Dev4

---

## 1. Dev1 → Dev2 연결

Dev1이 `POST /scan`을 이렇게 호출해야 합니다.

### 요청 형식

```python
POST http://[Dev2_서버_주소]/scan
Content-Type: application/json

{
  "task_id": "uuid-001",
  "pr_id": "42",
  "pr_diff": "diff --git a/auth.py b/auth.py\n+query = f'SELECT * FROM users WHERE id = {user_id}'",
  "developer": {
    "id": "junior_dev_01",
    "skill_level": "junior",
    "tech_stack": ["python", "fastapi"]
  },
  "context": {
    "architecture_docs": [],
    "coding_conventions": "",
    "previous_pr_issues": []
  }
}
```

### 응답

```json
HTTP 202 Accepted
{"status": "accepted", "task_id": "uuid-001"}
```

> **주의**: 202는 "접수 완료"이지 "분석 완료"가 아닙니다.
> 분석은 백그라운드에서 실행되므로 Dev1은 응답을 받은 뒤 기다릴 필요 없습니다.

### Dev1이 알아야 할 것

- Dev2 서버 주소 + 포트 (현재 로컬: `http://localhost:8005`)
- `pr_diff`는 unified diff 형식 문자열 (`+` 줄이 새로 추가된 코드)
- `skill_level`은 `"junior" | "mid" | "senior"` 중 하나
- `task_id`는 UUID — Dev1이 생성해서 넘겨줌

---

## 2. Dev2 → Dev4 연결

분석 완료 후 Critical 이슈 발생 시 Dev2의 `escalate` 노드가 Dev4 webhook으로 자동 전송합니다.

### Dev4에 보내는 데이터 형식 (Output Contract)

```json
POST http://[Dev4_서버_주소]/eval
Content-Type: application/json

{
  "task_id": "uuid-001",
  "agent": "security_scan",
  "issues": [
    {
      "severity": "Critical",
      "line": 12,
      "file": "auth.py",
      "message": "SQL 인젝션 가능성",
      "rule_id": "B608",
      "suggestion": "파라미터화된 쿼리 사용",
      "similar_issues": [
        {"pr_id": "PR-002", "similarity": 0.92, "message": "SQL 파라미터 미처리"}
      ]
    }
  ],
  "summary": {"critical": 1, "major": 0, "minor": 0},
  "execution_ms": 1200
}
```

> Critical이 없으면 Dev4 webhook 호출 없음. Dev4는 `GET /insights`로 결과 조회.

### Dev4가 알아야 할 것

- Dev2의 insights API 주소
  - `GET /insights/developer/{developer_id}` — 개발자별 이슈 이력
  - `GET /insights/team` — 팀 Top5 반복 이슈
  - `GET /insights/trends` — 주간 severity 추이
- `"agent"` 필드 값: `"static_analysis"` 또는 `"security_scan"`
- `"verdict"` 결정은 Dev4가 담당 — Dev2는 이슈 데이터만 생성

---

## 3. 연결 시 .env 변경 사항 (코드 변경 없음)

```bash
# Dev2의 .env 파일에서 아래만 교체하면 됩니다

# Dev4 서버 주소 (Dev4한테 받아서 입력)
DEV4_WEBHOOK_URL=http://[Dev4_실제_주소]/eval

# LLM 실제 사용 (데모 때 false로 변경)
USE_MOCK_LLM=false

# DB (Cloud SQL로 전환 시)
DATABASE_URL=postgresql+asyncpg://dev2:dev2@localhost:5432/dev2_db
```

---

## 4. 전체 흐름 요약

```
Dev1                    Dev2                    Dev4
  │                       │                       │
  │  POST /scan           │                       │
  │  (TaskPayload JSON)   │                       │
  │──────────────────────▶│                       │
  │  202 Accepted         │                       │
  │◀──────────────────────│                       │
  │                       │  (백그라운드 분석 중)    │
  │                       │                       │
  │                       │  Critical 발견 시       │
  │                       │  POST /eval            │
  │                       │  (AgentOutput JSON)    │
  │                       │──────────────────────▶│
  │                       │                       │
  │                       │  Dev4 결과 조회 시      │
  │                       │◀── GET /insights ─────│
```

---

## 5. 현재 MVP 테스트 방법 (팀 연동 전)

Dev1/Dev4 없이 Dev2 단독으로 테스트:

```bash
# 1. DB 시작
cd sub2_new/dev2
docker context use default
docker compose up -d postgres

# 2. 서버 시작
cd sub2_new
DATABASE_URL="postgresql+asyncpg://dev2:dev2@localhost:5432/dev2_db" \
USE_MOCK_LLM=true \
ANTHROPIC_API_KEY=sk-ant-dummy \
LANGCHAIN_TRACING_V2=false \
python -m uvicorn dev2.main:app --port 8005

# 3. 스캔 실행
curl -X POST http://localhost:8005/scan/mock-bandit

# 4. 결과 조회
curl http://localhost:8005/insights/developer/dev2
curl http://localhost:8005/insights/team
```
