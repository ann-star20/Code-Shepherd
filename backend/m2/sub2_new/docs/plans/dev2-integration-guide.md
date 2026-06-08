# Dev2 팀 연동 가이드

**작성일**: 2026-05-29 (2026-06-03 확장)
**대상**: Dev1, M4(커리큘럼)

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

## 2. Dev1 → Dev2 결과 취합 연결 (POST /aggregate)

M2+M3 분석이 둘 다 완료되면 Dev1(M0)이 결과를 묶어 Dev2에 전달합니다.

### 요청 형식

> **M2 결과(static_analysis + security_scan)만 전달.** M3 결과는 M3 서버가 별도로 M4에 전달.

```json
POST http://[Dev2_서버_주소]/aggregate
Content-Type: application/json

{
  "task_id": "uuid-001",
  "pr_id": "42",
  "developer": {
    "id": "junior_dev_01",
    "skill_level": "junior",
    "tech_stack": ["python", "fastapi"]
  },
  "context": {
    "architecture_docs": ["chunk_id_1"],
    "coding_conventions": "PEP8",
    "previous_pr_issues": ["N+1 쿼리"]
  },
  "all_results": [
    {"agent": "static_analysis", "task_id": "uuid-001", "issues": [...], "summary": {...}, "execution_ms": 1200},
    {"agent": "security_scan",   "task_id": "uuid-001", "issues": [...], "summary": {...}, "execution_ms": 900}
  ]
}
```

### 응답

```json
HTTP 202 Accepted
{"status": "accepted", "task_id": "uuid-001"}
```

> 백그라운드에서 aggregate → comment_refine → (slack_notify) → github_comment → M4 push 순으로 자동 실행됩니다.

---

## 3. Dev2 → M4(커리큘럼) 연결 — Push 방식

> **원칙**: M4가 결과를 요청(pull)하는 것이 아니라, Dev2 분석이 끝나면 **Dev2가 M4에 자동 전송(push)** 합니다.

### 언제 push하나?

`POST /aggregate` 파이프라인의 `aggregate_node`가 PostgreSQL 저장을 마친 직후 **항상** M4에 push합니다.
Critical 여부와 무관하게 매번 전송합니다.

### M4에 보내는 데이터 형식

```json
POST http://[M4_서버_주소]/curriculum/trigger
Content-Type: application/json

{
  "task_id": "uuid-001",
  "pr_id": "42",
  "developer_id": "junior_dev_01",
  "skill_level": "junior",
  "tech_stack": ["python", "fastapi"],
  "aggregated_issues": [
    {
      "severity": "Critical",
      "agent": "security_scan",
      "line": 12,
      "file": "auth.py",
      "message": "SQL 인젝션 가능성",
      "rule_id": "B608",
      "suggestion": "파라미터화된 쿼리 사용",
      "similar_issues": [{"pr_id": "PR-002", "similarity": 0.92}]
    }
  ],
  "summary": {"critical": 1, "major": 2, "minor": 3}
}
```

### M4가 알아야 할 것

- Dev2가 `POST /curriculum/trigger`로 자동 push하므로 **M4는 Dev2에게 따로 요청하지 않아도 됩니다**
- `aggregated_issues` 안에 M2+M3 전체 이슈가 포함되어 있음
- `summary`는 M2+M3 합산 집계
- 과거 이슈 이력이 필요하면 `GET /insights/developer/{developer_id}` 로 조회 가능 (참고용)

---

## 4. 연결 시 .env 변경 사항 전체

```bash
# Dev2의 .env 파일 — Week 5 연동 시 아래 값 교체

# M4 커리큘럼 모듈 (분석 완료 후 자동 push)
M4_WEBHOOK_URL=http://[M4_실제_주소]/curriculum/trigger

# GitHub PR 코멘트 등록
GITHUB_TOKEN=ghp_xxxx
GITHUB_REPO=org/repo-name

# Slack Critical 알림
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/xxx

# LLM 실제 사용 (개발 중 true, 통합/데모 시 false)
USE_MOCK_LLM=false

# DB (Cloud SQL로 전환 시)
DATABASE_URL=postgresql+asyncpg://dev2:dev2@localhost:5432/dev2_db
```

---

## 5. 전체 흐름 요약

```
Dev1(M0)               Dev2                    M4(커리큘럼)
  │                       │                       │
  │  POST /scan           │                       │
  │──────────────────────▶│                       │
  │  202 Accepted         │  (파이프라인1 실행 중)  │
  │◀──────────────────────│                       │
  │                       │                       │
  │  POST /aggregate      │                       │
  │  (M2+M3 결과 전달)     │                       │
  │──────────────────────▶│                       │
  │  202 Accepted         │  (파이프라인2 실행 중)  │
  │◀──────────────────────│                       │
  │                       │                       │
  │                       │  aggregate 완료 후     │
  │                       │  POST /curriculum/     │
  │                       │  trigger (자동 push)   │
  │                       │──────────────────────▶│
  │                       │                       │
  │                       │  Critical >= 1 시      │
  │                       │  → Slack 알림          │
  │                       │  → GitHub PR 코멘트    │
```

**핵심**: M4는 Dev2에게 결과를 요청하지 않습니다. Dev2 과정이 끝나면 M4에게 자동으로 데이터를 보냅니다.

---

## 6. 현재 MVP 테스트 방법 (팀 연동 전)

Dev1/M4 없이 Dev2 단독으로 테스트:

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

# 3. 파이프라인 1: 스캔 실행
curl -X POST http://localhost:8005/scan/mock-bandit

# 4. 파이프라인 2: 취합 실행 (M4 push 포함)
curl -X POST http://localhost:8005/aggregate \
  -H "Content-Type: application/json" \
  -d '{
    "task_id": "test-001", "pr_id": "1",
    "developer": {"id": "dev2", "skill_level": "junior", "tech_stack": ["python"]},
    "all_results": []
  }'

# 5. 결과 조회 (참고용)
curl http://localhost:8005/insights/developer/dev2
curl http://localhost:8005/insights/team
```
