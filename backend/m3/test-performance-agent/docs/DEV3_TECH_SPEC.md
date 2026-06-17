# Dev3 — 테스트 검증 + 성능 분석 에이전트 · 통합 설계서 (Build Spec)

> **이 문서의 목적**: 이 문서 **하나만** 읽고 Dev3 모듈 전체를 처음부터 구현할 수 있도록, 기획·기술·기능·워크플로우·데이터 계약을 모두 담은 단일 소스(Single Source of Truth).
> **독자**: Dev3를 구현하는 사람/에이전트. 사전 지식 불필요.
> **MAS 패턴**: Parallel Independent Agents · **하네스**: `asyncio.gather` + LangSmith
> **스택**: Python 3.11+ · Pydantic v2 · `ast` · `unidiff` · pytest-cov · Docker · (LLM: OpenAI/Anthropic/Gemini 중 택1)
> **연계 문서**: `PRD_조직지식관리_온보딩_플랫폼.md`(전체 플랫폼), `DB_데이터_요구사항.md`(공유 DB), `Dev3_에이전트_설계서.md`/`Dev3_테스트검증_성능분석_에이전트_설계가이드.md`(원본 설계·개념)

---

## 0. 30초 요약 (TL;DR)

1. **만드는 것** = 신입 개발자가 올린 PR 코드를 받아 **① 테스트가 충분한가 ② 코드가 느리거나 비효율적인가**를 자동 검사하는 분석 에이전트.
2. **입력** = Dev1 오케스트레이터가 모아 주는 JSON(`task_id`, `scan_id`, `pr_diff`, `repo`, `developer`).
3. **출력** = 표준 `issues[]` JSON **2개**(`test_verification`, `performance`) → Dev4가 받아 합격/불합격 판정.
4. **자체 DB 테이블 없음.** Dev2가 만든 공유 테이블(`scan_executions`/`scan_issues`/`scan_summaries`)에 같은 `scan_id`로 기록.
5. **핵심 원칙**: **AST = 사실 추출(정확) / LLM = 판단·설명·제안.** 측정 가능한 건 도구로, 추론이 필요한 것만 LLM으로.
6. **데모 핵심 시나리오** = N+1 쿼리 감지(F-PERF-02, P0). 발표 비중이 가장 큰 부분.

---

## 1. 제품 맥락 — Dev3는 코드 리뷰 파이프라인의 어디에 있나

### 1.1 전체 플랫폼 한 줄 정의
> "사내 지식을 AI가 자동 구조화하고(KMS), 신입 개발자의 PR을 자동 리뷰·학습경로화하는 멀티 에이전트 플랫폼."

팀은 6명: 프론트 1 + 서비스 구현 5(Dev1~5). Dev3는 그중 **분석 에이전트**다.

### 1.2 코드 리뷰 파이프라인에서의 위치

```
신입이 GitHub PR 제출
   │
[Dev1] 오케스트레이터 — Webhook 수신(HMAC-SHA256 검증), 의도 분류, KMS 문서 검색, 라우팅
   │   scan_executions 행 1건 생성 → scan_id 발급
   │
   ├── 4개 분석 에이전트 병렬 실행 (asyncio.gather, 60초 예산)
   │     [Dev2] 정적분석  (static_analysis)  ─┐
   │     [Dev2] 보안스캔  (security_scan)    ─┤  같은 scan_id 공유
   │     [Dev3] 테스트검증 (test_verification)┤  ← 나
   │     [Dev3] 성능분석   (performance)      ─┘  ← 나
   │
[Dev4] 평가 에이전트 — 4개 결과를 scan_id로 취합 → LGTM / 재작업 / 에스컬레이션 판정
   │
GitHub 코멘트 자동 등록 / Slack 알림 / Dev5 피드백 루프
```

### 1.3 Dev3의 정체성
- Dev3는 **"리뷰 의견을 쓰는 사람"이 아니라 "리뷰 근거(테스트·성능 데이터)를 만드는 사람"**.
- 합격/불합격(verdict) 판정은 **Dev4** 몫. Dev3는 **이슈(issue) 사실만** 만들어 넘긴다.
- 보안·컨벤션·정적분석은 **Dev2** 몫. Dev3는 **테스트·성능만**.

### 1.4 인접 에이전트와의 계약 한눈에

| 상대 | 방향 | 주고받는 것 |
|------|------|------------|
| **Dev1** | 입력 ← | `task_id`, `scan_id`, `pr_id`, `pr_diff`, `repo{clone_url,commit_sha,test_command}`, `developer{skill_level,tech_stack}` |
| **Dev2** | 공유 | 동일 `scan_id`로 같은 테이블에 기록 (형제 분석 에이전트). 실행 샌드박스(Docker) 공동 사용 |
| **Dev4** | 출력 → | `AgentOutput` 2개(`test_verification`, `performance`) JSON |
| **Dev5** | 간접 | Dev3가 만든 `scan_issues`를 Dev5가 집계 → `mistake_patterns` 생성 → Dev1이 `previous_pr_issues`로 다시 Dev3에 전달(루프) |

---

## 2. 책임 범위 — 요구사항

### 2.1 본업 (채점): F-TEST / F-PERF 8개

| ID | 요구사항 | 우선순위 | 담당 모듈 |
|----|----------|:---:|-----------|
| F-TEST-01 | 테스트 커버리지 측정 (라인/브랜치/함수) | **P0** | `coverage.py` |
| F-TEST-02 | 커버리지 80% 미달 시 Major 이슈 분류 | **P0** | `coverage.py` |
| F-TEST-03 | 엣지케이스 누락 탐지 (null·빈배열·음수·경계) | P1 | `edge_cases.py` (LLM) |
| F-TEST-04 | 단위 테스트 누락 함수 목록 제안 | P1 | `missing_funcs.py` |
| F-PERF-01 | 시간복잡도 추정 (O(n²) 이상 경고) | P1 | `complexity.py` |
| F-PERF-02 | N+1 쿼리 패턴 감지 | **P0** | `nplus1.py` |
| F-PERF-03 | 메모리 누수 가능 패턴 감지 | P1 | `memory_leak.py` (AST+LLM) |
| F-PERF-04 | 병목 지점 탐지 및 최적화 제안 | P2 | (차기 버전) |

### 2.2 검증 (채점기 검사): 2개

| 요구사항 | 우선순위 | 담당 |
|----------|:---:|------|
| 커버리지 측정 정확도 검증 에이전트 | P1 | `validation/eval.py` |
| 성능 분석 false alarm(오탐) 추적 에이전트 | P1 | `validation/eval.py` |

> **두 층 구분이 핵심**: ① 본업 = 신입 코드를 분석해 이슈를 뽑는다. ② 검증 = 내 에이전트가 똑바로 채점하는지 정답지(fixtures)로 확인한다.

---

## 3. 시스템 아키텍처

```
[입력 계약 수신]  task_id, scan_id, pr_id, repo{...}, pr_diff, developer
        │
[STEP 1 준비]  shallow clone + git fetch/checkout(commit_sha) → Docker 샌드박스 작업폴더
        │
[STEP 1.5a] coverage.measure()  ← 순차 선행 (missing_funcs가 coverage.json을 읽어야 하므로)
        │     Docker: pytest --cov → {repo_path}/coverage.json 생성 (최대 COV_TIMEOUT_S=15초)
        │
        ├──────────── asyncio.gather(return_exceptions=True) ─────────────┐
        │  [테스트 검증 브랜치]                                  [성능 분석 브랜치]
        │   ├ missing_fn  (AST ∖ coverage.json 실행함수)          ├ nplus1     (AST)
        │   └ edge_case   (LLM) ★opt-in                          ├ complexity (AST + LLM)
        │                                                         └ mem_leak   (AST + LLM) ★opt-in
        │                                                                 │
        └───────────────────────┬─────────────────────────────────────────┘
                                │  (탐지기별 예외는 빈 결과로 대체 → 부분 실패 허용)
[STEP 2 필터]  diff 교집합 → '신입이 바꾼 함수 범위' 이슈만 유지
                                │
[STEP 3 조립]  Pydantic 검증 → AgentOutput 2개(test_verification, performance) + summary 집계
                                │
[STEP 4 저장]  scan_issues INSERT + scan_summaries UPSERT (받은 scan_id 사용) · agent_traces 로깅
        │                       │
   LangSmith 추적          [출력] → Dev4
```

> **실행 순서 주의**: `coverage.measure()`는 gather 전에 순차 실행된다. `missing_funcs`가 coverage.json 파일에 의존하기 때문이다. 타이밍 계산: coverage 최대 15초 + gather 최대 8초 = **최대 23초** (30초 예산 이내).

**왜 asyncio.gather인가**: Dev3의 6개 탐지기는 서로 독립적(한 탐지기 결과가 다른 탐지기 입력이 아님)이라 **병렬 독립 에이전트(Parallel Independent Agents)** 패턴이 정확하다. LangGraph(상태 머신·조건 분기·HITL)는 Dev1/Dev4/Dev5의 몫이고, Dev3는 사람 개입 없이 30초 안에 자동 완결하므로 `asyncio.gather` 한 줄이면 충분하다.

---

## 4. I/O 데이터 계약 (가장 중요)

### 4.1 Pydantic 모델 — `contracts.py`

```python
"""Dev3 데이터 계약. 입출력 규격을 코드로 고정한다."""
from __future__ import annotations
from typing import Literal, Optional
from pydantic import BaseModel


# ── 입력 (Dev1 → Dev3) ─────────────────────────────
class RepoInfo(BaseModel):
    clone_url: str = ""
    commit_sha: str = ""
    language: str = "python"
    test_command: str = "pytest --cov=src --cov-report=json"

class Developer(BaseModel):
    id: str = "junior_dev_01"
    skill_level: Literal["junior", "mid", "senior"] = "junior"
    tech_stack: list[str] = []

class Dev3Context(BaseModel):                      # 후순위(△). MVP는 비워둠
    architecture_docs: list[str] = []
    coding_conventions: str = ""
    previous_pr_issues: list[str] = []             # Dev5→Dev1 경유 반복실수 맥락

class Dev3Input(BaseModel):
    task_id: str
    scan_id: int                                   # Dev1이 scan_executions 행 생성 후 발급 (필수)
    pr_id: str
    pr_diff: str                                   # unified diff
    repo: RepoInfo = RepoInfo()                    # 클론·커버리지 실행용 (Dev1과 합의 완료)
    developer: Developer = Developer()
    context: Dev3Context = Dev3Context()


# ── 이슈 (출력 단위) ───────────────────────────────
class Issue(BaseModel):
    severity: Literal["Critical", "Major", "Minor"]
    file: str
    line: Optional[int] = None
    message: str
    rule_id: str                                   # TEST-xxx / PERF-xxx
    suggestion: str = ""


# ── summary 카운트 — dict 대신 타입 고정으로 계약 위반을 Pydantic이 잡게 함 ──
class SummaryCount(BaseModel):
    critical: int = 0
    major: int = 0
    minor: int = 0


# ── 출력 (Dev3 → Dev4), agent별 1개씩 ──────────────
class AgentOutput(BaseModel):
    task_id: str
    scan_id: int                                   # Dev4가 DB join 시 사용 (Dev3Input.scan_id 그대로)
    pr_id: str                                     # Dev4가 GitHub 코멘트 등록 시 사용
    agent: Literal["test_verification", "performance"]
    issues: list[Issue]
    summary: SummaryCount
    metrics: Optional[dict] = None                 # DB scan_summaries.metrics 와 매칭 (nullable)
    #   test_verification → {"coverage_line":0.42,"coverage_branch":0.35,"coverage_func":0.33}
    #   performance       → None (커버리지 측정 안 함)
    execution_ms: int
```

> **DB 정합성(필수 준수)**: `metrics` 키/단위는 DB와 동일하게 — `coverage_line`/`coverage_branch`/`coverage_func`, **0~1 소수**. (예: 42% → `0.42`, 백분율 아님)
> MVP에서 브랜치·함수 커버리지 미지원 시 `coverage_line`만 포함 가능. 단 나머지 키는 `null`이 아니라 **아예 생략**할 것 (Dev4 파싱 오류 방지).

### 4.2 입력 JSON 예시 (Dev1 → Dev3)

```json
{
  "task_id": "uuid-1234",
  "scan_id": 42,
  "pr_id": "PR-001",
  "pr_diff": "diff --git a/src/posts.py b/src/posts.py\n--- /dev/null\n+++ b/src/posts.py\n@@ -0,0 +1,22 @@\n+def get_posts(post_ids):\n+    ...",
  "repo": {
    "clone_url": "https://github.com/team/proj.git",
    "commit_sha": "abc123",
    "language": "python",
    "test_command": "pytest --cov=src --cov-report=json"
  },
  "developer": {
    "id": "junior_dev_01",
    "skill_level": "junior",
    "tech_stack": ["python", "fastapi", "postgresql"]
  },
  "context": {
    "architecture_docs": ["chunk_id_1"],
    "coding_conventions": "",
    "previous_pr_issues": ["N+1 쿼리"]
  }
}
```

### 4.3 출력 JSON 예시 (Dev3 → Dev4) — 2개 배열

```json
[
  {
    "task_id": "uuid-1234",
    "scan_id": 42,
    "pr_id": "PR-001",
    "agent": "test_verification",
    "issues": [
      {"severity": "Major", "file": "(전체)", "line": null,
       "message": "테스트 라인 커버리지 20.0% < 기준 80%.",
       "rule_id": "TEST-001", "suggestion": "테스트를 추가해 커버리지를 80% 이상으로 올리세요."},
      {"severity": "Minor", "file": "src/posts.py", "line": 4,
       "message": "함수 'get_posts'에 대한 테스트 실행 흔적이 없습니다.",
       "rule_id": "TEST-004", "suggestion": "get_posts()에 대한 단위 테스트를 추가하세요."},
      {"severity": "Minor", "file": "src/posts.py", "line": 16,
       "message": "함수 'find_dups'에 대한 테스트 실행 흔적이 없습니다.",
       "rule_id": "TEST-004", "suggestion": "find_dups()에 대한 단위 테스트를 추가하세요."}
    ],
    "summary": {"critical": 0, "major": 1, "minor": 2},
    "metrics": {"coverage_line": 0.20},
    "execution_ms": 1500
  },
  {
    "task_id": "uuid-1234",
    "scan_id": 42,
    "pr_id": "PR-001",
    "agent": "performance",
    "issues": [
      {"severity": "Major", "file": "src/posts.py", "line": 7,
       "message": "N+1 쿼리: 루프 안에서 DB 호출이 반복됩니다.",
       "rule_id": "PERF-002", "suggestion": "joinedload()/selectinload() 등으로 루프 밖에서 한 번에 조회하세요."},
      {"severity": "Minor", "file": "src/posts.py", "line": 16,
       "message": "함수 'find_dups' 중첩 루프 깊이 2 → O(n^2) 추정.",
       "rule_id": "PERF-001", "suggestion": "set/dict 활용 또는 알고리즘 변경으로 복잡도를 낮추세요."}
    ],
    "summary": {"critical": 0, "major": 1, "minor": 1},
    "metrics": null,
    "execution_ms": 1500
  }
]
```

### 4.4 rule_id 네임스페이스 (팀 합의)

| 에이전트 | 접두사 | 예시 |
|----------|--------|------|
| 테스트 검증 | `TEST-` | TEST-001(커버리지), TEST-003(엣지), TEST-004(누락함수) |
| 성능 분석 | `PERF-` | PERF-001(복잡도), PERF-002(N+1), PERF-003(메모리누수) |
| (Dev2 보안) | `SEC-` | SEC-001 … (참고용, Dev3 영역 아님) |

---

## 5. 모듈/파일 구조

```
backend/dev3/
├── main.py                  # 진입점: 입력 → 병렬 탐지 → 필터 → 조립 → 저장 → 출력
├── contracts.py             # Pydantic 모델 (Input / Issue / SummaryCount / AgentOutput)
├── config/
│   └── settings.py          # 임계값·타임아웃·모델명 (하드코딩 금지, 전부 여기)
├── prepare/
│   ├── repo.py              # shallow clone + git fetch/checkout(commit_sha)
│   ├── sandbox.py           # Docker 실행 래퍼 (격리·타임아웃)
│   └── Dockerfile.sandbox   # pytest 미리 깐 베이스 이미지 (dev3-sandbox)
├── test_verification/
│   ├── coverage.py          # F-TEST-01,02  (골든) — coverage.json을 {repo_path}/coverage.json에 생성
│   ├── missing_funcs.py     # F-TEST-04     (골든) — {repo_path}/coverage.json 읽음 (coverage 완료 후 실행)
│   └── edge_cases.py        # F-TEST-03 (LLM/휴리스틱, opt-in — main 미연결)
├── performance/
│   ├── nplus1.py            # F-PERF-02     (골든)
│   ├── complexity.py        # F-PERF-01 (AST; LLM 빅오확정 opt-in)  (골든)
│   └── memory_leak.py       # F-PERF-03 (AST+LLM/휴리스틱, opt-in — main 미연결)
├── filter/
│   └── diff_filter.py       # diff 교집합 + 함수 확장 (unidiff + ast)
├── assemble/
│   └── output.py            # issues 합치기 + SummaryCount 집계 + Pydantic 검증
├── persist.py               # scan_issues INSERT + scan_summaries UPSERT
├── harness.py               # LangSmith 계측 데코레이터 + Eval 진입점 (키 없으면 no-op)
├── tracing.py               # Postgres agent_traces 요약 1행 로깅 (LangSmith와 중복 금지)
├── validation/
│   └── eval.py              # 검증 층: 라벨 샘플 채점 (오탐률·정확도), store=False로 호출
└── tests/
    └── fixtures/            # Mock 코드 샘플 + 정답 라벨 (golden)
```

**설계 원칙**: **요구사항 1개 = 파일 1개.** 모든 탐지기는 시그니처를 통일한다:
```python
def detect(repo_path: str, changed: dict[str, set[int]] | None) -> list[Issue]: ...
```
→ 새 탐지기를 끼우거나 교체하기 쉽다. (단 `coverage.measure()`만 `(issues, metrics)` 튜플 반환 — 측정치를 함께 내보내기 때문)

---

## 6. 파이프라인 상세 — `main.py`

```python
import asyncio, time
from contracts import Dev3Input, AgentOutput
from test_verification import coverage as coverage_mod
from test_verification import missing_funcs
from performance import nplus1, complexity
from filter.diff_filter import parse_diff, filter_issues
from assemble.output import assemble

# repo_path를 직접 주면(데모/테스트) 그 경로를 쓰고, 없으면 inp.repo로 shallow clone.
# store=False면 STEP 4(저장/추적)를 생략한다 — eval처럼 순수 채점용 호출 시 반드시 False.
async def run(inp: Dev3Input, repo_path: str | None = None, store: bool = True) -> list[AgentOutput]:
    t0 = time.monotonic()
    started_at = _now_iso()

    # STEP 1: 준비 — repo_path 없으면 inp.repo로 클론
    if repo_path is None:
        from prepare.repo import prepare_repo
        repo_path = await asyncio.to_thread(prepare_repo, inp.repo)
    changed = parse_diff(inp.pr_diff)                   # {파일: 바뀐 줄 범위}

    # STEP 1.5a: coverage 순차 선행 (missing_funcs가 {repo_path}/coverage.json을 읽어야 함)
    # 타이밍: 최대 COV_TIMEOUT_S=15초. asyncio.wait_for로 개별 제한.
    cov_issues, metrics = await asyncio.wait_for(
        asyncio.to_thread(coverage_mod.measure, repo_path),
        timeout=settings.COV_TIMEOUT_S,
    )

    # STEP 1.5b: 나머지 탐지기 병렬 — coverage 완료 후 실행 (missing_funcs: coverage.json 읽기 가능)
    #   _safe: 동기 탐지기를 스레드로 실행하고 예외를 [] 로 흡수 (partial_fail 로깅).
    #   return_exceptions=True는 _safe가 raise하지 않으므로 실질적 영향 없음 — 이중 안전망.
    results = await asyncio.gather(
        _safe(nplus1.detect,        repo_path, changed),  # PERF-002
        _safe(complexity.detect,    repo_path, changed),  # PERF-001 (AST; LLM 빅오확정은 opt-in)
        _safe(missing_funcs.detect, repo_path, changed),  # TEST-004 (coverage.json 필요)
        return_exceptions=True,
    )
    nplus1_i, cplx_i, missing_i = [r if isinstance(r, list) else [] for r in results]

    # ── opt-in 탐지기 (LLM/모킹 테스트 준비 후 연결) ──────────────────────
    #   edge_cases(TEST-003)·memory_leak(PERF-003)은 비결정적(LLM/휴리스틱)이라
    #   기본 경로에서 제외한다. 연결하려면 expected_output.json 골든 라벨도 함께 확장할 것.
    #     _safe(edge_cases.detect,  repo_path, changed),   # TEST-003
    #     _safe(memory_leak.detect, repo_path, changed),   # PERF-003

    # STEP 2: diff 교집합 필터 (신입이 바꾼 함수 범위만)
    test_issues = filter_issues(missing_i + cov_issues, changed, repo_path)
    perf_issues = filter_issues(nplus1_i + cplx_i,      changed, repo_path)

    # STEP 3: 조립 + Pydantic 검증
    ms = int((time.monotonic() - t0) * 1000)
    out_test = assemble(inp.task_id, inp.scan_id, inp.pr_id, "test_verification", test_issues, metrics, ms)
    out_perf = assemble(inp.task_id, inp.scan_id, inp.pr_id, "performance",       perf_issues, None,    ms)
    outputs = [out_test, out_perf]

    # STEP 4: 저장 + 트레이싱 (실패해도 분석 결과는 살림)
    if store:
        _store(inp, outputs, started_at)
    return outputs


def _store(inp: Dev3Input, outputs: list[AgentOutput], started_at: str) -> None:
    """persist + tracing을 묶어 호출. 각각 실패해도 분석 결과(outputs)에는 영향 없음."""
    try:
        from persist import persist
        persist(inp.scan_id, outputs)
    except Exception as e:
        print(f"[store_fail] persist: {e}")
    try:
        from tracing import log_trace
        log_trace(inp, outputs, started_at)
    except Exception as e:
        print(f"[store_fail] tracing: {e}")


async def _safe(fn, *args):
    """부분 실패 허용: 동기 탐지기를 스레드로 돌리고, 예외는 [] 로 흡수."""
    try:
        return await asyncio.to_thread(fn, *args)
    except Exception as e:
        print(f"[partial_fail] {fn.__module__}: {e}")
        return []
```

> **A안(현재 채택)**: 기본 `main.run()`은 **결정론적 골든 4종**(coverage·missing_funcs·nplus1·complexity)만 돌려 검증 층(eval)의 PASS를 보장한다. **edge_cases·memory_leak은 opt-in** — LLM 응답 모킹 테스트나 LangSmith LLM 평가 프레임워크가 준비되면 위 주석을 해제하고 `expected_output.json` 골든 라벨에 TEST-003·PERF-003을 추가해 **B안(6종 완전 연결)** 으로 확장한다.

> **부분 실패 정책**: `_safe`가 모든 탐지기 예외를 잡아 `[]` 반환하므로 탐지기 하나가 죽어도 나머지 결과는 Dev4로 전달된다. 죽은 탐지기는 `partial_fail`로 print 기록 (tracing.py와 연동하면 DB에도 남음).

---

## 7. 탐지기별 설계

모든 탐지기 시그니처: `detect(repo_path, changed) -> list[Issue]`
**원칙: AST = 사실 추출(정확) / LLM = 판단·설명·제안.** LLM 호출은 항상 Pydantic 스키마로 구조화 강제(인사말·잡담 차단).

| 파일 | 방법 | severity 규칙 | rule_id |
|------|------|--------------|---------|
| `coverage.py` | Docker `pytest --cov` → `coverage.json` 파싱. 측정치는 `metrics`로 | 라인 < 80% → **Major** | `TEST-001` |
| `missing_funcs.py` | AST 전체 함수 − coverage 실행 함수 = 차집합 | Minor | `TEST-004` |
| `edge_cases.py` | 함수+테스트 → LLM 구조화 출력 | Minor | `TEST-003` |
| `nplus1.py` | AST: `for/while` 본문에 `.query/.execute/.filter` 등 호출 | **Major** | `PERF-002` |
| `complexity.py` | AST 중첩 루프 깊이 ≥2 → LLM 빅오 확정 | O(n²) Minor / O(n³)↑ Major | `PERF-001` |
| `memory_leak.py` | AST: 안 닫힌 파일·전역 누적 append 등 → LLM 검토 | Minor | `PERF-003` |

### 7.1 `coverage.py` (F-TEST-01/02, P0)

- Docker 샌드박스에서 `pytest --cov=src --cov-report=json` 실행 → `{repo_path}/coverage.json` 파싱.
- **coverage.json 경로 규칙**: pytest-cov는 항상 실행 디렉터리에 `coverage.json`을 생성. Docker 마운트 경로가 `/work`이므로 컨테이너 안 `/work/coverage.json` = 호스트 `{repo_path}/coverage.json`. `missing_funcs`는 이 경로를 읽는다.
- **측정 종류 (F-TEST-01)**:

| 커버리지 종류 | coverage.json 키 | metrics 키 | MVP |
|---|---|---|---|
| 라인 | `totals.percent_covered` | `coverage_line` | **필수** |
| 브랜치 | `totals.covered_branches` / `totals.num_branches` | `coverage_branch` | △ (없으면 생략) |
| 함수 | pytest-cov 직접 미지원 → AST로 별도 계산 | `coverage_func` | △ (없으면 생략) |

- **브랜치는 `--cov-branch` 필요**: `run(use_sandbox=True)`가 pytest 명령에 `--cov-branch`를 자동 추가 → coverage.json에 `num_branches`/`covered_branches` 생성. 데모(파일 직접읽기)는 브랜치 데이터가 없으면 `coverage_branch` 생략.
- **함수 커버리지 계산식**: 파일별 `executed_lines` ∩ 함수 본문 줄 범위(`body[0]~end_lineno`)가 비지 않으면 '실행된 함수'. `coverage_func = 실행함수 / 전체함수`. (def 줄은 import 시 항상 실행되므로 본문만 본다)
- 측정값은 0~100 → `/100`으로 **0~1 소수** 변환. `metrics`에 측정된 키만 포함 (미측정 키는 생략, null 아님).
- `coverage_line < settings.COVERAGE_THRESHOLD`(0.80)면 `TEST-001` **Major** 이슈 1건. `file="(전체)"`, `line=None`.
- 반환은 예외적으로 `(list[Issue], metrics: dict | None)` 튜플.
- **fallback(환각 방지)**: deps 설치 실패 → 재시도 → 그래도 실패면 **"측정 불가"를 정직 보고**(숫자 지어내기 금지). 측정 불가 시 `metrics=None`, 이슈 없음.

### 7.2 `missing_funcs.py` (F-TEST-04, P1)

- **전제**: `coverage.py`가 먼저 실행되어 `{repo_path}/coverage.json`이 존재해야 함. `main.py`에서 coverage 순차 선행 후 gather로 호출하는 이유 (§3, §6 참고).
- `detect(repo_path, changed)` 내부에서 `{repo_path}/coverage.json`을 직접 읽음. 파일이 없으면 (coverage 실패 fallback) **이슈 0건 반환** (오탐 금지).
- AST로 레포 전체 함수 목록을 뽑고, `coverage.json`의 `files[*].executed_lines`와 비교.
- **함정(반드시 반영)**: `def` 줄은 import 시점에 항상 "실행됨"으로 잡힌다. 따라서 **함수 본문 줄 범위(`body[0].lineno ~ end_lineno`)** 만 보고, 그 범위가 `executed_lines`와 교집합이 없으면 "테스트 안 된 함수"로 판정. (def 줄로 판단하면 모든 함수가 covered로 오판됨)
- 누락 함수마다 `TEST-004` **Minor**, `line=node.lineno`.

### 7.3 `edge_cases.py` (F-TEST-03, P1) — LLM 주력

- AST로 신입이 수정한 함수만 오려서(타겟팅), LLM에 *"이 함수가 처리해야 하는데 테스트에 빠진 엣지케이스(null/0/음수/빈 값/경계)는?"* 질문.
- LLM 출력은 `class EdgeCases(BaseModel): missing: list[str]` 로 **구조화 강제**.
- 누락 케이스가 있으면 `TEST-003` **Minor**.
- **LLM 미가용 시**: API 키 없으면 규칙 휴리스틱(인자명 기반: `price→0/음수`, `rate→음수/>1`, `ids→빈 리스트/None` 등)으로 대체하고 메시지에 `[heuristic]` 표시. 키만 넣으면 그대로 LLM 버전으로 승격(둘 다 `list[Issue]` 반환).

### 7.4 `nplus1.py` (F-PERF-02, P0) — 데모 핵심

- AST `ast.walk`로 모든 `for/while` 노드를 찾고, 그 본문 안에 DB 호출(`.query/.execute/.filter/.get/.all/.first/.fetchone/.fetchall/.scalar/.count` 등 `ast.Attribute` 호출)이 있으면 N+1 후보.
- 같은 `(lineno, col_offset)` 중복은 `seen` 집합으로 1회만.
- `PERF-002` **Major**, `line=호출 줄`.
- DB 호출 이름 집합은 `settings.DB_CALL_NAMES`로 관리.

### 7.5 `complexity.py` (F-PERF-01, P1) — AST 의심 → LLM 확정

- 함수별 최대 중첩 루프 깊이를 재귀로 계산. 깊이 ≥2면 `O(n^depth)` 후보.
- 깊이 2 → **Minor**, 깊이 3↑ → **Major** (`settings`로 임계 조정 가능).
- **LLM 확정**: 후보 함수 소스를 LLM에 주고 실제 빅오·개선안을 받아 message에 반영. AST는 "의심", LLM은 "확정·설명". LLM 미가용 시 AST 추정값만 사용.
- `PERF-001`.

### 7.6 `memory_leak.py` (F-PERF-03, P1) — AST + LLM

- AST 패턴: ① `open()` 후 `with`/`close()` 없는 파일 핸들 ② 함수 밖(전역/속성)에 무한 `append` 누적 ③ 캐시 dict가 해제 없이 키 증가.
- 후보를 LLM에 "진짜 누수인가?" 교차검증 → 확신 낮으면 제외(오탐↓).
- `PERF-003` **Minor**(명백한 심각 누수는 Major).

---

## 8. diff 교집합 필터 — `filter/diff_filter.py`

**문제**: 프로젝트 전체 검사 결과를 신입에게 다 고치라 하면 레거시까지 떠넘기는 셈. **신입이 바꾼 부분만** 지적해야 한다.

**해법 (Intersection + 함수 확장)**:
1. `parse_diff(diff_text)` → `{파일경로: 새 파일에서 추가/변경된 줄 번호 집합}`. (운영은 `unidiff` 권장, 최소 구현은 `@@ ... +start,count @@` 헌크 직접 파싱)
2. `filter_issues(issues, changed, repo_path)`:
   - `file == "(전체)"` 또는 `line is None` → **항상 유지** (커버리지 등 파일 무관 이슈).
   - `file`이 diff에 없음 → **drop** (신입이 안 건드린 파일).
   - `line`이 바뀐 줄 집합에 포함 → 유지.
   - 아니면 **바뀐 줄이 속한 함수 전체 범위(1-hop 확장)** 안에 있으면 유지.

> **범위 원칙**: **실행 범위 = 레포 전체**(커버리지엔 전체 코드 필요), **지적 범위 = 바뀐 함수 + 1단계 연관**.
> **검증 포인트**: diff 밖 파일(예: `old_utils.py`)에 심은 N+1은 이 필터가 반드시 제거해야 한다 (검증 층의 `must_NOT_appear` 항목).

---

## 9. 실행 샌드박스 — `prepare/`

**왜 필요한가**: diff만으론 커버리지를 못 잰다. "테스트를 실제로 실행해서 어느 줄이 돌았는지" 세야 하므로 **돌릴 수 있는 전체 코드 한 벌(소스+테스트+실행환경)** 이 필요하다.

### 9.1 `repo.py` — 코드 받아오기

`git clone --depth 1 <url>` 은 기본 브랜치 HEAD 1커밋만 받는다. PR의 `commit_sha`가 HEAD가 아닌 이전 커밋이면 `git checkout <sha>`가 실패한다. 따라서 아래 흐름을 따른다:

```bash
# 1. shallow clone (최신 HEAD만)
git clone --depth 1 <clone_url> <work_dir>

# 2. sha가 이미 포함됐는지 확인 → 없으면 추가로 fetch
git -C <work_dir> fetch --depth 1 origin <commit_sha>

# 3. 정확한 커밋으로 체크아웃 (detached HEAD)
git -C <work_dir> checkout <commit_sha>
```

- **확장**: 레포 캐시 후 다음 PR은 `fetch --depth 1 origin <sha>` + `checkout`로 델타만.

### 9.2 `sandbox.py` — 격리 실행
신뢰 못 하는 남의 코드를 내 머신에 직접 돌리지 않고 컨테이너에 격리.

```bash
docker run --rm \
  --network none \      # 인터넷 차단
  --memory 512m \       # 메모리 상한
  --cpus 1 \            # CPU 상한
  --read-only \         # 컨테이너 루트 파일시스템 읽기전용 (마운트 볼륨 /work는 쓰기 가능)
  -v {work}:/work -w /work \
  dev3-sandbox sh -c "python -m pytest --cov=src --cov-report=json tests/ -q"
# timeout {COV_TIMEOUT_S}s docker run ... — 무한루프 코드 방어
```

- **`--read-only` 주의**: 컨테이너의 오버레이 파일시스템(루트)만 읽기전용이 됨. `-v`로 마운트된 `/work`(= 호스트 `{work_dir}`)는 **쓰기 가능**하므로 pytest-cov가 `/work/coverage.json`을 정상 생성함.
- **타임아웃 구분**:
  - `COV_TIMEOUT_S = 15` : pytest 실행 제한 (Docker 컨테이너 `timeout` 래퍼)
  - `DOCKER_TIMEOUT_S = 120` : `requirements.txt` 기반 의존성 설치 전용 (`pip install` 1회) — pytest 실행과 별도 단계
- **속도 핵심**: 매번 pip install 하면 30초 초과. → **pytest/pytest-cov를 미리 깐 베이스 이미지(`Dockerfile.sandbox` → `dev3-sandbox`)** 를 빌드해두고, 실행 시엔 `--network none`으로 오프라인 격리.
- **한글 경로 회피 + 충돌 방지**: 작업 폴더를 매 실행 `tempfile.mkdtemp(prefix="dev3_sandbox_")/repo`로 고유 생성해 복사 후 마운트.
- **커버리지 회수는 stdout 경유 (Windows+Docker 핵심 워크어라운드)**: 컨테이너(root)가 bind-mount에 쓴 `coverage.json`을 호스트가 못 읽는 문제가 있어, 컨테이너에서 `coverage json -o /dev/stdout`으로 JSON을 **표준출력**에 내보내고 마커(`@@@DEV3COVJSON@@@`) 뒤를 `raw_decode`로 파싱한다. 그 dict를 **호스트가 직접** `work/coverage.json`에 기록(호스트 소유라 탐지기가 항상 읽음).
- **명령 정규화**: `pytest ...` → `python -m pytest ...`로 변환(컨테이너에서 cwd를 sys.path에 넣어 `import src` 가능). `--cov-report=json` 자동 보강.
- **의존성 2단계 자동판단 (구현됨, `_detect_install_cmd`)**:
  ```
  requirements.txt 있음        → pip install -q -r requirements.txt
  pyproject/setup.py/setup.cfg → pip install -q -e .
  아무것도 없음                → 설치 생략
  ```
  - 의존성 **없음** → `--network none` 완전 격리 (정석, 빠름).
  - 의존성 **있음** → 설치엔 네트워크가 필요하므로 `--network bridge`로 `(설치 && 테스트)`를 한 컨테이너에서 실행 (timeout=300s).
  - 명령어 fallback: 입력 `test_command` 우선 → 없으면 `pytest --cov=src --cov-report=json`.
  - **검증 완료**: 의존성 없는 fixture(20%) + 의존성 있는 실제 레포 `gruns/icecream`(93.1%) 둘 다 컨테이너 실측 성공.
- **팀 공유**: Dev2도 ESLint/Pylint 실행에 샌드박스가 필요 → 샌드박스는 Dev2와 공유하는 공용 부품으로 한 번만 구축.

---

## 10. 출력 조립 — `assemble/output.py`

```python
def assemble(task_id, scan_id, pr_id, agent, issues, metrics, execution_ms) -> AgentOutput:
    summary = SummaryCount()
    for i in issues:
        setattr(summary, i.severity.lower(), getattr(summary, i.severity.lower()) + 1)
    return AgentOutput(
        task_id=task_id, scan_id=scan_id, pr_id=pr_id,
        agent=agent, issues=issues,
        summary=summary, metrics=metrics, execution_ms=execution_ms,
    )
```
- `summary`는 `SummaryCount` 모델로 집계 — Pydantic이 키 위반을 자동 검출.
- `metrics`는 `test_verification`만 채우고 `performance`는 `None`.
- `scan_id`/`pr_id`는 Dev4가 DB join 및 GitHub 코멘트 등록에 사용.
- Pydantic 생성 시점에 `severity`/`agent` 등 Literal 위반이 자동 검출 → 계약 위반 JSON이 Dev4로 못 나간다.

---

## 11. 데이터 저장 — `persist.py`

### 11.1 공유 DB 스키마 (Dev2 + Dev3 합의 확정 DDL — Postgres/Supabase)

> **⚠️ 실제 GCP(tasklink) 스키마 기준 (2026-05-28 확인)**: 아래는 합의 DDL이며, 운영 DB의 실제 컬럼과 차이가 있다. 실제 기준으로 코딩할 것.
> - `scan_executions`: `developer_id text`가 아니라 **`user_id uuid NOT NULL` (FK → `users.user_id`)**.
> - `scan_issues.agent` CHECK: **이미 `test_verification`/`performance` 포함됨** (적용 완료).
> - `scan_issues.scan_id` → `scan_executions.id` FK 존재.
> - **`scan_summaries` 테이블은 아직 없음** → Dev3가 `CREATE TABLE IF NOT EXISTS`로 생성(아래 DDL, 단 FK는 실제 `scan_executions(id)`에 맞춤). 이것이 유일하게 남은 스키마 변경.

```sql
-- 1) scan_executions (PR 스캔 1건 = 1행) — Dev1이 생성. Dev3는 생성하지 않음
--    실제 GCP 컬럼: id, task_id(text), pr_id(text), user_id(uuid FK users), scanned_at, execution_ms
CREATE TABLE scan_executions (
    id           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    task_id      text NOT NULL,
    pr_id        text NOT NULL,
    user_id      uuid NOT NULL REFERENCES users(user_id),   -- 실제 스키마 (설계 초안의 developer_id 아님)
    scanned_at   timestamptz NOT NULL DEFAULT now(),
    execution_ms int
);

-- 2) scan_issues (개별 이슈 1건 = 1행) — Dev3가 INSERT
CREATE TABLE scan_issues (
    id             bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    scan_id        bigint NOT NULL REFERENCES scan_executions(id) ON DELETE CASCADE,
    agent          text NOT NULL                         -- 🟢 Dev3 추가값 포함
                   CHECK (agent IN ('static_analysis','security_scan',
                                    'test_verification','performance')),
    severity       text NOT NULL CHECK (severity IN ('Critical','Major','Minor')),
    rule_id        text NOT NULL,                        -- TEST-001, PERF-002 ...
    file           text,
    line           int,
    message        text,
    suggestion     text,
    similar_issues jsonb NOT NULL DEFAULT '[]'
);

-- 3) scan_summaries (스캔 1건의 agent별 집계) — Dev3가 UPSERT
CREATE TABLE scan_summaries (
    id        bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    scan_id   bigint NOT NULL REFERENCES scan_executions(id) ON DELETE CASCADE,
    agent     text NOT NULL
              CHECK (agent IN ('static_analysis','security_scan',
                               'test_verification','performance')),
    critical  int NOT NULL DEFAULT 0,
    major     int NOT NULL DEFAULT 0,
    minor     int NOT NULL DEFAULT 0,
    metrics   jsonb,                                     -- 🟢 Dev3 추가: 커버리지(NULL=측정안함)
    CONSTRAINT uq_scan_summaries_scan_agent UNIQUE (scan_id, agent)
);
```

**Dev2 원본 대비 Dev3가 추가한 변경 3가지 (확정)**:
1. `scan_issues.agent` CHECK에 `test_verification`, `performance` 추가. → **GCP 적용 완료.**
2. `scan_summaries.agent` CHECK에 동일 추가. → scan_summaries 생성 시 함께 반영.
3. `scan_summaries.metrics jsonb`(nullable) 신설. **NULL = 측정 안 함(성능/보안), 값 있음 = 커버리지 측정함.** → scan_summaries 생성 시 반영.

> scan_summaries는 Dev3 `persist.py`가 첫 실행 시 `CREATE TABLE IF NOT EXISTS`로 보장(없을 때만 생성). FK 대상은 실제 `scan_executions(id)`.

### 11.2 저장 로직 (UPSERT)

```python
def persist(scan_id: int, outputs: list[AgentOutput], inp=None):
    # (운영) scan_executions 행은 Dev1이 이미 생성 → Dev3는 자식 행만 추가
    for out in outputs:
        # 재실행 멱등성: 이 scan의 기존 이슈 비우고 다시 INSERT
        delete scan_issues where scan_id = :scan_id and agent = out.agent
        for iss in out.issues:
            insert into scan_issues(scan_id, agent, severity, rule_id, file, line, message, suggestion) ...
        # 집계 + 커버리지 UPSERT
        insert into scan_summaries(scan_id, agent, critical, major, minor, metrics)
        values (...)
        on conflict (scan_id, agent) do update set
          critical = excluded.critical, major = excluded.major,
          minor = excluded.minor, metrics = excluded.metrics
```

> **로컬 데모 대체**: 자격증명 없이 돌도록 동일 구조를 **SQLite**(`dev3_demo.db`)로 실증 가능. UPSERT/`ON CONFLICT` SQL은 Postgres와 동일하게 작성 → 운영 전환 시 커넥션만 교체.

**GCP 운영 경로 (`persist_pg`)**: `.env`의 `POSTGRES_URL`로 psycopg2 연결.
- `scan_summaries`가 없으면 `CREATE TABLE IF NOT EXISTS`로 1회 보장.
- `scan_executions` 행은 **생성하지 않음**(Dev1 책임) — 주어진 `scan_id`로 `scan_issues` INSERT + `scan_summaries` UPSERT만.
- 테스트 검증은 **트랜잭션 + 롤백**으로 수행(합성 user/execution을 만들어 쓰고 읽은 뒤 rollback → 실데이터·PII 오염 0).
- 시그니처: `persist_pg(scan_id, outputs, conn=None)` — `conn` 주입 시 커밋은 호출자가 제어(테스트 롤백 가능).

### 11.3 데이터 계약 — 읽기 ≠ 쓰기

| 구분 | 데이터 | 출처/대상 | 방식 |
|------|--------|-----------|------|
| **READ** | `skill_level`, `tech_stack` | `developers` → `Dev3Input.developer` | Dev1이 입력에 실어줌 (Dev3는 직접 SELECT 안 함) |
| READ(△) | `previous_pr_issues` | `mistake_patterns`/`pr_reviews` → `Dev3Input.context` | 후순위, MVP 보류 |
| **WRITE** | 개별 이슈 | `scan_issues` | INSERT |
| WRITE | 집계+커버리지 | `scan_summaries` | UPSERT(scan_id, agent) |
| WRITE | 실행 일지 | `agent_traces` | INSERT |

> Dev3는 `scan_executions`를 **생성하지 않는다** — Dev1이 PR당 1건 만들고 `scan_id`를 입력에 실어줌. Dev3는 그 ID로 자식 행만 추가. 장기 누적 패턴(`mistake_patterns`)은 **Dev5 소유**.

---

## 12. 트레이싱 — `tracing.py`

**역할 분담**: 깊은 추적(LLM 호출·토큰·트리)은 **LangSmith**가 자동 수집. Postgres `agent_traces`엔 **요약 1행만** (중복 저장 금지).

### 12.1 `agent_traces` — 실제 GCP 스키마에 맞춤 (ALTER 불필요)

**실제 GCP 컬럼** (2026-05-28 확인): `trace_id text NOT NULL`, `task_id uuid`(nullable), `agent_name text`, `doc_id uuid`(nullable), `status text`, `started_at`, `ended_at`, `execution_ms int`, `error_message text`, `created_at`, `input_summary text`, `output_summary text`.

> 설계 초안은 `scan_id` 컬럼 추가를 제안했으나, **공유 테이블 ALTER 없이** 기존 컬럼만으로 로깅한다(리스크 최소화). 구현: `tracing.log_trace_pg(conn, ...)`.
> - `task_id`는 **uuid 타입** → uuid 문자열이면 컬럼에 저장, **uuid가 아니면(`"demo-001"` 등) NULL**로 두고 `output_summary`에 원본 보존.
> - `scan_id`는 별도 컬럼이 없으므로 **`output_summary`에 `{"scan_id":42,"task_id":...,"dev3_status":...}` JSON 텍스트로 동봉**.
> - `doc_id`는 비워둠(Dev3는 PR 추적이라 NULL).
> - **status CHECK 주의 (실측)**: GCP `agent_traces.status`는 `running`/`success`/`fail`/`review`만 허용 → **Dev3의 `partial_fail`은 허용값이 아님.** 따라서 `partial_fail → 'success'`로 매핑하고, 원래 상태는 `error_message`(원인) + `output_summary.dev3_status`에 보존. `execution_ms`는 CHECK `>= 0`.

Dev3가 채우는 컬럼: `trace_id`, `task_id`, `agent_name`(test_verification/performance), `status`(success/partial_fail/fail), `started_at`, `ended_at`, `execution_ms`, `error_message`, `output_summary`(scan_id 등 요약).

- 매 실행마다 에이전트별 1행 기록. 부분 실패한 탐지기는 `error_message`에 남김.
- LangSmith는 `LANGCHAIN_API_KEY` 환경변수로 연동(키 없으면 Postgres 로깅만).

---

## 13. 검증 층 — `validation/eval.py`

PRD의 "커버리지 정확도 / false alarm 추적 에이전트"의 실체 = **정답 라벨(golden) + 비교 스크립트**.

```
정답 라벨(expected_output.json) vs 에이전트 실제 출력
  → (rule_id, file, line) 키로 매칭
  - true_positive : 정답∩출력
  - false_negative: 정답−출력 (놓친 것)
  - false_positive: 출력−정답 (오탐, false alarm)
  - banned 위반   : must_NOT_appear 파일이 출력에 등장 (예: diff 밖 파일)
  - recall          = TP / 정답수
  - false_alarm_rate= FP / 출력수
  - coverage 정확도 = 측정 metrics vs 정답 metrics
  - passed = (FN==0 and FP==0 and 위반==0)
```

- 코드 고칠 때마다 `py validation/eval.py` 한 줄로 회귀 검증.
- **`eval.py`는 반드시 `main.run(inp, repo_path=..., store=False)`로 호출** — `store=True`(기본값) 그대로 쓰면 테스트마다 DB에 더미 데이터가 쌓인다.
- 결과를 LangSmith 데이터셋/Eval에 기록 → 오탐률 임계(>10%) 초과 시 프롬프트/룰 개선 루프.

---

## 14. 자기검증·재시도·안전망 (3층)

> 전제: Dev3는 LangGraph(HITL·조건 분기)가 **아님**. `asyncio` 병렬 구조라 사람 개입 없이 **예산 시간 안에 스스로 교정**하는 3층 안전망을 둔다.

### Layer 1 — 탐지기 내부 자기교정
| 장치 | 동작 | 초기값(settings) |
|------|------|----------------|
| LLM 출력 재시도 | Pydantic 검증 실패 → 오류를 LLM에 다시 주고 재시도 | 최대 2회 |
| AST ↔ LLM 교차검증 | AST가 후보 탐지 → LLM에 "진짜?" 확인 → 부정 시 제외 | — |
| confidence 강등 | LLM 확신 낮으면 버리거나 Minor로 강등 | `< 0.7` |

### Layer 2 — 파이프라인 안전망
| 장치 | 동작 |
|------|------|
| `return_exceptions=True` | 한 탐지기 죽어도 나머지 생존 |
| 개별 타임아웃 | `asyncio.wait_for`로 탐지기별 제한 |
| 커버리지 fallback | deps 실패 → 재시도 → 그래도 실패면 "측정 불가" 정직 보고(숫자 조작 금지) |
| `partial_fail` 로깅 | 죽은 탐지기를 `agent_traces.error_message`에 기록 |

### Layer 3 — 사후 자기평가 (검증 에이전트의 실체)
| 장치 | 동작 | 초기값 |
|------|------|--------|
| 오탐률/정확도 측정 | 라벨 샘플로 채점 (LangSmith Eval) | — |
| 개선 루프 | 오탐률 임계 초과 시 프롬프트/룰 개선 | 오탐률 > 10% |

---

## 15. 타임아웃 / 부분 실패 전략

| 레벨 | 한계 | 처리 |
|------|------|------|
| 전체 에이전트 | 30초 (비기능 요구사항) | 초과 시 Dev1이 해당 에이전트 결과 제외 |
| 탐지기 개별 | 분배(예: coverage 15s, LLM 각 8s) | `asyncio.wait_for` |
| Docker 실행 | `timeout` + 컨테이너 강제 종료 | 무한 루프 코드 방어 |
| 예외 발생 | `return_exceptions=True` | 빈 결과 대체 + `partial_fail` 로깅 |

> PR 제출 → 코멘트 등록 전체 예산은 **60초**(4개 에이전트 병렬). 문서 파이프라인은 별개(30초).

---

## 16. severity 매핑 규칙 (요약)

```
커버리지 라인 < 80%      → Major   (TEST-001)
N+1 쿼리                 → Major   (PERF-002)
O(n²)                    → Minor / O(n³)↑ Major   (PERF-001)
엣지케이스 누락          → Minor   (TEST-003)
테스트 누락 함수         → Minor   (TEST-004)
메모리 누수 의심         → Minor / 명백·심각 → Major   (PERF-003)
```
> **Critical은 Dev3 영역에 거의 없음**(보안=Dev2). 단 명백한 무한루프/심각 누수는 Major로.

---

## 17. 설정 관리 — `config/settings.py`

**하드코딩 금지.** 임계값·타임아웃·모델명은 전부 여기서 관리하고 실측 후 조정한다.

```python
COVERAGE_THRESHOLD     = 0.80
COMPLEXITY_MINOR_DEPTH = 2           # depth 2 → Minor
COMPLEXITY_MAJOR_DEPTH = 3           # depth 3↑ → Major
DB_CALL_NAMES = {"query","execute","filter","get","all","first",
                 "fetchone","fetchall","scalar","count"}

# ── 타임아웃 (3단계 구분) ───────────────────────────
AGENT_TIMEOUT_S      = 30    # Dev3 전체 예산 (Dev1이 30초 초과 시 해당 에이전트 결과 제외)
COV_TIMEOUT_S        = 15    # pytest 실행 제한 (docker timeout 래퍼) — AGENT_TIMEOUT_S 이내
LLM_TIMEOUT_S        = 8     # LLM 호출 단건 제한 — gather 내 병렬이므로 직렬합산 아님
DOCKER_TIMEOUT_S     = 120   # requirements.txt pip install 전용 (pytest 실행과 별도 단계)
                              # pip install은 AGENT_TIMEOUT_S 예산에 미포함 (사전 준비 단계)

LLM_MODEL            = "gpt-4o-mini"   # 또는 claude-sonnet-4-6
LLM_MAX_RETRY        = 2
LLM_CONFIDENCE_MIN   = 0.7
FALSE_ALARM_THRESHOLD = 0.10
SANDBOX_IMAGE        = "dev3-sandbox"
```

---

## 18. 기술 스택 / 의존성

| 용도 | 라이브러리 |
|------|-----------|
| 데이터 계약 | `pydantic>=2` |
| 코드 구조 분석 | `ast` (내장) |
| diff 파싱 | `unidiff` (또는 최소 구현) |
| 커버리지 | `pytest`, `pytest-cov` |
| 격리 실행 | Docker |
| LLM | `langchain-openai` / `anthropic` / `google-generativeai` 중 택1 (구조화 출력) |
| DB | `psycopg`/`supabase`(운영) · `sqlite3`(로컬 데모) |
| 추적 | LangSmith (`langsmith`, `LANGCHAIN_*` env) |

`requirements.txt` 최소: `pydantic>=2`, `pytest`, `pytest-cov`, `unidiff`. (LLM/LangSmith는 키 있을 때 활성)

---

## 19. 구현 순서 (로드맵) — "데모 최소동작부터 수직으로"

탐지기를 가로로 다 만들고 마지막에 합치면 통합 리스크가 뒤로 몰린다. **N+1 하나를 입력→출력까지 세로로 관통**시켜 전체 모양을 먼저 검증하고, 나머지를 같은 틀에 끼운다.

```
1단계   사전 협의 + contracts.py
        - Dev1 합의: Dev3Input에 scan_id + repo 블록
        - Dev2 확인: scan_issues/scan_summaries 공유(agent 확장, metrics 컬럼), 샌드박스 공동구축
        - contracts.py 먼저 고정

1.5단계 🟢 수직 슬라이스 (오늘의 목표)
        fixture 1개 → nplus1.py → diff_filter → assemble → "N+1 이슈 JSON 출력"

2단계   정답지(fixtures) + 검증 뼈대
        - N+1 / O(n²) / 엣지누락 / 저커버리지 / 정상 코드 + 정답 라벨(JSON)
        - 가짜 coverage.json 포함(Docker 없이 missing_funcs 개발 가능하게)
        - validation/eval.py 뼈대

3단계   나머지 탐지기 (순수 로직, 인프라 없이)
        - complexity.py / memory_leak.py / missing_funcs.py / edge_cases.py
        - coverage.py "초기 버전(venv/subprocess)" (P0 당겨오기)

4단계   교집합 필터 + 조립
        - filter/diff_filter.py / assemble/output.py

5단계   인프라 hardening + 병렬 완성
        - prepare/repo.py (shallow clone) / prepare/sandbox.py (Docker 격리)
        - main.py asyncio.gather(return_exceptions=True) 6탐지기 병렬

6단계   저장 + 옵저버빌리티
        - persist.py (scan_issues INSERT + scan_summaries UPSERT)
        - tracing.py (LangSmith + agent_traces, partial_fail 포함)
```

**현실적 총 기간**: 데모 최소동작(N+1 + 커버리지 P0, Docker 없이 venv) **2~3일** / 풀세트(6탐지기 + Docker + 검증층 + LangSmith) **1~2주**. 시간을 잡아먹는 건 "쓰기"가 아니라 **"돌려보고 고치기"**(Docker 의존성·타임아웃, LLM 프롬프트 튜닝).

---

## 20. 테스트 fixtures 명세 — `tests/fixtures/`

검증 층이 채점할 "과녁". 의도적으로 결함을 심은 샘플 + 정답 라벨.

### 20.1 샘플 PR 코드 (`sample_repo/src/posts.py`)
```python
def get_posts(post_ids):          # 테스트 없음 → TEST-004
    posts = []
    for pid in post_ids:
        post = db.query(f"SELECT * FROM posts WHERE id={pid}")  # N+1 → PERF-002
        posts.append(post)
    return posts

def calc_discount(price, rate):   # 유일하게 테스트됨
    return price * (1 - rate)

def find_dups(items):             # 이중 루프 O(n²) → PERF-001, 테스트 없음 → TEST-004
    result = []
    for i in items:
        for j in items:
            if i == j: result.append(i)
    return result
```
- `sample_repo/tests/test_posts.py` — `calc_discount`만 테스트 (저커버리지 유도, 아래 참고).
- `sample_repo/src/old_utils.py` — diff에 없는 레거시 N+1(필터가 제거하는지 검증).
- `sample_pr.diff` — `posts.py`만 추가하는 unified diff.
- `coverage.json` — Docker 전 단계용 (실측으로 대체 가능, `coverage_line=0.20` 맞춰 작성).

**`tests/test_posts.py` 내용 (coverage 20% 유도 — get_posts·find_dups 미테스트)**:
```python
from src.posts import calc_discount

def test_discount_basic():
    assert calc_discount(100, 0.1) == 90.0

def test_discount_zero():
    assert calc_discount(0, 0.5) == 0.0
```
→ `calc_discount` 1함수(2줄)만 실행. 전체 22줄 중 약 4줄 = 라인 커버리지 약 18~20%.

### 20.2 정답 라벨 (`expected_output.json`)
```json
{
  "test_verification": {
    "expected_issues": [
      {"rule_id": "TEST-004", "file": "src/posts.py", "line": 4},
      {"rule_id": "TEST-004", "file": "src/posts.py", "line": 16},
      {"rule_id": "TEST-001", "file": "(전체)"}
    ],
    "expected_metrics": {"coverage_line": 0.20}
  },
  "performance": {
    "expected_issues": [
      {"rule_id": "PERF-002", "file": "src/posts.py", "line": 7},
      {"rule_id": "PERF-001", "file": "src/posts.py", "line": 16}
    ]
  },
  "must_NOT_appear": [
    {"file": "src/old_utils.py", "reason": "diff 밖 레거시 → 교집합 필터가 제거해야 함"}
  ]
}
```
- 정상(결함 없는) 코드 샘플도 1개 둬서 **오탐 0** 검증.

---

## 21. 인접 팀과의 합의 사항 (체크리스트)

| 대상 | 항목 | 상태 |
|------|------|------|
| Dev1 | `Dev3Input`에 `scan_id` 추가 (scan_executions 행 생성 후 발급) | 합의 완료 |
| Dev1 | `repo` 블록(`clone_url`/`commit_sha`/`language`/`test_command`) 추가 | 합의 완료 |
| Dev1 | `developer`, `context.previous_pr_issues`를 DB에서 채워 전달 | Dev1 담당 |
| Dev2 | `scan_issues.agent`/`scan_summaries.agent` CHECK 확장 | 합의 완료 |
| Dev2 | `scan_summaries.metrics jsonb` 신설 | 합의 완료 |
| Dev2 | 실행 샌드박스(Docker) 공동 구축 | 논의 |
| 팀 | `agent_traces`에 `task_id`/`scan_id` 추가 + `doc_id` nullable | 합의 필요 |
| Dev4 | `scan_id` 하나로 4개 에이전트 결과 취합 | 합의 완료 |

---

## 22. 비기능 요구사항 (Dev3 관련)

| 항목 | 요구사항 |
|------|----------|
| 응답 시간 | PR → 코멘트 60초 이내(4개 병렬). Dev3 단독 30초 예산 |
| 추적성 | 모든 실행에 `trace_id` 부여 + LangSmith/`agent_traces` 로깅 |
| 안전성 | 남의 코드는 Docker 격리(`--network none`, 메모리·CPU 상한, 타임아웃) |
| 정직성 | 측정 불가 시 숫자 지어내지 않고 "측정 불가" 보고(환각 방지) |
| 테스트 | 각 탐지기 단위 테스트 + 검증층 E2E(`eval.py`) 필수 |
| 확장성 | 탐지기 = `detect()` 시그니처 통일 → 추가/교체 용이 |

---

## 23. 실행 방법 (요약)

```powershell
cd backend\dev3
py main.py                      # 입력→탐지→필터→조립→출력 (demo_output.json)
py validation\eval.py           # 정답 라벨과 비교 채점 (recall / false_alarm_rate / PASS)
py persist.py                   # DB 저장 + readback (로컬 SQLite)
py tracing.py                   # agent_traces 로깅 + readback

# Docker 샌드박스(실측 커버리지)
docker build -t dev3-sandbox -f prepare\Dockerfile.sandbox .
py prepare\sandbox.py
```
LLM 탐지기(edge_cases/complexity/memory_leak 확정)는 `OPENAI_API_KEY`(또는 `ANTHROPIC_API_KEY`/`GOOGLE_API_KEY`) 설정 시 자동 활성. LangSmith는 `LANGCHAIN_API_KEY`.

---

## 24. 입력 범위 결정 — 커버리지를 위해 코드를 어디까지 받나 (논제 확정)

**문제**: diff만으론 커버리지를 못 잰다(import·정의·테스트 파일이 없어 실행 불가). 어디까지 받나?

**원칙 — 범위 2단 분리**:
- **실행 범위 = 레포 전체**(소스+테스트+실행환경). 커버리지는 "테스트를 실제 실행해 어느 줄이 돌았나"라 전체가 필요.
- **지적 범위 = 바뀐 함수 + 1-hop**(diff 교집합 필터). 레거시는 안 건드림.

**받는 방법 (확정)**:
| 방식 | 받는 것 | Dev3 동작 | MVP |
|---|---|---|---|
| **A. shallow clone (확정/기본)** | `repo{clone_url, commit_sha, test_command}` | clone→checkout(sha)→Docker `pytest --cov` | ⭕ |
| B. CI 결과 위임 (fallback) | Dev1/CI가 `coverage.json` 전달 | **shallow clone 수행**(Docker pytest 생략) + coverage.json 파싱 | △ |

> **B안 주의**: coverage.json만 받더라도 성능 분석(AST)이 소스를 직접 읽어야 하므로 **shallow clone은 B안에서도 수행**한다. 생략되는 건 Docker 안에서 pytest를 돌리는 단계뿐이다.

→ 입력 `repo` 블록 필수. `commit_sha`로 PR 시점 정확 체크아웃. 두 방식 모두 산출 인터페이스는 `(cov_issues, metrics)` 동일.
→ **성능 분석(N+1·복잡도·누수)은 실행 불필요** — clone한 소스를 AST로 정적 분석만. 즉 **clone은 "커버리지 때문에" 필요**하고, 성능은 같은 소스를 재활용(부산물).

---

## 25. Dev4 출력 ↔ GCP DB 컬럼 매핑 + 추가 출력

DB = **GCP Cloud SQL (PostgreSQL)**. Dev3 JSON이 어떤 컬럼으로 쌓이는지 + persist 시점에 추가되는 필드.

### 25.1 `issues[]` → `scan_issues` (이슈 1개 = 1행)
| AgentOutput.issues[] | scan_issues 컬럼 | 비고 |
|---|---|---|
| — | `id` | DB auto (GENERATED) |
| (입력 scan_id) | `scan_id` | Dev1이 준 값을 persist가 주입 |
| agent | `agent` | test_verification / performance |
| severity | `severity` | |
| rule_id | `rule_id` | |
| file | `file` | |
| line | `line` | |
| message | `message` | |
| suggestion | `suggestion` | |
| — | `similar_issues` | 기본 `'[]'` INSERT, Dev5가 패턴 집계 후 UPDATE — 같은 scan 내 동일 rule_id 사전 집계는 Dev5 확장 시점에 결정 |

### 25.2 `summary`+`metrics` → `scan_summaries` (scan×agent = 1행, UPSERT)
| AgentOutput | scan_summaries 컬럼 |
|---|---|
| summary.critical/major/minor | `critical`/`major`/`minor` |
| metrics | `metrics`(jsonb), 성능=NULL |
| (입력 scan_id, agent) | `scan_id`, `agent` (UNIQUE) |

### 25.3 persist 시점에 "추가로 생성"되는 출력 (JSON엔 없지만 DB/트레이스에 쌓임)
- `scan_executions`: PR당 1행(**Dev1 생성·소유**). `scanned_at`=now()는 행 생성 시 자동. `execution_ms`(전체 스캔 소요시간)는 Dev1이 4개 에이전트 완료 후 UPDATE — **Dev3는 이 컬럼을 건드리지 않는다.**
- `scan_issues.id` / `similar_issues`.
- `agent_traces` 1행: trace_id·status·started/ended_at·execution_ms (§26) — Dev3 에이전트별 소요시간은 여기에 기록.
- LangSmith: 토큰·지연·LLM 호출 트리 (자동).

→ **Dev4가 직접 받는 건 JSON 2개**지만, **DB엔 더 풍부하게**(실행시간·집계·trace·similar) 쌓인다. Dev4는 `scan_id`로 join해 4개 에이전트 결과를 한 번에 읽음.

---

## 26. LangSmith 하네스 — `harness.py` / `tracing.py`

**역할 분담**: LangSmith = 깊은 추적(LLM 호출·토큰·트리) + Eval 데이터셋 / `agent_traces`(Postgres) = 요약 1행. **중복 저장 금지.**

### 26.0 run 계층 구조 (설계 원칙)

LangSmith UI에서 PR 1건 분석이 하나의 트리로 보여야 한다. `main.run()`을 `chain` 타입 parent run으로, 각 탐지기를 child run으로 묶는다. 키 없으면 전체 no-op이며 동작에는 영향 없다.

```
main.run()  [chain, metadata: task_id·scan_id·pr_id]
├── coverage.measure()        [tool]
├── nplus1.detect()           [tool]
├── complexity.detect()       [tool]
│   └── _llm_call()           [llm]   ← AST 의심 → LLM 확정 (opt-in)
├── missing_funcs.detect()    [tool]
├── edge_cases.detect()       [tool]  (opt-in)
│   └── _llm_call()           [llm]
└── memory_leak.detect()      [tool]  (opt-in)
    └── _llm_call()           [llm]
```

### 26.1 `harness.py` — 계측 + 평가 진입점

**설계 원칙**: 데코레이터는 모듈 import 시점에 적용된다. `task_id`/`scan_id` 같은 런타임 값을 `@instrument(task_id=inp.task_id)` 형태로 전달하는 건 불가능 (`inp`가 없음). 대신 `main.run()` 진입점에서 **parent run context**를 열고, 자식 탐지기 run이 이를 자동 상속하는 방식을 사용한다.

```python
import os
from langsmith import traceable

def instrument(name: str, run_type: str = "tool"):
    """탐지기/LLM 호출을 LangSmith run으로 감싼다. 키 없으면 원본 함수 그대로.
    task_id·scan_id·pr_id는 main.run()의 parent run context에서 자동 상속됨.
    (데코레이터는 definition time 적용 → runtime 값 직접 주입 불가)
    """
    def deco(fn):
        if not os.getenv("LANGCHAIN_API_KEY"):
            return fn
        return traceable(name=name, run_type=run_type)(fn)
    return deco

# 사용 예 (탐지기 — definition time에 붙임):
#   @instrument("nplus1")
#   def detect(repo_path, changed): ...
#
# 사용 예 (LLM 내부 호출):
#   @instrument("complexity_llm", "llm")
#   def _llm_call(source): ...
#
# main.run() 진입점 — parent context로 감싸면 모든 자식 run이 자동 연결됨:
#   import langsmith
#   with langsmith.trace("dev3_analysis", run_type="chain",
#                        metadata={"task_id": inp.task_id,
#                                  "scan_id": inp.scan_id,
#                                  "pr_id":   inp.pr_id}):
#       ...  # 이 블록 안의 @instrument 탐지기가 child run으로 자동 묶임
```

**`_safe` 와 partial_fail**: `_safe`가 예외를 잡아 `[]` 반환하면 LangSmith run이 성공처럼 보인다. `_safe` 내에서 현재 run tree에 `partial_fail` 태그를 달아 실패를 명시한다. 키 없으면 기존 `print`만.

### 26.2 Eval 구조 (`validation/eval.py` ↔ LangSmith)

```
fixtures/expected_output.json          ← 정답 라벨 (input + expected)
        │
LangSmith 데이터셋 "dev3-golden"      ← 업로드 (최초 1회 or fixtures 변경 시)
        │
evaluate(target=main.run, data="dev3-golden", evaluators=[...])
  ├── recall_evaluator         : TP / 정답수
  ├── false_alarm_evaluator    : FP / 출력수 → 0.10 초과 경고
  ├── coverage_error_evaluator : |측정값 − 정답값| ≤ 0.01
  └── banned_file_evaluator    : must_NOT_appear 위반 = 즉시 fail
```

- 결과는 LangSmith UI "Experiments" 탭에 자동 기록.
- `py validation/eval.py --upload-dataset` : fixtures → LangSmith 데이터셋 업로드.
- `py validation/eval.py` : 로컬 채점만 (키 없어도 동작, 키 있으면 결과 업로드).
- **커버리지 정확도 / 성능 false alarm 평가**: `settings.FALSE_ALARM_THRESHOLD`(0.10) 초과 시 프롬프트/룰 개선 루프.

### 26.3 `tracing.py` — 요약 1행 (구현됨)
- agent별 1행: trace_id·agent_name·task_id·scan_id·status(success/partial_fail/fail)·started/ended_at·execution_ms·error_message.
- LangSmith와 **중복 저장 금지**: Postgres에는 집계 1행만, 토큰/LLM 트리는 LangSmith 전담.

### 26.4 env
```
LANGCHAIN_API_KEY=...        # 있으면 LangSmith 추적+Eval, 없으면 tracing.py(Postgres)만
LANGCHAIN_PROJECT=dev3
```

---

*Dev3 통합 설계서 끝. 이 문서 + `contracts.py`만 있으면 어느 모듈부터든 독립 구현 가능하다.*
```
