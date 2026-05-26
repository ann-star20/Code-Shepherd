# Dev 2: 정적 분석 + 보안 스캔 에이전트 설계

**프로젝트**: 조직 지식 관리 + 개발자 온보딩 멀티 에이전트 플랫폼
**담당**: Dev 2
**작성일**: 2026-05-22
**포트폴리오 방향**: 데이터 엔지니어 + AX/DX

---

## 설계 방향 요약

**하이브리드 에이전트** 구조:
- CLI 도구(Pylint, Bandit, Semgrep, radon, pip-audit)는 subprocess로 직접 실행 → 속도/안정성 확보
- CLI 결과를 LangChain + **claude-sonnet-4-6** (팀 표준 LLM, CLAUDE.md §9)가 받아 severity 최종 판단 + 개선 제안 생성
- LangGraph StateGraph로 에이전트 상태 흐름 관리 (조건부 엣지로 Critical 자동 에스컬레이션)
- **RAG 패턴**: **pgVector** 유사 이슈 먼저 검색 (코사인 유사도, CLAUDE.md §9) → retrieved context를 LLM 프롬프트에 주입 → 판단
- **State 설계**: `Dev2State`는 팀 공통 `PRReviewState` 확장 (CLAUDE.md §11 — Week 5 통합 필수)
- **agent_traces 로깅**: 모든 에이전트 시작/종료 시 `common/harness.py` AgentHarness로 기록 (CLAUDE.md §3)
- **프롬프트 엔지니어링**: Few-shot + Chain-of-Thought + Structured Output + Domain Rules 적용
- **LLM Evaluation Harness**: LangSmith evaluate()로 severity 판단 정확도 측정 (LANGCHAIN_API_KEY)
- **LLMOps 비용 최적화**: 모델 라우팅(Critical/Major→claude-sonnet-4-6, Minor→스킵) + USE_MOCK_LLM 개발 모드 (CLAUDE.md §7)
- PostgreSQL(실시간) + BigQuery(분석용) 이중 적재
- Airflow로 일별 ETL + 주간 집계 / GitHub Webhook은 **Dev1 Orchestrator**가 수신 후 Dev2로 라우팅 (CLAUDE.md §4)

> 실제 현업 AI 시스템도 이 방식. 순수 LLM 도구 선택은 오류율과 비용 문제가 있음.

---

## 1. 전체 아키텍처

```
[GitHub PR 제출]
        │ Webhook
        ▼
[Dev1 Orchestrator]  ← CLAUDE.md §4: Webhook 수신은 Dev1 담당
  HMAC-SHA256 서명 검증 → 의도 분류 → Dev2/Dev3 병렬 라우팅
  (run_parallel_agents() 호출 — CLAUDE.md §6)
        │ PRReviewState (task_id, pr_id, pr_diff, developer_id, ...)
        ▼
[Dev2 LangGraph StateGraph]
  State: Dev2State (PRReviewState 확장 — CLAUDE.md §11)
  { task_id, pr_id, pr_diff, skill_level, ...  ← Dev1이 채움
    static_raw, security_raw, enriched, final_output  ← Dev2가 채움 }

  ┌──────────────────────────────────────────────┐
  │  Node: run_tools (asyncio.gather 병렬 실행)   │
  │  ┌─────────────────────┬────────────────────┐ │
  │  ▼                     ▼                    │ │
  │ [StaticAnalysis Tools] [SecurityScan Tools] │ │
  │  - Pylint (subprocess)  - Bandit (subprocess)│ │
  │  - radon (subprocess)   - Semgrep (subprocess│ │
  │  - CPD (subprocess)     - pip-audit (subproc)│ │
  │  결과: raw_issues        결과: raw_issues     │ │
  └──────────────────────────────────────────────┘
        │ raw 결과 (CLI 출력)
        ▼
  ┌──────────────────────────────────────────────┐
  │  Node: vector_search (pgVector) — RAG: Retrieve│
  │  - 이슈 메시지 임베딩 → pgVector 코사인 검색  │
  │    (CLAUDE.md §9: pgVector 팀 표준)           │
  │  - retrieved_context → 다음 노드(llm_judge)에│
  │    RAG 컨텍스트로 주입                       │
  └──────────────────────────────────────────────┘
        │ raw_issues + retrieved_context
        ▼
  ┌──────────────────────────────────────────────┐
  │  Node: llm_judge (LangChain + claude-sonnet-4-6)│
  │  — RAG: Augment + Generate (CLAUDE.md §9)    │
  │  - Few-shot + CoT 프롬프트 + 유사 사례 주입  │
  │  - 모델 라우팅: Critical/Major→claude-sonnet │
  │  - Minor 이슈는 LLM 스킵 (비용 최소화)       │
  │  - USE_MOCK_LLM=true: 개발 중 Mock 사용       │
  └──────────────────────────────────────────────┘
        │ enriched_issues
        ▼ (조건부 엣지)
  ┌──────────────┐     ┌──────────────────────────┐
  │ Critical 있음│─Yes→│ Node: escalate            │
  │              │     │ - Dev4에 즉시 알림        │
  └──────────────┘     └──────────────────────────┘
        │ No
        ▼
  ┌──────────────────────────────────────────────┐
  │  Node: store (pipeline.py)                   │
  │  - PostgreSQL 실시간 적재 (trace_id 포함)    │
  │  - BigQuery 분석용 적재                      │
  └──────────────────────────────────────────────┘
        │
  ┌─────┴──────┐
  ▼            ▼
[Dev4 전달]  [FastAPI Insights API]
(Output       /insights/developer/{id}  ← PostgreSQL
Contract A)   /insights/team            ← BigQuery
              /insights/trends          ← BigQuery

[Apache Airflow]
  - 일별 DAG: PostgreSQL → BigQuery ETL
  - 주간 DAG: 인사이트 집계 리포트

[Docker Compose]
  dev2 + postgres(pgvector) + airflow  ← Milvus 없음 (CLAUDE.md §9)
```

---

## 2. LangGraph StateGraph 설계

> **[CLAUDE.md §11 준수]** `Dev2State`는 팀 공통 `PRReviewState`를 확장한다.
> 독립 TypedDict로 만들면 Week 5 통합 시 Dev1 State 수신이 불가하다.

```python
from langgraph.graph import StateGraph, END
from typing import TypedDict, Optional, Literal

# ── 팀 공통 State (CLAUDE.md §11) ─────────────────────────────────────────
# 통합(Week 5): from common.state import PRReviewState
# 개발(Week 2~3): 인라인 정의 (구조 동일 유지 필수)
class PRReviewState(TypedDict, total=False):
    task_id: str          # Dev1이 채움
    pr_id: str            # Dev1이 채움
    pr_diff: str          # Dev1이 채움
    developer_id: str     # Dev1이 채움
    skill_level: Literal["junior", "mid", "senior"]  # Dev1이 채움
    tech_stack: list[str]
    architecture_docs: list[str]      # chunk_id (pgVector 검색 결과)
    coding_conventions: str
    previous_pr_issues: list[str]
    analysis_results: list[dict]      # Dev2/3가 채움 (Output Contract A)
    verdict: Optional[str]            # Dev4가 채움
    comment_body: Optional[str]
    learning_resources: Optional[list[dict]]
    issue_patterns: Optional[list[str]]
    curriculum_update: Optional[dict]

# ── Dev2 전용 추가 필드 ───────────────────────────────────────────────────
class Dev2State(PRReviewState, total=False):
    static_raw: list[dict]    # run_tools 노드: Pylint/radon 원본 결과
    security_raw: list[dict]  # run_tools 노드: Bandit/pip-audit 원본 결과
    enriched: list[dict]      # vector_search → llm_judge 중간 결과
    final_output: list[dict]  # store 노드: Output Contract A 최종 결과 (Dev4로 전달)

# ── LangGraph StateGraph ──────────────────────────────────────────────────
# [CLAUDE.md §3] LangSmith 콜백은 graph.invoke(config={"callbacks": [tracer]})로 주입
graph = StateGraph(Dev2State)
graph.add_node("run_tools", run_tools_node)         # CLI 병렬 실행
graph.add_node("vector_search", vector_search_node) # pgVector 유사 이슈 (RAG: Retrieve)
graph.add_node("llm_judge", llm_judge_node)         # claude-sonnet-4-6 (RAG: Generate)
graph.add_node("escalate", escalate_node)           # Critical 자동 에스컬레이션
graph.add_node("store", store_node)                 # DB 이중 적재

graph.set_entry_point("run_tools")
graph.add_edge("run_tools", "vector_search")        # RAG: 먼저 유사 이슈 검색
graph.add_edge("vector_search", "llm_judge")        # retrieved context 주입 후 LLM 판단
graph.add_conditional_edges(                        # Agentic Workflow: 조건 분기
    "llm_judge",
    lambda state: "escalate" if any(i["severity"] == "Critical" for i in state.get("enriched", [])) else "store",
    {"escalate": "escalate", "store": "store"}
)
graph.add_edge("escalate", "store")
graph.add_edge("store", END)
```

> **[CLAUDE.md §6] agent_traces 로깅**: `common/harness.py`의 `AgentHarness`가 담당.
> Dev2는 `run_parallel_agents()`로 호출되며, 타임아웃(30초)과 traces 기록이 자동 처리된다.
> 직접 `asyncio.gather()` 사용 또는 `agent_traces` 직접 INSERT 금지.

---

## 3. 각 노드 역할

| 노드 | 역할 | 기술 | AI Native 개념 |
|------|------|------|----------------|
| `run_tools` | 확장자 감지 → 언어별 도구 자동 선택 → asyncio.gather 병렬 실행 | Python, subprocess, asyncio | Agentic Workflow |
| `vector_search` | 이슈 임베딩 → **pgVector 코사인 유사도** 검색 → retrieved_context 반환 | **pgVector**, asyncpg | **RAG: Retrieve** (CLAUDE.md §9) |
| `llm_judge` | retrieved_context 주입 → severity 판단 + 개선 제안 | LangChain, **claude-sonnet-4-6** | **RAG: Augment+Generate**, 프롬프트 엔지니어링 (CLAUDE.md §9) |
| `escalate` | Critical 이슈 발견 시 Dev4에 즉시 알림 (CLAUDE.md §6) | FastAPI, httpx | **Agentic Workflow (조건부 분기)** |
| `store` | PostgreSQL 실시간 적재 (trace_id 포함) + BigQuery 분석용 적재 | PostgreSQL, BigQuery | AI Native (자동화) |

---

## 4. 디렉토리 구조

```
dev2/
├── graph.py                  # LangGraph StateGraph 정의
├── nodes/
│   ├── run_tools.py          # CLI 도구 병렬 실행 노드
│   ├── vector_search.py      # RAG Retrieve: pgVector 유사 이슈 코사인 검색 노드
│   ├── llm_judge.py          # RAG Generate: LangChain severity 판단 노드
│   ├── escalate.py           # Agentic 분기: Critical 자동 에스컬레이션
│   └── store.py              # DB 이중 적재 노드
├── prompts/
│   ├── severity_judge.py     # Few-shot + CoT 프롬프트 (프롬프트 엔지니어링)
│   └── suggestion.py         # 수준별(junior/mid/senior) 제안 프롬프트
├── tools/
│   ├── router.py             # 확장자 감지 → 언어별 도구 선택 (핵심)
│   ├── python/
│   │   ├── pylint_tool.py    # Pylint 코드 품질
│   │   ├── radon_tool.py     # radon 순환복잡도
│   │   └── bandit_tool.py    # Bandit 보안 취약점
│   ├── javascript/
│   │   ├── eslint_tool.py    # ESLint 코드 품질 (.js/.ts/.jsx/.tsx)
│   │   └── npm_audit_tool.py # npm audit CVE 스캔
│   ├── csharp/
│   │   └── roslyn_tool.py    # dotnet-format + Security Code Scan
│   ├── html/
│   │   └── htmlhint_tool.py  # HTMLHint 품질 + 인라인 스크립트 검사
│   ├── css/
│   │   └── stylelint_tool.py # Stylelint 품질
│   └── common/
│       ├── semgrep_tool.py   # Semgrep OWASP (전 언어 공통 보안)
│       └── pipit_tool.py     # pip-audit / npm audit CVE (언어별 분기)
├── pipeline.py               # PostgreSQL + BigQuery 이중 적재
├── db.py                     # PostgreSQL 연결 + 쿼리
├── vector_store/
│   └── similarity.py         # pgVector 유사 이슈 코사인 검색 (asyncpg)
├── api/
│   ├── scan.py               # POST /scan (Dev1 Orchestrator → Dev2 수신)
│   └── insights.py           # FastAPI 인사이트 엔드포인트 3종
├── dags/
│   ├── daily_etl.py          # Airflow 일별 PostgreSQL→BigQuery ETL
│   └── weekly_report.py      # Airflow 주간 인사이트 집계
├── schema.py                 # Pydantic 입출력 모델
├── Dockerfile
├── docker-compose.yml
└── tests/
    ├── test_tools.py         # CLI 도구 단위 테스트
    ├── test_nodes.py         # LangGraph 노드 단위 테스트
    ├── test_graph.py         # StateGraph E2E 테스트
    ├── test_insights.py      # FastAPI 엔드포인트 테스트
    └── eval/
        ├── golden_dataset.py # LLM 평가용 골든 데이터셋 (정답 있는 이슈 10개)
        └── test_severity_eval.py  # LangSmith evaluate() 정확도 측정
```

---

## 5. 다국어 지원 설계 (Multi-Language Support)

### 5-1. 언어별 도구 매핑

| 언어 | 확장자 | 코드 품질 도구 | 보안 도구 | CVE 스캔 |
|------|--------|--------------|----------|---------|
| **Python** | `.py` | Pylint, radon | Bandit | pip-audit |
| **JavaScript** | `.js` `.jsx` | ESLint | Semgrep | npm audit |
| **TypeScript** | `.ts` `.tsx` | ESLint (TS config) | Semgrep | npm audit |
| **C#** | `.cs` | dotnet-format | Semgrep, Security Code Scan | — |
| **HTML** | `.html` `.htm` | HTMLHint | Semgrep (인라인 스크립트) | — |
| **CSS** | `.css` `.scss` | Stylelint | — | — |
| **공통** | 전체 | — | **Semgrep** (OWASP 전 언어) | — |

> **Semgrep은 모든 언어에 적용** — 언어별 도구가 없는 경우에도 Semgrep이 보안 검사 커버

---

### 5-2. 언어 라우터 (tools/router.py)

```python
# tools/router.py
# 파일 확장자를 보고 어떤 도구를 쓸지 자동으로 결정

from pathlib import Path

# 확장자 → (코드품질 도구 함수, 보안 도구 함수, CVE 함수)
LANGUAGE_TOOL_MAP = {
    ".py":   ("python",     ["pylint", "radon"],   ["bandit"],  ["pip_audit"]),
    ".js":   ("javascript", ["eslint"],            ["semgrep"], ["npm_audit"]),
    ".jsx":  ("javascript", ["eslint"],            ["semgrep"], ["npm_audit"]),
    ".ts":   ("typescript", ["eslint_ts"],         ["semgrep"], ["npm_audit"]),
    ".tsx":  ("typescript", ["eslint_ts"],         ["semgrep"], ["npm_audit"]),
    ".cs":   ("csharp",     ["roslyn"],            ["semgrep"], []),
    ".html": ("html",       ["htmlhint"],          ["semgrep"], []),
    ".htm":  ("html",       ["htmlhint"],          ["semgrep"], []),
    ".css":  ("css",        ["stylelint"],         [],          []),
    ".scss": ("css",        ["stylelint"],         [],          []),
}

def detect_languages(files: list[str]) -> dict[str, list[str]]:
    """파일 목록 → 언어별 파일 그룹"""
    groups: dict[str, list[str]] = {}
    for f in files:
        ext = Path(f).suffix.lower()
        lang = LANGUAGE_TOOL_MAP.get(ext, ("unknown", [], [], []))[0]
        groups.setdefault(lang, []).append(f)
    return groups  # {"python": ["auth.py"], "javascript": ["app.js"], ...}

def get_tools_for_file(filepath: str) -> tuple:
    """파일 하나 → 사용할 도구 목록"""
    ext = Path(filepath).suffix.lower()
    return LANGUAGE_TOOL_MAP.get(ext, ("unknown", [], ["semgrep"], []))
```

---

### 5-3. run_tools 노드 — 다국어 분기

```python
# nodes/run_tools.py
async def run_tools_node(state: Dev2State) -> dict:
    diff = state["payload"]["pr_diff"]
    all_files = _extract_changed_files(diff)   # 모든 변경 파일 추출

    # 언어별로 파일 그룹화
    lang_groups = detect_languages(all_files)
    # 예: {"python": ["auth.py"], "javascript": ["app.js"], "html": ["index.html"]}

    # 각 언어 그룹을 asyncio.gather로 병렬 실행
    tasks = []
    for lang, files in lang_groups.items():
        tasks.append(_run_for_language(lang, files))

    results = await asyncio.gather(*tasks, return_exceptions=True)

    static_raw, security_raw = [], []
    for r in results:
        if isinstance(r, Exception):
            continue
        static_raw.extend(r["static"])
        security_raw.extend(r["security"])

    return {"static_raw": static_raw, "security_raw": security_raw}

async def _run_for_language(lang: str, files: list[str]) -> dict:
    """언어별 도구 실행"""
    RUNNERS = {
        "python":     _run_python,
        "javascript": _run_javascript,
        "typescript": _run_javascript,   # 동일 도구, 설정만 다름
        "csharp":     _run_csharp,
        "html":       _run_html,
        "css":        _run_css,
    }
    runner = RUNNERS.get(lang, _run_generic)  # 모르는 언어 → Semgrep만
    return await runner(files)

async def _run_python(files):
    static, security = await asyncio.gather(
        asyncio.to_thread(lambda: run_pylint(files) + run_radon(files)),
        asyncio.to_thread(lambda: run_bandit(files)),
    )
    security += run_semgrep(files, lang="python")  # 공통 보안도 추가
    return {"static": static, "security": security}

async def _run_javascript(files):
    static = run_eslint(files)
    security = run_semgrep(files, lang="javascript")
    return {"static": static, "security": security}

async def _run_csharp(files):
    static = run_roslyn(files)
    security = run_semgrep(files, lang="csharp")
    return {"static": static, "security": security}

async def _run_html(files):
    static = run_htmlhint(files)
    security = run_semgrep(files, lang="html")
    return {"static": static, "security": security}

async def _run_css(files):
    return {"static": run_stylelint(files), "security": []}

async def _run_generic(files):
    """알 수 없는 언어 → Semgrep 보안 검사만"""
    return {"static": [], "security": run_semgrep(files, lang="generic")}
```

---

### 5-4. 파일 추출 함수 확장

```python
def _extract_changed_files(diff: str) -> list[str]:
    """PR diff에서 변경된 모든 파일 추출 (.py .js .ts .cs .html .css 등)"""
    SUPPORTED = {".py", ".js", ".jsx", ".ts", ".tsx", ".cs", ".html", ".htm", ".css", ".scss"}
    files = []
    for line in diff.splitlines():
        if line.startswith("+++ b/"):
            path = line[6:]
            if Path(path).suffix.lower() in SUPPORTED:
                files.append(path)
    return files
```

---

## 6. LLM 판단 설계 (RAG + 프롬프트 엔지니어링 + LLMOps 비용 최적화)

### 6-1. RAG 흐름

```
CLI 도구 결과 (raw_issues)
    │
    ▼ [vector_search 노드]
pgVector: 이슈 메시지 임베딩 → 코사인 유사도 검색 (Retrieve)  ← CLAUDE.md §9
retrieved_context = [{"pr_id": "98", "similarity": 0.94, "how_resolved": "파라미터화 쿼리"}, ...]
    │
    ▼ [llm_judge 노드]
    ├─ severity == "Minor" → LLM 스킵, 그대로 반환
    │   (USE_MOCK_LLM=true: 개발 중 전체 스킵)  ← CLAUDE.md §7
    └─ severity == "Major" 또는 "Critical"
            │
            ▼
       LangChain Chain 호출 (Augment + Generate)
       - retrieved_context 프롬프트에 주입
       - Few-shot + CoT 프롬프트 (prompts/severity_judge.py)
       - 모델 라우팅: Critical/Major → claude-sonnet-4-6  ← CLAUDE.md §9
       - 출력: 최종 severity + 수준별 개선 제안
```

### 6-2. 프롬프트 엔지니어링 (prompts/severity_judge.py)

```python
# ① Few-shot: 판단 예시 3개 (Critical/Major/Minor 각 1개, 기준 보정)
# ② Chain-of-Thought: 5단계 분석 지시
# ③ Structured Output: 5개 필드 JSON 강제
# ④ RAG: 유사 사례 주입
# ⑤ Domain Rules: 파일 확장자+tech_stack으로 FE/BE 자동 판별 → 언어별 룰셋 주입

severity_prompt = ChatPromptTemplate.from_messages([
    ("system", """시니어 보안 엔지니어로서 단계별로 분석하세요.

[Few-shot 예시]
예시 1) SQL 파라미터 미처리 → Critical (입력값 직접 쿼리 삽입, 즉시 수정 필요)
예시 2) 순환복잡도 15 → Major (리팩토링 권고, 테스트 커버리지 확인)
예시 3) 변수명 스타일 위반 → Minor (코드 스멜, 다음 PR에서 수정)

[Domain Rules — 도메인별 규칙]
{domain_rules}

[과거 유사 사례 — RAG context]
{similar_cases}

[분석 단계 — Chain-of-Thought]
1단계) 이슈 패턴이 무엇인가? (SQL 인젝션? 복잡도? 코드 스멜?)
2단계) 과거 유사 사례와 비교하면 어떤 차이가 있나?
3단계) 최종 severity(Critical|Major|Minor)와 issue_type(Bug|Vulnerability|Code Smell)을 결정하라
4단계) {developer_level} 수준에 맞는 개선 방법을 제시하라
5단계) "A 말고 B 써라" 형태의 한 줄 resolution_example을 작성하라"""),
    ("human", "이슈: {message}\n현재 severity: {current_severity}\n개발자 수준: {developer_level}")
])
```

### 6-3. LLMOps 비용 최적화

```python
# nodes/llm_judge.py

# ① 모델 라우팅: severity별 다른 모델 (CLAUDE.md §9 — 팀 표준 claude-sonnet-4-6)
MODEL_ROUTING = {
    "Critical": "claude-sonnet-4-6",          # 정확도 최우선 (팀 표준 모델)
    "Major":    "claude-haiku-4-5-20251001",  # 균형 (빠른 모델)
    "Minor":    None,                          # 스킵 ($0) — 비용 최소화 핵심
}

# ② 프롬프트 캐싱: 같은 rule_id 반복 이슈는 캐시 활용
from functools import lru_cache

@lru_cache(maxsize=256)
def get_cached_judgment(rule_id: str, severity: str) -> dict | None: ...

# ③ 토큰 사용량 추적 → LangSmith + BigQuery 적재
token_usage = {"prompt_tokens": 0, "completion_tokens": 0, "cost_usd": 0.0}
```

### 6-4. LLM Evaluation Harness (tests/eval/)

```python
# tests/eval/test_severity_eval.py
from langsmith import evaluate
from langsmith.schemas import Example, Run

# 골든 데이터셋: 정답이 있는 이슈 10개
DATASET = [
    {"input": {"message": "SQL 파라미터 미처리", "current_severity": "Major"}, "expected": "Critical"},
    {"input": {"message": "변수명 snake_case 위반", "current_severity": "Minor"}, "expected": "Minor"},
    ...
]

def severity_accuracy(run: Run, example: Example) -> dict:
    return {"score": int(run.outputs["severity"] == example.outputs["expected"])}

# 실행: LangSmith 대시보드에 정확도 자동 기록
# 포트폴리오: "프롬프트 개선으로 정확도 87% → 93% 달성" 수치 제시 가능
results = evaluate(severity_chain, data=DATASET, evaluators=[severity_accuracy])
```

---

## 6. 기술스택 매핑

> **[CLAUDE.md §9 기준]** LLM: claude-sonnet-4-6 | Vector DB: pgVector | State: PRReviewState

| 기술 | Dev 2에서의 역할 | 직무 연관 | AI Native 개념 |
|------|----------------|----------|----------------|
| **Python** | 전체 구현 언어 | 공통 | — |
| **Docker** | 전체 서비스 컨테이너화 | 데이터 엔지니어 | LLMOps 인프라 |
| **Apache Airflow** | 일별 ETL + 주간 집계 배치 DAG | 데이터 엔지니어 | AI Native (자동화) |
| **BigQuery** | 스캔 결과 + 토큰 비용 분석용 DW 적재 | 데이터 엔지니어 | LLMOps 비용 추적 |
| **SQL** | PostgreSQL 실시간 + BigQuery 집계 쿼리 | 데이터 엔지니어 | — |
| ~~n8n~~ | ~~GitHub Webhook 트리거~~ → **Dev1 Orchestrator**가 담당 (CLAUDE.md §4) | — | — |
| **LangGraph** | StateGraph 5노드 + 조건부 엣지 에이전트 | AX/DX | **Agentic Workflow** |
| **LangChain** | Few-shot+CoT 프롬프트 체인 + 개선 제안 생성 | AX/DX | **프롬프트 엔지니어링** |
| **LangSmith** | @traceable 추적 + evaluate() 정확도 평가 (LANGCHAIN_API_KEY) | AX/DX | **LLM Evaluation Harness** |
| **Anthropic API (claude-sonnet-4-6)** | 모델 라우팅(Critical/Major→claude-sonnet, Minor→스킵) | AX/DX | LLMOps 비용 최적화 (CLAUDE.md §9) |
| **Vector DB (pgVector)** | 유사 이슈 코사인 검색 → LLM 프롬프트 컨텍스트 주입 | AX/DX | **RAG (Retrieve)** (CLAUDE.md §9) |
| **ESLint** | JS/TS 코드 품질 검사 (PRD F-SA-01) | AX/DX | 다국어 지원 |
| **Semgrep** | OWASP 룰셋 기반 전 언어 보안 검사 | AX/DX | 다국어 지원 |

---

## 7. Severity 분류 기준

| 1차 (CLI 도구) | 2차 (LLM 재판단 대상) | 최종 |
|---------------|----------------------|------|
| SQL Injection / XSS / CSRF | Yes | Critical 유지 또는 업그레이드 |
| CVE 점수 7.0+ | Yes | Critical 유지 |
| 순환복잡도 > 10 | Yes | Major 유지 또는 조정 |
| CVE 4.0~6.9 | Yes | Major 유지 또는 조정 |
| 코드 스멜 / 중복 | No (스킵) | Minor 그대로 |

---

## 8. DB 스키마 (PostgreSQL)

### 설계 원칙 (postgres-patterns 기반)

| 원칙 | 적용 내용 |
|------|----------|
| ID 타입 | `bigint GENERATED ALWAYS AS IDENTITY` — UUID보다 인덱스 효율 높음 |
| 문자열 | `text` 고정 — `varchar(n)` 불필요 |
| 타임스탬프 | `timestamptz` — timezone-aware |
| 시계열 인덱스 | `BRIN` — `scanned_at` 같은 순차 증가 컬럼에 최적 |
| JSONB 검색 | `GIN` — `similar_issues @> '[{"severity":"Critical"}]'` 패턴 |
| 복합 인덱스 | equality 컬럼 먼저, range 컬럼 나중 |
| 부분 인덱스 | Critical 이슈만 인덱싱 — 에스컬레이션 조회 최적화 |
| 커버링 인덱스 | 인사이트 쿼리에서 테이블 스캔 제거 |
| FK | 외래 키는 반드시 인덱스 추가 |

---

### 마이그레이션

```sql
-- 001_extensions.sql
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;  -- 슬로우 쿼리 모니터링

-- 보안 기본값
REVOKE ALL ON SCHEMA public FROM public;

-- 타임아웃 설정
ALTER SYSTEM SET idle_in_transaction_session_timeout = '30s';
ALTER SYSTEM SET statement_timeout = '30s';
SELECT pg_reload_conf();
```

```sql
-- 002_tables.sql

-- 스캔 실행 단위
-- [CLAUDE.md §3] trace_id: agent_traces 연결 키 ("pr_{12hex}" 형식)
CREATE TABLE scan_executions (
    id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    task_id       text        NOT NULL,
    trace_id      text        NOT NULL,   -- agent_traces.trace_id 연결 (CLAUDE.md §3)
    pr_id         text        NOT NULL,
    developer_id  text        NOT NULL,
    scanned_at    timestamptz NOT NULL DEFAULT now(),
    execution_ms  int
);

-- 개별 이슈 (핵심 테이블)
CREATE TABLE scan_issues (
    id                   bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    scan_id              bigint  NOT NULL REFERENCES scan_executions(id) ON DELETE CASCADE,
    agent                text    NOT NULL,   -- 'static_analysis' | 'security_scan'
    severity             text    NOT NULL,   -- 'Critical' | 'Major' | 'Minor'
    rule_id              text    NOT NULL,
    file                 text,
    line                 int,
    message              text,
    suggestion           text,
    similar_issues       jsonb   NOT NULL DEFAULT '[]',
    is_false_positive    boolean NOT NULL DEFAULT false  -- 오탐 표시 (검증 에이전트용)
);

-- 집계 (개인별/팀별 빠른 조회용)
CREATE TABLE scan_summaries (
    id        bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    scan_id   bigint  NOT NULL REFERENCES scan_executions(id) ON DELETE CASCADE,
    agent     text    NOT NULL,
    critical  int     NOT NULL DEFAULT 0,
    major     int     NOT NULL DEFAULT 0,
    minor     int     NOT NULL DEFAULT 0,
    CONSTRAINT uq_scan_summaries_scan_agent UNIQUE (scan_id, agent)  -- UPSERT 재스캔 대비
);
```

```sql
-- 003_indexes.sql

-- [1] BRIN: scanned_at 시계열 (순차 증가 → BRIN이 B-tree보다 90% 작음)
CREATE INDEX idx_scan_executions_scanned_at
    ON scan_executions USING brin (scanned_at);

-- [2] 복합 B-tree: developer 인사이트 쿼리
--     equality(developer_id) 먼저, range(scanned_at) 나중
CREATE INDEX idx_scan_executions_developer_time
    ON scan_executions (developer_id, scanned_at DESC);

-- [3] FK 인덱스: scan_id (JOIN 성능)
CREATE INDEX idx_scan_issues_scan_id
    ON scan_issues (scan_id);

CREATE INDEX idx_scan_summaries_scan_id
    ON scan_summaries (scan_id);

-- [4] 복합 인덱스: 팀별 인사이트 쿼리
--     GROUP BY rule_id, severity → 두 컬럼 함께
CREATE INDEX idx_scan_issues_rule_severity
    ON scan_issues (rule_id, severity);

-- [5] 부분 인덱스: Critical 이슈만 (에스컬레이션 조회 전용)
--     Critical은 전체의 5~10% → 인덱스 크기 대폭 감소
CREATE INDEX idx_scan_issues_critical
    ON scan_issues (scan_id, rule_id)
    WHERE severity = 'Critical';

-- [6] GIN: similar_issues JSONB 검색
--     WHERE similar_issues @> '[{"pr_id": "98"}]' 패턴
CREATE INDEX idx_scan_issues_similar
    ON scan_issues USING gin (similar_issues);

-- [7] 커버링 인덱스: /insights/developer 쿼리
--     SELECT rule_id, severity, COUNT(*) ... WHERE developer_id = ?
--     → INCLUDE로 테이블 스캔 없이 인덱스만으로 응답
CREATE INDEX idx_executions_developer_covering
    ON scan_executions (developer_id)
    INCLUDE (id, scanned_at);
```

```sql
-- 004_upsert_helpers.sql

-- scan_summaries UPSERT (재스캔 시 덮어쓰기)
-- 같은 scan_id + agent 조합이 중복 삽입될 경우 대비
ALTER TABLE scan_summaries
    ADD CONSTRAINT uq_scan_summaries_scan_agent UNIQUE (scan_id, agent);

-- UPSERT 사용 예시
INSERT INTO scan_summaries (scan_id, agent, critical, major, minor)
VALUES ($1, $2, $3, $4, $5)
ON CONFLICT (scan_id, agent)
DO UPDATE SET
    critical = EXCLUDED.critical,
    major    = EXCLUDED.major,
    minor    = EXCLUDED.minor;
```

---

### 인사이트 쿼리 (인덱스 활용 설계)

```sql
-- /insights/developer/{developer_id}
-- idx_scan_executions_developer_time 사용
SELECT si.rule_id, si.severity, COUNT(*) AS count
FROM scan_issues si
JOIN scan_executions se ON si.scan_id = se.id
WHERE se.developer_id = $1
GROUP BY si.rule_id, si.severity
ORDER BY count DESC;

-- /insights/team (이번 달 Top 5)
-- idx_scan_executions_scanned_at (BRIN) + idx_scan_issues_rule_severity 사용
SELECT si.rule_id, si.severity, COUNT(*) AS count
FROM scan_issues si
JOIN scan_executions se ON si.scan_id = se.id
WHERE se.scanned_at >= date_trunc('month', now())
GROUP BY si.rule_id, si.severity
ORDER BY count DESC
LIMIT 5;

-- /insights/trends (주차별 Critical 추이)
-- BRIN 스캔 → GROUP BY
SELECT
    date_trunc('week', se.scanned_at) AS week,
    se.developer_id,
    SUM(ss.critical)                  AS critical_count
FROM scan_summaries ss
JOIN scan_executions se ON ss.scan_id = se.id
GROUP BY week, se.developer_id
ORDER BY week;

-- 커서 페이지네이션 (OFFSET 대신 사용 — O(1))
-- /insights/developer?cursor=last_id
SELECT si.rule_id, si.severity, si.message
FROM scan_issues si
JOIN scan_executions se ON si.scan_id = se.id
WHERE se.developer_id = $1
  AND si.id > $last_id          -- 커서 기반
ORDER BY si.id
LIMIT 20;

-- Critical 에스컬레이션 조회 (부분 인덱스 활용)
-- idx_scan_issues_critical 사용 (WHERE severity = 'Critical' 부분 인덱스)
SELECT si.file, si.line, si.message, si.rule_id
FROM scan_issues si
WHERE si.severity = 'Critical'
  AND si.scan_id = $1;
```

---

### 모니터링 쿼리

```sql
-- 슬로우 쿼리 탐지 (pg_stat_statements)
SELECT query, mean_exec_time, calls
FROM pg_stat_statements
WHERE mean_exec_time > 100
ORDER BY mean_exec_time DESC
LIMIT 10;

-- 인덱스 미적용 FK 탐지
SELECT conrelid::regclass AS table, a.attname AS column
FROM pg_constraint c
JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = ANY(c.conkey)
WHERE c.contype = 'f'
  AND NOT EXISTS (
    SELECT 1 FROM pg_index i
    WHERE i.indrelid = c.conrelid AND a.attnum = ANY(i.indkey)
  );

-- 테이블 bloat 확인 (VACUUM 필요 여부)
SELECT relname, n_dead_tup, last_vacuum
FROM pg_stat_user_tables
WHERE n_dead_tup > 1000
ORDER BY n_dead_tup DESC;
```

---

## 9. BigQuery 스키마

```sql
CREATE TABLE dev2_dataset.scan_issues_daily (
  scan_date     DATE,
  developer_id  STRING,
  pr_id         STRING,
  agent         STRING,
  severity      STRING,
  rule_id       STRING,
  file          STRING,
  message       STRING
)
PARTITION BY scan_date
CLUSTER BY developer_id, severity;
```

---

## 10. 입출력 계약

### 입력: n8n → POST /scan

```json
{
  "task_id": "uuid",
  "pr_id": "github-pr-number",
  "pr_diff": "string (unified diff format)",
  "developer": {
    "id": "string",
    "skill_level": "junior | mid | senior",
    "tech_stack": ["python", "fastapi"]
  }
}
```

### 출력: Dev2 → Dev4

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
      "rule_id": "SEC-001",
      "suggestion": "파라미터화된 쿼리 사용 권장 (예시 코드 포함)",
      "resolution_example": "f-string SQL 조합 금지. asyncpg :param 사용",
      "similar_issues": [
        { "pr_id": "98", "date": "2026-04-10", "similarity": 0.94 }
      ]
    }
  ],
  "summary": { "critical": 1, "major": 3, "minor": 7 },
  "execution_ms": 1200
}
```

---

## 11. Docker Compose

```yaml
services:
  dev2:
    build: .
    ports:
      - "8002:8002"
    env_file: .env
    depends_on: [postgres, milvus]

  postgres:
    image: postgres:16
    environment:
      POSTGRES_DB: dev2_db
      POSTGRES_USER: user
      POSTGRES_PASSWORD: password
    volumes:
      - postgres_data:/var/lib/postgresql/data

  milvus:
    image: milvusdb/milvus:v2.4.0
    ports:
      - "19530:19530"
    volumes:
      - milvus_data:/var/lib/milvus

  airflow:
    image: apache/airflow:2.9.0
    ports:
      - "8080:8080"
    volumes:
      - ./dags:/opt/airflow/dags
    command: standalone

  n8n:
    image: n8nio/n8n
    ports:
      - "5678:5678"
    volumes:
      - n8n_data:/home/node/.n8n

volumes:
  postgres_data:
  milvus_data:
  n8n_data:
```

---

## 12. 검증 에이전트 (PRD P1)

### 12-1. 오탐(False Positive)률 추적

**목적**: CLI 도구 + LLM이 잘못 탐지한 이슈를 추적해 룰셋/프롬프트 개선에 활용

**흐름:**
```
개발자가 이슈 무시 → PATCH /issues/{id}/dismiss
    → scan_issues.is_false_positive = true
    → Airflow 주간 DAG: rule_id별 오탐률 집계 → BigQuery
    → LangSmith Evaluation 골든 데이터셋에 자동 추가 (오탐 케이스)
```

**DB 변경**: `scan_issues`에 `is_false_positive boolean DEFAULT false` 컬럼 추가

**API 추가:**
```python
# api/insights.py
PATCH /issues/{issue_id}/dismiss
→ scan_issues.is_false_positive = true 업데이트
→ 응답: {"issue_id": id, "is_false_positive": true}
```

**Airflow 주간 집계 쿼리:**
```sql
-- rule_id별 오탐률: 오탐 수 / 전체 탐지 수
SELECT
    rule_id,
    COUNT(*) FILTER (WHERE is_false_positive = true)  AS fp_count,
    COUNT(*)                                           AS total_count,
    ROUND(
        COUNT(*) FILTER (WHERE is_false_positive = true) * 100.0 / COUNT(*), 1
    ) AS fp_rate_pct
FROM scan_issues
WHERE created_at >= now() - interval '7 days'
GROUP BY rule_id
ORDER BY fp_rate_pct DESC;
```

> 오탐률 20% 초과 rule_id → Slack 알림 ("SEC-005 룰이 오탐이 많습니다, 룰셋 검토 필요")

---

### 12-2. 보안 룰셋 최신화 확인

**목적**: Bandit/Semgrep 룰셋이 최신 버전인지 주기적으로 확인해 알림

**Airflow 주간 DAG에 노드 추가 (`dags/weekly_report.py`):**

```python
def check_ruleset_versions(**context):
    import subprocess, requests

    tools = {
        "bandit":  {"cmd": ["bandit", "--version"], "github": "PyCQA/bandit"},
        "semgrep": {"cmd": ["semgrep", "--version"], "github": "semgrep/semgrep"},
    }

    outdated = []
    for name, cfg in tools.items():
        # 현재 설치 버전
        result = subprocess.run(cfg["cmd"], capture_output=True, text=True)
        current = result.stdout.strip().split()[-1]

        # GitHub 최신 릴리즈 버전
        resp = requests.get(
            f"https://api.github.com/repos/{cfg['github']}/releases/latest",
            headers={"Accept": "application/vnd.github.v3+json"},
            timeout=10,
        )
        latest = resp.json()["tag_name"].lstrip("v")

        if current != latest:
            outdated.append(f"{name}: {current} → {latest} 업데이트 필요")

    if outdated:
        # Slack 알림 (SLACK_WEBHOOK_URL 환경변수)
        notify_slack("\n".join(outdated), channel="#team-security")

ruleset_check = PythonOperator(
    task_id="check_ruleset_versions",
    python_callable=check_ruleset_versions,
)

# 주간 DAG 흐름: 오탐률 집계 → 룰셋 버전 체크
aggregate_fp_rate >> ruleset_check
```

---

## 12-1. TDD 방법론

모든 구현은 **Red → Green → Refactor** 사이클을 따른다.

### 원칙

1. **테스트 먼저** — 구현 전 실패하는 테스트를 먼저 작성한다.
2. **최소 구현** — 테스트 통과에 필요한 최소 코드만 작성한다.
3. **리팩토링** — 통과 후 코드 품질 개선 (테스트는 계속 통과 상태 유지).
4. **Mock 기반 단위 테스트** — 실제 DB/LLM 없이 통과해야 함 (CLAUDE.md §10, §13).
5. **커버리지 80% 이상** — `pytest --cov=dev2` 기준.

### 테스트 파일 매핑

| 구현 대상 | 테스트 파일 | Mock 대상 |
|----------|------------|-----------|
| CLI 도구 (tools/) | `tests/test_tools.py` | `subprocess.run` |
| LangGraph 노드 | `tests/test_nodes.py` | pgVector, LLM, subprocess |
| StateGraph 전체 | `tests/test_graph.py` | 전체 노드 Mock |
| FastAPI 엔드포인트 | `tests/test_insights.py` | DB, LangGraph |
| LLM 평가 | `tests/eval/test_severity_eval.py` | LangSmith evaluate() |

### Red → Green → Refactor 예시

```python
# Red: 실패하는 테스트 먼저
def test_llm_judge_returns_contract():
    result = llm_judge_node(mock_state)
    assert result["agent"] == "static_analysis"
    assert "issues" in result
    assert "summary" in result  # ← 아직 구현 없으므로 실패

# Green: 최소 구현으로 통과
def llm_judge_node(state):
    return {"agent": "static_analysis", "issues": [], "summary": {}}

# Refactor: 실제 LLM 호출 + Output Contract 준수로 개선
```

---

## 13. 개발 우선순위 (주차별)

| 주차 | 목표 | 완료 기준 |
|------|------|-----------|
| Week 1 | schema + DB 스키마 + Docker 세팅 | docker-compose up 전체 실행 |
| Week 2~3 | CLI 도구 (tools/) + LangGraph StateGraph + LLM 판단 노드 | 스캔 → LLM 판단 → DB 적재 E2E |
| Week 4 | Milvus 유사 이슈 + BigQuery 적재 + FastAPI | /insights/* 응답 확인 |
| Week 5 | Airflow DAG + n8n 워크플로우 | GitHub PR → n8n → Dev2 E2E |
| Week 6 | 버그 수정 + 전체 데모 | 전체 데모 시나리오 동작 |

---

## 14. 포트폴리오 포인트

| 직무 | 역량 |
|------|------|
| **데이터 엔지니어** | PostgreSQL→BigQuery ETL, Airflow DAG, 파티셔닝 쿼리 최적화, Docker 컨테이너화 |
| **AX/DX** | LangGraph 에이전트 설계, LangChain 체인, OpenAI API 통합, Milvus 벡터 검색, n8n 워크플로우 자동화 |
