# Dev2 — 정적 분석 · 보안 스캔 에이전트

PR diff를 받아 다국어 정적 분석과 보안 스캔을 수행하고, LLM(claude-sonnet-4-6)으로 심각도를 재판단하는 Dev2 에이전트 서비스.

---

## 목차

1. [아키텍처 개요](#아키텍처-개요)
2. [파이프라인 흐름](#파이프라인-흐름)
3. [디렉토리 구조](#디렉토리-구조)
4. [API 엔드포인트](#api-엔드포인트)
5. [입출력 계약](#입출력-계약)
6. [지원 언어 및 도구](#지원-언어-및-도구)
7. [환경변수](#환경변수)
8. [실행 방법](#실행-방법)
9. [테스트](#테스트)

---

## 아키텍처 개요

```
Dev1 Orchestrator
      │ POST /scan (TaskPayload)
      ▼
┌─────────────────────────────────────────────┐
│  Dev2 LangGraph StateGraph                  │
│                                             │
│  run_tools → vector_search → llm_judge      │
│                                    │        │
│                          Critical ≥ 1?      │
│                          ├─ Yes → escalate  │
│                          └─ No  ─┐          │
│                                  ▼          │
│                               store         │
└─────────────────────────────────────────────┘
      │ final_output (Output Contract §5-A)
      ▼
Dev4 Aggregator (3-Way 판정: lgtm / rework / escalate)
```

**MAS 역할**: Parallel Independent Agent (`asyncio.gather`로 Dev3과 병렬 실행)

---

## 파이프라인 흐름

### 1. `run_tools` — 다국어 CLI 병렬 실행

- PR diff에서 변경 파일 추출
- 확장자 기반 언어 감지 (`tools/router.py`)
- 언어별 CLI 도구를 `asyncio.gather`로 병렬 실행 (타임아웃 30초)
- 결과: `static_raw` (정적분석) + `security_raw` (보안스캔)

### 2. `vector_search` — RAG Retrieve

- `static_raw` + `security_raw` 이슈 메시지를 임베딩
- pgVector 코사인 유사도 검색으로 과거 유사 이슈 조회
- 결과: `enriched` (유사 이슈 주입된 이슈 목록)

### 3. `llm_judge` — LLM severity 재판단

- **모델 라우팅** (비용 최적화):
  | severity | 모델 |
  |---|---|
  | Critical | claude-sonnet-4-6 |
  | Major | claude-haiku-4-5 |
  | Minor | LLM 생략 (CLI 판단 신뢰) |
- 파싱 실패 시 1회 재시도 → 원래 severity 유지 (fallback)

### 4. `escalate` (조건부)

- Critical 이슈 ≥ 1건이면 실행
- Dev4 Aggregator에 HTTP 즉시 알림
- 알림 실패 시 로그만 남기고 파이프라인 계속 진행

### 5. `store` — OLTP + OLAP 이중 적재

- PostgreSQL: `scan_executions` → `scan_issues` → `scan_summaries`
- BigQuery: analytics DW (실패 시 스킵)
- `final_output` 반환 (Dev4로 전달되는 Output Contract)

---

## 디렉토리 구조

```
dev2/
├── main.py               # FastAPI 앱 조립
├── graph.py              # LangGraph StateGraph 조립 + run_dev2 진입점
├── schema.py             # Pydantic 모델 + TypedDict State 정의
├── db.py                 # SQLAlchemy AsyncSession (PostgreSQL)
│
├── api/
│   ├── scan.py           # POST /scan (비동기 접수)
│   ├── insights.py       # GET /insights/developer/{id}, /team, /trends
│   └── issues.py         # PATCH /issues/{id}/dismiss
│
├── nodes/
│   ├── run_tools.py      # 노드 1: CLI 병렬 실행
│   ├── vector_search.py  # 노드 2: pgVector RAG Retrieve
│   ├── llm_judge.py      # 노드 3: LLM severity 재판단
│   ├── escalate.py       # 노드 4: Critical 에스컬레이션 (조건부)
│   └── store.py          # 노드 5: PostgreSQL + BigQuery 적재
│
├── tools/
│   ├── router.py         # 확장자 → 언어 + 도구 라우팅
│   ├── python/           # Pylint, Radon, Bandit
│   ├── javascript/       # ESLint, npm-audit
│   ├── csharp/           # Roslyn
│   ├── html/             # HTMLHint
│   ├── css/              # Stylelint
│   └── common/           # Semgrep, pip-audit
│
├── prompts/
│   └── severity_judge.py # LLM 프롬프트 생성 (단일 책임)
│
├── dags/
│   ├── daily_etl.py      # Airflow DAG: 매일 스캔 결과 ETL
│   └── weekly_report.py  # Airflow DAG: 주간 보안 리포트
│
├── migrations/           # PostgreSQL 스키마 마이그레이션
└── tests/                # pytest 단위 테스트 (Mock 기반)
```

---

## API 엔드포인트

### `POST /scan` — PR 분석 트리거

```http
POST /scan
Content-Type: application/json
```

**Request Body** (`TaskPayload`):
```json
{
  "task_id": "uuid",
  "pr_id": "42",
  "pr_diff": "--- a/auth.py\n+++ b/auth.py\n...",
  "developer": {
    "id": "dev-001",
    "skill_level": "junior",
    "tech_stack": ["python", "fastapi"]
  },
  "context": {
    "architecture_docs": ["chunk-id-1"],
    "coding_conventions": "PEP8 준수",
    "previous_pr_issues": ["N+1 쿼리"]
  }
}
```

**Response**: `202 Accepted`
```json
{ "accepted": true, "task_id": "uuid", "message": "분석이 접수됐습니다." }
```

### `GET /insights/developer/{developer_id}`

개발자별 누적 이슈 통계 조회

### `GET /insights/team`

팀 전체 이슈 통계 조회

### `GET /insights/trends`

시계열 이슈 추이 조회

### `PATCH /issues/{issue_id}/dismiss`

오탐(False Positive) 마킹

### `GET /health`

```json
{ "status": "ok", "service": "dev2" }
```

---

## 입출력 계약

### 입력 — Dev1 → Dev2 (`TaskPayload`)

CLAUDE.md §5-B 참고

### 출력 — Dev2 → Dev4 (`AgentOutput`)

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
      "message": "SQL 인젝션 위험",
      "rule_id": "B608",
      "suggestion": "파라미터 바인딩 사용",
      "resolution_example": "cursor.execute('SELECT * FROM users WHERE id = %s', (user_id,))",
      "similar_issues": []
    }
  ],
  "summary": { "critical": 1, "major": 2, "minor": 3 },
  "execution_ms": 1200
}
```

---

## 지원 언어 및 도구

| 언어 | 정적 분석 | 보안 스캔 | 의존성 감사 |
|---|---|---|---|
| Python | Pylint, Radon | Bandit, Semgrep | pip-audit |
| JavaScript/TypeScript | ESLint | Semgrep | npm-audit |
| C# | Roslyn | Semgrep | - |
| HTML | HTMLHint | Semgrep | - |
| CSS/SCSS | Stylelint | - | - |

---

## 환경변수

```bash
# LLM
ANTHROPIC_API_KEY=sk-ant-xxxx
USE_MOCK_LLM=true            # 개발 중: true / 통합·데모: false

# Database
POSTGRES_URL=postgresql+asyncpg://user:pass@localhost:5432/onboarding_db
PGVECTOR_DIMENSION=4096      # Upstage: 4096 / Ollama: 768

# LangSmith
LANGCHAIN_TRACING_V2=true
LANGCHAIN_API_KEY=ls__xxxx
LANGCHAIN_PROJECT=dev2-{github_id}

# Dev4 알림
DEV4_WEBHOOK_URL=http://dev4-service:8004/escalate

# BigQuery (선택)
GOOGLE_APPLICATION_CREDENTIALS=/path/to/key.json
BIGQUERY_PROJECT_ID=your-project
BIGQUERY_DATASET=dev2_analytics
```

---

## 실행 방법

### 로컬 개발 (Mock 모드)

```bash
cd sub2_new
pip install -r dev2/requirements.txt
USE_MOCK_LLM=true uvicorn dev2.main:app --reload --port 8002
```

Swagger UI: http://localhost:8002/docs

### Docker Compose

```bash
cd sub2_new/dev2
docker-compose up
```

---

## 테스트

```bash
cd sub2_new
pytest dev2/tests/ -v
```

- 모든 테스트는 Mock 기반 (실제 DB/LLM 불필요)
- `USE_MOCK_LLM=true` 기본값으로 실행
