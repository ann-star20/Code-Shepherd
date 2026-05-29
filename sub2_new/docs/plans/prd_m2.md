# M2 코드 리뷰 모듈 — Dev2 담당자 PRD

> 기반: 팀 공통 PRD v1.6 (M2 코드 리뷰 모듈)
> 작성일: 2026-05-29

---

## 1. 모듈 한 줄 정의

GitHub PR 제출 시 **60초 이내** (Dev2 단독 30초)에 다국어 정적 분석·보안 스캔을 실행하고,
RAG 유사 이슈 주입 + LLM severity 재판단을 거쳐 표준 Output Contract JSON을 생성한다.

---

## 2. 팀 PRD 기준 M2 위치

```
M0 Orchestrator
    │
    ├──► [M2 코드 리뷰 모듈 — 내 담당]
    │         └── AgentOutput × 2 → M0 취합
    │
    └──► M3 테스트 커버리지 모듈
              └── AgentOutput × 2 → M0 취합

M0 취합 → M4 학습 커리큘럼 → GitHub PR 코멘트 + Slack 알림
```

- **입력**: M0(Dev1)이 전달하는 `TaskPayload` (PR Diff + KMS 컨텍스트)
- **출력**: `AgentOutput` × 2 (`static_analysis` + `security_scan`) → M0
- **실행 방식**: M3와 `asyncio.gather`로 동시 실행 (상호 의존 없음)
- **타임아웃**: 30초 — 초과 시 `make_timeout_result()` 반환, 파이프라인 블로킹 금지

---

## 3. 담당 외 기능 (팀 PRD M2 명세 vs 실제 분업)

팀 공통 PRD M2 섹션에 기술되어 있으나 **Dev2 구현 범위 밖**인 기능이다.

| 팀 PRD M2 명세 | 실제 담당 | Dev2 역할 |
|---------------|----------|----------|
| GitHub PR 코멘트 등록 | **Dev4(M4)** | Dev2는 이슈 JSON(`final_output`) 생성까지만. 코멘트 작성은 Dev4가 처리 |
| Slack 즉시 알림 | **Dev4(M4)** | Dev2 `escalate` 노드는 `DEV4_WEBHOOK_URL`로 HTTP POST만 전송. Slack 발송은 Dev4 담당 |
| 관련 사내 문서 링크 제공 | **Dev4(M4)** | KMS 문서 링크는 Dev4가 PR 코멘트 생성 시 포함 |
| 반복 실수 감지 + 코딩 가이드 업데이트 제안 | **Dev5** | `mistake_patterns` 테이블 분석 및 제안은 Dev5 담당 |
| GitHub Webhook 수신 | **Dev1(M0)** | Dev2는 `POST /scan` 수신만. Webhook 수신·라우팅은 Dev1 담당. n8n 미사용 (CLAUDE.md §4) |

**Dev2의 책임 경계**: PR Diff 수신 → 정적분석·보안스캔 → severity 판단 → Output Contract JSON 생성 → Dev4 전달. **"이슈 데이터 생성"만 담당**. "이슈 표시·전달·학습 연계"는 Dev4/Dev5 담당.

---

## 4. 구현된 아키텍처

### LangGraph StateGraph — 5노드 파이프라인

```
START
  └─→ run_tools      (CLI 도구 다국어 병렬 실행)
  └─→ vector_search  (pgVector RAG — 유사 이슈 검색 + enrichment)
  └─→ llm_judge      (RAG Generate — claude-sonnet-4-6 severity 재판단)
  └─→ [조건부 분기]
        ├─ Critical ≥ 1 → escalate (Dev4 즉시 HTTP 알림) → store
        └─ Critical = 0 → store (escalate 건너뜀)
  └─→ store          (Pydantic 검증 + PostgreSQL OLTP + BigQuery OLAP 이중 적재)
  └─→ END
```

**조건부 엣지가 "Agentic Workflow"의 핵심**: LLM 판단 결과(Critical 유무)에 따라 실행 경로가 동적으로 결정됨.

### 노드별 역할

| 노드 | 입력 State 필드 | 출력 State 필드 | 비고 |
|------|----------------|----------------|------|
| `run_tools` | `pr_diff` | `static_raw`, `security_raw` | 언어별 병렬, asyncio.to_thread |
| `vector_search` | `static_raw`, `security_raw` | `enriched` | pgVector 코사인 유사도 검색 |
| `llm_judge` | `enriched`, `skill_level` | `enriched` (업데이트) | 모델 라우팅, Minor는 생략 |
| `escalate` | `enriched`, `task_id` | `{}` (state 변경 없음) | DEV4_WEBHOOK_URL POST |
| `store` | `enriched`, `task_id` 등 | `final_output` | Pydantic 경계 검증 + DB 적재 |

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
      "severity": "Critical | Major | Minor",
      "issue_type": "Bug | Vulnerability | Code Smell",
      "line": 42,
      "file": "src/auth.py",
      "message": "SQL 인젝션 가능성",
      "rule_id": "B608",
      "suggestion": "파라미터화된 쿼리 사용 권장",
      "resolution_example": "db.execute('SELECT * FROM t WHERE id = ?', [user_id])",
      "similar_issues": [
        {"pr_id": "PR-002", "similarity": 0.92, "message": "SQL 파라미터 미처리"}
      ]
    }
  ],
  "summary": { "critical": 1, "major": 2, "minor": 3 },
  "execution_ms": 1200
}
```

> **필드 삭제 금지.** 내부 필드(`llm_judged`, `llm_model`, `_source`)는 store 노드에서 Pydantic 경계 검증 시 자동 제거됨.

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
[x] schema.py         PRReviewState, Dev2State, TaskPayload, AgentOutput (Pydantic)
[x] graph.py          LangGraph StateGraph 5노드 + 조건부 escalate 엣지
[x] run_tools.py      다국어 CLI 병렬 실행 (asyncio.gather + to_thread)
[x] vector_search.py  pgVector RAG enrichment (Mock/실제 전환)
[x] llm_judge.py      모델 라우팅 + LLM severity 재판단 + fallback
[x] escalate.py       Critical HTTP 알림 노드
[x] store.py          Pydantic 검증 + PostgreSQL + BigQuery 이중 적재
[x] api/scan.py       POST /scan (202, BackgroundTasks) + mock-bandit 엔드포인트
[x] tools/            Python/JS/TS/C#/HTML/CSS 도구 구현
[x] prompts/          severity_judge.py — build_severity_prompt()
[x] tests/            단위 테스트, eval, fixtures

[ ] Week 5 — Mock → Dev1 실제 연결 (ANALYSIS_AGENT_URL 교체)
[ ] Week 5 — USE_MOCK_LLM=false 통합 테스트
[ ] Week 5 — common/harness.py run_parallel_agents() 로 교체
[ ] Week 5 — api/insights.py GET 엔드포인트 완성
[ ] Week 5 — PATCH /issues/{id}/dismiss 오탐 처리 엔드포인트 완성
```

---

## 18. 담당 파일 구조

```
dev2/
├── schema.py              # PRReviewState, Dev2State, Pydantic 모델
├── graph.py               # LangGraph StateGraph 조립 + run_dev2() 진입점
├── main.py                # FastAPI 앱 초기화
├── db.py                  # AsyncSessionLocal, insert_* 함수
├── nodes/
│   ├── run_tools.py       # CLI 도구 다국어 병렬 실행
│   ├── vector_search.py   # pgVector RAG enrichment
│   ├── llm_judge.py       # LLM severity 재판단 (모델 라우팅)
│   ├── escalate.py        # Critical 조건부 알림
│   └── store.py           # PostgreSQL + BigQuery 적재
├── api/
│   ├── scan.py            # POST /scan, POST /scan/mock-bandit
│   ├── insights.py        # GET /insights/*
│   └── issues.py          # PATCH /issues/{id}/dismiss
├── tools/
│   ├── router.py          # detect_languages()
│   ├── python/            # pylint, bandit, radon
│   ├── javascript/        # eslint, npm_audit
│   ├── csharp/            # roslyn
│   ├── html/              # htmlhint
│   ├── css/               # stylelint
│   └── common/            # semgrep, pipit
├── prompts/
│   └── severity_judge.py  # build_severity_prompt()
├── vector_store/          # pgVector 검색 유틸
├── mock_vulnerable/
│   └── auth.py            # 데모용 취약 코드 (SQL Injection)
└── tests/
    ├── test_graph.py
    ├── test_tools.py
    ├── test_nodes.py
    ├── test_prompts.py
    ├── test_schema.py
    ├── test_insights.py
    ├── eval/              # LangSmith 평가 데이터셋
    └── fixtures/          # 취약 코드 샘플
```
