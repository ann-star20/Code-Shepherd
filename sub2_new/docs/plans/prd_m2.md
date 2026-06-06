# M2 코드 리뷰 모듈 — Dev2 담당자 PRD

> 기반: 팀 공통 PRD v1.6 (M2 코드 리뷰 모듈)
> 작성일: 2026-05-29

---


## 1. 모듈 한 줄 정의

GitHub PR 제출 시 **60초 이내** (Dev2 단독 30초)에 다국어 정적 분석·보안 스캔을 실행하고,
RAG 유사 이슈 주입 + LLM severity 재판단을 거쳐 표준 Output Contract JSON을 생성한다.

---

## 2. 팀 PRD 기준 M2 위치 (확장 담당 범위)

```
M0 Orchestrator
    │
    ├──► [M2 코드 리뷰 모듈 — 내 담당: G]
    │         └── AgentOutput × 2
    │
    └──► M3 테스트 커버리지 모듈
              └── AgentOutput × 2

M0 → [이슈 취합 — 내 담당: I]
         ├──► PostgreSQL 저장 (유저 이슈 리스트)
         ├──► [LLM 코멘트 정제 — 내 담당: M]
         │         ├──► GitHub PR 코멘트 — 내 담당: N
         │         └──► Critical 시 Slack 알림 — 내 담당: O
         └──► M4 학습 커리큘럼 (Dev5 담당)
```

**Dev2 전체 책임 범위:**

| 노드 | 역할 | 트리거 |
|------|------|--------|
| G | PR Diff 정적분석·보안스캔 → AgentOutput | `POST /scan` |
| I | M2+M3 결과 취합 → PostgreSQL 저장 | `POST /aggregate` |
| M | LLM으로 사용자 수준 맞춤 코멘트 생성 + KMS 링크 | aggregate 완료 후 자동 |
| N | GitHub PR에 코멘트 등록 | comment_refine 완료 후 자동 |
| O | Critical 이슈 시 Slack 시니어 알림 | Critical ≥ 1 조건부 |

- **파이프라인 1 (G)**: M0 → `POST /scan` → 분석 5노드 그래프 → AgentOutput 반환
- **파이프라인 2 (I→M→N→O)**: M0 → `POST /aggregate` (M2+M3 결과 전달) → 취합·코멘트·알림 그래프

---

## 3. 담당 외 기능

| 팀 PRD 명세 | 실제 담당 | 비고 |
|------------|----------|------|
| 반복 실수 감지 + 코딩 가이드 업데이트 제안 | **Dev5** | `mistake_patterns` 테이블 분석은 Dev5 담당 |
| M4 학습 커리큘럼 생성 | **Dev5** | 이슈 데이터는 Dev2 DB에서 조회, 커리큘럼 생성은 Dev5 |
| GitHub Webhook 수신 | **Dev1(M0)** | Dev2는 `POST /scan`, `POST /aggregate` 수신만 |

---

## 4. 구현된 아키텍처

### LangGraph StateGraph — 7노드 파이프라인 (파이프라인 1)

```
START
  └─→ tool_router_agent    (PR 맥락 기반 도구 선택 → tool_plan)
  └─→ run_tools            (tool_plan.selected_tools 기반 병렬 실행)
  └─→ vector_search        (pgVector RAG — 유사 이슈 검색 + enrichment)
  └─→ llm_judge            (RAG Generate — severity 재판단 + concept 매핑)
  └─→ action_decider_agent (후속 액션 추천 → action_decision)
  └─→ [조건부 분기]
        ├─ early_escalation → escalate → store
        └─ 그 외           → store
  └─→ store                (Pydantic 검증 + PostgreSQL OLTP + BigQuery OLAP 이중 적재)
  └─→ END
```

**Agentic Workflow 두 축**:
- `tool_router_agent`: PR 맥락 → 필요 도구만 선택 (불필요 도구 스킵, 비용 절감)
- `action_decider_agent`: 이슈 결과 → 후속 액션 추천 (M0/Dev4 참고용, M2 직접 실행 안 함)

### 노드별 역할

| 노드 | 입력 State 필드 | 출력 State 필드 | 비고 |
|------|----------------|----------------|------|
| `tool_router_agent` | `pr_diff`, `tech_stack`, `previous_pr_issues` | `tool_plan` | 규칙 기반, LLM 없음 |
| `run_tools` | `pr_diff`, `tool_plan` | `static_raw`, `security_raw` | tool_plan 없으면 전체 도구 fallback |
| `vector_search` | `static_raw`, `security_raw` | `enriched` | pgVector 코사인 유사도 검색 |
| `llm_judge` | `enriched`, `skill_level` | `enriched` (업데이트) | 모델 라우팅 + concept_mapper 호출 |
| `action_decider_agent` | `enriched` | `action_decision` | 규칙 기반, LLM 없음 |
| `escalate` | `enriched`, `task_id` | `{}` (state 변경 없음) | early_escalation 시만 진입 |
| `store` | `enriched`, `action_decision` 등 | `final_output` | summary.recommended_action + metadata.action_decision 포함 |

---

## 5. 지원 언어 및 도구 스택

| 언어 | 정적 분석 | 보안 스캔 | 비고 |
|------|----------|----------|------|
| Python | Pylint + Radon (순환복잡도) | Bandit + Semgrep | 핵심 언어 |
| JavaScript / TypeScript | ESLint | Semgrep + npm audit | TS도 ESLint로 처리 |
| C# | Roslyn | Semgrep | — |
| HTML | HTMLHint | Semgrep | — |
| CSS / SCSS | Stylelint | (없음) | — |
| 기타 | — | Semgrep (generic) | 알 수 없는 확장자 |

지원 확장자: `.py .js .jsx .ts .tsx .cs .html .htm .css .scss`

**LLM 최소화 원칙**: CLI 도구 우선. LLM은 severity 재판단이 필요한 케이스에만.

---

## 6. Severity 분류 기준

| 조건 | Severity | 담당 도구 |
|------|----------|----------|
| SQL Injection / XSS / CSRF 탐지 | **Critical** | Bandit / Semgrep |
| CVE CVSS 7.0 이상 | **Critical** | pip-audit / npm audit |
| CVE CVSS 4.0 ~ 6.9 | **Major** | pip-audit / npm audit |
| 순환복잡도 > 10 | **Major** | Radon |
| 코드 스멜 (함수 > 50줄, 파라미터 > 5개) | **Minor** | Pylint |
| 중복 코드 / 일반 lint | **Minor** | Pylint / ESLint |

---

## 7. LLM 모델 라우팅 전략 (비용 최적화)

| Severity | 모델 | 이유 |
|----------|------|------|
| Critical | `claude-sonnet-4-6` | 보안·품질 직접 영향 → 최고 정확도 필요 |
| Major | `claude-haiku-4-5-20251001` | 리팩토링 필요 → 빠르고 저렴 |
| Minor | **생략** | CLI 도구 판단 신뢰, 비용 절감 |

LLM 호출 시 `build_severity_prompt()`로 프롬프트 생성:
- similar_cases (pgVector 검색 결과) RAG 주입
- developer_level 맞춤 설명
- tech_stack 컨텍스트

---

## 8. 입출력 계약 (Output Contract)

### 7-A. 입력: M0(Dev1) → M2

```json
{
  "task_id": "uuid",
  "pr_id": "github-pr-number",
  "pr_diff": "string (unified diff format)",
  "context": {
    "architecture_docs": ["chunk_id_1"],
    "coding_conventions": "string",
    "previous_pr_issues": ["SQL 인젝션"]
  },
  "developer": {
    "id": "string",
    "skill_level": "junior | mid | senior",
    "tech_stack": ["python", "fastapi"]
  }
}
```

### 7-B. 출력: M2 → M0 (`final_output` — AgentOutput × 2)

```json
{
  "agent": "static_analysis | security_scan",
  "task_id": "uuid",
  "issues": [
    {
      "severity": "Critical",
      "issue_type": "Vulnerability",
      "line": 42,
      "file": "src/auth.py",
      "message": "SQL 인젝션 가능성",
      "rule_id": "B608",
      "suggestion": "파라미터화된 쿼리 사용 권장",
      "resolution_example": "db.execute('SELECT * FROM t WHERE id = ?', [user_id])",
      "similar_issues": [
        {"pr_id": "PR-002", "similarity": 0.92, "message": "SQL 파라미터 미처리"}
      ],
      "concept": "SQL Injection",
      "mistake_type": "raw_query",
      "concept_id": "sql_injection",
      "mistake_type_concept_id": "sql_injection.raw_query",
      "confidence_score": 0.92,
      "code_snippet": "query = \"SELECT * FROM users WHERE name = '\" + username + \"'\"",
      "learning_context": {
        "framework": "django",
        "language": "python",
        "domain_context": "ecommerce"
      }
    }
  ],
  "summary": { "critical": 1, "major": 2, "minor": 3 },
  "execution_ms": 1200
}
```

> **필드 삭제 금지.** 내부 필드(`llm_judged`, `llm_model`, `_source`)는 store 노드에서 Pydantic 경계 검증 시 자동 제거됨.
> M4 필드(`concept` ~ `learning_context`)는 `concept_mapper.py` 룰 기반으로 자동 채워짐.
> `concept`이 빈 문자열이면 매핑 미지원 이슈 (lint 등) — M4에서 무시 처리.

---

## 9. State 구조

### Dev2State (PRReviewState 확장)

```python
# Dev1이 채움 (입력)
task_id, pr_id, pr_diff, developer_id, skill_level, tech_stack
architecture_docs, coding_conventions, previous_pr_issues

# Dev2 전용 (파이프라인 내부)
static_raw: list[dict]    # run_tools 노드 출력 — CLI 정적 분석 원본
security_raw: list[dict]  # run_tools 노드 출력 — CLI 보안 스캔 원본
enriched: list[dict]      # vector_search → llm_judge 순서로 업데이트
                           # (_source 태그 포함: "static" | "security")

# M0로 반환 (출력)
final_output: list[dict]  # AgentOutput × 2 (Output Contract)
```

---

## 10. DB 스키마

### 테이블 관계

```
scan_executions (1)
    ├──── scan_issues (N)      -- 이슈별 행
    └──── scan_summaries (2)   -- static_analysis / security_scan 집계
```

### scan_executions

| 컬럼 | 타입 | 설명 |
|------|------|------|
| `id` | bigint PK | 자동 증가 |
| `task_id` | text | M0 부여 UUID |
| `trace_id` | text | `pr_{12hex}` 형식 (CLAUDE.md §3) |
| `pr_id` | text | GitHub PR 번호 |
| `developer_id` | text | GitHub 로그인 |
| `scanned_at` | timestamptz | 실행 시각 |
| `execution_ms` | int | 소요 시간 |

### scan_issues

| 컬럼 | 타입 | 설명 |
|------|------|------|
| `id` | bigint PK | 자동 증가 |
| `scan_id` | bigint FK | scan_executions.id CASCADE |
| `agent` | text | `static_analysis` \| `security_scan` |
| `severity` | text | Critical \| Major \| Minor |
| `rule_id` | text | 룰 식별자 (예: B608, SEC-001) |
| `file` | text | 파일 경로 |
| `line` | int | 라인 번호 |
| `message` | text | 이슈 설명 |
| `suggestion` | text | LLM 개선 제안 |
| `similar_issues` | jsonb | pgVector 유사 이슈 결과 |
| `is_false_positive` | boolean | 오탐 표시 (기본 false) |

### scan_summaries

| 컬럼 | 타입 | 설명 |
|------|------|------|
| `id` | bigint PK | — |
| `scan_id` | bigint FK | CASCADE |
| `agent` | text | static_analysis \| security_scan |
| `critical / major / minor` | int | severity별 집계 |
| (UNIQUE) | | `(scan_id, agent)` — UPSERT 기준 |

### 인덱스

```sql
-- 시계열 조회 (BRIN: 크기 90% 절감)
CREATE INDEX idx_scan_executions_scanned_at ON scan_executions USING brin (scanned_at);
-- 개발자별 인사이트
CREATE INDEX idx_scan_executions_developer_time ON scan_executions (developer_id, scanned_at DESC);
-- Critical 에스컬레이션 전용 부분 인덱스
CREATE INDEX idx_scan_issues_critical ON scan_issues (scan_id, rule_id) WHERE severity = 'Critical';
-- JSONB 검색
CREATE INDEX idx_scan_issues_similar ON scan_issues USING gin (similar_issues);
```

---

## 11. API 엔드포인트

| 메서드 | 경로 | 설명 |
|--------|------|------|
| `POST /scan` | 202 Accepted | M0 → Dev2 분석 트리거 (BackgroundTasks) |
| `POST /scan/mock-bandit` | 200 | MVP 테스트: mock_vulnerable 폴더 Bandit 스캔 → Cloud SQL 저장 |
| `GET /insights/developer/{id}` | 200 | 개발자별 이슈 이력 조회 |
| `GET /insights/team` | 200 | 팀 Top5 반복 이슈 |
| `GET /insights/trends` | 200 | 주간 severity 추이 |
| `PATCH /issues/{id}/dismiss` | 200 | 오탐 표시 (`is_false_positive = true`) |

### POST /scan 흐름

```
요청 수신 → TaskPayload(Pydantic 검증) → _payload_to_state() → Dev2State
→ BackgroundTasks.add_task(run_dev2, state)
→ 즉시 202 반환
→ 백그라운드에서 LangGraph 5노드 파이프라인 실행
```

---

## 12. Trace 구조

### LangSmith 프로젝트명

```bash
LANGCHAIN_PROJECT=dev2-{본인_github_id}     # 개발 중 (팀원 trace 혼합 방지)
# 통합 시: onboarding-platform-integrated
```

### Trace ID 형식

```
PR 파이프라인:    pr_{12자리 hex}                          (store 노드의 trace_id)
서브 에이전트:    pr_{12hex}_{agent_name}_{4hex}
예: pr_3a9f1c2b44e0 / pr_3a9f1c2b44e0_static_analysis_a1b2
```

### agent_traces 기록 구조

```json
{
  "trace_id": "pr_3a9f1c2b44e0",
  "task_id": "uuid",
  "agent_name": "StaticAnalysisAgent | SecurityScanAgent",
  "status": "success | fail | timeout",
  "started_at": "ISO8601",
  "ended_at": "ISO8601",
  "execution_ms": 1200,
  "error_message": null
}
```

---

## 13. 오류 처리 기준

| 상황 | 처리 |
|------|------|
| `pr_diff` 비어 있음 | 빈 결과 반환, 파이프라인 계속 |
| 언어별 CLI 도구 30초 타임아웃 | 해당 언어 결과 제외, 나머지 계속 |
| LLM JSON 파싱 실패 | 1회 재시도 → 실패 시 원래 severity 유지 |
| LLM 30초 타임아웃 | 원래 severity 유지 |
| pgVector 검색 0건 | 빈 리스트 반환 (예외 없음) |
| PostgreSQL 적재 실패 | **re-raise** (핵심 기능 — 파이프라인 중단) |
| BigQuery 적재 실패 | 로그만 남기고 스킵 (analytics 장애가 PR 리뷰 블록 금지) |
| Dev4 HTTP 알림 실패 | 로그만 남기고 스킵 (알림 실패가 리뷰 블록 금지) |
| `POSTGRES_URL` 미설정 | pgVector Mock 검색으로 fallback |
| `asyncpg` 미설치 | Mock 모드로 동작 (lazy import) |

---

## 14. Mock / 실제 전환

```bash
# .env 기본값
USE_MOCK_LLM=true   # 개발 중: LLM 호출 없음, 결정적 Mock 응답
                     # 통합/데모: false로 변경
```

| 환경변수 | Mock (true) | 실제 (false) |
|---------|------------|-------------|
| 임베딩 | MD5 해시 기반 결정적 벡터 | OpenAI text-embedding-3-small |
| pgVector 검색 | 키워드 패턴 매칭 Mock | asyncpg 실제 쿼리 |
| LLM 판단 | 원래 severity 그대로 반환 | claude-sonnet-4-6 / haiku-4-5 |

---

## 15. M0·M4와의 연동

### M0 판정 기준 (Dev4가 처리, 참고용)

| M2 + M3 합산 결과 | M0 판정 | 후속 처리 |
|------------------|---------|----------|
| Critical ≥ 1 | `escalate` | Slack 즉시 알림 (시니어 개발자) |
| Major ≥ 3 | `rework` | PR 코멘트 + 힌트, 최대 3회 리트라이 |
| Critical = 0, Major < 3 | `lgtm` | 시니어 최종 승인 요청 |

> M2는 **판정하지 않는다.** `escalate/lgtm/rework` 결정은 M0(Dev4 평가 로직)가 담당.
> M2의 Critical 감지 시 escalate 노드는 Dev4에 조기 알림용 HTTP POST만 보낸다.

---

## 16. 데모 시나리오 (MVP 필수)

| 시나리오 | 파일 | 탐지 규칙 | 기대 출력 |
|---------|------|----------|----------|
| SQL 인젝션 | `mock_vulnerable/auth.py` | B608 (Bandit) | Critical — escalate 경로 |
| 순환복잡도 | 중첩 if/for 함수 | Radon CC > 10 | Major |

`POST /scan/mock-bandit` 엔드포인트로 mock_vulnerable 폴더 직접 스캔 가능.

---

## 17. 구현 완료 체크리스트

```
# ── 파이프라인 1 (G: 분석) ──────────────────────────────────
[x] schema.py         PRReviewState, Dev2State, TaskPayload, AgentOutput (Pydantic)
[x] graph.py          LangGraph StateGraph 5노드 + 조건부 escalate 엣지
[x] run_tools.py      다국어 CLI 병렬 실행 (asyncio.gather + to_thread)
[x] vector_search.py  pgVector RAG enrichment (Mock/실제 전환)
[x] llm_judge.py      모델 라우팅 + LLM severity 재판단 + fallback
[x] escalate.py       Critical 조건부 알림 (→ 파이프라인 2 O 노드로 교체 예정)
[x] store.py          Pydantic 검증 + PostgreSQL + BigQuery 이중 적재
[x] api/scan.py       POST /scan (202, BackgroundTasks) + mock-bandit 엔드포인트
[x] tools/            Python/JS/TS/C#/HTML/CSS 도구 구현
[x] prompts/          severity_judge.py — build_severity_prompt()
[x] tests/            단위 테스트, eval, fixtures

# ── 파이프라인 2 (I→M→N→O: 취합·코멘트·알림) ──────────────
[ ] nodes/aggregate.py      M2+M3 결과 취합 + PostgreSQL 저장
[ ] nodes/comment_refine.py LLM 수준별 코멘트 생성 + KMS 문서 링크
[ ] nodes/github_comment.py GitHub PR 코멘트 등록 (PyGitHub)
[ ] nodes/slack_notify.py   Critical 시 Slack 시니어 알림
[ ] prompts/comment_refine.py  build_comment_prompt()
[ ] api/aggregate.py        POST /aggregate 엔드포인트
[ ] aggregate_graph.py      취합·코멘트 LangGraph 조립
[ ] tests/test_aggregate.py 취합 파이프라인 단위 테스트

# ── Week 5 연동 ──────────────────────────────────────────────
[ ] Week 5 — Mock → Dev1 실제 연결 (ANALYSIS_AGENT_URL 교체)
[ ] Week 5 — USE_MOCK_LLM=false 통합 테스트
[ ] Week 5 — common/harness.py run_parallel_agents() 로 교체
[ ] Week 5 — POST /aggregate Dev1 실제 연결
[ ] Week 5 — GITHUB_TOKEN 실제 PR 코멘트 테스트
[ ] Week 5 — SLACK_WEBHOOK_URL Critical 알림 테스트
```

---

## 18. 담당 파일 구조

```
dev2/
├── schema.py                  # PRReviewState, Dev2State, AggregatePayload 등
├── graph.py                   # 파이프라인 1: 분석 5노드 StateGraph
├── aggregate_graph.py         # 파이프라인 2: 취합·코멘트·알림 StateGraph
├── main.py                    # FastAPI 앱 초기화
├── db.py                      # AsyncSessionLocal, insert_* 함수
├── nodes/
│   ├── run_tools.py           # CLI 도구 다국어 병렬 실행
│   ├── vector_search.py       # pgVector RAG enrichment
│   ├── llm_judge.py           # LLM severity 재판단 (모델 라우팅)
│   ├── escalate.py            # (파이프라인1 레거시 — 파이프라인2 slack_notify로 대체)
│   ├── store.py               # PostgreSQL + BigQuery 적재
│   ├── aggregate.py           # [신규] M2+M3 결과 취합 + DB 저장
│   ├── comment_refine.py      # [신규] LLM 수준별 코멘트 + KMS 링크
│   ├── github_comment.py      # [신규] GitHub PR 코멘트 등록
│   └── slack_notify.py        # [신규] Critical Slack 알림
├── api/
│   ├── scan.py                # POST /scan, POST /scan/mock-bandit
│   ├── aggregate.py           # [신규] POST /aggregate
│   ├── insights.py            # GET /insights/*
│   └── issues.py              # PATCH /issues/{id}/dismiss
├── prompts/
│   ├── severity_judge.py      # build_severity_prompt()
│   └── comment_refine.py      # [신규] build_comment_prompt()
├── tools/ ...
├── mock_vulnerable/ ...
└── tests/
    ├── test_aggregate.py      # [신규] 취합 파이프라인 테스트
    └── ...
```

---

## 19. 파이프라인 2 상세 설계 (I→M→N→O)

### 트리거 흐름

```
M0 Orchestrator
  │
  ├── asyncio.gather([M2(POST /scan), M3(POST /scan)])
  │         ↓ 둘 다 완료
  └── POST /aggregate  ← M0가 M2+M3 결과 묶어서 전송
          ↓
    aggregate_graph.ainvoke()
          ↓
    [I] aggregate_node   → PostgreSQL pr_aggregated_results 저장
          ↓
    [M] comment_refine_node → LLM 수준별 코멘트 + KMS 링크
          ↓ (조건부)
    Critical ≥ 1 → [O] slack_notify_node → [N] github_comment_node
    Critical = 0 →                         [N] github_comment_node
          ↓
        END
```

### POST /aggregate 입력 계약

> **M2 결과만 포함.** M3(test_verification, performance)는 M3 서버에서 별도로 M4에 전달.
> Dev2는 자신의 분석 결과(static_analysis + security_scan)만 처리한다.

```json
{
  "task_id": "uuid",
  "pr_id": "42",
  "developer": {
    "id": "junior_dev_01",
    "skill_level": "junior",
    "tech_stack": ["python", "fastapi"]
  },
  "context": {
    "architecture_docs": ["chunk_id_1"],
    "coding_conventions": "PEP8 준수",
    "previous_pr_issues": ["N+1 쿼리"]
  },
  "all_results": [
    {"agent": "static_analysis", "task_id": "uuid", "issues": [...], "summary": {...}, "execution_ms": 1200},
    {"agent": "security_scan",   "task_id": "uuid", "issues": [...], "summary": {...}, "execution_ms": 900}
  ]
}
```

### AggregateState (새 TypedDict)

```python
class AggregateState(TypedDict, total=False):
    # 입력 (POST /aggregate 수신)
    task_id: str
    pr_id: str
    developer_id: str
    skill_level: Literal["junior", "mid", "senior"]
    tech_stack: list[str]
    architecture_docs: list[str]     # KMS chunk_id 목록
    coding_conventions: str
    previous_pr_issues: list[str]
    all_results: list[dict]          # M2+M3 AgentOutput 4개

    # aggregate_node 출력
    aggregated_issues: list[dict]    # 취합 + severity 정렬
    total_summary: dict              # {"critical": N, "major": N, "minor": N}

    # comment_refine_node 출력
    comment_body: str                # GitHub PR 코멘트 마크다운

    # github_comment_node 출력
    github_comment_id: Optional[int]
    github_comment_url: Optional[str]
```

---

## 20. 노드별 설계

### [I] aggregate_node

```python
# dev2/nodes/aggregate.py
# 역할: M2+M3 전체 이슈 취합 → severity 정렬 → PostgreSQL 저장

async def aggregate_node(state: AggregateState) -> dict:
    all_issues = []
    total = {"critical": 0, "major": 0, "minor": 0}

    for result in state["all_results"]:
        for issue in result["issues"]:
            all_issues.append({**issue, "agent": result["agent"]})
        for k in total:
            total[k] += result["summary"].get(k, 0)

    # severity 순서: Critical → Major → Minor
    ORDER = {"Critical": 0, "Major": 1, "Minor": 2}
    sorted_issues = sorted(all_issues, key=lambda x: ORDER.get(x["severity"], 3))

    # pr_aggregated_results 테이블에 저장
    await insert_aggregated_result(state["task_id"], state["pr_id"],
                                   state["developer_id"], sorted_issues, total)

    return {"aggregated_issues": sorted_issues, "total_summary": total}
```

**저장 테이블 (신규):**

```sql
CREATE TABLE pr_aggregated_results (
    id           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    task_id      text NOT NULL,
    pr_id        text NOT NULL,
    developer_id text NOT NULL,
    issues       jsonb NOT NULL DEFAULT '[]',
    summary      jsonb NOT NULL DEFAULT '{}',
    created_at   timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX idx_pr_agg_task ON pr_aggregated_results (task_id);
CREATE INDEX idx_pr_agg_developer ON pr_aggregated_results (developer_id, created_at DESC);
```

---

### [M] comment_refine_node

```python
# dev2/nodes/comment_refine.py
# 역할: LLM으로 수준별 코멘트 + KMS 문서 링크 생성

async def comment_refine_node(state: AggregateState) -> dict:
    if USE_MOCK_LLM:
        comment = _build_mock_comment(state)
        return {"comment_body": comment}

    prompt = build_comment_prompt(
        issues=state["aggregated_issues"],
        summary=state["total_summary"],
        skill_level=state["skill_level"],
        tech_stack=state["tech_stack"],
        architecture_docs=state["architecture_docs"],  # KMS 링크 참조
        previous_pr_issues=state["previous_pr_issues"],
    )

    llm = ChatAnthropic(model="claude-sonnet-4-6", temperature=0)
    response = await llm.ainvoke(prompt)
    return {"comment_body": response.content}
```

**프롬프트 전략 (`build_comment_prompt`):**

```
[수준별 설명 지침]
- junior: 왜 문제인지 + 수정 예시 코드 필수
- mid:    원인 + 관련 패턴 설명
- senior: 이슈 목록 + 핵심 포인트만

[KMS 문서 링크]
architecture_docs chunk_id → KMS API로 URL 조회 후 삽입

[코멘트 구조]
## 자동 코드 리뷰 결과
### Critical (N건)
| 파일 | 라인 | 이슈 | 수정 방법 |
...
### Major (N건) ...
### Minor (N건) ...
📚 관련 사내 문서: [N+1 쿼리 방지 가이드](kms://...)
```

---

### [N] github_comment_node

```python
# dev2/nodes/github_comment.py
# 역할: PyGitHub로 PR 코멘트 등록

async def github_comment_node(state: AggregateState) -> dict:
    token = os.getenv("GITHUB_TOKEN", "")
    if not token:
        logger.warning("GITHUB_TOKEN 미설정 — GitHub 코멘트 스킵")
        return {}

    try:
        import asyncio
        from github import Github  # PyGitHub — lazy import

        g = Github(token)
        repo_name = os.getenv("GITHUB_REPO", "")     # 예: "org/repo-name"
        repo = await asyncio.to_thread(g.get_repo, repo_name)
        pr = await asyncio.to_thread(repo.get_pull, int(state["pr_id"]))
        comment = await asyncio.to_thread(pr.create_issue_comment, state["comment_body"])

        logger.info("GitHub PR #%s 코멘트 등록 완료 (id=%d)", state["pr_id"], comment.id)
        return {"github_comment_id": comment.id, "github_comment_url": comment.html_url}

    except Exception as exc:
        # GitHub API 실패 → 로그만 남기고 파이프라인 계속
        logger.error("github_comment_node 실패 (non-fatal): %s", exc)
        return {}
```

**필요 환경변수:**
```bash
GITHUB_TOKEN=ghp_xxxx          # PR 코멘트 작성용 (repo 쓰기 권한)
GITHUB_REPO=org/repo-name      # 대상 레포지토리
```

---

### [O] slack_notify_node

```python
# dev2/nodes/slack_notify.py
# 역할: Critical ≥ 1 시 시니어 개발자 Slack 즉시 알림

async def slack_notify_node(state: AggregateState) -> dict:
    slack_url = os.getenv("SLACK_WEBHOOK_URL", "")
    if not slack_url:
        logger.warning("SLACK_WEBHOOK_URL 미설정 — Slack 알림 스킵")
        return {}

    critical_issues = [i for i in state["aggregated_issues"] if i["severity"] == "Critical"]
    summary = state["total_summary"]

    lines = [f"• `{i['file']}:{i['line']}` — {i['message']}" for i in critical_issues[:5]]
    message = {
        "text": (
            f"🚨 *PR #{state['pr_id']} Critical 이슈 {summary['critical']}건 감지*\n"
            f"개발자: `{state['developer_id']}` | Major: {summary['major']} | Minor: {summary['minor']}\n"
            + "\n".join(lines)
        )
    }

    try:
        import httpx
        async with httpx.AsyncClient() as client:
            await client.post(slack_url, json=message, timeout=5.0)
        logger.info("Slack 알림 전송 완료 (PR #%s)", state["pr_id"])
    except Exception as exc:
        # Slack 실패 → 파이프라인 중단 금지 (CLAUDE.md §12)
        logger.error("Slack 알림 실패 (non-fatal): %s", exc)

    return {}
```

**필요 환경변수:**
```bash
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/xxx
SLACK_CHANNEL_SECURITY=#team-security   # 참고용 (Webhook URL에 채널 포함됨)
```

---

## 21. aggregate_graph.py (파이프라인 2 StateGraph)

```python
# dev2/aggregate_graph.py

from langgraph.graph import StateGraph, END
from dev2.schema import AggregateState
from dev2.nodes.aggregate import aggregate_node
from dev2.nodes.comment_refine import comment_refine_node
from dev2.nodes.github_comment import github_comment_node
from dev2.nodes.slack_notify import slack_notify_node

def _route_after_refine(state: AggregateState) -> str:
    """Critical ≥ 1이면 Slack 먼저, 없으면 GitHub 코멘트로 바로"""
    return "slack_notify" if state["total_summary"].get("critical", 0) >= 1 else "github_comment"

def build_aggregate_graph():
    g = StateGraph(AggregateState)
    g.add_node("aggregate",      aggregate_node)
    g.add_node("comment_refine", comment_refine_node)
    g.add_node("slack_notify",   slack_notify_node)
    g.add_node("github_comment", github_comment_node)

    g.set_entry_point("aggregate")
    g.add_edge("aggregate", "comment_refine")
    g.add_conditional_edges("comment_refine", _route_after_refine, {
        "slack_notify":   "slack_notify",
        "github_comment": "github_comment",
    })
    g.add_edge("slack_notify", "github_comment")   # Slack 후 GitHub 코멘트
    g.add_edge("github_comment", END)

    return g.compile()
```

---

## 22. 오류 처리 (파이프라인 2 추가분)

| 상황 | 처리 |
|------|------|
| `all_results` 비어 있음 | 빈 취합 결과 반환, 파이프라인 계속 |
| PostgreSQL 취합 저장 실패 | **re-raise** (핵심 기능) |
| LLM 코멘트 생성 실패 | 폴백: 이슈 목록만 나열하는 기본 텍스트 사용 |
| GitHub API 429 Rate Limit | `time.sleep(60)` 후 1회 재시도, 재실패 시 로그만 |
| GitHub API 401/403 | Slack 에스컬레이션 후 로그 기록 |
| Slack 알림 실패 | 로그만 남기고 무시 (GitHub 코멘트는 계속 진행) |
| `GITHUB_TOKEN` 미설정 | 경고 로그 후 스킵 (개발 환경 정상 동작) |
| `SLACK_WEBHOOK_URL` 미설정 | 경고 로그 후 스킵 |

---

## 23. 환경변수 추가분 (.env)

```bash
# ── 파이프라인 2 신규 추가 ──────────────────────────────────
GITHUB_TOKEN=ghp_xxxx                   # PR 코멘트 작성 (repo write 권한)
GITHUB_REPO=org/repo-name               # 대상 레포 (예: myteam/task-link)
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/xxx
SLACK_CHANNEL_SECURITY=#team-security   # 참고용
KMS_API_URL=http://dev1-server/kms      # KMS 문서 링크 조회 (Dev1 API)
```
