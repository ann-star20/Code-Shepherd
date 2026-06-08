# Dev2 다음 세션 작업 인계서 (2026-06-04 → 다음날)

## 오늘 완료한 것

| 항목 | 상태 |
|------|------|
| 파이프라인 1 구현 (run_tools→llm_judge→store→github_comment) | 완료 |
| 파이프라인 2 구현 (aggregate→comment_refine→github_comment) | 완료 |
| `.env` 파일 생성 (Cloud SQL IP 설정) | 완료 |
| pj3_data(OWASP) 데이터로 run_tools_node 실행 검증 | 완료 |
| Google Cloud 연결 방법 파악 | 완료 |

---

## 내일 바로 시작할 것 (우선순위 순)

### 1. `insert_aggregated_result()` 함수 추가 — 30분

**파일:** `sub2_new/dev2/db.py`

`aggregate_node`가 이 함수를 호출하는데 아직 없음. 추가해야 함:

```python
async def insert_aggregated_result(
    task_id: str,
    pr_id: str,
    developer_id: str,
    issues: list[dict],
    summary: dict,
) -> int:
    # scan_executions에 INSERT → scan_id 받아서
    # scan_issues에 각 이슈 INSERT
    # scan_summaries에 UPSERT
```

### 2. semgrep 설치 — 5분

```bash
pip install semgrep
```

현재 `_run_python: semgrep 실패 — [WinError 2]` 오류 발생 중.

### 3. 테스트 픽스처 파일 생성 — 1시간

**없는 파일 2개:**

- `sub2_new/dev2/tests/fixtures/pr_diffs.py` — PR diff 샘플 (SQL injection, clean, N+1)
- `sub2_new/dev2/tests/fixtures/agent_outputs.py` — AgentOutput 샘플 (Critical/Major/clean 3종)

### 4. DB seed 데이터 삽입 — 30분

Cloud SQL(`34.22.101.111:5432/tasklink`)에 없는 것:

```sql
-- developers 테이블
INSERT INTO developers (id, skill_level, tech_stack) VALUES
  ('junior_dev_01', 'junior', '["python","fastapi","postgresql"]'),
  ('senior_dev_01', 'senior', '["python","fastapi","postgresql"]');

-- pr_reviews 테이블 (이전 이력 seed)
-- PR-001: N+1 쿼리 rework 시나리오
-- PR-002: SQL 인젝션 escalate 시나리오
```

### 5. POST /scan 서버 띄워서 E2E 실행 — 1시간

```bash
# .env에 API 키 먼저 설정 후
cd sub2_new
uvicorn dev2.main:app --reload --port 8002

# 다른 터미널에서
curl -X POST http://localhost:8002/scan \
  -H "Content-Type: application/json" \
  -d '{
    "task_id": "pj3-test-001",
    "pr_id": "42",
    "pr_diff": "--- /dev/null\n+++ b/pj3_data/BenchmarkPython-main/testcode/BenchmarkTest00054.py\n+...",
    "developer": {"id": "junior_dev_01", "skill_level": "junior", "tech_stack": ["python"]},
    "context": {}
  }'
```

---

## 내일 세션 시작 프롬프트 (Claude에게 붙여넣기)

```
어제 Dev2 M2 파이프라인 작업하다 멈췄어.
오늘 이어서 할게.

현재 상태:
- 파이프라인 1, 2 코드 구현은 완료
- .env 파일 있음 (Cloud SQL 34.22.101.111 연결됨)
- pj3_data(OWASP BenchmarkPython) 데이터로 run_tools_node 검증 완료

오늘 해야 할 것 (우선순위 순):
1. db.py에 insert_aggregated_result() 함수 추가 (aggregate_node가 호출하는데 없음)
2. semgrep 설치 (pip install semgrep)
3. tests/fixtures/pr_diffs.py, agent_outputs.py 파일 생성
4. Cloud SQL에 seed 데이터 삽입 (developers, pr_reviews 테이블)
5. uvicorn으로 서버 띄워서 POST /scan E2E 실행

먼저 1번부터 시작해줘.
```

---

## 참고: 주요 파일 위치

| 파일 | 역할 |
|------|------|
| `sub2_new/dev2/db.py` | DB 함수 (insert_aggregated_result 추가 필요) |
| `sub2_new/dev2/nodes/aggregate.py` | 파이프라인 2 진입 노드 |
| `sub2_new/dev2/aggregate_graph.py` | 파이프라인 2 그래프 조립 |
| `sub2_new/dev2/graph.py` | 파이프라인 1 그래프 조립 |
| `sub2_new/dev2/main.py` | FastAPI 앱 (uvicorn 실행 대상) |
| `sub2_new/dev2/.env` | 환경변수 (API 키 채워야 함) |
| `sub2_new/pj3_data/` | OWASP BenchmarkPython 테스트 데이터 1230개 |
