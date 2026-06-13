# 실행 런북 — Dev2(M2) 정적분석·보안 스캔 on `m2_mixed_case`

> 대상 데이터: `pj3_data/datasets/JH_PJ3/m2_mixed_case/` (12 케이스)
> 대상 기능: `sub2_new/dev2/` (M2 파이프라인)
> 최종 검증: 2026-06-07 (sqli_case E2E Cloud SQL 적재 확인)

---

## 0. 한눈에 — 가장 빠른 실행

```powershell
# 1) 저장소 루트가 아니라 sub2_new 에서 실행해야 한다 (import 경로 기준)
cd C:\Users\USER\Documents\GitHub\Task-Link\sub2_new

# 2) 전역 python(C:\Python314)으로 m2_mixed_case 전체 일괄 실행
python run_all.py > result_all.txt 2>&1

# 3) 결과 로그 확인
notepad result_all.txt
```

- **Docker 불필요.** 로컬 전역 python 한 줄이면 된다 (아래 §1 이유).
- `run_all.py`의 `CASES_ROOT`가 `m2_mixed_case`로 고정돼 있어 **이 데이터셋 전체(12개)** 를 자동으로 돈다.
- 단일 케이스만 보려면: `python run_case.py ..\pj3_data\datasets\JH_PJ3\m2_mixed_case\sqli_case`

---

## 1. 환경 선택 — venv? Docker? (결론: 로컬 전역 python)

| 방식 | 쓰나? | 이유 |
|------|-------|------|
| **로컬 전역 python `C:\Python314`** | ✅ **권장** | asyncpg·sentence_transformers·anthropic·langgraph·bandit 전부 설치돼 있고 검증됨 |
| 로컬 venv `dev2/test3`·`test311` | ❌ 금지 | `sentence_transformers` 미설치 → bge-m3 임베딩이 mock으로 fallback(RAG 무의미) |
| Docker (`dev2/docker-compose.yml`) | 선택 | 비-Python 언어 보안(semgrep)·다중 서비스 통합 때만. 이 작업엔 불필요 |

### 1-1. 전역 python인지 먼저 확인 (필수)
```powershell
python -c "import sys; print(sys.executable)"
# 기대: C:\Python314\python.exe  (가 아니면 아래로 명시 호출)
# C:\Python314\python.exe run_all.py > result_all.txt 2>&1
```

### 1-2. 의존성 점검 (한 번만)
```powershell
python -c "import asyncpg, sentence_transformers, anthropic, langgraph, bandit, langchain_anthropic; print('deps OK')"
# 누락 시: python -m pip install -r dev2\requirements.txt
```

### 1-3. `.env` 점검 (가장 흔한 사고 지점)
`sub2_new/dev2/.env` 에 아래가 **반드시** 있어야 한다 (run_all/run_case가 이 파일을 로드):
```env
USE_MOCK_LLM=false
DATABASE_URL=postgresql+asyncpg://postgres:...@34.22.101.111:5432/tasklink   # store 적재(asyncpg)
POSTGRES_URL=postgresql://postgres:...@34.22.101.111:5432/tasklink           # pgVector 검색·조회
ANTHROPIC_API_KEY=sk-ant-...                                                 # llm_judge
LANGCHAIN_TRACING_V2=true / LANGCHAIN_API_KEY=lsv2_... / LANGCHAIN_PROJECT=dev2-wooya  # LangSmith(선택)
```
> ⚠️ 상위(루트) `.env`로 이 파일을 덮어쓰지 말 것 — `DATABASE_URL`이 사라지고 `USE_MOCK_LLM=true`가 되어 store가 깨진다.

### 1-4. (선택) Docker로 돌릴 때
semgrep(비-Python 언어 보안 룰셋)까지 필요하거나 전체 스택 통합 시에만:
```powershell
cd C:\Users\USER\Documents\GitHub\Task-Link\sub2_new\dev2
docker compose up --build
```
> Windows 로컬 실행에선 semgrep이 자동 skip되고 Python 보안은 **bandit**이 담당한다(정상). Docker(Linux)에선 semgrep OWASP 룰셋이 추가로 작동한다.

### 1-5. 다른 컴퓨터에서 처음 실행할 때

전역 `C:\Python314` 환경이 없는 신규 머신에서는 아래 순서로 세팅한다.

```powershell
# Step 1. Python 3.11+ 설치 확인
python --version

# Step 2. 의존성 설치 (venv 또는 전역 — sentence_transformers 포함 필수)
pip install -r sub2_new\dev2\requirements.txt

# Step 3. .env 파일 생성 (sub2_new/dev2/.env)
USE_MOCK_LLM=false
DATABASE_URL=postgresql+asyncpg://postgres:<비밀번호>@34.22.101.111:5432/tasklink
POSTGRES_URL=postgresql://postgres:<비밀번호>@34.22.101.111:5432/tasklink
ANTHROPIC_API_KEY=sk-ant-...
LANGCHAIN_TRACING_V2=true
LANGCHAIN_API_KEY=lsv2_...
LANGCHAIN_PROJECT=dev2-<본인GitHub_ID>
```

> ⚠️ **bge-m3 모델 (4.56 GB)** — 첫 실행 시 HuggingFace에서 자동 다운로드된다.
> 시간이 오래 걸리면 기존 머신의 캐시 폴더를 복사해도 된다.
> - Windows: `C:\Users\<계정>\.cache\huggingface\`

**파이프라인 구조만 빠르게 확인하고 싶을 때** (API 키·모델 없이):
```env
USE_MOCK_LLM=true   # bge-m3·Anthropic 호출 없이 동작, severity·RAG는 mock
```

---

## 2. 무엇이 실행되나 — 워크플로우 단계별 실행 파일

진입점: `run_all.py` → 각 케이스마다 `run_dev2(state)` 호출 → LangGraph 파이프라인 1 실행.
그래프 정의: **`sub2_new/dev2/graph.py`** (`build_graph()`).

```
[케이스 로드]  run_all.py / run_case.py
     │  vulnerable.py + expected_issue.json → Dev2State(pr_diff=unified diff)
     ▼
[1] tool_router_agent ─ PR 맥락 보고 돌릴 도구 선택
     │  파일: dev2/nodes/tool_router_agent.py  (+ dev2/tools/router.py 언어/도구 매핑)
     ▼
[2] run_tools ─ 선택된 CLI 도구 병렬 실행 (정적+보안 raw 이슈)
     │  파일: dev2/nodes/run_tools.py
     │   └ Python:  dev2/tools/python/pylint_tool.py   (정적)
     │             dev2/tools/python/radon_tool.py    (복잡도)
     │             dev2/tools/python/bandit_tool.py   (보안)
     │             dev2/tools/common/semgrep_tool.py  (보안, Windows는 skip)
     │   └ (타 언어: eslint/npm_audit/roslyn/htmlhint/stylelint_tool.py)
     ▼
[3] vector_search ─ RAG Retrieve: 이슈를 bge-m3로 임베딩 → pgVector 유사 과거이슈 주입
     │  파일: dev2/nodes/vector_search.py  (sentence_transformers bge-m3 + chunk_embeddings, POSTGRES_URL)
     ▼
[4] llm_judge ─ RAG Generate: LLM severity 재판단 + M4 개념 매핑
     │  파일: dev2/nodes/llm_judge.py
     │   ├ 프롬프트:  dev2/prompts/severity_judge.py
     │   ├ LLM:       claude-sonnet-4-6(Critical)/haiku(Major), Minor는 생략
     │   └ 개념매핑:  dev2/nodes/concept_mapper.py  (keyword/concept_id/code_snippet/name_of_function 등)
     ▼
[5] action_decider_agent ─ 후속 액션 추천(early_escalation / store_only ...)
     │  파일: dev2/nodes/action_decider_agent.py
     ▼
[6] (조건부) route_after_action_decider  → graph.py 내 분기 함수
     │   ├ early_escalation → escalate (dev2/nodes/escalate.py) → store
     │   └ 그 외            → store
     ▼
[7] store ─ Cloud SQL 적재 (+ 선택적 BigQuery)
        파일: dev2/nodes/store.py
          └ Repository: dev2/repositories/scan_repository.py
              └ SQL:    dev2/db.py  (DATABASE_URL, asyncpg/SQLAlchemy)
          적재 테이블: scan_executions → scan_issues → scan_summaries
          반환: final_output = [AgentOutput dict, ...]  (Dev4/M4 입력 계약)
```

### (선택) 파이프라인 2 — 코멘트 생성
`run_all.py`는 첫 성공 케이스로 파이프라인 2도 1회 돌린다. 진입점 `run_aggregate(payload)`,
그래프: **`dev2/aggregate_graph.py`**.
```
aggregate (dev2/nodes/aggregate.py)
  → comment 정제 (dev2/nodes/comment_refine.py + dev2/prompts/comment_refine.py)
  → github 코멘트 (dev2/nodes/github_comment.py, GITHUB_TOKEN 없으면 미등록)
  → slack 알림   (dev2/nodes/slack_notify.py, Critical 시)
```

---

## 3. 실행 명령 — 시나리오별

### A. m2_mixed_case 전체 (권장)
```powershell
cd C:\Users\USER\Documents\GitHub\Task-Link\sub2_new
python run_all.py > result_all.txt 2>&1
notepad result_all.txt
```
출력: 케이스별 탐지 이슈 + `[요약]` 탐지율 테이블 + 파이프라인 2 결과.

### B. 단일 케이스 (빠른 확인/디버그)
```powershell
cd C:\Users\USER\Documents\GitHub\Task-Link\sub2_new
python run_case.py ..\pj3_data\datasets\JH_PJ3\m2_mixed_case\sqli_case
# 다른 케이스: command_injection_case / path_traversal_case / hardcoded_secret_case / mixed_case_01 ...
```

---

## 4. 적재 결과 확인 (Cloud SQL 조회)

```powershell
cd C:\Users\USER\Documents\GitHub\Task-Link\sub2_new
python -c "import asyncio,os,pathlib; from dotenv import load_dotenv; load_dotenv(pathlib.Path('dev2/.env')); import asyncpg; U=os.getenv('POSTGRES_URL','').replace('postgresql+asyncpg://','postgresql://');
async def m():
 c=await asyncpg.connect(U)
 r=await c.fetch('''SELECT se.pr_id, si.agent, si.severity, si.rule_id, si.keyword
   FROM scan_executions se JOIN scan_issues si ON si.scan_id=se.id
   ORDER BY se.id DESC LIMIT 20'''); [print(dict(x)) for x in r]; await c.close()
asyncio.run(m())"
```
- 한 케이스 실행 시 에이전트별로 `scan_executions` 행이 생기고(static_analysis/security_scan), 이슈는 `scan_issues`에 적재된다.
- 채워지는 핵심 컬럼: `severity, rule_id, keyword, concept_id, mistake_type_concept_id, name_of_function, code_snippet` (M4가 소비).

---

## 5. 트러블슈팅

| 증상 | 원인 | 해결 |
|------|------|------|
| `bge-m3 임베딩 실패 → Mock fallback` 로그 | venv로 실행(sentence_transformers 없음) | 전역 `C:\Python314\python.exe`로 실행 |
| store 단계 연결 실패 / localhost 접속 | `.env`에 `DATABASE_URL` 없음(루트 .env로 덮어씀) | `dev2/.env`에 asyncpg `DATABASE_URL` 복구 |
| `llm_judge` 결과가 전부 원본 severity | `USE_MOCK_LLM=true` 또는 `ANTHROPIC_API_KEY` 없음 | `.env`에 `USE_MOCK_LLM=false` + 키 설정 |
| `semgrep [WinError 2]` | Windows 미지원(정상) | 무시 — 현재는 graceful skip(debug 로그)으로 처리됨. bandit이 Python 보안 담당 |
| `developers`/FK 관련 오류 | seed 미존재 | `developers`에 `junior_dev_01`(id `00000000-…-001`) seed 필요 |
| LangSmith에 trace 안 뜸 | `LANGCHAIN_*` 미설정 | `.env`에 `LANGCHAIN_TRACING_V2=true`/`LANGCHAIN_API_KEY`/`LANGCHAIN_PROJECT=dev2-wooya` |

---

## 6. 비용 주의
`USE_MOCK_LLM=false`는 **케이스·이슈마다 실제 Anthropic 호출(과금)**. 12케이스 일괄 실행 시 다수 호출이 발생한다.
적재 경로만 빠르게 점검하려면 일시적으로 `USE_MOCK_LLM=true`로 두면 LLM/임베딩 없이 파이프라인 구조만 돈다(단, severity·RAG는 mock).
