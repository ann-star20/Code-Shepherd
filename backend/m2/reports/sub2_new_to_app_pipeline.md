# sub2_new → app/ 통합 파이프라인

**일자**: 2026-06-12 | **브랜치**: `feature/module2-static-security`
**목적**: 내가 작업한 풍부한 설계(`backend/m2/sub2_new/dev2/`)가 운영 폴더(`backend/m2/app/`, sub2_new 제외)로 **어떤 순서로, 어떤 변형을 거쳐** 들어가는지의 이식 경로를 문서화한다.
**범위**: 분석·계획만. 코드 변경 없음.

---

## 0. 두 트리의 관계 (핵심)

| | `sub2_new/dev2/` | `app/` |
|---|---|---|
| 정체 | 내가 만든 **원본 풍부한 설계** (LangGraph 7노드 + 코멘트/알림/벡터검색) | docker 스택이 실제로 호출하는 **운영 실체** |
| 진입 | `POST /scan` (202 + BackgroundTasks → `run_dev2`) | `/analyze/static`·`/analyze/security`·`/webhook/github`·`/orchestrate/review` |
| 분석 흐름 | StateGraph: tool_router → run_tools → vector_search → llm_judge → action_decider → (escalate\|store) | `orchestrator.run_m2_orchestration` 순차 호출 (decision → analyzer×2 → m4) |
| 네임스페이스 | `dev2.*` (`from dev2.schema import ...`) | `app.*` (`from app.contract import ...`) |
| 상태 | 미연결 청사진 (그대로는 docker에서 안 돎) | 가동 중 + 일부 이식 완료 |

> **이식 = `dev2.*` 모듈을 `app.*` 네임스페이스로 옮기면서, LangGraph StateGraph 흐름을 운영 오케스트레이터(`run_m2_orchestration`)의 단계로 평탄화(flatten)하는 작업.**

---

## 1. 파일 단위 매핑표 (sub2_new → app)

| sub2_new/dev2 | app/ 목적지 | 변형 | 상태 |
|---|---|---|---|
| `db.py` | `app/db.py` | 그대로 복사 (verbatim) | ✅ 완료 |
| `schema.py` | `app/contract.py` | `Issue`→`IssueItem`, `AgentOutput`→`AgentResult`, `TaskPayload`→`M2AnalyzeRequest`/`M2OrchestrateRequest`. 공통 계약은 `shared.contracts` 재사용 | ✅ 부분 (핵심 모델 이식, M4 매핑 필드는 미이식) |
| `graph.py` (`run_dev2`, `build_graph`) | `app/orchestrator.py` (`run_m2_orchestration`) | **StateGraph → 순차 함수 호출로 평탄화.** 노드=함수, 조건엣지=if 분기 | ✅ 핵심 흐름 / ⏳ 노드별 세부(vector/llm/action) 미이식 |
| `main.py` | `app/main.py` | scan/aggregate/insights/issues 라우터 → `/analyze/*`·`/orchestrate/review`로 축소 | ✅ 축소 이식 |
| `api/scan.py` (`POST /scan` 202+BG) | `app/webhook.py` + `app/main.py` | webhook 진입 + 동기 오케스트레이션 (현 설계는 동기, 무거워지면 202+BG 복원) | ✅ 이식(동기형) |
| `tools/router.py` (`detect_languages`) | `app/analyzer.py` (`_parse_diff`, `_SUPPORTED_EXT`) | 언어 감지 로직 축소 내장 | ✅ 부분 |
| `tools/python/*`, `javascript/*`, `common/semgrep` | `app/analyzer.py` 내 도구 실행부 | run_tools의 언어별 병렬을 analyzer가 흡수 | ✅ 부분(Pylint/Radon/Bandit/ESLint/Semgrep) / ⏳ csharp·html·css 미이식 |
| `nodes/run_tools.py` | `app/analyzer.py` | StateGraph 노드 → 순수 함수. tool_plan 분기는 `decision.py`로 일부 흡수 | ✅ 부분 |
| `nodes/tool_router_agent.py` | `app/decision.py` (`decide`) | LLM 도구선택 → 규칙기반 skip/needs 판정으로 축소 | ✅ 축소 이식 |
| `nodes/action_decider_agent.py` | `app/orchestrator.py` status 계산 (partial/success) | 3-way 추천 → 단순 fail 집계로 축소 | ✅ 축소 / ⏳ early_escalation 미이식 |
| `nodes/store.py` | `app/orchestrator.py`(`run_single_agent`) + `app/db.py` | scan_executions/issues/summaries 저장 호출로 이식 | ✅ 완료 |
| `nodes/vector_search.py` | `app/services/` (미생성) | pgVector 유사이슈 검색 | ⏳ 미이식 |
| `nodes/llm_judge.py` | `app/services/` (미생성) | LLM severity 판정/enrich | ⏳ 미이식 |
| `nodes/escalate.py` | `app/clients/`(slack) | early_escalation 경로 | ⏳ 미이식 |
| `nodes/aggregate.py`, `comment_generate.py`, `comment_refine.py`, `github_comment.py`, `slack_notify.py`, `concept_mapper.py` | (코멘트 소유 모듈 합의 후 결정) | 파이프라인 2(취합→코멘트→알림). **코멘트 소유 미합의(m2 vs m3)** | ⏳ 보류 — 합의 선행 |
| `repositories/scan_repository.py` | `app/db.py` 직접 호출로 대체 | Repository 추상 생략(운영은 db 함수 직접) | △ 미이식(설계상 생략) |
| `prompts/*` | (llm_judge/comment 이식 시 동반) | | ⏳ 미이식 |
| `vector_store/` | (vector_search 이식 시 동반) | | ⏳ 미이식 |
| `dags/*` (airflow ETL) | 운영 범위 밖 | daily_etl/weekly_report | ✖ 비대상 |
| `webhook-gateway_2/*` | `app/webhook.py`로 대체 | 별도 게이트웨이 → m2 내장 webhook | ✖ 비대상(대체됨) |
| `api/aggregate.py`, `insights.py`, `issues.py` | (필요 시 추후) | 조회/취합 API | ⏳ 미이식 |

범례: ✅완료 · ⏳보류(이식 예정) · △설계상 생략 · ✖비대상

---

## 2. 네임스페이스 변환 규칙

이식 시 모든 import를 기계적으로 치환한다.

```text
from dev2.schema   import X    →  from app.contract import X      (또는 shared.contracts)
from dev2.db       import X    →  from app.db import X
from dev2.tools.*  import X    →  app/analyzer.py 내부로 흡수
from dev2.nodes.*  import X    →  app/orchestrator.py 또는 app/services/* 함수로
dev2.graph.run_dev2            →  app.orchestrator.run_m2_orchestration
```

**LangGraph 평탄화 규칙**: `StateGraph.add_node(f)` → `f`를 `app/services/`의 순수 async 함수로,
`add_conditional_edges(router)` → `orchestrator` 내부 `if` 분기로 변환한다.
State(`Dev2State` dict) 대신 `M2OrchestrateRequest`/`AgentResult`(Pydantic)를 인자/반환으로 사용.

---

## 3. 이식 의존성 순서 (아래→위)

이식은 의존성이 적은 하위 레이어부터 올라간다. (Clean Architecture: 안쪽 먼저)

```
1. db.py                 ✅  (의존 없음 — 가장 먼저, 완료)
2. schema → contract     ✅  (Pydantic 계약)
3. tools/* → analyzer    ✅부분 (도구 실행, 외부 CLI만 의존)
4. run_tools/store 노드   ✅  (analyzer+db 위에 얹힘)
5. graph → orchestrator  ✅핵심 (3·4를 순차 조립)
6. scan.py → webhook     ✅  (orchestrator를 호출하는 입구)
─────────────── 여기까지 가동 ───────────────
7. vector_search/llm_judge → services   ⏳  (LLM/pgVector 의존 — RAG enrich)
8. action_decider/escalate              ⏳  (7 위, slack 의존)
9. aggregate/comment/github_comment     ⏳  (코멘트 소유 합의 후)
```

---

## 4. 단계별 파이프라인 (현재 가동 흐름)

이식된 운영 경로의 end-to-end:

```
GitHub PR webhook
  → app/webhook.py        서명검증 → event/action 필터 → diff fetch
  → app/orchestrator.run_m2_orchestration
       → app/decision.decide(pr_diff)        [tool_router_agent 축소판]  skip 가능
       → app/analyzer.analyze × 2            [run_tools 평탄화]  static / security
       → app/db (insert_scan_*)              [store 노드]  scan_executions/issues/summaries
       → app/services/result_persist         [신규]  review_issue (opt-in)
       → app/services/result_mapper          AgentResult → M4EvaluateRequest
       → app/clients/m4_client.evaluate       /evaluate (graceful)
  → M2OrchestrateResponse
```

미이식 노드가 들어갈 자리(점선):

```
analyze ──┐
          ├→ [vector_search] ─→ [llm_judge enrich] ─→ [action_decider]  ⏳
          │        (pgVector)        (LLM severity)      (escalate?)
store ────┘                                               └→ [escalate/slack]  ⏳
                                                          └→ [aggregate→comment→github]  ⏳(합의)
```

---

## 5. 이미 이식 완료 vs 보류

**완료(가동 중)**
- `db.py` 전량, `schema`→`contract` 핵심 모델, 도구 실행(Py/JS+Semgrep), `store`(scan 테이블), 오케스트레이터 핵심 흐름, webhook 진입.

**보류(이식 예정 — 의존/합의 선행)**
- `vector_search`·`llm_judge`·`prompts`·`vector_store`: LLM/pgVector 연결 필요.
- `action_decider`/`escalate`: 3-way 추천·slack 알림.
- `aggregate`/`comment_*`/`github_comment`/`slack_notify`: **코멘트 소유 모듈(m2 vs m3) 합의 선행** (MEMORY 기록된 3자 불일치).
- `repositories/`: 운영은 `db.py` 직접 호출로 대체(추상 레이어 생략).

**비대상**
- `dags/`(airflow), `webhook-gateway_2/`(m2 내장 webhook으로 대체), `api/aggregate|insights|issues`(필요 시 추후).

---

## 6. 이식 시 주의점 (충돌·함정)

1. **severity 표기 이원화**: scan_issues는 `Critical/Major/Minor`(원본), review_issue는 `critical/high/medium/low`(m4 CHECK). 이식 시 매핑 고정 필요(`result_persist._SEVERITY_MAP`). m4 통계 키와 합의 전까지 잠정.
2. **이중 저장 경로 공존**: `store` 이식분(scan_* 테이블, dev2 소유)과 신규 `result_persist`(review_issue, m4 소유)가 동시 동작. 통합 시 소유/중복 정리 필요.
3. **타임아웃 처리 위치**: 원본 `CLAUDE.md §6` 경고 — `try/except asyncio.TimeoutError`는 반드시 harness `async with` **바깥**. 평탄화하면서 이 위치 규칙 유지.
4. **동기 vs 202+BG**: `scan.py`는 202+BackgroundTasks. 운영 webhook은 동기 채택(분석 경량). 무거워지면 원본 패턴으로 복원.
5. **State→Pydantic 전환**: `Dev2State`(TypedDict dict)를 운영에선 Pydantic 모델로 받으므로, 노드 이식 시 `state.get("x")` → 명시적 인자/속성으로 바꿔야 함.
6. **공유 계약 불변**: `shared/contracts.py`는 m2 단독 변경 금지. schema의 신규 필드는 `app/contract.py`(AgentResult, extra=ignore)에만 추가.
