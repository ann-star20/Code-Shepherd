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
| 4-b | llm_judge 노드 — severity 판단 | LangChain, OpenAI API | P0 |
| 4-c | vector_search 노드 — 유사 이슈 검색 | Milvus, OpenAI Embeddings | P0 |
| 4-d | store 노드 — 이중 적재 | PostgreSQL, BigQuery, SQL | P0 |
| 5 | StateGraph 조립 | LangGraph, LangSmith | P0 |
| 6 | FastAPI 엔드포인트 | FastAPI, SQL | P0 |
| 7 | Airflow DAG + n8n | Airflow, BigQuery, n8n | P1 |
| 8 | 전체 테스트 + E2E | pytest, docker-compose | 마무리 |
