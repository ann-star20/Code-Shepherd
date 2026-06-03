# Dev 2: 정적 분석 + 보안 스캔 에이전트 구현 계획

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** LangGraph StateGraph 기반 하이브리드 에이전트. CLI 도구(Pylint/Bandit 등)로 1차 분석 후 LangChain + **claude-sonnet-4-6**가 severity 판단 + 개선 제안 생성. **pgVector** 유사 이슈 검색 + PostgreSQL/BigQuery 이중 적재 + FastAPI 인사이트 API 제공.

> ⚠️ **담당 외 기능 (팀 PRD M2 명세 vs 실제 분업)**
> 팀 공통 PRD M2에 기술되어 있으나 **Dev2 구현 범위 밖**인 기능:
> - **GitHub PR 코멘트 등록** → Dev4(M4) 담당. Dev2는 이슈 JSON만 생성해 Dev4에 전달
> - **Slack 즉시 알림** → Dev4(M4) 담당. Dev2 escalate 노드는 Dev4 webhook HTTP POST만 수행
> - **관련 사내 문서 링크 제공** → Dev4(M4) 담당. KMS 링크는 Dev4가 PR 코멘트에 포함
> - **반복 실수 감지 + 코딩 가이드 업데이트 제안** → Dev5 담당 (mistake_patterns 테이블)
> - **GitHub Webhook 수신** → Dev1(M0) 담당. Dev2는 POST /scan 수신만. n8n 미사용 (CLAUDE.md §4)

**Architecture:** LangGraph StateGraph 5노드 (run_tools → **vector_search → llm_judge** → escalate(조건부) → store). RAG 패턴: vector_search가 pgVector 코사인 유사도로 유사 이슈 먼저 검색 → llm_judge 프롬프트에 주입. 모델 라우팅(Critical/Major→**claude-sonnet-4-6**, Minor→스킵). GitHub Webhook은 **Dev1 Orchestrator**가 수신 → Dev2로 라우팅 (n8n 미사용, CLAUDE.md §4 참고).

> **[CLAUDE.md §9 준수]** LLM: claude-sonnet-4-6 | Vector DB: pgVector | State: PRReviewState 확장

**Tech Stack:** Python 3.11+, LangGraph, LangChain, **Anthropic API (claude-sonnet-4-6)**, **pgVector**, PostgreSQL, BigQuery, Apache Airflow, Docker, FastAPI, Pylint, Bandit, Semgrep, pip-audit, radon, LangSmith

---

## Task 1: Docker + 프로젝트 초기 세팅

**Files:**
- Create: `dev2/Dockerfile`
- Create: `dev2/docker-compose.yml`
- Create: `dev2/requirements.txt`
- Create: `dev2/.env.example`

**Step 1: 디렉토리 구조 생성**

```bash
mkdir -p dev2/nodes dev2/vector_store dev2/api dev2/dags dev2/prompts
mkdir -p dev2/tests/fixtures dev2/tests/eval
mkdir -p dev2/tools/python dev2/tools/javascript dev2/tools/csharp
mkdir -p dev2/tools/html dev2/tools/css dev2/tools/common
touch dev2/__init__.py dev2/nodes/__init__.py dev2/prompts/__init__.py
touch dev2/tools/__init__.py
touch dev2/tools/python/__init__.py dev2/tools/javascript/__init__.py
touch dev2/tools/csharp/__init__.py dev2/tools/html/__init__.py
touch dev2/tools/css/__init__.py dev2/tools/common/__init__.py
touch dev2/vector_store/__init__.py dev2/api/__init__.py
```

**Step 2: requirements.txt 작성**

```
fastapi==0.111.0
uvicorn==0.29.0
langgraph==0.1.19
langchain==0.2.0
langchain-anthropic==0.1.23
langsmith==0.1.63
anthropic==0.28.0
pgvector==0.3.2
psycopg[binary,pool]==3.1.19
sqlalchemy[asyncio]==2.0.30
asyncpg==0.29.0
google-cloud-bigquery==3.22.0
apache-airflow==2.9.0
pydantic==2.7.1
pylint==3.2.0
bandit==1.7.8
pip-audit==2.7.3
radon==6.0.1
python-dotenv==1.0.1
pytest==8.2.0
pytest-asyncio==0.23.6
httpx==0.27.0
```

> ⚠️ **팀 표준 기술스택 준수**
> - LLM: `anthropic` (claude-sonnet-4-6) — OpenAI 대신 팀 표준
> - Vector DB: `pgvector` (PostgreSQL 확장) — Milvus 대신 팀 표준
> - `pymilvus` 사용 금지 (별도 Milvus 서버 의존성 제거)

**Step 3: .env.example 작성**

```bash
# ===== LangSmith (Harness) — CLAUDE.md 섹션 3 필수 =====
LANGCHAIN_TRACING_V2=true
LANGCHAIN_API_KEY=ls__xxxx
LANGCHAIN_PROJECT=dev2-alice          # 반드시 dev2-{본인 GitHub ID} 형식 사용
                                       # 예: dev2-alice, dev2-bob
                                       # ⚠️ dev2-agent 같은 역할명만 쓰면 팀원 trace가 섞임

# ===== LLM — 팀 표준 Claude =====
ANTHROPIC_API_KEY=sk-ant-xxxx
USE_MOCK_LLM=true                     # 개발 중 true, 통합 테스트/데모 시 false

# ===== Database =====
POSTGRES_URL=postgresql+asyncpg://user:password@postgres:5432/dev2_db
PGVECTOR_DIMENSION=4096               # 팀 결정값 — Upstage:4096 / Ollama:768 (통일 필수)

# ===== BigQuery (분석용 DW) =====
GOOGLE_APPLICATION_CREDENTIALS=/app/credentials/bigquery.json
BIGQUERY_PROJECT_ID=your_project_id
BIGQUERY_DATASET=dev2_dataset

# ===== Slack (보안 룰셋 업데이트 알림 — 주간 Airflow DAG 전용) =====
# ⚠️ PR Critical 에스컬레이션 Slack 알림은 Dev4(M4) 담당
# Dev2는 escalate 노드에서 DEV4_WEBHOOK_URL로 HTTP POST만 전송
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/xxx
SLACK_CHANNEL_SECURITY=#team-security

# ===== Agent Service URLs (Mock 기반 개발용) =====
DEV4_WEBHOOK_URL=http://mock-server:8001/eval   # Critical 에스컬레이션 전달
```

**Step 4: Dockerfile 작성**

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN apt-get update && apt-get install -y nodejs npm && npm install -g eslint
COPY . .
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8002"]
```

**Step 5: docker-compose.yml 작성**

```yaml
# [CLAUDE.md §9] Vector DB: pgVector (PostgreSQL 확장) — Milvus 서비스 제거
services:
  dev2:
    build: .
    ports: ["8002:8002"]
    env_file: .env
    depends_on: [postgres]   # ← milvus 의존성 제거

  postgres:
    image: pgvector/pgvector:pg16    # ← pgvector 내장 이미지 (pgVector HNSW 인덱스)
    environment:
      POSTGRES_DB: dev2_db
      POSTGRES_USER: user
      POSTGRES_PASSWORD: password
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./dev2/migrations:/docker-entrypoint-initdb.d  # 시작 시 마이그레이션 자동 실행
    ports: ["5432:5432"]
    command: >
      postgres -c shared_preload_libraries=vector
               -c statement_timeout=30s
               -c idle_in_transaction_session_timeout=30s

  airflow:
    image: apache/airflow:2.9.0
    ports: ["8080:8080"]
    volumes: [./dags:/opt/airflow/dags]
    command: standalone
    depends_on: [postgres]

volumes:
  postgres_data:
```

> **Milvus 제거 이유**: CLAUDE.md §9 팀 표준이 pgVector이므로 별도 Milvus 서버 불필요.
> pgVector는 PostgreSQL 확장으로 동일 postgres 컨테이너에 포함됨.

**Step 6: 실행 확인**

```bash
cd dev2
docker-compose up -d
docker-compose ps
```
Expected: 3개 서비스 모두 Up (dev2, postgres, airflow)

**Step 7: 커밋**

```bash
git add dev2/
git commit -m "chore: Docker + 프로젝트 초기 세팅"
```

---

## Task 2: Pydantic 스키마 + DB 스키마

**Files:**
- Create: `dev2/schema.py`
- Create: `dev2/db.py`
- Create: `dev2/migrations/001_initial.sql`
- Create: `dev2/tests/test_schema.py`

**Step 1: 실패하는 테스트 작성**

```python
# dev2/tests/test_schema.py
from dev2.schema import TaskPayload, AgentOutput, Issue, Summary, Dev2State

def test_task_payload():
    p = TaskPayload(
        task_id="uuid-001", pr_id="1",
        pr_diff="+++ b/src/auth.py",
        developer={"id": "dev-001", "skill_level": "junior", "tech_stack": ["python"]},
        context={"architecture_docs": ["chunk-001"], "coding_conventions": "PEP8",
                 "previous_pr_issues": ["N+1 쿼리"]}  # context 필드 포함 (CLAUDE.md §5-B)
    )
    assert p.developer.skill_level == "junior"
    assert p.context.previous_pr_issues == ["N+1 쿼리"]

def test_task_payload_context_defaults():
    # context 없이도 기본값으로 동작해야 함
    p = TaskPayload(
        task_id="uuid-002", pr_id="2",
        pr_diff="+++ b/src/app.py",
        developer={"id": "dev-001", "skill_level": "junior", "tech_stack": ["python"]}
    )
    assert p.context.architecture_docs == []
    assert p.context.previous_pr_issues == []

def test_dev2_state_extends_pr_review_state():
    # Dev2State는 PRReviewState 필드를 모두 포함해야 함 (CLAUDE.md §11)
    state: Dev2State = {
        "task_id": "uuid-001",
        "pr_id": "1",
        "pr_diff": "+++ b/src/auth.py",
        "developer_id": "dev-001",
        "static_raw": [],
        "security_raw": [],
        "enriched": [],
        "final_output": [],
    }
    assert state["task_id"] == "uuid-001"
    assert state["enriched"] == []

def test_issue_with_similar():
    issue = Issue(
        severity="Critical", line=42, file="src/auth.py",
        message="SQL 인젝션", rule_id="SEC-001",
        suggestion="파라미터화된 쿼리", similar_issues=[{"pr_id": "98", "similarity": 0.94}]
    )
    assert issue.similar_issues[0]["similarity"] == 0.94
```

**Step 2: 테스트 실패 확인**

```bash
pytest dev2/tests/test_schema.py -v
```
Expected: FAIL with `ModuleNotFoundError`

**Step 3: schema.py 구현**

> **[CLAUDE.md §11 준수]** `Dev2State`는 팀 공통 `PRReviewState`를 확장해야 한다.
> Week 5 통합 시 Dev1이 채운 State를 그대로 수신하므로, 독립 TypedDict로 만들면
> 필드 누락/타입 충돌이 발생한다.

```python
# dev2/schema.py
from pydantic import BaseModel
from typing import Literal, Optional, TypedDict

# ── 팀 공통 State (CLAUDE.md §11) ──────────────────────────────────────────
# 실제 통합 시: from common.state import PRReviewState
# 개발 단계(Week 2~3): 아래 인라인 정의로 대체 — 필드 구조 동일해야 함
class PRReviewState(TypedDict, total=False):
    # Dev1이 채움 (입력)
    task_id: str
    pr_id: str
    pr_diff: str
    developer_id: str
    skill_level: Literal["junior", "mid", "senior"]
    tech_stack: list[str]
    architecture_docs: list[str]        # chunk_id 목록 (pgVector 검색 결과)
    coding_conventions: str
    previous_pr_issues: list[str]
    # Dev2/3가 채움
    analysis_results: list[dict]
    # Dev4가 채움
    verdict: Optional[Literal["lgtm", "rework", "escalate"]]
    comment_body: Optional[str]
    learning_resources: Optional[list[dict]]
    # Dev5가 채움
    issue_patterns: Optional[list[str]]
    curriculum_update: Optional[dict]

# ── Dev2 전용 추가 필드 (PRReviewState 확장) ─────────────────────────────────
class Dev2State(PRReviewState, total=False):
    """
    Dev2 내부 처리 State.
    PRReviewState 필드를 모두 상속하며, Dev2 파이프라인 전용 필드를 추가한다.
    통합(Week 5) 시 common.state.PRReviewState 임포트로 교체.
    """
    static_raw: list[dict]      # CLI 도구 원본 결과 (run_tools 노드 출력)
    security_raw: list[dict]    # 보안 도구 원본 결과 (run_tools 노드 출력)
    enriched: list[dict]        # pgVector 유사 이슈 + LLM 판단 결과
    final_output: list[dict]    # Output Contract A 형식 최종 결과

# ── Pydantic 모델 (Dev1 → Dev2 입력 계약 검증, CLAUDE.md §5-B) ─────────────
class Developer(BaseModel):
    id: str
    skill_level: Literal["junior", "mid", "senior"]
    tech_stack: list[str]

class TaskContext(BaseModel):
    """CLAUDE.md §5-B: Dev1 → Dev2/3 입력 계약의 context 필드"""
    architecture_docs: list[str] = []       # chunk_id 목록
    coding_conventions: str = ""
    previous_pr_issues: list[str] = []

class TaskPayload(BaseModel):
    """CLAUDE.md §5-B: Dev1 → Dev2/3 입력 계약 전체"""
    task_id: str
    pr_id: str
    pr_diff: str
    developer: Developer
    context: TaskContext = TaskContext()    # ← context 필드 추가 (팀 계약 준수)

class Issue(BaseModel):
    severity: Literal["Critical", "Major", "Minor"]
    line: int
    file: str
    message: str
    rule_id: str
    suggestion: str
    similar_issues: list[dict] = []

class Summary(BaseModel):
    critical: int = 0
    major: int = 0
    minor: int = 0

class AgentOutput(BaseModel):
    """CLAUDE.md §5-A: Dev2/3 → Dev4 Output Contract"""
    agent: Literal["static_analysis", "security_scan"]
    task_id: str
    issues: list[Issue] = []
    summary: Summary = Summary()
    execution_ms: int
```

**Step 4: 마이그레이션 파일 작성 (4개로 분리)**

```sql
-- dev2/migrations/001_extensions.sql
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;

-- 보안 기본값
REVOKE ALL ON SCHEMA public FROM public;

-- 타임아웃 설정
ALTER SYSTEM SET idle_in_transaction_session_timeout = '30s';
ALTER SYSTEM SET statement_timeout = '30s';
SELECT pg_reload_conf();
```

```sql
-- dev2/migrations/002_tables.sql

-- [CLAUDE.md §3] agent_traces 연동을 위해 trace_id 컬럼 포함
-- trace_id 형식: "pr_{12hex}" (PR 파이프라인), "{parent}_{agent}_{4hex}" (서브 에이전트)
CREATE TABLE scan_executions (
    id            bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    task_id       text        NOT NULL,
    trace_id      text        NOT NULL,  -- agent_traces.trace_id 연결 (CLAUDE.md §3)
    pr_id         text        NOT NULL,
    developer_id  text        NOT NULL,
    scanned_at    timestamptz NOT NULL DEFAULT now(),
    execution_ms  int
);

CREATE TABLE scan_issues (
    id              bigint  GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    scan_id         bigint  NOT NULL REFERENCES scan_executions(id) ON DELETE CASCADE,
    agent           text    NOT NULL,   -- 'static_analysis' | 'security_scan'
    severity        text    NOT NULL,   -- 'Critical' | 'Major' | 'Minor'
    rule_id         text    NOT NULL,
    file            text,
    line            int,
    message              text,
    suggestion           text,
    similar_issues       jsonb    NOT NULL DEFAULT '[]',
    is_false_positive    boolean  NOT NULL DEFAULT false  -- 오탐 표시
);

CREATE TABLE scan_summaries (
    id        bigint  GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    scan_id   bigint  NOT NULL REFERENCES scan_executions(id) ON DELETE CASCADE,
    agent     text    NOT NULL,
    critical  int     NOT NULL DEFAULT 0,
    major     int     NOT NULL DEFAULT 0,
    minor     int     NOT NULL DEFAULT 0,
    CONSTRAINT uq_scan_summaries_scan_agent UNIQUE (scan_id, agent)
);
```

```sql
-- dev2/migrations/003_indexes.sql

-- BRIN: scanned_at 시계열 (순차 증가 → B-tree보다 크기 90% 작음)
CREATE INDEX idx_scan_executions_scanned_at
    ON scan_executions USING brin (scanned_at);

-- 복합: developer 인사이트 쿼리 (equality 먼저, range 나중)
CREATE INDEX idx_scan_executions_developer_time
    ON scan_executions (developer_id, scanned_at DESC);

-- FK 인덱스: JOIN 성능
CREATE INDEX idx_scan_issues_scan_id    ON scan_issues (scan_id);
CREATE INDEX idx_scan_summaries_scan_id ON scan_summaries (scan_id);

-- 복합: 팀별 인사이트 GROUP BY rule_id, severity
CREATE INDEX idx_scan_issues_rule_severity
    ON scan_issues (rule_id, severity);

-- 부분 인덱스: Critical만 (에스컬레이션 조회 전용, 전체의 5~10%)
CREATE INDEX idx_scan_issues_critical
    ON scan_issues (scan_id, rule_id)
    WHERE severity = 'Critical';

-- GIN: similar_issues JSONB 검색
CREATE INDEX idx_scan_issues_similar
    ON scan_issues USING gin (similar_issues);

-- 커버링: /insights/developer 쿼리 (테이블 스캔 제거)
CREATE INDEX idx_executions_developer_covering
    ON scan_executions (developer_id)
    INCLUDE (id, scanned_at);
```

**Step 5: 마이그레이션 실행**

```bash
psql postgresql://user:password@localhost:5432/dev2_db \
  -f dev2/migrations/001_extensions.sql \
  -f dev2/migrations/002_tables.sql \
  -f dev2/migrations/003_indexes.sql
```
Expected: CREATE TABLE 3개, CREATE INDEX 8개, UNIQUE 제약 1개

**Step 6: db.py 구현**

```python
# dev2/db.py
import os, json
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import text

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://user:password@localhost:5432/dev2_db")
engine = create_async_engine(DATABASE_URL)
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

async def insert_scan_execution(payload: dict, execution_ms: int, trace_id: str) -> int:
    """
    scan_executions에 스캔 실행 기록을 INSERT한다.
    trace_id: CLAUDE.md §3 형식 ("pr_{12hex}" 또는 서브 에이전트 trace)
    """
    async with AsyncSessionLocal() as s:
        r = await s.execute(text("""
            INSERT INTO scan_executions (task_id, trace_id, pr_id, developer_id, execution_ms)
            VALUES (:task_id, :trace_id, :pr_id, :developer_id, :execution_ms)
            RETURNING id
        """), {
            "task_id": payload["task_id"],
            "trace_id": trace_id,           # agent_traces 연결 키 (CLAUDE.md §3)
            "pr_id": payload["pr_id"],
            "developer_id": payload["developer"]["id"],
            "execution_ms": execution_ms,
        })
        await s.commit()
        return r.scalar()  # bigint 반환 (str 변환 불필요)

async def insert_scan_issues(scan_id: int, issues: list[dict], agent: str):
    if not issues:
        return
    async with AsyncSessionLocal() as s:
        for i in issues:
            await s.execute(text("""
                INSERT INTO scan_issues
                  (scan_id, agent, severity, rule_id, file, line, message, suggestion, similar_issues)
                VALUES
                  (:scan_id, :agent, :severity, :rule_id, :file, :line, :message, :suggestion, :similar_issues)
            """), {
                "scan_id": scan_id,
                "agent": agent,
                "severity": i["severity"],
                "rule_id": i["rule_id"],
                "file": i.get("file", ""),
                "line": i.get("line", 0),
                "message": i["message"],
                "suggestion": i["suggestion"],
                "similar_issues": json.dumps(i.get("similar_issues", [])),
            })
        await s.commit()

async def insert_scan_summary(scan_id: int, agent: str, summary: dict):
    async with AsyncSessionLocal() as s:
        # UPSERT: 재스캔 시 덮어쓰기 (uq_scan_summaries_scan_agent 활용)
        await s.execute(text("""
            INSERT INTO scan_summaries (scan_id, agent, critical, major, minor)
            VALUES (:scan_id, :agent, :critical, :major, :minor)
            ON CONFLICT (scan_id, agent)
            DO UPDATE SET
                critical = EXCLUDED.critical,
                major    = EXCLUDED.major,
                minor    = EXCLUDED.minor
        """), {"scan_id": scan_id, "agent": agent, **summary})
        await s.commit()
```

**Step 7: 테스트 통과 확인**

```bash
pytest dev2/tests/test_schema.py -v
```
Expected: PASS 3 tests

**Step 8: 커밋**

```bash
git add dev2/schema.py dev2/db.py dev2/migrations/ dev2/tests/test_schema.py
git commit -m "feat: Pydantic 스키마 + LangGraph State + DB 스키마"
```

---

## Task 3: CLI 도구 + 다국어 라우터 (tools/)

**Files:**
- Create: `dev2/tools/router.py`
- Create: `dev2/tools/python/pylint_tool.py`
- Create: `dev2/tools/python/radon_tool.py`
- Create: `dev2/tools/python/bandit_tool.py`
- Create: `dev2/tools/javascript/eslint_tool.py`
- Create: `dev2/tools/javascript/npm_audit_tool.py`
- Create: `dev2/tools/csharp/roslyn_tool.py`
- Create: `dev2/tools/html/htmlhint_tool.py`
- Create: `dev2/tools/css/stylelint_tool.py`
- Create: `dev2/tools/common/semgrep_tool.py`
- Create: `dev2/tools/common/pipit_tool.py`
- Create: `dev2/tests/fixtures/bad_code.py`
- Create: `dev2/tests/fixtures/vulnerable_code.py`
- Create: `dev2/tests/fixtures/bad_code.js`
- Create: `dev2/tests/fixtures/bad_code.html`
- Create: `dev2/tests/test_tools.py`

**Step 1: 테스트 픽스처 작성**

```python
# dev2/tests/fixtures/bad_code.py
def bad_function(a, b, c, d, e, f, g):  # 파라미터 과다
    unused = 42
    return a + b

def very_complex(a, b, c):
    if a:
        if b:
            if c:
                for i in range(10):
                    if i % 2:
                        if i > 5:
                            if a > b:
                                if b > c:
                                    if c > 0:
                                        return i
    return 0
```

```python
# dev2/tests/fixtures/vulnerable_code.py
import sqlite3

def get_user(username):
    conn = sqlite3.connect("test.db")
    cursor = conn.cursor()
    query = "SELECT * FROM users WHERE name = '" + username + "'"  # SQL Injection
    cursor.execute(query)
    return cursor.fetchall()
```

```javascript
// dev2/tests/fixtures/bad_code.js
var x = 1        // var 대신 const/let 사용해야 함
eval("alert(1)") // 보안 위험: eval 사용
```

```html
<!-- dev2/tests/fixtures/bad_code.html -->
<html>
<body>
  <script>eval("xss")</script>  <!-- XSS 위험 -->
  <img src=x onerror="alert(1)">
</body>
</html>
```

**Step 2: 실패하는 테스트 작성**

```python
# dev2/tests/test_tools.py
import pytest
from dev2.tools.python.pylint_tool import run_pylint
from dev2.tools.python.radon_tool import run_radon
from dev2.tools.python.bandit_tool import run_bandit
from dev2.tools.javascript.eslint_tool import run_eslint
from dev2.tools.common.semgrep_tool import run_semgrep
from dev2.tools.router import detect_languages, get_tools_for_file

# Python 도구 테스트
def test_pylint_returns_issues():
    issues = run_pylint(["dev2/tests/fixtures/bad_code.py"])
    assert len(issues) > 0
    assert all(i["severity"] in ("Critical","Major","Minor") for i in issues)

def test_radon_detects_complexity():
    issues = run_radon(["dev2/tests/fixtures/bad_code.py"])
    assert any("순환복잡도" in i["message"] for i in issues)

def test_bandit_detects_sql_injection():
    issues = run_bandit(["dev2/tests/fixtures/vulnerable_code.py"])
    assert len(issues) > 0

# JavaScript 도구 테스트
def test_eslint_returns_issues():
    issues = run_eslint(["dev2/tests/fixtures/bad_code.js"])
    assert len(issues) > 0
    assert all(i["severity"] in ("Critical","Major","Minor") for i in issues)

# 공통 보안 (Semgrep)
def test_semgrep_detects_html_xss():
    issues = run_semgrep(["dev2/tests/fixtures/bad_code.html"], lang="html")
    assert len(issues) > 0

# 라우터 테스트
def test_router_detects_language():
    groups = detect_languages(["auth.py", "app.js", "index.html", "style.css"])
    assert "python" in groups
    assert "javascript" in groups
    assert "html" in groups
    assert "css" in groups

def test_router_unknown_extension():
    # 모르는 확장자 → semgrep만 실행
    _, static, security, _ = get_tools_for_file("file.rb")
    assert static == []
    assert "semgrep" in security
```

**Step 3: 테스트 실패 확인**

```bash
pytest dev2/tests/test_tools.py -v
```
Expected: FAIL with `ImportError`

**Step 4: router.py 구현**

```python
# dev2/tools/router.py
from pathlib import Path

LANGUAGE_TOOL_MAP = {
    ".py":   ("python",     ["pylint", "radon"],  ["bandit", "semgrep"], ["pip_audit"]),
    ".js":   ("javascript", ["eslint"],           ["semgrep"],           ["npm_audit"]),
    ".jsx":  ("javascript", ["eslint"],           ["semgrep"],           ["npm_audit"]),
    ".ts":   ("typescript", ["eslint_ts"],        ["semgrep"],           ["npm_audit"]),
    ".tsx":  ("typescript", ["eslint_ts"],        ["semgrep"],           ["npm_audit"]),
    ".cs":   ("csharp",     ["roslyn"],           ["semgrep"],           []),
    ".html": ("html",       ["htmlhint"],         ["semgrep"],           []),
    ".htm":  ("html",       ["htmlhint"],         ["semgrep"],           []),
    ".css":  ("css",        ["stylelint"],        [],                    []),
    ".scss": ("css",        ["stylelint"],        [],                    []),
}

def detect_languages(files: list[str]) -> dict[str, list[str]]:
    groups: dict[str, list[str]] = {}
    for f in files:
        ext = Path(f).suffix.lower()
        lang = LANGUAGE_TOOL_MAP.get(ext, ("unknown", [], ["semgrep"], []))[0]
        groups.setdefault(lang, []).append(f)
    return groups

def get_tools_for_file(filepath: str) -> tuple:
    ext = Path(filepath).suffix.lower()
    return LANGUAGE_TOOL_MAP.get(ext, ("unknown", [], ["semgrep"], []))
```

**Step 5: Python 도구 구현**

```python
# dev2/tools/python/pylint_tool.py
import subprocess, json

SEVERITY_MAP = {"E": "Critical", "F": "Critical", "W": "Major", "C": "Minor", "R": "Minor"}

def run_pylint(files: list[str]) -> list[dict]:
    if not files:
        return []
    r = subprocess.run(
        ["pylint", "--output-format=json", "--score=no"] + files,
        capture_output=True, text=True, timeout=30
    )
    try:
        raw = json.loads(r.stdout)
    except json.JSONDecodeError:
        return []
    return [{
        "severity": SEVERITY_MAP.get(i.get("type","W")[0].upper(), "Minor"),
        "line": i.get("line", 0), "file": i.get("path", ""),
        "message": i.get("message", ""),
        "rule_id": f"SA-{i.get('message-id','UNKNOWN')}",
        "suggestion": f"Pylint: {i.get('symbol','')}",
        "similar_issues": [],
    } for i in raw]
```

```python
# dev2/tools/python/radon_tool.py
import subprocess, json

def run_radon(files: list[str]) -> list[dict]:
    if not files:
        return []
    r = subprocess.run(
        ["radon", "cc", "--json", "--min", "B"] + files,
        capture_output=True, text=True, timeout=30
    )
    try:
        raw = json.loads(r.stdout)
    except json.JSONDecodeError:
        return []
    issues = []
    for filepath, funcs in raw.items():
        for func in funcs:
            cc = func.get("complexity", 0)
            if cc > 10:
                issues.append({
                    "severity": "Major", "line": func.get("lineno", 0),
                    "file": filepath,
                    "message": f"순환복잡도 {cc} 감지. 함수: {func.get('name')}",
                    "rule_id": "SA-COMPLEXITY",
                    "suggestion": "함수를 더 작은 단위로 분리하세요.",
                    "similar_issues": [],
                })
    return issues
```

```python
# dev2/tools/python/bandit_tool.py
import subprocess, json

SEVERITY_MAP = {"HIGH": "Critical", "MEDIUM": "Major", "LOW": "Minor"}

def run_bandit(files: list[str]) -> list[dict]:
    if not files:
        return []
    r = subprocess.run(
        ["bandit", "-r", "-f", "json"] + files,
        capture_output=True, text=True, timeout=30
    )
    try:
        raw = json.loads(r.stdout)
    except json.JSONDecodeError:
        return []
    return [{
        "severity": SEVERITY_MAP.get(i.get("issue_severity","LOW"), "Minor"),
        "line": i.get("line_number", 0), "file": i.get("filename", ""),
        "message": i.get("issue_text", ""),
        "rule_id": f"SEC-{i.get('test_id','UNKNOWN')}",
        "suggestion": i.get("more_info", "Bandit 보안 가이드 참조"),
        "similar_issues": [],
    } for i in raw.get("results", [])]
```

**Step 6: JavaScript / TypeScript 도구 구현**

```python
# dev2/tools/javascript/eslint_tool.py
import subprocess, json

SEVERITY_MAP = {2: "Critical", 1: "Major", 0: "Minor"}

def run_eslint(files: list[str], ts: bool = False) -> list[dict]:
    if not files:
        return []
    config = "--ext .ts,.tsx" if ts else "--ext .js,.jsx"
    r = subprocess.run(
        ["eslint", "--format=json", config] + files,
        capture_output=True, text=True, timeout=30
    )
    try:
        raw = json.loads(r.stdout)
    except json.JSONDecodeError:
        return []
    issues = []
    for file_result in raw:
        for msg in file_result.get("messages", []):
            issues.append({
                "severity": SEVERITY_MAP.get(msg.get("severity", 1), "Minor"),
                "line": msg.get("line", 0),
                "file": file_result.get("filePath", ""),
                "message": msg.get("message", ""),
                "rule_id": f"JS-{msg.get('ruleId','UNKNOWN')}",
                "suggestion": f"ESLint rule: {msg.get('ruleId','')}",
                "similar_issues": [],
            })
    return issues
```

```python
# dev2/tools/javascript/npm_audit_tool.py
import subprocess, json

def run_npm_audit() -> list[dict]:
    r = subprocess.run(
        ["npm", "audit", "--json"],
        capture_output=True, text=True, timeout=60
    )
    try:
        raw = json.loads(r.stdout)
    except json.JSONDecodeError:
        return []
    SEVERITY_MAP = {"critical": "Critical", "high": "Critical",
                    "moderate": "Major", "low": "Minor"}
    return [{
        "severity": SEVERITY_MAP.get(v.get("severity","low"), "Minor"),
        "line": 0, "file": "package.json",
        "message": f"npm CVE: {v.get('name')} — {v.get('title','')}",
        "rule_id": f"CVE-{v.get('cves',['UNKNOWN'])[0]}",
        "suggestion": f"업그레이드: {v.get('fixAvailable',{}).get('version','확인 필요')}",
        "similar_issues": [],
    } for v in raw.get("vulnerabilities", {}).values()]
```

**Step 7: HTML / CSS / C# 도구 구현**

```python
# dev2/tools/html/htmlhint_tool.py
import subprocess, json

def run_htmlhint(files: list[str]) -> list[dict]:
    if not files:
        return []
    r = subprocess.run(
        ["htmlhint", "--format=json"] + files,
        capture_output=True, text=True, timeout=30
    )
    try:
        raw = json.loads(r.stdout)
    except json.JSONDecodeError:
        return []
    issues = []
    for file_result in raw:
        for msg in file_result.get("messages", []):
            issues.append({
                "severity": "Major" if msg.get("type") == "error" else "Minor",
                "line": msg.get("line", 0), "file": file_result.get("fileid", ""),
                "message": msg.get("message", ""),
                "rule_id": f"HTML-{msg.get('rule',{}).get('id','UNKNOWN')}",
                "suggestion": msg.get("rule",{}).get("description",""),
                "similar_issues": [],
            })
    return issues
```

```python
# dev2/tools/css/stylelint_tool.py
import subprocess, json

def run_stylelint(files: list[str]) -> list[dict]:
    if not files:
        return []
    r = subprocess.run(
        ["stylelint", "--formatter=json"] + files,
        capture_output=True, text=True, timeout=30
    )
    try:
        raw = json.loads(r.stdout)
    except json.JSONDecodeError:
        return []
    issues = []
    for file_result in raw:
        for w in file_result.get("warnings", []):
            issues.append({
                "severity": "Major" if w.get("severity") == "error" else "Minor",
                "line": w.get("line", 0), "file": file_result.get("source", ""),
                "message": w.get("text", ""),
                "rule_id": f"CSS-{w.get('rule','UNKNOWN')}",
                "suggestion": f"Stylelint rule: {w.get('rule','')}",
                "similar_issues": [],
            })
    return issues
```

```python
# dev2/tools/csharp/roslyn_tool.py
import subprocess, re

def run_roslyn(files: list[str]) -> list[dict]:
    """dotnet build --no-restore 로 Roslyn 분석기 실행"""
    if not files:
        return []
    r = subprocess.run(
        ["dotnet", "build", "--no-restore", "--verbosity=normal"],
        capture_output=True, text=True, timeout=60
    )
    issues = []
    # dotnet 출력 파싱: "path(line,col): warning CSXXXX: message"
    pattern = re.compile(r"(.+)\((\d+),\d+\): (warning|error) (CS\w+): (.+)")
    for line in r.stdout.splitlines():
        m = pattern.match(line.strip())
        if m:
            issues.append({
                "severity": "Critical" if m.group(3) == "error" else "Major",
                "line": int(m.group(2)), "file": m.group(1),
                "message": m.group(5),
                "rule_id": f"CS-{m.group(4)}",
                "suggestion": f"Roslyn: {m.group(4)} 참조",
                "similar_issues": [],
            })
    return issues
```

**Step 8: 공통 보안 도구 (Semgrep) 구현**

```python
# dev2/tools/common/semgrep_tool.py
import subprocess, json

SEVERITY_MAP = {"ERROR": "Critical", "WARNING": "Major", "INFO": "Minor"}

def run_semgrep(files: list[str], lang: str = "generic") -> list[dict]:
    """Semgrep OWASP 룰셋 — 전 언어 공통 보안 검사"""
    if not files:
        return []
    r = subprocess.run(
        ["semgrep", "--config=p/owasp-top-ten", "--json"] + files,
        capture_output=True, text=True, timeout=60
    )
    try:
        raw = json.loads(r.stdout)
    except json.JSONDecodeError:
        return []
    return [{
        "severity": SEVERITY_MAP.get(i.get("extra",{}).get("severity","WARNING"), "Major"),
        "line": i.get("start",{}).get("line", 0),
        "file": i.get("path", ""),
        "message": i.get("extra",{}).get("message",""),
        "rule_id": f"OWASP-{i.get('check_id','UNKNOWN').split('.')[-1]}",
        "suggestion": i.get("extra",{}).get("fix","Semgrep OWASP 가이드 참조"),
        "similar_issues": [],
    } for i in raw.get("results", [])]
```

**Step 9: 테스트 통과 확인**

```bash
pytest dev2/tests/test_tools.py -v
```
Expected: PASS 7 tests

**Step 10: 커밋**

```bash
git add dev2/tools/ dev2/tests/test_tools.py dev2/tests/fixtures/
git commit -m "feat: 다국어 CLI 도구 구현 (Python/JS/TS/C#/HTML/CSS + Semgrep 공통)"
```

---

## Task 4-a: run_tools 노드 — CLI 병렬 실행 (asyncio.gather)

**Files:**
- Create: `dev2/nodes/run_tools.py`
- Create: `dev2/tests/test_nodes.py`

**Step 1: 실패하는 테스트 작성**

```python
# dev2/tests/test_nodes.py
import pytest
from unittest.mock import patch, AsyncMock
from dev2.schema import Dev2State

PAYLOAD = {
    "task_id": "uuid-001", "pr_id": "1",
    "pr_diff": "+++ b/src/auth.py\n+query = sql + user",
    "developer": {"id": "dev-001", "skill_level": "junior", "tech_stack": ["python"]}
}

@pytest.mark.asyncio
async def test_run_tools_node_populates_raw():
    from dev2.nodes.run_tools import run_tools_node
    with patch("dev2.nodes.run_tools._run_for_language", new_callable=AsyncMock,
               return_value={
                   "static": [{"severity":"Major","line":1,"file":"a.py","message":"msg","rule_id":"SA-001","suggestion":"fix","similar_issues":[]}],
                   "security": [{"severity":"Critical","line":2,"file":"a.py","message":"sql","rule_id":"SEC-001","suggestion":"fix","similar_issues":[]}],
               }):
        state = Dev2State(payload=PAYLOAD, static_raw=[], security_raw=[], enriched=[], final_output=[])
        result = await run_tools_node(state)
        assert len(result["static_raw"]) > 0
        assert len(result["security_raw"]) > 0

@pytest.mark.asyncio
async def test_run_tools_handles_exception():
    from dev2.nodes.run_tools import run_tools_node
    with patch("dev2.nodes.run_tools._run_for_language",
               new_callable=AsyncMock, side_effect=Exception("tool error")):
        state = Dev2State(payload=PAYLOAD, static_raw=[], security_raw=[], enriched=[], final_output=[])
        result = await run_tools_node(state)
        assert result["static_raw"] == []  # 예외 시 빈 리스트 반환
```

**Step 2: 테스트 실패 확인**

```bash
pytest dev2/tests/test_nodes.py::test_run_tools_node_populates_raw -v
pytest dev2/tests/test_nodes.py::test_run_tools_handles_exception -v
```
Expected: FAIL with `ImportError`

**Step 3: run_tools.py 구현**

```python
# dev2/nodes/run_tools.py
import asyncio
from pathlib import Path
from dev2.schema import Dev2State
from dev2.tools.router import detect_languages
from dev2.tools.python.pylint_tool import run_pylint
from dev2.tools.python.radon_tool import run_radon
from dev2.tools.python.bandit_tool import run_bandit
from dev2.tools.javascript.eslint_tool import run_eslint
from dev2.tools.javascript.npm_audit_tool import run_npm_audit
from dev2.tools.csharp.roslyn_tool import run_roslyn
from dev2.tools.html.htmlhint_tool import run_htmlhint
from dev2.tools.css.stylelint_tool import run_stylelint
from dev2.tools.common.semgrep_tool import run_semgrep

SUPPORTED = {".py", ".js", ".jsx", ".ts", ".tsx", ".cs", ".html", ".htm", ".css", ".scss"}

def _extract_changed_files(diff: str) -> list[str]:
    return [l[6:] for l in diff.splitlines()
            if l.startswith("+++ b/") and Path(l[6:]).suffix.lower() in SUPPORTED]

async def run_tools_node(state: Dev2State) -> dict:
    diff = state["payload"]["pr_diff"]
    all_files = _extract_changed_files(diff)
    lang_groups = detect_languages(all_files)  # {"python": [...], "javascript": [...], ...}

    tasks = [_run_for_language(lang, files) for lang, files in lang_groups.items()]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    static_raw, security_raw = [], []
    for r in results:
        if isinstance(r, Exception):
            continue
        static_raw.extend(r["static"])
        security_raw.extend(r["security"])

    return {"static_raw": static_raw, "security_raw": security_raw}

async def _run_for_language(lang: str, files: list[str]) -> dict:
    """언어별 도구 실행 + Semgrep 공통 보안 검사"""
    RUNNERS = {
        "python":     _run_python,
        "javascript": _run_javascript,
        "typescript": _run_javascript,
        "csharp":     _run_csharp,
        "html":       _run_html,
        "css":        _run_css,
    }
    runner = RUNNERS.get(lang, _run_generic)
    return await runner(files)

async def _run_python(files):
    static = await asyncio.to_thread(lambda: run_pylint(files) + run_radon(files))
    security = await asyncio.to_thread(lambda: run_bandit(files) + run_semgrep(files, lang="python"))
    return {"static": static, "security": security}

async def _run_javascript(files):
    static = await asyncio.to_thread(lambda: run_eslint(files))
    security = run_semgrep(files, lang="javascript") + run_npm_audit()
    return {"static": static, "security": security}

async def _run_csharp(files):
    static = await asyncio.to_thread(lambda: run_roslyn(files))
    return {"static": static, "security": run_semgrep(files, lang="csharp")}

async def _run_html(files):
    static = await asyncio.to_thread(lambda: run_htmlhint(files))
    return {"static": static, "security": run_semgrep(files, lang="html")}

async def _run_css(files):
    return {"static": await asyncio.to_thread(lambda: run_stylelint(files)), "security": []}

async def _run_generic(files):
    return {"static": [], "security": run_semgrep(files, lang="generic")}
```

**Step 4: 테스트 통과 확인**

```bash
pytest dev2/tests/test_nodes.py -v
```
Expected: PASS 2 tests

**Step 5: 커밋**

```bash
git add dev2/nodes/run_tools.py dev2/tests/test_nodes.py
git commit -m "feat: run_tools 노드 — 다국어 라우터 + asyncio.gather 언어별 병렬 실행"
```

---

## Task 4-b: 프롬프트 엔지니어링 — prompts/severity_judge.py

> **AI Native 개념**: 프롬프트 엔지니어링 (Few-shot + Chain-of-Thought + Structured Output)

**Files:**
- Create: `dev2/prompts/severity_judge.py`
- Create: `dev2/tests/test_prompts.py`

**Step 1: 실패하는 테스트 작성**

```python
# dev2/tests/test_prompts.py
from dev2.prompts.severity_judge import build_severity_prompt

def test_prompt_includes_similar_cases():
    prompt = build_severity_prompt(
        message="SQL 파라미터 미처리",
        current_severity="Major",
        developer_level="junior",
        similar_cases=[{"pr_id": "98", "similarity": 0.94, "message": "SQL 인젝션"}]
    )
    # Few-shot 예시 포함 확인
    assert "SQL 파라미터 미처리" in prompt
    assert "98" in prompt  # RAG context 주입 확인

def test_prompt_empty_similar_cases():
    prompt = build_severity_prompt(
        message="변수명 위반", current_severity="Minor",
        developer_level="senior", similar_cases=[]
    )
    assert "유사 사례 없음" in prompt
```

**Step 2: 테스트 실패 확인**

```bash
pytest dev2/tests/test_prompts.py -v
```
Expected: FAIL with `ImportError`

**Step 3: prompts/severity_judge.py 구현**

```python
# dev2/prompts/severity_judge.py
# ① Few-shot: 판단 예시 3개
# ② Chain-of-Thought: 단계별 분석 지시
# ③ RAG: retrieved_context 주입
# ④ Structured Output: JSON 형식 강제

FEW_SHOT_EXAMPLES = """
[판단 예시]
예시 1) SQL 파라미터 미처리 → Critical (입력값 직접 쿼리 삽입, 즉시 수정)
예시 2) 순환복잡도 15 → Major (리팩토링 권고, 테스트 커버리지 확인)
예시 3) 변수명 snake_case 위반 → Minor (코드 스멜, 다음 PR에서 수정)
"""

def build_severity_prompt(
    message: str,
    current_severity: str,
    developer_level: str,
    similar_cases: list[dict],
) -> str:
    cases_text = "\n".join(
        f"- PR #{c['pr_id']} (유사도 {c['similarity']}): {c.get('message','')}"
        for c in similar_cases
    ) if similar_cases else "유사 사례 없음"

    return f"""{FEW_SHOT_EXAMPLES}

[과거 유사 사례 — RAG context]
{cases_text}

[분석 단계 — Chain-of-Thought]
1. 이슈 패턴이 무엇인가?
2. 과거 사례와 비교하면?
3. 최종 severity 결정 (Critical/Major/Minor)
4. {developer_level} 수준 맞춤 개선 방법

이슈: {message}
현재 severity: {current_severity}
개발자 수준: {developer_level}

JSON으로만 답하세요: {{"severity": "Critical|Major|Minor", "suggestion": "string"}}"""
```

**Step 4: 테스트 통과 확인**

```bash
pytest dev2/tests/test_prompts.py -v
```
Expected: PASS 2 tests

**Step 5: 커밋**

```bash
git add dev2/prompts/ dev2/tests/test_prompts.py
git commit -m "feat: 프롬프트 엔지니어링 — Few-shot + CoT + RAG context 주입"
```

---

## Task 4-c: llm_judge 노드 — LangChain + Claude severity 판단 + 모델 라우팅

> **AI Native 개념**: RAG (Augment + Generate), LLMOps 모델 라우팅 + 비용 최적화
> **[CLAUDE.md §9 준수]** LLM은 팀 표준 `claude-sonnet-4-6` 사용 (OpenAI 금지)

**Files:**
- Create: `dev2/nodes/llm_judge.py`
- Modify: `dev2/tests/test_nodes.py`

**Step 1: 실패하는 테스트 추가**

```python
# dev2/tests/test_nodes.py 에 추가
@pytest.mark.asyncio
async def test_llm_judge_skips_minor():
    from dev2.nodes.llm_judge import llm_judge_node
    minor = {"severity":"Minor","line":1,"file":"a.py","message":"msg","rule_id":"SA-001","suggestion":"fix","similar_issues":[]}
    state = Dev2State(payload=PAYLOAD, static_raw=[minor], security_raw=[], enriched=[], final_output=[])
    with patch("dev2.nodes.llm_judge.chain") as mock_chain:
        result = await llm_judge_node(state)
        mock_chain.ainvoke.assert_not_called()   # Minor는 LLM 호출 안 함
        assert result["enriched"][0]["severity"] == "Minor"

@pytest.mark.asyncio
async def test_llm_judge_upgrades_critical():
    from dev2.nodes.llm_judge import llm_judge_node
    major = {"severity":"Major","line":42,"file":"auth.py","message":"SQL 인젝션","rule_id":"SEC-001","suggestion":"fix","similar_issues":[]}
    state = Dev2State(payload=PAYLOAD, static_raw=[major], security_raw=[], enriched=[], final_output=[])
    with patch("dev2.nodes.llm_judge.chain") as mock_chain:
        mock_chain.ainvoke = AsyncMock(return_value='{"severity": "Critical", "suggestion": "파라미터화된 쿼리 사용하세요."}')
        result = await llm_judge_node(state)
        assert result["enriched"][0]["severity"] == "Critical"
        assert "파라미터화된 쿼리" in result["enriched"][0]["suggestion"]
```

**Step 2: 테스트 실패 확인**

```bash
pytest dev2/tests/test_nodes.py::test_llm_judge_skips_minor -v
pytest dev2/tests/test_nodes.py::test_llm_judge_upgrades_critical -v
```
Expected: FAIL with `ImportError`

**Step 3: llm_judge.py 구현**

```python
# dev2/nodes/llm_judge.py
# [CLAUDE.md §9] LLM: claude-sonnet-4-6 (팀 표준)
# [CLAUDE.md §7] USE_MOCK_LLM=true 시 실제 API 호출 없이 Mock 반환
import json, os
from functools import lru_cache
from langchain_anthropic import ChatAnthropic    # ← OpenAI 대신 Anthropic (CLAUDE.md §9)
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langsmith import traceable
from dev2.schema import Dev2State
from dev2.prompts.severity_judge import build_severity_prompt

USE_MOCK_LLM = os.getenv("USE_MOCK_LLM", "true").lower() == "true"

# ① LLMOps 모델 라우팅: severity별 비용/정확도 균형
# [CLAUDE.md §9] 팀 표준 LLM: claude-sonnet-4-6
MODEL_ROUTING = {
    "Critical": "claude-sonnet-4-6",   # 정확도 최우선 (팀 표준 모델)
    "Major":    "claude-haiku-4-5-20251001",  # 균형 (빠른 모델)
    "Minor":    None,                   # 스킵 ($0)
}

# ② Mock LLM: 개발 중 실제 API 호출 없음 (CLAUDE.md §7)
async def _mock_llm_judge(issue: dict) -> dict:
    """USE_MOCK_LLM=true 시 사용. 실제 LLM 없이 결정론적 응답."""
    return {
        "severity": issue["severity"],
        "suggestion": f"[MOCK] {issue.get('suggestion', 'fix it')}",
    }

# ③ 프롬프트 캐싱: 동일 rule_id 반복 이슈는 캐시 hit
@lru_cache(maxsize=256)
def _get_cached_llm(model: str) -> ChatAnthropic:
    return ChatAnthropic(model=model, temperature=0)  # langchain_anthropic 사용

@traceable(name="llm_judge")  # LangSmith 추적 (CLAUDE.md §3)
async def llm_judge_node(state: Dev2State) -> dict:
    # RAG: vector_search 노드가 먼저 실행되어 enriched에 similar_issues가 있음
    all_issues = state["enriched"]
    # CLAUDE.md §11 PRReviewState 필드 사용 (payload 대신 skill_level 직접 접근)
    developer_level = state.get("skill_level", "junior")
    result = []

    for issue in all_issues:
        # ④ Minor는 LLM 스킵 → 비용 최소화 핵심 전략
        if issue["severity"] == "Minor":
            result.append(issue)
            continue

        try:
            if USE_MOCK_LLM:
                # 개발 단계(Week 2~3): Mock 응답 반환 (CLAUDE.md §7)
                parsed = await _mock_llm_judge(issue)
            else:
                # 통합/데모: 실제 Claude API 호출 (CLAUDE.md §9)
                model = MODEL_ROUTING[issue["severity"]]
                llm = _get_cached_llm(model)
                chain = ChatPromptTemplate.from_messages([
                    ("human", "{prompt_text}")
                ]) | llm | StrOutputParser()

                # RAG: similar_issues(retrieved_context)를 프롬프트에 주입 (Augment)
                prompt_text = build_severity_prompt(
                    message=issue["message"],
                    current_severity=issue["severity"],
                    developer_level=developer_level,
                    similar_cases=issue.get("similar_issues", []),  # RAG context
                )
                response = await chain.ainvoke({"prompt_text": prompt_text})
                # [CLAUDE.md §12] LLM 응답 파싱 실패 처리
                try:
                    parsed = json.loads(response)
                except json.JSONDecodeError:
                    parsed = {"severity": issue["severity"], "suggestion": issue["suggestion"]}

            result.append({
                **issue,
                "severity": parsed.get("severity", issue["severity"]),
                "suggestion": parsed.get("suggestion", issue["suggestion"]),
            })
        except Exception:
            result.append(issue)  # LLM 실패 시 CLI 결과 원본 유지

    return {"enriched": result}
```

**Step 4: 테스트 통과 확인**

```bash
pytest dev2/tests/test_nodes.py -v
```
Expected: PASS 4 tests

**Step 5: 커밋**

```bash
git add dev2/nodes/llm_judge.py dev2/tests/test_nodes.py
git commit -m "feat: llm_judge 노드 — claude-sonnet-4-6 + USE_MOCK_LLM + RAG context 주입"
```

---

## Task 4-d: vector_search 노드 — pgVector RAG Retrieve

> **AI Native 개념**: RAG (Retrieve) — 유사 이슈 먼저 검색 후 llm_judge에 context 제공
> **[CLAUDE.md §9 준수]** Vector DB: pgVector (팀 표준) — Milvus 사용 금지

**Files:**
- Create: `dev2/nodes/vector_search.py`
- Modify: `dev2/tests/test_nodes.py`

**Step 1: 실패하는 테스트 추가**

```python
# dev2/tests/test_nodes.py 에 추가
@pytest.mark.asyncio
async def test_vector_search_adds_similar_issues():
    # RAG Retrieve: static_raw + security_raw → enriched (similar_issues 포함)
    from dev2.nodes.vector_search import vector_search_node
    raw = {"severity":"Critical","line":42,"file":"auth.py","message":"SQL 인젝션","rule_id":"SEC-001","suggestion":"fix","similar_issues":[]}
    state = Dev2State(payload=PAYLOAD, static_raw=[raw], security_raw=[], enriched=[], final_output=[])
    with patch("dev2.nodes.vector_search._search", return_value=[{"pr_id":"98","similarity":0.94,"message":"SQL 인젝션"}]):
        result = await vector_search_node(state)
        assert len(result["enriched"]) == 1
        assert result["enriched"][0]["similar_issues"][0]["similarity"] == 0.94

@pytest.mark.asyncio
async def test_vector_search_returns_empty_on_no_match():
    from dev2.nodes.vector_search import vector_search_node
    raw = {"severity":"Minor","line":1,"file":"a.py","message":"unused var","rule_id":"SA-001","suggestion":"fix","similar_issues":[]}
    state = Dev2State(payload=PAYLOAD, static_raw=[raw], security_raw=[], enriched=[], final_output=[])
    with patch("dev2.nodes.vector_search._search", return_value=[]):
        result = await vector_search_node(state)
        assert result["enriched"][0]["similar_issues"] == []
```

**Step 2: 테스트 실패 확인**

```bash
pytest dev2/tests/test_nodes.py::test_vector_search_adds_similar_issues -v
```
Expected: FAIL with `ImportError`

**Step 3: vector_search.py 구현**

```python
# dev2/nodes/vector_search.py
# [CLAUDE.md §9] RAG Retrieve: CLI raw 이슈 → pgVector 유사 검색 → enriched에 similar_issues 추가
# → 다음 노드(llm_judge)가 RAG context로 활용
# pgVector 코사인 유사도: <=> 연산자 (1 - cosine_similarity 반환)
import os, logging
import asyncpg
from dev2.schema import Dev2State

logger = logging.getLogger(__name__)

POSTGRES_URL = os.getenv("POSTGRES_URL", "postgresql://user:password@localhost:5432/dev2_db")
PGVECTOR_DIMENSION = int(os.getenv("PGVECTOR_DIMENSION", "4096"))  # 팀 공통값 (CLAUDE.md §8)
SIMILARITY_THRESHOLD = 0.85  # 코사인 유사도 0.85 미만 제외

async def _get_embedding(text: str) -> list[float]:
    """
    텍스트 임베딩 생성.
    [CLAUDE.md §14] EMBEDDING_MODEL 환경변수로 제어.
    개발 중(USE_MOCK_LLM=true): 0 벡터 반환 (실제 API 없이 동작)
    """
    if os.getenv("USE_MOCK_LLM", "true").lower() == "true":
        return [0.0] * PGVECTOR_DIMENSION  # Mock 임베딩
    # 실제 임베딩: anthropic/openai 중 팀 결정 모델 사용
    # PGVECTOR_DIMENSION과 일치해야 함 (CLAUDE.md §8 경고 참고)
    from anthropic import Anthropic
    client = Anthropic()
    # claude-sonnet-4-6 임베딩 또는 팀 합의 임베딩 모델
    raise NotImplementedError("임베딩 모델 팀 합의 후 구현 (PGVECTOR_DIMENSION 통일 필수)")

async def _search(message: str) -> list[dict]:
    """
    pgVector 코사인 유사도 검색 (CLAUDE.md §9 pgVector 팀 표준).
    [CLAUDE.md §12] 검색 결과 0건 → 빈 리스트 반환, 예외 던지지 않음.
    """
    try:
        embedding = await _get_embedding(message)
        embedding_str = "[" + ",".join(str(v) for v in embedding) + "]"

        conn = await asyncpg.connect(POSTGRES_URL)
        try:
            # <=> : pgVector 코사인 거리 (거리 = 1 - 유사도)
            rows = await conn.fetch(f"""
                SELECT
                    si.id,
                    se.pr_id,
                    si.message,
                    se.scanned_at::date::text AS scan_date,
                    1 - (si.embedding <=> $1::vector({PGVECTOR_DIMENSION})) AS similarity
                FROM scan_issues si
                JOIN scan_executions se ON se.id = si.scan_id
                WHERE si.embedding IS NOT NULL
                  AND 1 - (si.embedding <=> $1::vector({PGVECTOR_DIMENSION})) > $2
                ORDER BY similarity DESC
                LIMIT 3
            """, embedding_str, SIMILARITY_THRESHOLD)
        finally:
            await conn.close()

        if not rows:
            logger.warning(f"pgVector search: 0 results for '{message[:50]}'")
            return []  # [CLAUDE.md §12] 0결과 → 빈 리스트 반환

        return [
            {
                "pr_id": str(r["pr_id"]),
                "message": r["message"],
                "date": r["scan_date"],
                "similarity": round(float(r["similarity"]), 3),
            }
            for r in rows
        ]
    except Exception as e:
        logger.error(f"pgVector search error: {e}")
        return []  # 검색 실패 → 빈 리스트 (파이프라인 중단 없음)

async def vector_search_node(state: Dev2State) -> dict:
    """
    RAG Retrieve 노드: static_raw + security_raw → enriched (similar_issues 포함).
    [CLAUDE.md §8] pgVector HNSW 인덱스 사용 (chunk_embeddings 테이블 기준).
    """
    all_raw = state.get("static_raw", []) + state.get("security_raw", [])
    enriched = []
    for issue in all_raw:
        similar = await _search(issue["message"])
        enriched.append({**issue, "similar_issues": similar})
    return {"enriched": enriched}
```

**Step 4: 테스트 통과 확인**

```bash
pytest dev2/tests/test_nodes.py -v
```
Expected: PASS 6 tests

**Step 5: 커밋**

```bash
git add dev2/nodes/vector_search.py dev2/tests/test_nodes.py
git commit -m "feat: vector_search 노드 — RAG Retrieve (pgVector 코사인 유사도 검색)"
```

---

## Task 4-e: LLM Evaluation Harness — LangSmith evaluate()

> **AI Native 개념**: 하네스 엔지니어링 — LLM 출력 품질을 골든 데이터셋으로 측정

**Files:**
- Create: `dev2/tests/eval/golden_dataset.py`
- Create: `dev2/tests/eval/test_severity_eval.py`

**Step 1: 골든 데이터셋 작성**

```python
# dev2/tests/eval/golden_dataset.py
# 정답이 있는 이슈 10개: CLI 도구 출력 → LLM이 어떻게 판단해야 하는지

GOLDEN_DATASET = [
    {
        "input":    {"message": "SQL 파라미터 미처리", "current_severity": "Major", "developer_level": "junior", "similar_cases": []},
        "expected": "Critical",  # SQL Injection → 무조건 Critical
    },
    {
        "input":    {"message": "변수명 snake_case 위반", "current_severity": "Minor", "developer_level": "senior", "similar_cases": []},
        "expected": "Minor",
    },
    {
        "input":    {"message": "순환복잡도 18 (함수 분리 권고)", "current_severity": "Major", "developer_level": "mid", "similar_cases": []},
        "expected": "Major",
    },
    {
        "input":    {"message": "CVE-2024-1234 (CVSS 9.1)", "current_severity": "Major", "developer_level": "junior", "similar_cases": []},
        "expected": "Critical",  # CVSS 9.1 → Critical 업그레이드
    },
    {
        "input":    {"message": "하드코딩된 비밀번호 발견", "current_severity": "Major", "developer_level": "junior", "similar_cases": []},
        "expected": "Critical",
    },
]
```

**Step 2: 평가 테스트 작성**

```python
# dev2/tests/eval/test_severity_eval.py
# 실행: LANGCHAIN_API_KEY 있을 때만 (CI에서는 스킵)
import os, pytest

@pytest.mark.skipif(not os.getenv("LANGCHAIN_API_KEY"), reason="LangSmith API key not set")
def test_severity_accuracy():
    from langsmith import evaluate
    from langsmith.schemas import Run, Example
    from dev2.nodes.llm_judge import llm_judge_node
    from dev2.tests.eval.golden_dataset import GOLDEN_DATASET

    def severity_accuracy(run: Run, example: Example) -> dict:
        return {"score": int(run.outputs.get("severity") == example.outputs["expected"])}

    results = evaluate(
        llm_judge_node,
        data=GOLDEN_DATASET,
        evaluators=[severity_accuracy],
        experiment_prefix="dev2-severity-judge",
    )

    scores = [r["evaluation_results"]["results"][0].score for r in results]
    accuracy = sum(scores) / len(scores)
    print(f"\nSeverity 판단 정확도: {accuracy*100:.1f}%")
    # 포트폴리오: 정확도 수치를 LangSmith 대시보드에서 확인 가능
    assert accuracy >= 0.7, f"정확도 70% 미달: {accuracy*100:.1f}%"
```

**Step 3: 실행 확인 (LangSmith API key 필요)**

```bash
LANGCHAIN_API_KEY=your_key pytest dev2/tests/eval/ -v -s
```
Expected: 정확도 출력 + LangSmith 대시보드에 실험 결과 기록

**Step 4: 커밋**

```bash
git add dev2/tests/eval/
git commit -m "feat: LLM Evaluation Harness — LangSmith 정확도 측정"
```

---

## Task 4-f: store 노드 — PostgreSQL + BigQuery 이중 적재

**Files:**
- Create: `dev2/nodes/store.py`
- Modify: `dev2/tests/test_nodes.py`

**Step 1: 실패하는 테스트 추가**

```python
# dev2/tests/test_nodes.py 에 추가
@pytest.mark.asyncio
async def test_store_node_returns_final_output():
    from dev2.nodes.store import store_node
    issues = [
        {"severity":"Critical","line":42,"file":"auth.py","message":"SQL 인젝션","rule_id":"SEC-001","suggestion":"fix","similar_issues":[],"_source":"security"},
        {"severity":"Major","line":10,"file":"app.py","message":"복잡도 높음","rule_id":"SA-COMPLEXITY","suggestion":"분리하세요","similar_issues":[],"_source":"static"},
    ]
    state = Dev2State(payload=PAYLOAD, static_raw=[], security_raw=[], enriched=issues, final_output=[])
    with patch("dev2.nodes.store._persist", new_callable=AsyncMock), \
         patch("dev2.nodes.store._load_bigquery"):
        result = await store_node(state)
        assert len(result["final_output"]) == 2
        agents = {r["agent"] for r in result["final_output"]}
        assert agents == {"static_analysis", "security_scan"}
```

**Step 2: 테스트 실패 확인**

```bash
pytest dev2/tests/test_nodes.py::test_store_node_returns_final_output -v
```
Expected: FAIL with `ImportError`

**Step 3: store.py 구현**

```python
# dev2/nodes/store.py
import os, time, asyncio, datetime
from dev2.schema import Dev2State, AgentOutput, Issue, Summary
from dev2.db import insert_scan_execution, insert_scan_issues, insert_scan_summary

def _build_output(issues: list[dict], agent: str, task_id: str, start: float) -> dict:
    return AgentOutput(
        agent=agent,
        task_id=task_id,
        issues=[Issue(**{k: v for k, v in i.items() if k != "_source"}) for i in issues],
        summary=Summary(
            critical=sum(1 for i in issues if i["severity"] == "Critical"),
            major=sum(1 for i in issues if i["severity"] == "Major"),
            minor=sum(1 for i in issues if i["severity"] == "Minor"),
        ),
        execution_ms=int((time.time() - start) * 1000),
    ).model_dump()

async def _persist(output: dict, payload: dict):
    scan_id = await insert_scan_execution(payload, output["execution_ms"])
    await insert_scan_issues(scan_id, output["issues"], output["agent"])
    await insert_scan_summary(scan_id, output["agent"], output["summary"])
    _load_bigquery(output, payload)

def _load_bigquery(output: dict, payload: dict):
    project = os.getenv("BIGQUERY_PROJECT_ID", "")
    if not project:
        return  # 로컬 개발 시 스킵
    from google.cloud import bigquery
    client = bigquery.Client()
    table = f"{project}.{os.getenv('BIGQUERY_DATASET','dev2_dataset')}.scan_issues_daily"
    rows = [
        {"scan_date": datetime.date.today().isoformat(),
         "developer_id": payload["developer"]["id"],
         "pr_id": payload["pr_id"], "agent": output["agent"],
         "severity": i["severity"], "rule_id": i["rule_id"],
         "file": i.get("file",""), "message": i["message"]}
        for i in output["issues"]
    ]
    if rows:
        client.insert_rows_json(table, rows)

async def store_node(state: Dev2State) -> dict:
    enriched = state["enriched"]
    payload = state["payload"]
    start = time.time()

    static_issues = [i for i in enriched if i.get("_source") == "static"]
    security_issues = [i for i in enriched if i.get("_source") == "security"]

    static_output = _build_output(static_issues, "static_analysis", payload["task_id"], start)
    security_output = _build_output(security_issues, "security_scan", payload["task_id"], start)

    # PostgreSQL + BigQuery 동시 적재
    await asyncio.gather(
        _persist(static_output, payload),
        _persist(security_output, payload),
        return_exceptions=True
    )
    return {"final_output": [static_output, security_output]}
```

**Step 4: 테스트 통과 확인**

```bash
pytest dev2/tests/test_nodes.py -v
```
Expected: PASS 7 tests

**Step 5: 커밋**

```bash
git add dev2/nodes/store.py dev2/tests/test_nodes.py
git commit -m "feat: store 노드 — PostgreSQL + BigQuery 이중 적재"
```

---

## Task 4-g: M4 개념 매핑 — concept_mapper + Issue 스키마 확장 ✅ 완료

> **AI Native 개념**: Ontology 기반 이슈 구조화 — rule_id/message 패턴 → M4 학습 커리큘럼용 개념 매핑
> **상태**: 구현 완료 + 테스트 30/30 PASS (2026-06-03)

**목표**: M4 학습 커리큘럼 모듈이 학습자료를 생성할 수 있도록,
각 이슈에 보안 개념(concept) / 실수 유형(mistake_type) / 코드 스니펫 / 학습 컨텍스트를 자동으로 부여.

> ⚠️ **M2 역할 경계**
> - M2가 하는 것: 이슈를 Concept/mistake_type으로 분류한 구조화 데이터 생성
> - M2가 하지 않는 것: 학습자료 생성, GitHub 코멘트 생성 (M4 담당)

**Files:**
- Modify: `dev2/schema.py` — `LearningContext` 모델 추가, `Issue`에 M4 필드 7개 추가
- Create: `dev2/nodes/concept_mapper.py` — 룰 기반 개념 매핑 + snippet 추출
- Modify: `dev2/nodes/llm_judge.py` — `llm_judge_node` 끝에 매핑 호출 추가
- Modify: `dev2/nodes/store.py` — `_ISSUE_FIELDS` 확장
- Create: `dev2/tests/test_concept_mapper.py` — 테스트 30개

---

**Step 1: schema.py — LearningContext 추가 + Issue 필드 확장**

```python
# dev2/schema.py

class LearningContext(BaseModel):
    """M4 학습자료 생성용 컨텍스트 — 프레임워크/언어/도메인 정보"""
    framework: str = "none"          # "django" | "fastapi" | "flask" | "none"
    language: str = "python"         # "python" | "javascript" | "typescript" | ...
    domain_context: str = "ecommerce"  # MVP 기본값

class Issue(BaseModel):
    # ── 기존 필드 (변경 없음) ──────────────────────────────────────────────────
    severity: Literal["Critical", "Major", "Minor"]
    issue_type: Literal["Bug", "Vulnerability", "Code Smell"] = "Bug"
    line: int
    file: str
    message: str
    rule_id: str
    suggestion: str
    resolution_example: str = ""
    status: Literal["Open", "Accepted", "False Positive"] = "Open"
    similar_issues: list[dict] = []
    # ── M4 매핑 필드 (신규, 모두 optional) ────────────────────────────────────
    concept: str = ""                        # "SQL Injection" | "XSS" | "CSRF" | "AUTH_VULNERABILITY"
    mistake_type: str = ""                   # "raw_query" | "mark_safe_misuse" | ...
    concept_id: str = ""                     # "sql_injection" | "xss" | ...
    mistake_type_concept_id: str = ""        # "sql_injection.raw_query" | ...
    confidence_score: float = 0.0            # 분류 신뢰도 0.0~1.0
    code_snippet: str = ""                   # 문제 코드 조각 (없으면 "snippet_unavailable")
    learning_context: LearningContext = LearningContext()
```

**하위 호환성**: 모든 신규 필드에 기본값이 있으므로 기존 코드 변경 불필요.

---

**Step 2: concept_mapper.py 구현**

**매핑 우선순위**:
```
1. rule_id 직접 매핑  → confidence 높음 (0.85~0.95)
2. message 패턴 매핑  → confidence 중간 (0.60~0.82)
3. 미매핑              → concept="" confidence=0.0
```

**confidence 기준**:
```
>= 0.8 → mistake_type 명확 매핑 (mistake_type_concept_id 채워짐)
<  0.8 → mistake_type = "general", mistake_type_concept_id = "{concept_id}.general"
```

**지원 rule_id 매핑**:

| rule_id | concept | mistake_type | confidence |
|---------|---------|--------------|------------|
| B608 | SQL Injection | raw_query | 0.92 |
| SEC-B608 | SQL Injection | raw_query | 0.92 |
| B703 | XSS | mark_safe_misuse | 0.90 |
| B308 | XSS | mark_safe_misuse | 0.88 |
| B506 | CSRF | csrf_exempt_misuse | 0.88 |
| B105 | AUTH_VULNERABILITY | hardcoded_credential | 0.95 |
| B106 | AUTH_VULNERABILITY | hardcoded_credential | 0.95 |

**message 패턴 매핑 (rule_id 미매핑 시)**:

| 패턴 | concept | confidence |
|------|---------|------------|
| `sql inject`, `parameteriz`, `raw.query` | SQL Injection | 0.75 |
| `mark_safe`, `innerHTML` | XSS | 0.78 |
| `xss`, `cross.site.script` | XSS | 0.65 |
| `csrf_exempt`, `csrf.token` | CSRF | 0.80 |
| `login_required`, `is_authenticated` | AUTH_VULNERABILITY | 0.82 |
| `hardcoded.password` | AUTH_VULNERABILITY | 0.85 |

**code_snippet 추출 로직**:
```
pr_diff (unified diff) 파싱
  → "+++ b/{file}" 로 파일 섹션 탐색
  → "@@ -a,b +c,d @@" 로 현재 라인 번호 추적
  → "+" 로 시작하는 추가 라인 중 target_line 번호 매칭
  → 찾으면: 코드 문자열 반환 (앞 "+" 제거)
  → 못 찾으면: "snippet_unavailable" (빈 문자열 아님)
```

**learning_context 추론 로직**:
```
파일 확장자 → language (.py→python, .js/.jsx→javascript, .ts/.tsx→typescript ...)
tech_stack / 파일 경로 → framework (django > fastapi > flask > none)
domain_context → "ecommerce" (MVP 고정값)
```

**핵심 함수 시그니처**:
```python
def enrich_with_concept_mapping(issue: dict, pr_diff: str, tech_stack: list[str]) -> dict:
    """
    단일 이슈 dict에 M4 매핑 필드를 추가하여 반환.
    이미 concept이 채워져 있으면 덮어쓰지 않음 (LLM이 먼저 채운 경우 보존).
    """

def extract_snippet(pr_diff: str, target_file: str, target_line: int) -> str:
    """unified diff → target 라인 코드 추출. 실패 시 "snippet_unavailable"."""

def infer_learning_context(file: str, tech_stack: list[str]) -> LearningContext:
    """파일 확장자 + tech_stack → LearningContext 추론."""
```

---

**Step 3: llm_judge.py 수정 — 매핑 호출 추가**

```python
# llm_judge_node() 함수 끝, return 직전에 추가
from dev2.nodes.concept_mapper import enrich_with_concept_mapping

# severity 재판단 완료 후 M4 개념 매핑 적용
pr_diff: str = state.get("pr_diff", "")
judged = [
    enrich_with_concept_mapping(j, pr_diff, tech_stack)
    for j in judged
]
```

**파이프라인 내 위치**:
```
run_tools → vector_search → llm_judge → [concept mapping] → escalate → store
```

---

**Step 4: store.py 수정 — _ISSUE_FIELDS 확장**

```python
# 변경 전
_ISSUE_FIELDS = frozenset({
    "severity", "line", "file", "message", "rule_id", "suggestion", "similar_issues",
})

# 변경 후
_ISSUE_FIELDS = frozenset({
    # 기존 필드 (issue_type, resolution_example, status 누락 버그도 수정)
    "severity", "issue_type", "line", "file", "message", "rule_id",
    "suggestion", "resolution_example", "status", "similar_issues",
    # M4 매핑 필드
    "concept", "mistake_type", "concept_id", "mistake_type_concept_id",
    "confidence_score", "code_snippet", "learning_context",
})
```

> **부가 수정**: `issue_type`, `resolution_example`, `status`가 기존에도 `Issue` 모델에 있었지만
> `_ISSUE_FIELDS` 누락으로 AgentOutput 출력에서 걸러지던 버그도 함께 수정.

---

**Step 5: 테스트 실행 확인**

```bash
pytest dev2/tests/test_concept_mapper.py -v
```

```
30 passed in 0.11s

TestLookupConcept         (7)  rule_id / message 패턴 매핑
TestConfidenceThreshold   (2)  confidence 0.8 기준 분기
TestExtractSnippet        (4)  snippet 추출 + "snippet_unavailable" fallback
TestInferLearningContext  (6)  언어/프레임워크 추론
TestEnrichWithConceptMapping (8)  통합 + 기존 필드 보존 확인
TestAgentOutputPydantic   (3)  Pydantic 검증 통과
```

---

**Step 6: 최종 출력 예시 (AgentOutput 내 issue 1개)**

```json
{
  "severity": "Critical",
  "issue_type": "Vulnerability",
  "line": 42,
  "file": "src/auth.py",
  "message": "SQL 인젝션 가능성",
  "rule_id": "B608",
  "suggestion": "파라미터화된 쿼리 사용",
  "resolution_example": "",
  "similar_issues": [],
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
```

**Step 7: 커밋**

```bash
git add dev2/schema.py dev2/nodes/concept_mapper.py dev2/nodes/llm_judge.py \
        dev2/nodes/store.py dev2/tests/test_concept_mapper.py
git commit -m "feat: M4 개념 매핑 — concept_mapper + Issue 스키마 확장 (30 tests PASS)"
```

---

## Task 4-h: tool_router_agent + action_decider_agent — Agentic 노드 추가 ✅ 완료

> **AI Native 개념**: Agentic Workflow — PR 맥락 기반 도구 선택 + 분석 결과 기반 액션 추천
> **상태**: 구현 완료 + 테스트 47/47 PASS (2026-06-03)

**목표**: 기존 5노드 파이프라인을 7노드로 확장.
- `tool_router_agent`: 매번 모든 도구를 실행하지 않고 PR 맥락에 맞는 도구만 선택 (비용 절감)
- `action_decider_agent`: LLM 없이 규칙 기반으로 후속 액션 추천 (M2는 추천만, 실행은 M0/Dev4)

**Files:**
- Create: `dev2/nodes/tool_router_agent.py`
- Create: `dev2/nodes/action_decider_agent.py`
- Modify: `dev2/schema.py` — ToolPlan, ActionDecision 모델 추가; Dev2State, Summary, AgentOutput 확장
- Modify: `dev2/nodes/run_tools.py` — tool_plan.selected_tools 지원 (없으면 기존 동작 fallback)
- Modify: `dev2/nodes/store.py` — action_decision → summary.recommended_action + metadata.action_decision 포함
- Modify: `dev2/graph.py` — 7노드 구조, route_after_action_decider 라우터
- Create: `dev2/tests/test_tool_router_agent.py` — 22개 테스트
- Create: `dev2/tests/test_action_decider_agent.py` — 19개 테스트
- Modify: `dev2/tests/test_graph.py` — 5개 테스트 (새 노드 구조 반영)

---

**Step 1: schema.py — ToolPlan, ActionDecision 모델 추가**

```python
class ToolPlan(BaseModel):
    changed_files: list[str] = []
    detected_languages: list[str] = []
    risk_keywords: list[str] = []
    dependency_changed: bool = False
    selected_tools: list[str] = []   # ALLOWED_TOOLS 중 선택된 것만
    llm_required: bool = True
    reason: list[str] = []

class ActionDecision(BaseModel):
    recommended_action: Literal[
        "early_escalation", "request_rework", "needs_human_review", "store_only"
    ]
    reason: str
    confidence: float
    signals: dict[str, Any] = {}

# Summary에 recommended_action 추가 (기본값 "" — 기존 코드 변경 불필요)
class Summary(BaseModel):
    critical: int = 0
    major: int = 0
    minor: int = 0
    recommended_action: str = ""   # action_decider_agent 추천값

# AgentOutput에 metadata 추가 (기본값 {} — 기존 코드 변경 불필요)
class AgentOutput(BaseModel):
    ...
    metadata: dict[str, Any] = {}  # action_decision 등 부가 정보

# Dev2State에 신규 필드
class Dev2State(PRReviewState, total=False):
    ...
    tool_plan: Optional[dict]        # tool_router_agent 출력
    action_decision: Optional[dict]  # action_decider_agent 출력
```

---

**Step 2: tool_router_agent.py — 규칙 기반 도구 선택**

**선택 가능 도구 (ALLOWED_TOOLS):**
```python
{"pylint", "radon", "bandit", "semgrep", "eslint", "npm_audit",
 "pip_audit", "roslyn", "htmlhint", "stylelint"}
```

**선택 규칙 요약:**

| 조건 | 선택 도구 |
|------|-----------|
| `.py` 파일 변경 | pylint, radon |
| `.py` + 보안 키워드 감지 | + bandit, semgrep |
| `requirements.txt` / `pyproject.toml` | pip_audit |
| `.js/.jsx/.ts/.tsx` 파일 | eslint |
| JS/TS + 보안 키워드 | + semgrep |
| `package.json` / `package-lock.json` | npm_audit |
| `.cs` 파일 | roslyn, semgrep |
| `.html/.htm` 파일 | htmlhint |
| HTML + XSS 키워드 | + semgrep |
| `.css/.scss` 파일 | stylelint |
| 알 수 없는 확장자 + 보안 키워드 | semgrep |
| previous_pr_issues에 보안 이력 | 보안 도구 강화 + llm_required=True |

**핵심 함수:**
```python
def build_tool_plan(diff: str, tech_stack: list[str], previous_pr_issues: list[str]) -> ToolPlan:
    # 1. _extract_all_files(diff): +++ b/ 라인 추출
    # 2. _detect_risk_keywords(diff): + 라인 기준 보안 키워드 탐지
    # 3. _has_security_pr_history(previous_pr_issues): 보안 이슈 이력 확인
    # 4. 파일별 규칙 적용 → selected 집합 구성
    # 5. ALLOWED_TOOLS 필터 적용
    # 6. ToolPlan 반환
```

---

**Step 3: action_decider_agent.py — 규칙 기반 액션 추천**

**판단 우선순위:**

```
1. Critical ≥ 1           → "early_escalation"  (실제 escalate 노드 진입)
2. Major ≥ 3              → "request_rework"     (store로 이동, M0/Dev4가 판단)
3. 중요 파일 Major 이상    → "needs_human_review" (store로 이동)
4. confidence < 0.6        → "needs_human_review" (store로 이동)
5. 그 외                  → "store_only"
```

**중요 파일 키워드:** auth, login, password, token, session, permission, admin, payment, billing, order, checkout

**주의**: `request_rework`, `needs_human_review`는 M2가 직접 실행하지 않음. store에 기록만 하고 M0/Dev4가 참고.

---

**Step 4: run_tools.py 수정 — tool_plan 지원**

```python
async def run_tools_node(state: Dev2State) -> dict:
    tool_plan = state.get("tool_plan")

    if tool_plan and tool_plan.get("selected_tools"):
        # tool_plan 기반 실행 (선택된 도구만)
        selected_tools = set(tool_plan["selected_tools"])
        all_files = tool_plan.get("changed_files") or _extract_changed_files(diff)
        ...
    else:
        # fallback: 기존 전체 도구 실행
        ...

    # _run_for_language(lang, files, selected_tools=None) 시그니처로 변경
    # selected_tools=None이면 기존처럼 전체 도구 실행
```

---

**Step 5: store.py 수정 — action_decision 포함**

```python
def _build_output(issues, agent, task_id, exec_ms, action_decision=None) -> dict:
    ...
    # Summary에 recommended_action 추가
    summary = Summary(
        ...,
        recommended_action=action_decision.get("recommended_action", "") if action_decision else "",
    )
    # metadata에 action_decision 포함
    metadata = {"action_decision": {...}} if action_decision else {}

    return AgentOutput(..., summary=summary, metadata=metadata).model_dump()
```

---

**Step 6: graph.py 수정 — 7노드 구조**

```python
# 새 구조
g.add_node("tool_router_agent",    tool_router_agent_node)
g.add_node("run_tools",            run_tools_node)
g.add_node("vector_search",        vector_search_node)
g.add_node("llm_judge",            llm_judge_node)
g.add_node("action_decider_agent", action_decider_agent_node)
g.add_node("escalate",             escalate_node)
g.add_node("store",                store_node)

g.set_entry_point("tool_router_agent")
g.add_edge("tool_router_agent",    "run_tools")
g.add_edge("run_tools",            "vector_search")
g.add_edge("vector_search",        "llm_judge")
g.add_edge("llm_judge",            "action_decider_agent")
g.add_conditional_edges(
    "action_decider_agent",
    route_after_action_decider,   # early_escalation → escalate, 그 외 → store
    {"escalate": "escalate", "store": "store"},
)
g.add_edge("escalate", "store")
g.add_edge("store",    END)

# backward compatibility alias
_route_after_judge = route_after_action_decider
```

---

**Step 7: 테스트 결과**

```bash
pytest dev2/tests/test_tool_router_agent.py \
       dev2/tests/test_action_decider_agent.py \
       dev2/tests/test_graph.py -v
```
```
47 passed in 1.16s

test_tool_router_agent.py   (22): 도구 선택 규칙, 보안 키워드, 의존성 파일, previous_pr_issues
test_action_decider_agent.py (19): 4가지 판정 규칙, route 분기, signals 확인
test_graph.py                (5):  7노드 순서, Critical escalate, store_only 흐름, output 포함
```

---

**Step 8: 커밋**

```bash
git add dev2/schema.py dev2/graph.py \
        dev2/nodes/tool_router_agent.py dev2/nodes/action_decider_agent.py \
        dev2/nodes/run_tools.py dev2/nodes/store.py \
        dev2/tests/test_tool_router_agent.py \
        dev2/tests/test_action_decider_agent.py \
        dev2/tests/test_graph.py
git commit -m "feat: tool_router_agent + action_decider_agent — 7노드 Agentic 파이프라인 (47 tests PASS)"
```

---

## Task 5: LangGraph StateGraph 조립

> **AI Native 개념**: Agentic Workflow — 조건부 엣지로 Critical 자동 에스컬레이션

**Files:**
- Create: `dev2/graph.py`
- Create: `dev2/nodes/escalate.py`
- Create: `dev2/tests/test_graph.py`

**Step 1: 실패하는 테스트 작성**

```python
# dev2/tests/test_graph.py
import pytest
from unittest.mock import patch, AsyncMock
from dev2.graph import build_graph

# [CLAUDE.md §11] PRReviewState 기반 초기 State — Dev1 Orchestrator가 채워주는 필드
INITIAL_STATE: Dev2State = {
    # PRReviewState 필드 (Dev1이 채움)
    "task_id": "uuid-001",
    "pr_id": "1",
    "pr_diff": "+++ b/src/auth.py\n+query = sql + user",
    "developer_id": "dev-001",
    "skill_level": "junior",
    "tech_stack": ["python"],
    "architecture_docs": [],
    "coding_conventions": "",
    "previous_pr_issues": [],
    # Dev2 전용 필드 (초기값)
    "static_raw": [],
    "security_raw": [],
    "enriched": [],
    "final_output": [],
}

@pytest.mark.asyncio
async def test_graph_returns_final_output():
    with patch("dev2.nodes.run_tools._run_for_language", new_callable=AsyncMock,
               return_value={"static": [], "security": []}), \
         patch("dev2.nodes.vector_search._search", return_value=[]), \
         patch("dev2.nodes.store._persist", new_callable=AsyncMock), \
         patch("dev2.nodes.store._load_bigquery"):
        graph = build_graph()
        result = await graph.ainvoke(INITIAL_STATE)
        assert "final_output" in result
        assert isinstance(result["final_output"], list)

@pytest.mark.asyncio
async def test_graph_escalates_on_critical():
    # 조건부 엣지: Critical 이슈 발견 시 escalate 노드 통과
    critical_issue = {"severity":"Critical","line":42,"file":"auth.py","message":"SQL 인젝션",
                      "rule_id":"SEC-001","suggestion":"fix","similar_issues":[]}
    with patch("dev2.nodes.run_tools._run_for_language", new_callable=AsyncMock,
               return_value={"static": [], "security": [critical_issue]}), \
         patch("dev2.nodes.vector_search._search", return_value=[]), \
         patch("dev2.nodes.llm_judge.llm_judge_node", new_callable=AsyncMock,
               return_value={"enriched": [critical_issue]}), \
         patch("dev2.nodes.escalate.notify_dev4", new_callable=AsyncMock) as mock_notify, \
         patch("dev2.nodes.store._persist", new_callable=AsyncMock), \
         patch("dev2.nodes.store._load_bigquery"):
        graph = build_graph()
        await graph.ainvoke(INITIAL_STATE)
        mock_notify.assert_called_once()  # Critical → escalate 노드 실행 확인
```

**Step 2: 테스트 실패 확인**

```bash
pytest dev2/tests/test_graph.py -v
```
Expected: FAIL with `ImportError`

**Step 3: escalate.py 구현**

```python
# dev2/nodes/escalate.py
# [CLAUDE.md §6] Critical ≥ 1 → Slack 즉시 알림 + Dev4 전달
# [CLAUDE.md §12] Slack API 실패 → 로그만 남기고 파이프라인 계속 진행
import os, httpx, logging
from dev2.schema import Dev2State

logger = logging.getLogger(__name__)

async def notify_dev4(critical_issues: list[dict], task_id: str):
    """Critical 이슈 발견 시 Dev4(평가 에이전트)에 즉시 알림"""
    dev4_url = os.getenv("DEV4_WEBHOOK_URL", "")
    if not dev4_url:
        logger.warning("DEV4_WEBHOOK_URL not set — escalation skipped")
        return
    try:
        async with httpx.AsyncClient() as client:
            await client.post(dev4_url, json={
                "task_id": task_id,
                "alert": "Critical issues found",
                "issues": critical_issues,
            }, timeout=5.0)
    except Exception as e:
        # [CLAUDE.md §12] Slack/알림 실패는 전체 파이프라인을 막지 않음
        logger.error(f"Dev4 notify failed (non-fatal): {e}")

async def escalate_node(state: Dev2State) -> dict:
    critical = [i for i in state.get("enriched", []) if i["severity"] == "Critical"]
    # [CLAUDE.md §11] PRReviewState 필드 직접 사용 (payload 대신 task_id)
    await notify_dev4(critical, state.get("task_id", ""))
    return {}  # state 변경 없음, store로 pass
```

**Step 4: graph.py 구현**

```python
# dev2/graph.py
# [CLAUDE.md §3] agent_traces 로깅 필수: AgentHarness(common/harness.py) 사용
# [CLAUDE.md §6] 타임아웃: run_parallel_agents() — 직접 asyncio.gather 금지
import os, asyncio
from langchain_core.callbacks import LangChainTracer
from langgraph.graph import StateGraph, END
from langsmith import traceable
from dev2.schema import Dev2State
from dev2.nodes.run_tools import run_tools_node
from dev2.nodes.vector_search import vector_search_node
from dev2.nodes.llm_judge import llm_judge_node
from dev2.nodes.escalate import escalate_node
from dev2.nodes.store import store_node

# [CLAUDE.md §3] LangSmith 트레이서 (LANGCHAIN_PROJECT=dev2-{github_id})
_tracer = LangChainTracer(project_name=os.getenv("LANGCHAIN_PROJECT", "dev2-local"))

def _route_after_judge(state: Dev2State) -> str:
    """Agentic Workflow 조건부 분기: Critical 있으면 escalate, 없으면 바로 store"""
    return "escalate" if any(i["severity"] == "Critical" for i in state.get("enriched", [])) else "store"

def build_graph():
    g = StateGraph(Dev2State)
    g.add_node("run_tools", run_tools_node)
    g.add_node("vector_search", vector_search_node)   # RAG Retrieve (pgVector)
    g.add_node("llm_judge", llm_judge_node)           # RAG Generate (claude-sonnet-4-6)
    g.add_node("escalate", escalate_node)             # Agentic 분기 (Critical 에스컬레이션)
    g.add_node("store", store_node)

    g.set_entry_point("run_tools")
    g.add_edge("run_tools", "vector_search")          # RAG: 먼저 검색
    g.add_edge("vector_search", "llm_judge")          # context 주입 후 판단
    g.add_conditional_edges("llm_judge", _route_after_judge, {
        "escalate": "escalate",
        "store": "store",
    })
    g.add_edge("escalate", "store")
    g.add_edge("store", END)

    return g.compile()

@traceable(name="Dev2Agent")
async def run_dev2(initial_state: Dev2State) -> list[dict]:
    """
    Dev2 에이전트 진입점.
    [CLAUDE.md §3] LangSmith 콜백은 config로 주입 (함수 내부 하드코딩 금지).
    [CLAUDE.md §3] agent_traces 기록은 common/harness.py AgentHarness가 담당.
       → run_parallel_agents()에서 자동 처리되므로 여기서 직접 INSERT 금지.

    호출 방식 (Dev1 Orchestrator에서):
        # common/harness.py의 run_parallel_agents 사용 (CLAUDE.md §6)
        results = await run_parallel_agents(
            agents=[
                ("static_analysis", run_dev2_static, (initial_state,), {}),
                ("security_scan",   run_dev2_security, (initial_state,), {}),
            ],
            db_pool=pool,
            pr_trace_id=pr_trace,
            task_id=initial_state["task_id"],
        )
    """
    graph = build_graph()
    result = await graph.ainvoke(
        initial_state,
        config={"callbacks": [_tracer]},  # [CLAUDE.md §3] LangSmith config 주입
    )
    return result.get("final_output", [])
```

**Step 4: 테스트 통과 확인**

```bash
pytest dev2/tests/test_graph.py -v
```
Expected: PASS 2 tests

**Step 5: 커밋**

```bash
git add dev2/graph.py dev2/nodes/escalate.py dev2/tests/test_graph.py
git commit -m "feat: LangGraph StateGraph 조립 (AgentHarness + PRReviewState + Critical 에스컬레이션)"
```

---

## Task 6: FastAPI (POST /scan + Insights API)

**Files:**
- Create: `dev2/api/scan.py`
- Create: `dev2/api/insights.py`
- Create: `dev2/api/issues.py`
- Create: `dev2/main.py`
- Create: `dev2/tests/test_insights.py`

**Step 1: 실패하는 테스트 작성**

```python
# dev2/tests/test_insights.py
import pytest
from httpx import AsyncClient
from unittest.mock import patch, AsyncMock
from dev2.main import app

@pytest.mark.asyncio
async def test_scan_accepted():
    with patch("dev2.api.scan.run_dev2", new_callable=AsyncMock, return_value=[]):
        async with AsyncClient(app=app, base_url="http://test") as client:
            r = await client.post("/scan", json={
                "task_id": "uuid-001", "pr_id": "1", "pr_diff": "+++ b/a.py",
                "developer": {"id": "dev-001", "skill_level": "junior", "tech_stack": ["python"]}
            })
        assert r.status_code == 202

@pytest.mark.asyncio
async def test_developer_insights():
    async with AsyncClient(app=app, base_url="http://test") as client:
        r = await client.get("/insights/developer/dev-001")
    assert r.status_code == 200
    assert "developer_id" in r.json()

@pytest.mark.asyncio
async def test_team_insights():
    async with AsyncClient(app=app, base_url="http://test") as client:
        r = await client.get("/insights/team")
    assert r.status_code == 200
    assert "top_issues" in r.json()

@pytest.mark.asyncio
async def test_trends():
    async with AsyncClient(app=app, base_url="http://test") as client:
        r = await client.get("/insights/trends")
    assert r.status_code == 200
    assert "trends" in r.json()

@pytest.mark.asyncio
async def test_dismiss_issue():
    # 오탐 표시: PATCH /issues/{id}/dismiss
    async with AsyncClient(app=app, base_url="http://test") as client:
        r = await client.patch("/issues/1/dismiss")  # insights prefix 없음 (별도 라우터)
    assert r.status_code == 200
    assert r.json()["is_false_positive"] is True
```

**Step 2: 테스트 실패 확인**

```bash
pytest dev2/tests/test_insights.py -v
```
Expected: FAIL with `ImportError`

**Step 3: scan.py 구현**

```python
# dev2/api/scan.py
from fastapi import APIRouter, BackgroundTasks
from dev2.schema import TaskPayload
from dev2.graph import run_dev2

router = APIRouter()

@router.post("/scan", status_code=202)
async def trigger_scan(payload: TaskPayload, background_tasks: BackgroundTasks):
    background_tasks.add_task(run_dev2, payload.model_dump())
    return {"status": "accepted", "task_id": payload.task_id}
```

**Step 4: insights.py 구현**

```python
# dev2/api/insights.py
from fastapi import APIRouter
from sqlalchemy import text
from dev2.db import AsyncSessionLocal

router = APIRouter(prefix="/insights", tags=["insights"])

@router.get("/developer/{developer_id}")
async def get_developer_insights(developer_id: str):
    async with AsyncSessionLocal() as s:
        r = await s.execute(text("""
            SELECT si.rule_id, si.severity, COUNT(*) as count
            FROM scan_issues si JOIN scan_executions se ON si.scan_id = se.id
            WHERE se.developer_id = :did
            GROUP BY si.rule_id, si.severity ORDER BY count DESC
        """), {"did": developer_id})
    return {"developer_id": developer_id, "issues": [dict(row) for row in r.mappings().all()]}

@router.get("/team")
async def get_team_insights():
    async with AsyncSessionLocal() as s:
        r = await s.execute(text("""
            SELECT si.rule_id, si.severity, COUNT(*) as count
            FROM scan_issues si JOIN scan_executions se ON si.scan_id = se.id
            WHERE se.scanned_at >= date_trunc('month', now())
            GROUP BY si.rule_id, si.severity ORDER BY count DESC LIMIT 5
        """))
    return {"top_issues": [dict(row) for row in r.mappings().all()]}

@router.get("/trends")
async def get_trends():
    async with AsyncSessionLocal() as s:
        r = await s.execute(text("""
            SELECT date_trunc('week', se.scanned_at) as week,
                   se.developer_id, SUM(ss.critical) as critical_count
            FROM scan_summaries ss JOIN scan_executions se ON ss.scan_id = se.id
            GROUP BY week, se.developer_id ORDER BY week
        """))
    return {"trends": [dict(row) for row in r.mappings().all()]}

# insights.py는 /insights prefix 라우터만 담당. dismiss는 별도 파일로 분리.
```

**Step 5-a: issues.py (dismiss 전용 라우터) 구현**

```python
# dev2/api/issues.py
# /issues prefix 라우터 — dismiss 엔드포인트만 담당
from fastapi import APIRouter
from sqlalchemy import text
from dev2.db import AsyncSessionLocal

router = APIRouter(prefix="/issues", tags=["issues"])

@router.patch("/{issue_id}/dismiss")
async def dismiss_issue(issue_id: int):
    """개발자가 이슈를 오탐으로 표시 → is_false_positive = true"""
    async with AsyncSessionLocal() as s:
        await s.execute(text("""
            UPDATE scan_issues SET is_false_positive = true WHERE id = :id
        """), {"id": issue_id})
        await s.commit()
    return {"issue_id": issue_id, "is_false_positive": True}
```

**Step 5-b: main.py 구현**

```python
# dev2/main.py
from fastapi import FastAPI
from dev2.api.scan import router as scan_router
from dev2.api.insights import router as insights_router
from dev2.api.issues import router as issues_router

app = FastAPI(title="Dev2: Static Analysis + Security Scan Agent")
app.include_router(scan_router)       # POST /scan
app.include_router(insights_router)   # GET  /insights/*
app.include_router(issues_router)     # PATCH /issues/{id}/dismiss

@app.get("/health")
async def health():
    return {"status": "ok", "service": "dev2"}
```

**Step 6: 테스트 통과 확인**

```bash
pytest dev2/tests/test_insights.py -v
```
Expected: PASS 5 tests

**Step 7: 커밋**

```bash
git add dev2/api/ dev2/main.py dev2/tests/test_insights.py
git commit -m "feat: FastAPI POST /scan + Insights API 3종 + PATCH /issues/{id}/dismiss"
```

---

## Task 7: Airflow DAG + n8n 워크플로우

**Files:**
- Create: `dev2/dags/daily_etl.py`
- Create: `dev2/dags/weekly_report.py`
- Create: `dev2/n8n/github_webhook_workflow.json`

**Step 1: daily_etl.py 구현**

```python
# dev2/dags/daily_etl.py
from airflow import DAG
from airflow.operators.python import PythonOperator
from datetime import datetime, timedelta
import os, asyncio, json
from google.cloud import bigquery

async def _fetch_yesterday():
    import asyncpg
    conn = await asyncpg.connect(os.getenv("DATABASE_URL_SYNC"))
    yesterday = (datetime.now() - timedelta(days=1)).date()
    rows = await conn.fetch("""
        SELECT se.developer_id, se.pr_id, si.agent, si.severity, si.rule_id, si.file, si.message
        FROM scan_issues si JOIN scan_executions se ON si.scan_id = se.id
        WHERE se.scanned_at::date = $1
    """, yesterday)
    await conn.close()
    return [dict(r) for r in rows], str(yesterday)

def extract(**ctx):
    rows, date = asyncio.run(_fetch_yesterday())
    ctx["ti"].xcom_push(key="rows", value=rows)
    ctx["ti"].xcom_push(key="date", value=date)

def load(**ctx):
    rows = ctx["ti"].xcom_pull(key="rows")
    date = ctx["ti"].xcom_pull(key="date")
    if not rows:
        return
    bq = bigquery.Client()
    table = f"{os.getenv('BIGQUERY_PROJECT_ID')}.dev2_dataset.scan_issues_daily"
    bq.insert_rows_json(table, [{**r, "scan_date": date} for r in rows])

with DAG("dev2_daily_etl", schedule_interval="0 2 * * *",
         start_date=datetime(2026, 5, 22), catchup=False,
         default_args={"retries": 1, "retry_delay": timedelta(minutes=5)}) as dag:
    extract_task = PythonOperator(task_id="extract", python_callable=extract)
    load_task = PythonOperator(task_id="load", python_callable=load)
    extract_task >> load_task
```

**Step 2: weekly_report.py 구현 (오탐률 집계 + 룰셋 버전 체크 포함)**

```python
# dev2/dags/weekly_report.py
from airflow import DAG
from airflow.operators.python import PythonOperator
from datetime import datetime, timedelta
from google.cloud import bigquery
import os, subprocess, requests

# ① 주간 인사이트 집계
def generate_report(**ctx):
    bq = bigquery.Client()
    query = f"""
        SELECT developer_id, severity, COUNT(*) as count
        FROM `{os.getenv('BIGQUERY_PROJECT_ID')}.dev2_dataset.scan_issues_daily`
        WHERE scan_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 7 DAY)
        GROUP BY developer_id, severity ORDER BY count DESC
    """
    results = [dict(r) for r in bq.query(query).result()]
    print(f"주간 인사이트: {results}")

# ② 오탐률(false positive) 집계 — PRD 검증 요구사항
def aggregate_false_positive_rate(**ctx):
    """rule_id별 오탐률 집계 → 20% 초과 시 Slack 알림"""
    import asyncpg, asyncio

    async def _run():
        conn = await asyncpg.connect(os.getenv("DATABASE_URL"))
        rows = await conn.fetch("""
            SELECT
                rule_id,
                COUNT(*) FILTER (WHERE is_false_positive = true) AS fp_count,
                COUNT(*)                                          AS total,
                ROUND(
                    COUNT(*) FILTER (WHERE is_false_positive = true) * 100.0 / NULLIF(COUNT(*), 0), 1
                ) AS fp_rate
            FROM scan_issues
            WHERE created_at >= now() - interval '7 days'
            GROUP BY rule_id
            ORDER BY fp_rate DESC NULLS LAST
        """)
        await conn.close()
        return rows

    rows = asyncio.run(_run())
    high_fp = [r for r in rows if r["fp_rate"] and r["fp_rate"] > 20]

    if high_fp:
        msg = "\n".join(f"- {r['rule_id']}: 오탐률 {r['fp_rate']}% ({r['fp_count']}/{r['total']}건)" for r in high_fp)
        slack_url = os.getenv("SLACK_WEBHOOK_URL", "")
        if slack_url:
            requests.post(slack_url, json={"text": f"⚠️ 오탐률 20% 초과 룰 발견\n{msg}"}, timeout=5)

# ③ 보안 룰셋 최신화 확인 — PRD 검증 요구사항
def check_ruleset_versions(**ctx):
    """Bandit / Semgrep 최신 버전 비교 → 구버전이면 Slack 알림"""
    tools = {
        "bandit":  {"cmd": ["bandit", "--version"], "github": "PyCQA/bandit"},
        "semgrep": {"cmd": ["semgrep", "--version"], "github": "semgrep/semgrep"},
    }
    outdated = []
    for name, cfg in tools.items():
        try:
            result = subprocess.run(cfg["cmd"], capture_output=True, text=True, timeout=10)
            current = result.stdout.strip().split()[-1]
            resp = requests.get(
                f"https://api.github.com/repos/{cfg['github']}/releases/latest",
                headers={"Accept": "application/vnd.github.v3+json"}, timeout=10,
            )
            latest = resp.json()["tag_name"].lstrip("v")
            if current != latest:
                outdated.append(f"{name}: 현재 {current} → 최신 {latest}")
        except Exception as e:
            print(f"{name} 버전 체크 실패: {e}")

    if outdated:
        slack_url = os.getenv("SLACK_WEBHOOK_URL", "")
        if slack_url:
            requests.post(slack_url, json={
                "text": "🔔 보안 룰셋 업데이트 필요\n" + "\n".join(outdated)
            }, timeout=5)

with DAG("dev2_weekly_report", schedule_interval="0 9 * * MON",
         start_date=datetime(2026, 5, 22), catchup=False,
         default_args={"retries": 1, "retry_delay": timedelta(minutes=5)}) as dag:

    t1 = PythonOperator(task_id="generate_weekly_insights",   python_callable=generate_report)
    t2 = PythonOperator(task_id="aggregate_false_positive",   python_callable=aggregate_false_positive_rate)
    t3 = PythonOperator(task_id="check_ruleset_versions",     python_callable=check_ruleset_versions)

    t1 >> t2 >> t3   # 인사이트 → 오탐률 → 룰셋 순서
```

**Step 3: Airflow UI에서 DAG 확인**

```
http://localhost:8080 (admin/admin)
DAG 목록: dev2_daily_etl, dev2_weekly_report 확인
```

**Step 4: n8n 워크플로우 설정 (UI)**

```
http://localhost:5678

노드 구성:
[Webhook] POST /github-pr
    ↓
[Function] payload 변환
  return [{ json: {
    task_id: $uuid(),
    pr_id: String($input.first().json.body.number),
    pr_diff: $input.first().json.body.pull_request?.body || "",
    developer: { id: $input.first().json.body.pull_request?.user?.login, skill_level: "junior", tech_stack: ["python"] }
  }}]
    ↓
[HTTP Request] POST http://dev2:8002/scan
```

**Step 5: n8n 워크플로우 JSON export**

n8n UI → Export → `dev2/n8n/github_webhook_workflow.json` 저장

**Step 6: 커밋**

```bash
git add dev2/dags/ dev2/n8n/
git commit -m "feat: Airflow DAG (일별 ETL + 주간 리포트) + n8n GitHub Webhook 워크플로우"
```

---

## TDD 방법론 (전 Task 공통 적용)

모든 Task는 **Red → Green → Refactor** 사이클로 구현한다.

### 원칙

1. **테스트 먼저 작성** — 구현 코드보다 테스트를 먼저 작성한다. 테스트가 실패(Red)하는 것을 확인 후 구현 시작.
2. **최소 구현** — 테스트를 통과(Green)할 최소한의 코드만 작성한다.
3. **리팩토링** — 테스트가 통과된 상태에서 코드 품질을 개선한다.
4. **Mock 기반** — 실제 DB/LLM 없이 `unittest.mock`으로 단위 테스트 작성 (CLAUDE.md §10, §13).
5. **커버리지 80% 이상** — `pytest --cov=dev2` 기준 (Task 8에서 최종 확인).

### Task별 TDD 적용 순서

| Task | 테스트 파일 | 테스트 대상 |
|------|------------|------------|
| Task 2 | `tests/test_schemas.py` | Pydantic 스키마 검증, DB 모델 |
| Task 3 | `tests/test_tools.py` | CLI 도구 subprocess 실행, 언어 라우터 |
| Task 4-a | `tests/test_nodes.py` | run_tools 노드 (Mock subprocess) |
| Task 4-b | `tests/test_nodes.py` | llm_judge 노드 (Mock LLM) |
| Task 4-c | `tests/test_nodes.py` | vector_search 노드 (Mock pgVector) |
| Task 4-d | `tests/test_nodes.py` | store 노드 (Mock DB) |
| Task 5 | `tests/test_graph.py` | StateGraph E2E (전체 Mock) |
| Task 6 | `tests/test_insights.py` | FastAPI 엔드포인트 (TestClient) |

### 사이클 예시

```python
# 1. Red: 테스트 먼저 작성 (실패 확인)
def test_run_tools_returns_issues():
    result = run_tools_node(mock_state)
    assert "static_raw" in result
    assert isinstance(result["static_raw"], list)

# 2. Green: 최소 구현으로 테스트 통과
def run_tools_node(state: Dev2State) -> dict:
    return {"static_raw": [], "security_raw": []}

# 3. Refactor: 실제 로직으로 개선 (테스트는 계속 통과)
```

---

## Task 8: 전체 테스트 + E2E 확인

**Step 1: 전체 테스트 실행**

```bash
pytest dev2/tests/ -v --tb=short
```
Expected: 전체 PASS

**Step 2: 커버리지 확인**

```bash
pytest dev2/tests/ --cov=dev2 --cov-report=term-missing
```
Expected: 80% 이상

**Step 3: docker-compose 전체 실행**

```bash
docker-compose up --build -d
docker-compose ps
```
Expected: 5개 서비스 모두 Up

**Step 4: E2E 흐름 확인**

```bash
# health check
curl http://localhost:8002/health

# 스캔 트리거 (취약 코드 포함 diff)
curl -X POST http://localhost:8002/scan \
  -H "Content-Type: application/json" \
  -d '{"task_id":"e2e-001","pr_id":"1","pr_diff":"+++ b/src/auth.py\n+query = sql + username","developer":{"id":"dev-001","skill_level":"junior","tech_stack":["python"]}}'

# 결과 확인
curl http://localhost:8002/insights/developer/dev-001
curl http://localhost:8002/insights/team
curl http://localhost:8002/insights/trends
```
Expected: 각 엔드포인트 200 응답 + 데이터 확인

**Step 5: LangSmith 트레이스 확인**

```
https://smith.langchain.com → dev2-agent 프로젝트
Dev2Agent → run_tools → llm_judge → vector_search → store 노드 흐름 확인
```

**Step 6: 최종 커밋**

```bash
git add .
git commit -m "feat: Dev2 전체 구현 완료 — LangGraph 하이브리드 에이전트 (LangChain+Milvus+BigQuery+Airflow+n8n)"
```

---

## 구현 순서 요약

| Task | 내용 | 기술 | 우선순위 |
|------|------|------|----------|
| 1 | Docker + 프로젝트 세팅 | Docker, docker-compose | 필수 선행 |
| 2 | Pydantic 스키마 + DB | Python, SQL, PostgreSQL | 필수 선행 |
| 3 | CLI 도구 | Pylint, Bandit, radon, pip-audit | P0 |
| 4-a | run_tools 노드 — CLI 병렬 실행 | asyncio.gather, Python | P0 |
| 4-b | llm_judge 노드 — severity 판단 | LangChain, Claude API | P0 |
| 4-c | vector_search 노드 — 유사 이슈 검색 | pgVector | P0 |
| 4-d | store 노드 — 이중 적재 | PostgreSQL, BigQuery, SQL | P0 |
| 5 | StateGraph 조립 (파이프라인 1) | LangGraph, LangSmith | P0 |
| 6 | FastAPI 엔드포인트 (POST /scan) | FastAPI, SQL | P0 |
| 7 | Airflow DAG + n8n | Airflow, BigQuery, n8n | P1 |
| 8 | 전체 테스트 + E2E (파이프라인 1) | pytest, docker-compose | 마무리 |
| **4-g** | **M4 개념 매핑 — concept_mapper + Issue 스키마 확장** | **Python, Pydantic** | **P0 ✅ 완료** |
| **4-h** | **tool_router_agent + action_decider_agent — Agentic 노드 추가** | **Python, LangGraph** | **P0 ✅ 완료** |
| 9 | aggregate 노드 + DB 스키마 추가 | PostgreSQL, Python | P0 |
| 10 | comment_refine 노드 (LLM 코멘트 + KMS 링크) | Claude API, LangChain | P0 |
| 11 | github_comment + slack_notify 노드 | PyGitHub, Slack API | P0 |
| 12 | aggregate_graph 조립 + POST /aggregate API | LangGraph, FastAPI | P0 |
| 13 | 파이프라인 2 전체 테스트 + E2E | pytest, GitHub API Mock | 마무리 |

---

## Task 9: aggregate 노드 + DB 스키마 추가 (I)

> **PRD 노드 I**: M2+M3 결과 취합 → PostgreSQL 저장

**Files:**
- Create: `dev2/nodes/aggregate.py`
- Create: `dev2/migrations/004_aggregate_table.sql`
- Modify: `dev2/db.py` (insert_aggregated_result 추가)
- Modify: `dev2/tests/test_nodes.py`

**Step 1: 마이그레이션 작성**

```sql
-- dev2/migrations/004_aggregate_table.sql
CREATE TABLE pr_aggregated_results (
    id           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    task_id      text        NOT NULL,
    pr_id        text        NOT NULL,
    developer_id text        NOT NULL,
    issues       jsonb       NOT NULL DEFAULT '[]',
    summary      jsonb       NOT NULL DEFAULT '{}',
    created_at   timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX idx_pr_agg_task       ON pr_aggregated_results (task_id);
CREATE INDEX idx_pr_agg_developer  ON pr_aggregated_results (developer_id, created_at DESC);
CREATE INDEX idx_pr_agg_issues     ON pr_aggregated_results USING gin (issues);
```

**Step 2: db.py에 insert 함수 추가**

```python
# dev2/db.py 에 추가
import json

async def insert_aggregated_result(
    task_id: str, pr_id: str, developer_id: str,
    issues: list[dict], summary: dict
) -> int:
    async with AsyncSessionLocal() as s:
        r = await s.execute(text("""
            INSERT INTO pr_aggregated_results
              (task_id, pr_id, developer_id, issues, summary)
            VALUES (:task_id, :pr_id, :developer_id, :issues, :summary)
            RETURNING id
        """), {
            "task_id": task_id,
            "pr_id": pr_id,
            "developer_id": developer_id,
            "issues": json.dumps(issues),
            "summary": json.dumps(summary),
        })
        await s.commit()
        return r.scalar()
```

**Step 3: 실패하는 테스트 작성**

```python
# dev2/tests/test_nodes.py 에 추가
@pytest.mark.asyncio
async def test_aggregate_node_combines_results():
    from dev2.nodes.aggregate import aggregate_node
    from dev2.schema import AggregateState

    all_results = [
        {"agent": "static_analysis",   "task_id": "u1", "issues": [
            {"severity": "Major", "line": 10, "file": "a.py", "message": "복잡도",
             "rule_id": "SA-001", "suggestion": "분리", "similar_issues": []}
        ], "summary": {"critical": 0, "major": 1, "minor": 0}, "execution_ms": 100},
        {"agent": "test_verification", "task_id": "u1", "issues": [
            {"severity": "Critical", "line": 5, "file": "b.py", "message": "커버리지 부족",
             "rule_id": "TEST-001", "suggestion": "테스트 추가", "similar_issues": []}
        ], "summary": {"critical": 1, "major": 0, "minor": 0}, "execution_ms": 200},
    ]
    state = AggregateState(
        task_id="u1", pr_id="1", developer_id="dev-001",
        skill_level="junior", tech_stack=["python"],
        architecture_docs=[], coding_conventions="", previous_pr_issues=[],
        all_results=all_results, aggregated_issues=[], total_summary={},
        comment_body="",
    )
    with patch("dev2.nodes.aggregate.insert_aggregated_result", new_callable=AsyncMock):
        result = await aggregate_node(state)
        assert result["total_summary"]["critical"] == 1
        assert result["total_summary"]["major"] == 1
        # Critical이 먼저 정렬돼야 함
        assert result["aggregated_issues"][0]["severity"] == "Critical"

@pytest.mark.asyncio
async def test_aggregate_node_empty_results():
    from dev2.nodes.aggregate import aggregate_node
    from dev2.schema import AggregateState
    state = AggregateState(
        task_id="u2", pr_id="2", developer_id="dev-001",
        skill_level="junior", tech_stack=[], architecture_docs=[],
        coding_conventions="", previous_pr_issues=[], all_results=[],
        aggregated_issues=[], total_summary={}, comment_body="",
    )
    with patch("dev2.nodes.aggregate.insert_aggregated_result", new_callable=AsyncMock):
        result = await aggregate_node(state)
        assert result["aggregated_issues"] == []
        assert result["total_summary"] == {"critical": 0, "major": 0, "minor": 0}
```

**Step 4: aggregate.py 구현**

```python
# dev2/nodes/aggregate.py
import os, logging
import httpx
from dev2.schema import AggregateState
from dev2.db import insert_aggregated_result

logger = logging.getLogger(__name__)

_SEVERITY_ORDER = {"Critical": 0, "Major": 1, "Minor": 2}


async def _notify_m4(state: AggregateState, sorted_issues: list[dict], total: dict) -> None:
    """
    M4 커리큘럼 모듈에 결과 push.
    M4가 pull 요청을 보내는 것이 아니라 Dev2 과정이 끝나면 자동으로 전송.
    Critical 여부와 무관하게 항상 호출.
    실패 시 로그만 남기고 파이프라인 계속 진행 (CLAUDE.md §12).
    """
    m4_url = os.getenv("M4_WEBHOOK_URL", "")
    if not m4_url:
        logger.warning("aggregate_node: M4_WEBHOOK_URL 미설정 — M4 push 스킵 (개발 환경 정상)")
        return

    payload = {
        "task_id":           state["task_id"],
        "pr_id":             state["pr_id"],
        "developer_id":      state["developer_id"],
        "skill_level":       state.get("skill_level", "junior"),
        "tech_stack":        state.get("tech_stack", []),
        "aggregated_issues": sorted_issues,
        "summary":           total,
    }

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(m4_url, json=payload, timeout=5.0)
            logger.info(
                "aggregate_node: M4 push 완료 (task_id=%s, status=%d)",
                state["task_id"], resp.status_code,
            )
    except Exception as exc:
        # M4 알림 실패 → 로그만 남기고 파이프라인 계속 (CLAUDE.md §12)
        logger.error("aggregate_node: M4 push 실패 (non-fatal) — %s", exc)


async def aggregate_node(state: AggregateState) -> dict:
    """
    PRD 노드 I: M2+M3 AgentOutput 전체 취합 → severity 정렬 → PostgreSQL 저장 → M4 push.
    판정(lgtm/rework/escalate)은 하지 않는다 — 이슈 데이터 정리 + 전달만 담당.
    """
    all_issues: list[dict] = []
    total = {"critical": 0, "major": 0, "minor": 0}

    for result in state.get("all_results", []):
        agent = result.get("agent", "unknown")
        for issue in result.get("issues", []):
            all_issues.append({**issue, "agent": agent})
        s = result.get("summary", {})
        for k in total:
            total[k] += s.get(k, 0)

    # Critical → Major → Minor 순 정렬
    sorted_issues = sorted(
        all_issues,
        key=lambda x: _SEVERITY_ORDER.get(x.get("severity", "Minor"), 3)
    )

    try:
        await insert_aggregated_result(
            task_id=state["task_id"],
            pr_id=state["pr_id"],
            developer_id=state["developer_id"],
            issues=sorted_issues,
            summary=total,
        )
    except Exception as exc:
        logger.error("aggregate_node: DB 저장 실패 — %s", exc)
        raise  # 핵심 기능 — re-raise

    logger.info(
        "aggregate_node: PR #%s 취합 완료 (critical=%d, major=%d, minor=%d)",
        state["pr_id"], total["critical"], total["major"], total["minor"],
    )

    # DB 저장 완료 후 M4에 자동 push (pull 방식 아님)
    await _notify_m4(state, sorted_issues, total)

    return {"aggregated_issues": sorted_issues, "total_summary": total}
```

**Step 5: 마이그레이션 실행**

```bash
psql $DATABASE_URL -f dev2/migrations/004_aggregate_table.sql
```
Expected: CREATE TABLE, CREATE INDEX 3개

**Step 6: 테스트 통과 확인**

```bash
pytest dev2/tests/test_nodes.py::test_aggregate_node_combines_results -v
pytest dev2/tests/test_nodes.py::test_aggregate_node_empty_results -v
```
Expected: PASS 2 tests

**Step 7: 커밋**

```bash
git add dev2/nodes/aggregate.py dev2/migrations/004_aggregate_table.sql dev2/db.py dev2/tests/test_nodes.py
git commit -m "feat: aggregate 노드 — M2+M3 결과 취합 + PostgreSQL 저장 (PRD 노드 I)"
```

---

## Task 10: comment_refine 노드 (M)

> **PRD 노드 M**: LLM으로 사용자 수준 맞춤 코멘트 생성 + KMS 문서 링크 삽입

**Files:**
- Create: `dev2/nodes/comment_refine.py`
- Create: `dev2/prompts/comment_refine.py`
- Modify: `dev2/tests/test_nodes.py`

**Step 1: 실패하는 테스트 작성**

```python
# dev2/tests/test_nodes.py 에 추가
@pytest.mark.asyncio
async def test_comment_refine_junior_includes_example():
    from dev2.nodes.comment_refine import comment_refine_node
    from dev2.schema import AggregateState

    state = AggregateState(
        task_id="u1", pr_id="1", developer_id="dev-001",
        skill_level="junior", tech_stack=["python"],
        architecture_docs=[], coding_conventions="", previous_pr_issues=[],
        all_results=[],
        aggregated_issues=[
            {"severity": "Critical", "file": "auth.py", "line": 12,
             "message": "SQL 인젝션", "rule_id": "B608",
             "suggestion": "파라미터화된 쿼리 사용", "agent": "security_scan",
             "similar_issues": []}
        ],
        total_summary={"critical": 1, "major": 0, "minor": 0},
        comment_body="",
    )
    with patch.dict("os.environ", {"USE_MOCK_LLM": "true"}):
        result = await comment_refine_node(state)
        assert "comment_body" in result
        assert len(result["comment_body"]) > 0
        assert "Critical" in result["comment_body"]

@pytest.mark.asyncio
async def test_comment_refine_fallback_on_llm_failure():
    from dev2.nodes.comment_refine import comment_refine_node
    from dev2.schema import AggregateState

    state = AggregateState(
        task_id="u2", pr_id="2", developer_id="dev-001",
        skill_level="senior", tech_stack=["python"],
        architecture_docs=[], coding_conventions="", previous_pr_issues=[],
        all_results=[], aggregated_issues=[], total_summary={"critical": 0, "major": 0, "minor": 0},
        comment_body="",
    )
    with patch.dict("os.environ", {"USE_MOCK_LLM": "false"}), \
         patch("dev2.nodes.comment_refine.ChatAnthropic") as mock_llm:
        mock_llm.return_value.ainvoke = AsyncMock(side_effect=Exception("LLM 오류"))
        result = await comment_refine_node(state)
        # 폴백: 이슈 없음 메시지
        assert "comment_body" in result
        assert len(result["comment_body"]) > 0
```

**Step 2: prompts/comment_refine.py 구현**

```python
# dev2/prompts/comment_refine.py

LEVEL_GUIDE = {
    "junior": "왜 문제인지 이유와 수정 예시 코드를 반드시 포함하세요.",
    "mid":    "문제 원인과 관련 패턴을 설명하세요. 코드 예시는 선택.",
    "senior": "이슈 목록과 핵심 포인트만 간결하게 작성하세요.",
}

def build_comment_prompt(
    issues: list[dict],
    summary: dict,
    skill_level: str,
    tech_stack: list[str],
    architecture_docs: list[str],
    previous_pr_issues: list[str],
) -> str:
    level_guide = LEVEL_GUIDE.get(skill_level, LEVEL_GUIDE["junior"])
    issue_lines = "\n".join(
        f"- [{i['severity']}] {i['file']}:{i['line']} ({i['agent']}) — {i['message']} / 제안: {i['suggestion']}"
        for i in issues
    )
    prev = ", ".join(previous_pr_issues) if previous_pr_issues else "없음"
    docs = ", ".join(architecture_docs) if architecture_docs else "없음"

    return f"""당신은 신입 개발자 코드 리뷰 전문가입니다.

[개발자 수준]: {skill_level}
[작성 지침]: {level_guide}
[기술 스택]: {", ".join(tech_stack)}
[과거 반복 이슈]: {prev}
[참조 가능 KMS chunk_id]: {docs}

[분석 결과]
Critical: {summary.get("critical", 0)}건 | Major: {summary.get("major", 0)}건 | Minor: {summary.get("minor", 0)}건

[이슈 목록]
{issue_lines if issue_lines else "이슈 없음"}

위 정보를 바탕으로 GitHub PR 코멘트를 마크다운으로 작성하세요.
구조: ## 자동 코드 리뷰 결과 → Critical 섹션 → Major 섹션 → Minor 섹션 → 관련 문서 링크
"""
```

**Step 3: comment_refine.py 구현**

```python
# dev2/nodes/comment_refine.py
import os, logging
from langchain_anthropic import ChatAnthropic
from dev2.schema import AggregateState
from dev2.prompts.comment_refine import build_comment_prompt

logger = logging.getLogger(__name__)
USE_MOCK_LLM = os.getenv("USE_MOCK_LLM", "true").lower() == "true"


def _build_mock_comment(state: AggregateState) -> str:
    """USE_MOCK_LLM=true 시 결정적 폴백 코멘트 생성"""
    s = state.get("total_summary", {})
    issues = state.get("aggregated_issues", [])
    lines = [
        f"| {i.get('file','')} | {i.get('line','')} | {i.get('severity','')} | {i.get('message','')} |"
        for i in issues[:10]
    ]
    table = "\n".join(lines) if lines else "이슈 없음"
    return (
        f"## 자동 코드 리뷰 결과 [MOCK]\n\n"
        f"**Critical**: {s.get('critical', 0)}건 | **Major**: {s.get('major', 0)}건 | **Minor**: {s.get('minor', 0)}건\n\n"
        f"| 파일 | 라인 | Severity | 이슈 |\n|---|---|---|---|\n{table}"
    )


async def comment_refine_node(state: AggregateState) -> dict:
    """
    PRD 노드 M: LLM으로 사용자 수준 맞춤 PR 코멘트 생성.
    USE_MOCK_LLM=true → 결정적 Mock 코멘트 반환 (실제 API 없음).
    LLM 실패 → 폴백 코멘트 생성 (파이프라인 중단 없음).
    """
    if USE_MOCK_LLM or os.getenv("USE_MOCK_LLM", "true").lower() == "true":
        return {"comment_body": _build_mock_comment(state)}

    try:
        prompt = build_comment_prompt(
            issues=state.get("aggregated_issues", []),
            summary=state.get("total_summary", {}),
            skill_level=state.get("skill_level", "junior"),
            tech_stack=state.get("tech_stack", []),
            architecture_docs=state.get("architecture_docs", []),
            previous_pr_issues=state.get("previous_pr_issues", []),
        )
        llm = ChatAnthropic(model="claude-sonnet-4-6", temperature=0)
        response = await llm.ainvoke(prompt)
        return {"comment_body": response.content}

    except Exception as exc:
        logger.error("comment_refine_node: LLM 실패, 폴백 코멘트 사용 — %s", exc)
        return {"comment_body": _build_mock_comment(state)}
```

**Step 4: 테스트 통과 확인**

```bash
pytest dev2/tests/test_nodes.py::test_comment_refine_junior_includes_example -v
pytest dev2/tests/test_nodes.py::test_comment_refine_fallback_on_llm_failure -v
```
Expected: PASS 2 tests

**Step 5: 커밋**

```bash
git add dev2/nodes/comment_refine.py dev2/prompts/comment_refine.py dev2/tests/test_nodes.py
git commit -m "feat: comment_refine 노드 — LLM 수준별 PR 코멘트 생성 + 폴백 (PRD 노드 M)"
```

---

## Task 11: github_comment + slack_notify 노드 (N, O)

> **PRD 노드 N**: GitHub PR 코멘트 등록  
> **PRD 노드 O**: Critical 시 Slack 시니어 알림

**Files:**
- Create: `dev2/nodes/github_comment.py`
- Create: `dev2/nodes/slack_notify.py`
- Modify: `dev2/tests/test_nodes.py`

**Step 1: 실패하는 테스트 작성**

```python
# dev2/tests/test_nodes.py 에 추가
@pytest.mark.asyncio
async def test_github_comment_posts_comment():
    from dev2.nodes.github_comment import github_comment_node
    from dev2.schema import AggregateState

    state = AggregateState(
        task_id="u1", pr_id="42", developer_id="dev-001",
        skill_level="junior", tech_stack=[], architecture_docs=[],
        coding_conventions="", previous_pr_issues=[], all_results=[],
        aggregated_issues=[], total_summary={},
        comment_body="## 자동 리뷰\nCritical 1건 발견",
    )
    mock_comment = MagicMock()
    mock_comment.id = 999
    mock_comment.html_url = "https://github.com/org/repo/pull/42#issuecomment-999"

    with patch.dict("os.environ", {"GITHUB_TOKEN": "ghp_test", "GITHUB_REPO": "org/repo"}), \
         patch("dev2.nodes.github_comment.Github") as mock_gh:
        mock_repo = MagicMock()
        mock_pr = MagicMock()
        mock_pr.create_issue_comment.return_value = mock_comment
        mock_gh.return_value.get_repo.return_value = mock_repo
        mock_repo.get_pull.return_value = mock_pr

        result = await github_comment_node(state)
        assert result["github_comment_id"] == 999

@pytest.mark.asyncio
async def test_github_comment_skips_without_token():
    from dev2.nodes.github_comment import github_comment_node
    from dev2.schema import AggregateState

    state = AggregateState(
        task_id="u1", pr_id="1", developer_id="dev-001",
        skill_level="junior", tech_stack=[], architecture_docs=[],
        coding_conventions="", previous_pr_issues=[], all_results=[],
        aggregated_issues=[], total_summary={}, comment_body="test",
    )
    with patch.dict("os.environ", {"GITHUB_TOKEN": ""}):
        result = await github_comment_node(state)
        assert result == {}  # 토큰 없으면 스킵

@pytest.mark.asyncio
async def test_slack_notify_sends_on_critical():
    from dev2.nodes.slack_notify import slack_notify_node
    from dev2.schema import AggregateState

    state = AggregateState(
        task_id="u1", pr_id="42", developer_id="dev-001",
        skill_level="junior", tech_stack=[], architecture_docs=[],
        coding_conventions="", previous_pr_issues=[], all_results=[],
        aggregated_issues=[
            {"severity": "Critical", "file": "auth.py", "line": 12,
             "message": "SQL 인젝션", "rule_id": "B608",
             "suggestion": "fix", "agent": "security_scan", "similar_issues": []}
        ],
        total_summary={"critical": 1, "major": 0, "minor": 0},
        comment_body="",
    )
    with patch.dict("os.environ", {"SLACK_WEBHOOK_URL": "https://hooks.slack.com/test"}), \
         patch("dev2.nodes.slack_notify.httpx") as mock_httpx:
        mock_client = AsyncMock()
        mock_httpx.AsyncClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_httpx.AsyncClient.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await slack_notify_node(state)
        mock_client.post.assert_called_once()

@pytest.mark.asyncio
async def test_slack_notify_skips_without_url():
    from dev2.nodes.slack_notify import slack_notify_node
    from dev2.schema import AggregateState

    state = AggregateState(
        task_id="u1", pr_id="1", developer_id="dev-001",
        skill_level="junior", tech_stack=[], architecture_docs=[],
        coding_conventions="", previous_pr_issues=[], all_results=[],
        aggregated_issues=[], total_summary={"critical": 0, "major": 0, "minor": 0},
        comment_body="",
    )
    with patch.dict("os.environ", {"SLACK_WEBHOOK_URL": ""}):
        result = await slack_notify_node(state)
        assert result == {}  # URL 없으면 스킵
```

**Step 2: github_comment.py 구현**

```python
# dev2/nodes/github_comment.py
import os, asyncio, logging

logger = logging.getLogger(__name__)


async def github_comment_node(state) -> dict:
    """
    PRD 노드 N: PyGitHub로 PR 코멘트 등록.
    GITHUB_TOKEN 미설정 → 경고 후 스킵 (개발 환경 정상 동작).
    GitHub API 실패 → 로그 후 스킵 (파이프라인 중단 금지).
    """
    token = os.getenv("GITHUB_TOKEN", "")
    repo_name = os.getenv("GITHUB_REPO", "")
    comment_body = state.get("comment_body", "")

    if not token:
        logger.warning("github_comment_node: GITHUB_TOKEN 미설정 — 스킵")
        return {}
    if not repo_name:
        logger.warning("github_comment_node: GITHUB_REPO 미설정 — 스킵")
        return {}
    if not comment_body:
        logger.warning("github_comment_node: comment_body 비어 있음 — 스킵")
        return {}

    try:
        from github import Github  # PyGitHub — lazy import

        g = Github(token)
        repo = await asyncio.to_thread(g.get_repo, repo_name)
        pr = await asyncio.to_thread(repo.get_pull, int(state["pr_id"]))
        comment = await asyncio.to_thread(pr.create_issue_comment, comment_body)

        logger.info(
            "github_comment_node: PR #%s 코멘트 등록 완료 (id=%d)",
            state["pr_id"], comment.id,
        )
        return {"github_comment_id": comment.id, "github_comment_url": comment.html_url}

    except Exception as exc:
        logger.error("github_comment_node: 실패 (non-fatal) — %s", exc)
        return {}
```

**Step 3: slack_notify.py 구현**

```python
# dev2/nodes/slack_notify.py
import os, logging
import httpx

logger = logging.getLogger(__name__)


async def slack_notify_node(state) -> dict:
    """
    PRD 노드 O: Critical ≥ 1 시 Slack 시니어 알림.
    SLACK_WEBHOOK_URL 미설정 → 경고 후 스킵.
    Slack 실패 → 로그만 남기고 스킵 (파이프라인 중단 금지 — CLAUDE.md §12).
    """
    slack_url = os.getenv("SLACK_WEBHOOK_URL", "")
    if not slack_url:
        logger.warning("slack_notify_node: SLACK_WEBHOOK_URL 미설정 — 스킵")
        return {}

    summary = state.get("total_summary", {})
    critical_issues = [
        i for i in state.get("aggregated_issues", [])
        if i.get("severity") == "Critical"
    ]

    lines = [
        f"• `{i.get('file', '')}:{i.get('line', '')}` — {i.get('message', '')}"
        for i in critical_issues[:5]
    ]
    message = {
        "text": (
            f"🚨 *PR #{state.get('pr_id', '?')} Critical 이슈 "
            f"{summary.get('critical', 0)}건 감지*\n"
            f"개발자: `{state.get('developer_id', '?')}` | "
            f"Major: {summary.get('major', 0)} | Minor: {summary.get('minor', 0)}\n"
            + "\n".join(lines)
        )
    }

    try:
        async with httpx.AsyncClient() as client:
            await client.post(slack_url, json=message, timeout=5.0)
        logger.info("slack_notify_node: Slack 알림 전송 완료 (PR #%s)", state.get("pr_id"))
    except Exception as exc:
        logger.error("slack_notify_node: Slack 알림 실패 (non-fatal) — %s", exc)

    return {}
```

**Step 4: 테스트 통과 확인**

```bash
pytest dev2/tests/test_nodes.py -k "github_comment or slack_notify" -v
```
Expected: PASS 4 tests

**Step 5: requirements.txt에 PyGitHub 추가**

```
PyGitHub==2.3.0
```

**Step 6: 커밋**

```bash
git add dev2/nodes/github_comment.py dev2/nodes/slack_notify.py dev2/tests/test_nodes.py dev2/requirements.txt
git commit -m "feat: github_comment + slack_notify 노드 — PR 코멘트 등록 + Critical Slack 알림 (PRD 노드 N, O)"
```

---

## Task 12: aggregate_graph 조립 + POST /aggregate API

> 파이프라인 2 전체 연결: aggregate → comment_refine → (slack_notify) → github_comment

**Files:**
- Create: `dev2/aggregate_graph.py`
- Create: `dev2/api/aggregate.py`
- Create: `dev2/schema.py` 에 AggregatePayload, AggregateState 추가
- Create: `dev2/tests/test_aggregate.py`
- Modify: `dev2/main.py`

**Step 1: schema.py에 AggregateState 추가**

```python
# dev2/schema.py 에 추가
from typing import Optional

class AggregatePayload(BaseModel):
    """POST /aggregate 입력 계약 (M0 → Dev2)"""
    task_id: str
    pr_id: str
    developer: Developer
    context: TaskContext = TaskContext()
    all_results: list[dict] = []    # AgentOutput × 4 (M2×2 + M3×2)

class AggregateState(TypedDict, total=False):
    # 입력
    task_id: str
    pr_id: str
    developer_id: str
    skill_level: Literal["junior", "mid", "senior"]
    tech_stack: list[str]
    architecture_docs: list[str]
    coding_conventions: str
    previous_pr_issues: list[str]
    all_results: list[dict]
    # aggregate_node 출력
    aggregated_issues: list[dict]
    total_summary: dict
    # comment_refine_node 출력
    comment_body: str
    # github_comment_node 출력
    github_comment_id: Optional[int]
    github_comment_url: Optional[str]
```

**Step 2: aggregate_graph.py 구현**

```python
# dev2/aggregate_graph.py
import os, logging
from langchain_core.callbacks import LangChainTracer
from langgraph.graph import StateGraph, END
from dev2.schema import AggregateState
from dev2.nodes.aggregate import aggregate_node
from dev2.nodes.comment_refine import comment_refine_node
from dev2.nodes.github_comment import github_comment_node
from dev2.nodes.slack_notify import slack_notify_node

logger = logging.getLogger(__name__)
_tracer = LangChainTracer(project_name=os.getenv("LANGCHAIN_PROJECT", "dev2-local"))


def _route_after_refine(state: AggregateState) -> str:
    """Critical ≥ 1 → Slack 먼저 알림 후 GitHub 코멘트. 없으면 바로 GitHub 코멘트."""
    return "slack_notify" if state.get("total_summary", {}).get("critical", 0) >= 1 else "github_comment"


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
    g.add_edge("slack_notify", "github_comment")  # Slack 알림 후 GitHub 코멘트
    g.add_edge("github_comment", END)

    return g.compile()


async def run_aggregate(payload_dict: dict) -> dict:
    """POST /aggregate BackgroundTasks 진입점"""
    initial: AggregateState = {
        "task_id":            payload_dict["task_id"],
        "pr_id":              payload_dict["pr_id"],
        "developer_id":       payload_dict["developer"]["id"],
        "skill_level":        payload_dict["developer"]["skill_level"],
        "tech_stack":         payload_dict["developer"]["tech_stack"],
        "architecture_docs":  payload_dict.get("context", {}).get("architecture_docs", []),
        "coding_conventions": payload_dict.get("context", {}).get("coding_conventions", ""),
        "previous_pr_issues": payload_dict.get("context", {}).get("previous_pr_issues", []),
        "all_results":        payload_dict.get("all_results", []),
        "aggregated_issues":  [],
        "total_summary":      {},
        "comment_body":       "",
    }
    graph = build_aggregate_graph()
    result = await graph.ainvoke(initial, config={"callbacks": [_tracer]})
    return result
```

**Step 3: api/aggregate.py 구현**

```python
# dev2/api/aggregate.py
from fastapi import APIRouter, BackgroundTasks
from dev2.schema import AggregatePayload
from dev2.aggregate_graph import run_aggregate

router = APIRouter()

@router.post("/aggregate", status_code=202)
async def trigger_aggregate(payload: AggregatePayload, background_tasks: BackgroundTasks):
    """
    M0가 M2+M3 결과를 묶어 전송 → 취합·코멘트·알림 파이프라인 비동기 실행.
    202 즉시 반환 (BackgroundTasks).
    """
    background_tasks.add_task(run_aggregate, payload.model_dump())
    return {"status": "accepted", "task_id": payload.task_id}
```

**Step 4: main.py에 aggregate 라우터 등록**

```python
# dev2/main.py 수정
from dev2.api.aggregate import router as aggregate_router
app.include_router(aggregate_router)   # POST /aggregate
```

**Step 5: 실패하는 테스트 작성**

```python
# dev2/tests/test_aggregate.py
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from httpx import AsyncClient
from dev2.main import app

# M2 결과만 포함 (static_analysis + security_scan)
# M3(test_verification, performance)는 M3 서버에서 별도로 M4에 전달
ALL_RESULTS_MOCK = [
    {"agent": "static_analysis", "task_id": "u1",
     "issues": [{"severity": "Critical", "line": 10, "file": "auth.py",
                 "message": "SQL 인젝션", "rule_id": "B608",
                 "suggestion": "파라미터 쿼리", "similar_issues": []}],
     "summary": {"critical": 1, "major": 0, "minor": 0}, "execution_ms": 500},
    {"agent": "security_scan",   "task_id": "u1", "issues": [],
     "summary": {"critical": 0, "major": 0, "minor": 0}, "execution_ms": 300},
]

@pytest.mark.asyncio
async def test_aggregate_endpoint_accepted():
    with patch("dev2.api.aggregate.run_aggregate", new_callable=AsyncMock):
        async with AsyncClient(app=app, base_url="http://test") as client:
            r = await client.post("/aggregate", json={
                "task_id": "u1", "pr_id": "42",
                "developer": {"id": "dev-001", "skill_level": "junior", "tech_stack": ["python"]},
                "all_results": ALL_RESULTS_MOCK,
            })
        assert r.status_code == 202
        assert r.json()["task_id"] == "u1"

@pytest.mark.asyncio
async def test_aggregate_graph_critical_triggers_slack():
    """Critical 이슈 → slack_notify → github_comment 경로 확인"""
    from dev2.aggregate_graph import build_aggregate_graph
    from dev2.schema import AggregateState

    initial: AggregateState = {
        "task_id": "u1", "pr_id": "42", "developer_id": "dev-001",
        "skill_level": "junior", "tech_stack": ["python"],
        "architecture_docs": [], "coding_conventions": "", "previous_pr_issues": [],
        "all_results": ALL_RESULTS_MOCK,
        "aggregated_issues": [], "total_summary": {}, "comment_body": "",
    }

    with patch("dev2.nodes.aggregate.insert_aggregated_result", new_callable=AsyncMock), \
         patch("dev2.nodes.slack_notify.httpx") as mock_httpx, \
         patch("dev2.nodes.github_comment.Github") as mock_gh:

        mock_client = AsyncMock()
        mock_httpx.AsyncClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_httpx.AsyncClient.return_value.__aexit__ = AsyncMock(return_value=False)

        mock_comment = MagicMock(id=1, html_url="https://github.com/org/repo/pull/42#1")
        mock_gh.return_value.get_repo.return_value.get_pull.return_value \
            .create_issue_comment.return_value = mock_comment

        import os
        os.environ["USE_MOCK_LLM"] = "true"
        os.environ["SLACK_WEBHOOK_URL"] = "https://hooks.slack.com/test"
        os.environ["GITHUB_TOKEN"] = "ghp_test"
        os.environ["GITHUB_REPO"] = "org/repo"

        graph = build_aggregate_graph()
        result = await graph.ainvoke(initial)

        # Critical 있으므로 Slack 호출됐어야 함
        mock_client.post.assert_called_once()
        assert result.get("total_summary", {}).get("critical", 0) == 1

@pytest.mark.asyncio
async def test_aggregate_graph_no_critical_skips_slack():
    """Critical 없음 → slack_notify 건너뜀 → github_comment 직접"""
    from dev2.aggregate_graph import build_aggregate_graph
    from dev2.schema import AggregateState

    no_critical_results = [
        {"agent": "static_analysis", "task_id": "u2",
         "issues": [{"severity": "Minor", "line": 5, "file": "app.py",
                     "message": "lint", "rule_id": "E501",
                     "suggestion": "fix", "similar_issues": []}],
         "summary": {"critical": 0, "major": 0, "minor": 1}, "execution_ms": 100},
    ]
    initial: AggregateState = {
        "task_id": "u2", "pr_id": "99", "developer_id": "dev-001",
        "skill_level": "senior", "tech_stack": ["python"],
        "architecture_docs": [], "coding_conventions": "", "previous_pr_issues": [],
        "all_results": no_critical_results,
        "aggregated_issues": [], "total_summary": {}, "comment_body": "",
    }

    with patch("dev2.nodes.aggregate.insert_aggregated_result", new_callable=AsyncMock), \
         patch("dev2.nodes.slack_notify.httpx") as mock_httpx, \
         patch("dev2.nodes.github_comment.Github"):

        import os
        os.environ["USE_MOCK_LLM"] = "true"
        os.environ["SLACK_WEBHOOK_URL"] = "https://hooks.slack.com/test"
        os.environ["GITHUB_TOKEN"] = "ghp_test"
        os.environ["GITHUB_REPO"] = "org/repo"

        graph = build_aggregate_graph()
        result = await graph.ainvoke(initial)

        # Critical 없으므로 Slack 호출 없어야 함
        mock_httpx.AsyncClient.assert_not_called()
        assert result.get("total_summary", {}).get("critical", 0) == 0
```

**Step 6: 테스트 통과 확인**

```bash
pytest dev2/tests/test_aggregate.py -v
```
Expected: PASS 3 tests

**Step 7: 커밋**

```bash
git add dev2/aggregate_graph.py dev2/api/aggregate.py dev2/schema.py dev2/main.py dev2/tests/test_aggregate.py
git commit -m "feat: aggregate_graph (파이프라인 2) + POST /aggregate API — I→M→N→O 전체 연결"
```

---

## Task 13: 파이프라인 2 전체 테스트 + E2E 확인

**Step 1: 전체 테스트 실행**

```bash
pytest dev2/tests/ -v --tb=short
```
Expected: 전체 PASS

**Step 2: 커버리지 확인**

```bash
pytest dev2/tests/ --cov=dev2 --cov-report=term-missing
```
Expected: 80% 이상

**Step 3: E2E 흐름 확인 (Mock)**

```bash
# 파이프라인 1: 분석
curl -X POST http://localhost:8005/scan \
  -H "Content-Type: application/json" \
  -d '{
    "task_id": "e2e-001", "pr_id": "42",
    "pr_diff": "+++ b/src/auth.py\n+query = sql + username",
    "developer": {"id": "dev-001", "skill_level": "junior", "tech_stack": ["python"]}
  }'

# 파이프라인 2: 취합 + 코멘트 + 알림
curl -X POST http://localhost:8005/aggregate \
  -H "Content-Type: application/json" \
  -d '{
    "task_id": "e2e-001", "pr_id": "42",
    "developer": {"id": "dev-001", "skill_level": "junior", "tech_stack": ["python"]},
    "context": {"architecture_docs": [], "coding_conventions": "", "previous_pr_issues": []},
    "all_results": [
      {"agent": "static_analysis",   "task_id": "e2e-001", "issues": [], "summary": {"critical": 0, "major": 0, "minor": 0}, "execution_ms": 100},
      {"agent": "security_scan",     "task_id": "e2e-001", "issues": [{"severity": "Critical", "line": 12, "file": "auth.py", "message": "SQL 인젝션", "rule_id": "B608", "suggestion": "파라미터 쿼리", "similar_issues": []}], "summary": {"critical": 1, "major": 0, "minor": 0}, "execution_ms": 900},
      {"agent": "test_verification", "task_id": "e2e-001", "issues": [], "summary": {"critical": 0, "major": 0, "minor": 0}, "execution_ms": 200},
      {"agent": "performance",       "task_id": "e2e-001", "issues": [], "summary": {"critical": 0, "major": 0, "minor": 0}, "execution_ms": 150}
    ]
  }'

# 결과 확인
curl http://localhost:8005/insights/developer/dev-001
```

Expected:
- `/aggregate` → 202 Accepted
- 백그라운드: aggregate → comment_refine → slack_notify → github_comment 실행
- `/insights/developer/dev-001` → Critical 1건 포함 응답

**Step 4: 최종 커밋**

```bash
git add .
git commit -m "feat: Dev2 파이프라인 2 전체 완성 — M2+M3 취합·LLM 코멘트·GitHub PR·Slack 알림 (PRD I→M→N→O)"
```

---

## 구현 순서 요약 (최종)
