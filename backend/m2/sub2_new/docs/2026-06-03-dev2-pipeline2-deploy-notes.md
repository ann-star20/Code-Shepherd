# Dev2 파이프라인 2 — 환경/배포 잔여 작업 노트

> 작성일: 2026-06-03
> 관련 구현계획: [`plans/2026-05-22-dev2-implementation-plan.md`](plans/2026-05-22-dev2-implementation-plan.md) Task 9~13

## 요약

파이프라인 2(취합 → 코멘트 → GitHub 등록 → Slack 알림, PRD 노드 I→M→N→O)의
**코드 구현 + 단위 테스트는 완료**되었다. 아래 항목은 코드가 아니라 **실행 환경/배포
단계**에서 처리해야 하는 것들로, 로컬/CI에서는 의존성 미설치 또는 외부 리소스 부재로
실행되지 않는다.

```
pytest dev2/tests/test_aggregate.py   → 7 passed
pytest dev2/tests/ (dags/adapter 제외) → 134 passed, 3 skipped
```

---

## 1. DB 마이그레이션 004 적용 필요

- **파일**: `dev2/migrations/004_aggregate_table.sql` (작성 완료)
- **상태**: 파일만 존재. 실제 `CREATE TABLE pr_aggregated_results`는 미적용
  (개발 환경에 실행 중인 PostgreSQL 없음).
- **자동 적용 경로**: `docker-compose.yml`이 `./dev2/migrations`를
  `/docker-entrypoint-initdb.d`로 마운트 → **postgres 컨테이너 최초 기동 시 자동 실행**.
  단, 이미 초기화된 볼륨(`postgres_data`)에는 init 스크립트가 재실행되지 않음.
- **수동 적용 (기존 볼륨에 추가할 때)**:
  ```bash
  psql "$DATABASE_URL" -f dev2/migrations/004_aggregate_table.sql
  ```
  기대 결과: `CREATE TABLE` 1개 + `CREATE INDEX` 3개.

## 2. Apache Airflow 미설치 (test_dags.py 14건 실패)

- **원인**: 로컬/CI에 `apache-airflow` 미설치 → `from airflow import DAG` ImportError.
- **범위**: DAG 코드(`dev2/dags/daily_etl.py`, `weekly_report.py`)는 존재.
  파이프라인 2(Task 9~13)와 무관한 기존 환경 이슈.
- **해결**: `pip install apache-airflow==2.9.0` 후 `pytest dev2/tests/test_dags.py`.
  (Airflow는 의존성이 무거워 분석 컨테이너와 분리된 `airflow` 서비스에서만 실행 권장.)

## 3. webhook-gateway 어댑터 테스트 경로 (test_dev2_adapter.py 1건)

- **원인**: `test_dev2_adapter.py`가 `from registry import ...` 형태로
  `dev2/webhook-gateway_2/`를 sys.path 루트로 가정. 기본 rootdir에서는 모듈 미발견.
- **해결**: 해당 디렉토리에서 실행하거나 `PYTHONPATH`/conftest로 경로 추가.
  역시 기존 이슈로, 파이프라인 2 범위 밖.

## 4. n8n 워크플로우 — 의도적 생략

- 구현계획 Task 7에 `dev2/n8n/github_webhook_workflow.json`이 있으나
  **`CLAUDE.md §4`에서 "n8n 미사용"으로 명시**됨 (GitHub Webhook 수신은 Dev1 담당).
- 따라서 미생성이 정상. 추후 정책 변경 시에만 추가.

## 5. 외부 연동 환경변수 (운영 시 .env 설정)

파이프라인 2 노드는 환경변수 미설정 시 **경고 로그 후 스킵**(개발 환경 정상 동작).
운영/데모에서 실제 동작시키려면 다음을 설정한다.

| 변수 | 사용 노드 | 미설정 시 동작 |
|------|-----------|----------------|
| `M4_WEBHOOK_URL` | `aggregate` | M4 push 스킵 |
| `GITHUB_TOKEN`, `GITHUB_REPO` | `github_comment` | 코멘트 등록 스킵 |
| `SLACK_WEBHOOK_URL` | `slack_notify` | Slack 알림 스킵 |
| `USE_MOCK_LLM` | `comment_refine` | `true`면 Mock 코멘트(실 API 미호출) |
| `ANTHROPIC_API_KEY` | `comment_refine` | `USE_MOCK_LLM=false`일 때만 필요 |

## 6. E2E 수동 확인 (DB + 서비스 기동 후)

```bash
docker-compose up --build -d

curl -X POST http://localhost:8002/aggregate \
  -H "Content-Type: application/json" \
  -d '{
    "task_id": "e2e-001", "pr_id": "42",
    "developer": {"id": "dev-001", "skill_level": "junior", "tech_stack": ["python"]},
    "context": {"architecture_docs": [], "coding_conventions": "", "previous_pr_issues": []},
    "all_results": [
      {"agent": "security_scan", "task_id": "e2e-001",
       "issues": [{"severity": "Critical", "line": 12, "file": "auth.py",
                   "message": "SQL 인젝션", "rule_id": "B608",
                   "suggestion": "파라미터 쿼리", "similar_issues": []}],
       "summary": {"critical": 1, "major": 0, "minor": 0}, "execution_ms": 900}
    ]
  }'
# 기대: 202 Accepted → 백그라운드 aggregate → comment_refine → github_comment → slack_notify
```
