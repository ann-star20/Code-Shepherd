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

---
---

# [2026-06-12 추가] app/ ↔ docs/MODULE_CONTRACT.md §Module 2 정합 작업 (미결정)

> 위 인계서(sub2_new 파이프라인)와 **별개 주제**다.
> 운영 스텁 `backend/m2/app/`을 공통 계약 `docs/MODULE_CONTRACT.md` §Module 2와
> 맞추는 작업. **범위 결정 단계에서 멈춤** — 아래 옵션 중 사용자가 고르면 진행.

## 지금까지 한 것 (커밋 완료)

| 커밋 | 내용 |
|------|------|
| `010416e4` | app/ 엔드포인트가 **AgentResult**(M2AnalyzeResponse 상위집합) 반환하도록 구현. `app/contract.py` 신규(빌더/검증/sub-trace/타임아웃). `backend/m2/MODULE_CONTRACT.md`(as-built 계약) 신규. 테스트 보강. sub2_new/common harness·trace 중복본 제거. |
| `0358d4db` | `backend/m2/MODULE_CONTRACT.md`에 GLOBAL_AGENT_RULE 준수 매핑표 + 보류 방침 추가. |

## 핵심 결론: 출력 데이터 계약은 **이미 일치**

`docs/MODULE_CONTRACT.md` §164-184 `agent_result` 10필드 vs 현재 `app/contract.py` `AgentResult`:
task_id·trace_id·agent_name·module_id·status(success/fail/hitl_pending)·issues·summary·
validation_result(pass/fail/skip)·execution_ms·next_agent:null → **전부 충족**.
추가 필드(agent·sub_trace_id·error_message)는 docs가 "필드 추가 가능"이라 명시 → 위반 아님.

## 남은 차이 = 전부 아키텍처/보류 (m2 단독 수정 불가)

| 차이 | docs 규칙 | 현재 app/ | 단독 수정 불가 이유 |
|------|-----------|-----------|---------------------|
| 통신 모델 | PlatformState + LangGraph 노드 | REST(M2AnalyzeRequest→AgentResult) | m1이 REST로 호출(`m1/app/clients/module_clients.py`). LangGraph 전환 시 m1/m3 동시 재작성 → 검증된 연동 깨짐 |
| m1 병렬 | asyncio.gather(m2,m3) | m1이 직렬 await | **m1 코드** 영역(타 모듈) |
| uses_kms | true (컨벤션·이전이슈 참조) | context 받지만 미사용 | 스텁에 LLM/pgVector 없음 → 결정적 구현 불가, 넣으면 동작 날조 |
| uses_langsmith | true | 미적용 | 사용자가 "후에" 보류 결정 |

## 다음 세션 결정 사항 — 범위 3택 (사용자 선택 대기 중)

1. **현행 유지 + 차이 문서화 (가장 안전, 추천)**
   - 출력 계약 이미 일치 → 코드 변경 없음. REST vs LangGraph·kms·langsmith 차이는
     "통합 시 합의" 항목으로 `backend/m2/MODULE_CONTRACT.md`에 명시(이미 일부 기재됨).
   - m1/m3 연동 안전.

2. **context 실사용만 추가 (m2 단독 가능, 효과 제한적)**
   - 요청 `AnalysisContext`(coding_conventions·previous_pr_issues)를 `analyzer.py`가 참조해
     이슈에 반영. 단 LLM 없는 스텁이라 결정적 규칙 수준으로만 가능.

3. **LangGraph 전면 전환 (대규모·고위험)**
   - app/을 PlatformState/LangGraph 노드로 재작성해 docs 아키텍처와 완전 일치.
   - **m1 REST 호출부·m3까지 동시 변경 필요 → 현재 파이프라인 깨짐. 크로스모듈 합의 필수.**
   - CLAUDE.md "다른 모듈 담당 파일 임의 수정 금지" 위반 소지 → 팀 합의 없이는 금지.

## 다음 세션 시작 프롬프트

```
m2 app/ 을 docs/MODULE_CONTRACT.md §Module 2와 맞추는 작업 이어서 할게.
backend/m2/sub2_new/docs/plans/dev2-next-session.md 의
"[2026-06-12 추가]" 섹션 읽고 시작해줘.
출력 계약은 이미 일치하는 거 확인했고, 범위 3택 중 _번으로 진행해줘.
```

## 관련 파일

| 파일 | 역할 |
|------|------|
| `backend/m2/app/contract.py` | AgentResult 모델 + 빌더/검증/sub-trace/타임아웃 |
| `backend/m2/app/main.py` | 엔드포인트(AgentResult 반환) |
| `backend/m2/MODULE_CONTRACT.md` | m2 as-built 계약 + GLOBAL_AGENT_RULE 준수 매핑 |
| `docs/MODULE_CONTRACT.md` §141-213 | 공통 계약 Module 2 규격(이상안, **수정 금지**) |
| `backend/m1/app/clients/module_clients.py` | m1의 m2 REST 호출부(L72·96 `M2AnalyzeResponse(**resp.json())`) |
