# 파이프라인 2 작업 분해 — 왜 10~16시간인가?

> 각 Task가 실제로 뭘 하는지 구체적으로 설명

---

## Task 9 — aggregate_node (2~3시간)

**하는 일**: M2 자체 결과 2개(static_analysis + security_scan) → 하나로 합쳐서 DB 저장 → M4에 push

> M3 결과는 포함 안 함. M3는 M3 방식대로 별도 전달. Dev2는 M2 결과만 처리.

**흐름**:
```
파이프라인 1(분석) 끝
  └─ static_analysis 결과
  └─ security_scan 결과
       ↓
aggregate_node: 두 개 합치기 + severity 정렬
       ↓
PostgreSQL 저장
       ↓
M4에 push (M2 결과만)

M3는 M3 서버에서 별도로 M4에 push (Dev2 관여 없음)
```

**POST /aggregate 입력 (M2 결과만)**:

```json
{
  "task_id": "uuid-001",
  "pr_id": "42",
  "developer": { "id": "junior_dev_01", "skill_level": "junior", ... },
  "all_results": [
    {"agent": "static_analysis", "issues": [...], "summary": {...}},
    {"agent": "security_scan",   "issues": [...], "summary": {...}}
  ]
}
```

**실제 만들어야 하는 것**:

```
dev2/nodes/aggregate.py        ← 이슈 합치는 코드 (60줄)
dev2/migrations/004_*.sql      ← 새 테이블 만드는 SQL (10줄)
dev2/db.py                     ← insert 함수 1개 추가 (20줄)
dev2/tests/test_nodes.py       ← 테스트 2개 추가 (50줄)
```

**왜 2~3시간이냐**:
- 코드 자체는 30분이면 됨
- M4 push HTTP 호출 테스트할 때 Mock 설정이 복잡함
- DB insert 테스트에서 AsyncMock 패턴 맞추는 데 시간 걸림

**사실 빠르면**: 1.5시간

---

## Task 10 — comment_refine_node (2~3시간)

**하는 일**: 이슈 목록 받아서 Claude API 호출 → 개발자 수준에 맞는 PR 코멘트 텍스트 생성

**실제 만들어야 하는 것**:

```
dev2/nodes/comment_refine.py   ← Claude 호출 코드 (70줄)
dev2/prompts/comment_refine.py ← 프롬프트 템플릿 (40줄)
dev2/tests/test_nodes.py       ← 테스트 2개 추가 (60줄)
```

**왜 2~3시간이냐**:
- 코드 자체는 빠름
- 프롬프트가 문제 — junior/mid/senior 수준별로 다르게 나와야 함
- USE_MOCK_LLM=true/false 전환 테스트 패턴 맞추기

**사실 빠르면**: 1시간 (프롬프트 품질은 Week 5에 다듬으면 되니까)

---

## Task 11 — github_comment + slack_notify (2~3시간)

**하는 일**:
- GitHub PR에 코멘트 등록 (PyGitHub 라이브러리)
- Critical 있으면 Slack에 알림 전송 (httpx POST)

**실제 만들어야 하는 것**:

```
dev2/nodes/github_comment.py   ← PyGitHub 호출 (60줄)
dev2/nodes/slack_notify.py     ← httpx POST (50줄)
dev2/tests/test_nodes.py       ← 테스트 4개 추가 (100줄)
requirements.txt               ← PyGitHub 추가
```

**왜 2~3시간이냐**:
- 코드 자체는 단순함
- GitHub API Mock이 지저분함
  ```python
  mock_gh.return_value.get_repo.return_value.get_pull.return_value.create_issue_comment...
  ```
  이걸 4개 테스트마다 설정해야 함
- Slack도 AsyncClient Mock이 까다로움

**사실 빠르면**: 1.5시간

---

## Task 12 — aggregate_graph + POST /aggregate API (2~3시간)

**하는 일**: 만든 노드 4개를 
 + FastAPI 엔드포인트 추가

**실제 만들어야 하는 것**:

```
dev2/aggregate_graph.py        ← LangGraph StateGraph 조립 (60줄)
dev2/api/aggregate.py          ← FastAPI POST /aggregate (20줄)
dev2/schema.py                 ← AggregateState, AggregatePayload 추가 (40줄)
dev2/main.py                   ← 라우터 등록 1줄
dev2/tests/test_aggregate.py   ← 테스트 3개 (120줄)
```

**왜 2~3시간이냐**:
- 조립 자체는 빠름 (설계 이미 돼 있음)
- 조건부 엣지 (Critical → Slack → GitHub, 아니면 바로 GitHub) 테스트
- 전체 그래프 E2E 테스트에서 Mock 6개 동시에 패치해야 함

**사실 빠르면**: 1시간

---

## Task 13 — 전체 테스트 + 디버깅 (2~4시간)

**하는 일**: 다 붙여서 실제로 돌려보기

**실제 하는 것**:

```bash
pytest dev2/tests/ --cov=dev2   ← 전체 테스트 실행
docker compose up               ← 실제 DB로 확인
curl POST /aggregate            ← 실제 API 호출
```

**왜 2~4시간이냐**:
- 테스트 통과해도 실제 실행하면 환경변수 빠진 것, import 순서 문제, async 타이밍 등 나옴
- 디버깅 시간은 예측 불가
- 커버리지 80% 맞추려면 빠진 케이스 추가해야 함

**사실 빠르면**: 1시간 (첫 번째에 다 통과하면)

---

## 결론: 실제로는 더 빠를 수 있다

| 조건 | 예상 시간 |
|------|-----------|
| 설계 다 있고 코드 패턴 익숙하면 | **5~7시간** |
| 처음 해보는 라이브러리 없으면 | **7~10시간** |
| 디버깅 안 막히면 | **10시간 이내** |

**오래 걸리는 진짜 이유**:
1. 코드 작성보다 **테스트 Mock 설정**이 더 오래 걸림
2. GitHub/Slack API는 실제 토큰 없이 테스트하기 까다로움
3. async + LangGraph + httpx 조합에서 타이밍 버그 나오면 잡기 어려움

**빠르게 끝내는 방법**:
- Task 9 → 12 순서로 뼈대 먼저 완성
- Task 10(프롬프트), 11(GitHub/Slack)은 Mock으로만 테스트 통과시키고 Week 5에 실제 연결
- 커버리지는 나중에 맞추기
