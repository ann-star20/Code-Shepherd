# MODULE_CONTRACT.md — Module 2 (정적 분석 + 보안 분석) 실제 구현 계약

**버전**: v1.0 (as-built) | **작성일**: 2026-06-11
**기준 소스**: `backend/m2/app/main.py`, `backend/m2/app/analyzer.py`, `backend/_shared/shared/contracts.py`

> 이 문서는 **현재 운영 중인 m2 스텁(`backend/m2/app/`)의 실제 입출력 계약**이다.
> 루트 [`docs/MODULE_CONTRACT.md`](../../docs/MODULE_CONTRACT.md) §Module 2는
> PlatformState/LangGraph/AgentResult 기반의 **이상적 설계안**으로, 아래 실제 구현과 다르다.
> 차이는 본 문서 끝 「설계안과의 차이」 절에 정리한다. **통합 시 기준은 본 문서다.**

---

## 모듈 개요

```yaml
module_id:    module_2_static_security
module_name:  정적 분석 + 보안 분석
service:      m2-analysis (FastAPI)
port:         8003
responsibility: >
  m1(오케스트레이터)이 전달한 PR unified diff를 받아
  정적 분석(pylint / radon / eslint)과
  보안 스캔(bandit / semgrep — OWASP Top 10)을 수행하고
  IssueItem 목록 + 심각도 요약을 반환한다.
  코멘트 생성·DB 저장·LLM·RAG는 현재 app/ 스텁에 없다(분석부 전용).

orchestration: >
  m1이 단일 오케스트레이터. PR 트리거 시 m1이 diff_url을 1회 fetch하여
  pr_diff에 담아 /analyze/static → /analyze/security 순서로 직렬(await) 호출한다.
  (병렬 아님. 클라이언트 httpx async, timeout 60초.)
  두 응답을 m1이 M3ReviewRequest로 묶어 m3 /review로 전달 → 집계·저장.

uses_db:        false   # app/ 스텁은 DB 미연결
uses_llm:       false   # LLM/RAG 없음 (도구 기반 결정적 분석)
uses_kms:       false   # context 필드는 받지만 현재 분석에 미사용
uses_langsmith: false   # app/ 스텁 미적용
```

---

## 엔드포인트

| Method | Path                | 설명                                  |
|--------|---------------------|---------------------------------------|
| GET    | `/health`           | 헬스체크 → `{"status":"ok","service":"m2-analysis"}` |
| POST   | `/analyze/static`   | 정적 분석 (pylint / radon / eslint)   |
| POST   | `/analyze/security` | 보안 스캔 (bandit / semgrep)          |

두 POST 엔드포인트는 **요청/응답 스키마가 동일**하며, 응답 `agent` 필드 값만 다르다.

---

## 입력 — `M2AnalyzeRequest`

```yaml
M2AnalyzeRequest:
  task_id:   str              # 필수 — 트리거 단위 추적 키
  pr_id:     str              # 필수 — PR 번호 (문자열)
  pr_diff:   str              # 필수 — unified diff 본문 (m1이 diff_url fetch한 결과)
  context:   AnalysisContext  # 선택 — 기본 빈 객체 (현재 분석에 미사용)
  developer: DeveloperProfile | null   # 선택 — (현재 분석에 미사용)
  trace_id:  str | null       # 선택

AnalysisContext:
  architecture_docs:  list[str]   # 기본 []
  coding_conventions: str         # 기본 ""
  previous_pr_issues: list[str]   # 기본 []

DeveloperProfile:
  id:          str
  skill_level: "junior | mid | senior"   # 기본 "junior"
  tech_stack:  list[str]                 # 기본 []
```

> **현재 동작 주의**: `app/analyzer.py`는 `pr_diff`만 사용한다.
> `context`(아키텍처 문서·컨벤션·과거 이슈)와 `developer`(숙련도·스택)는
> 요청으로 받기만 하고 무시한다(`main.py`는 `analyze(payload.pr_diff, agent)`만 호출).
> RAG/숙련도 기반 피드백을 넣으려면 `analyzer.py` 수정이 필요하다.

### required_state_fields

```yaml
- task_id
- pr_id
- pr_diff
```

`pr_diff`가 비었거나 지원 확장자 파일이 없으면 빈 결과를 반환한다(오류 아님).

---

## 출력 — `AgentResult` (M2AnalyzeResponse 상위집합)

엔드포인트는 `app/contract.py`의 **`AgentResult`** 를 반환한다.
이는 기존 `M2AnalyzeResponse`(task_id/agent/issues/summary/execution_ms)의 **상위집합**으로,
MODULE_CONTRACT가 요구하는 계약 필드(agent_name·module_id·status·validation_result·
sub_trace_id·error_message·next_agent)를 추가로 담는다.

> **하위호환**: m1은 `M2AnalyzeResponse(**resp.json())`로 역직렬화하며
> Pydantic v2 기본값(`extra="ignore"`)이 추가 계약 필드를 무시한다.
> 따라서 본 응답을 도입해도 m1/m3 호출 경로는 깨지지 않는다.
> 다운스트림(m3 `M3ReviewRequest`)에는 M2AnalyzeResponse 부분집합만 흘러간다.

```yaml
AgentResult:
  # ── M2AnalyzeResponse 호환 필드 (하위호환) ──
  task_id:           str                              # 요청 task_id echo
  agent:             "static_analysis | security_scan"  # 엔드포인트별 고정
  issues:            list[IssueItem]                  # 기본 []
  summary:           IssueSummary                     # 심각도별 카운트
  execution_ms:      int                              # 분석 소요 시간(ms), 항상 >= 1
  # ── MODULE_CONTRACT 추가 계약 필드 ──
  trace_id:          str | null                       # 요청 trace_id passthrough
  sub_trace_id:      str                              # pr_{12hex}_{agent}_{4hex}
  agent_name:        "StaticAnalysisAgent | SecurityScanAgent"
  module_id:         "module_2"                       # 고정
  status:            "success | fail | hitl_pending"
  validation_result: "pass | fail | skip"
  error_message:     str | null                       # 실패 시 사유, 성공 시 null
  next_agent:        null                             # m2는 종단 — 항상 null

IssueItem:
  severity:   "Critical | Major | Minor"
  line:       int | null
  file:       str | null     # 임시 작업 디렉토리 기준 상대경로로 정규화됨
  message:    str
  rule_id:    str | null     # 접두사로 도구 구분 (아래 표)
  suggestion: str | null

IssueSummary:
  critical: int   # 기본 0
  major:    int
  minor:    int
```

> 현재 응답에는 **도구 실행/스킵 상태(`tools`)와 단계별 trace(`stages`)가 없다.**
> 프론트(`SecurityPage` / `M2PipelineFlow`)는 해당 필드가 없으면 자동 숨김/폴백한다.
> 실데이터를 원하면 `shared/contracts.py`(M2 응답) + m3 persist 스키마 + `/review` 수정 필요(크로스 모듈).

---

## rule_id 접두사 → 도구 매핑

| 접두사    | 도구                | agent             | 대상 언어        |
|-----------|---------------------|-------------------|------------------|
| `SA-`     | pylint / radon      | static_analysis   | Python           |
| `JS-`     | eslint              | static_analysis   | JavaScript / TS  |
| `SEC-`    | bandit              | security_scan     | Python           |
| `OWASP-`  | semgrep (owasp-top-ten) | security_scan | Python / JS / TS |

특수 rule_id: `SA-COMPLEXITY` (radon 순환복잡도 > 10 → Major).

### 도구 라우팅 (`_run_tools`)

```text
static_analysis:
  python          → pylint + radon
  javascript/ts   → eslint
security_scan:
  python          → bandit + semgrep
  javascript/ts   → semgrep
```

지원 확장자: `.py .js .jsx .ts .tsx` (그 외는 분석 제외).

### 도구 severity → 계약 severity 매핑

```yaml
pylint:  {E,F → Critical, W → Major, C,R → Minor}
bandit:  {HIGH → Critical, MEDIUM → Major, LOW → Minor}
semgrep: {ERROR → Critical, WARNING → Major, INFO → Minor}
eslint:  {2 → Critical, 1 → Major, 0 → Minor}
radon:   {complexity > 10 → Major}
```

---

## validation_rule

```yaml
- 1차: AgentResult Pydantic 검증 (response_model 직렬화 — contract.py)
- 2차: execution_ms > 0 (build 시 max(_, 1)로 보장), issues 목록 타입 검증
- 3차: rule_id 접두사 형식 확인 (SA-/JS-/SEC-/OWASP-)

validation_result 산출(app/contract.py validate_result):
  - "skip" — 이슈 없음 (검증 대상 없음)
  - "fail" — execution_ms <= 0 또는 형식 위반 rule_id 존재 → status="fail"
  - "pass" — 이슈 존재 + 모든 rule_id 형식 유효
```

---

## retry_rule / error_rule

```yaml
retry_rule:
  - 도구 부재(FileNotFoundError/OSError): 재시도 없이 graceful skip(빈 결과)
  - 도구 타임아웃(30초/도구): 재시도 없이 graceful skip
  - 도구 출력 JSON 파싱 실패: 해당 도구만 빈 결과

error_rule:
  - pr_diff 비었거나 지원 파일 없음: 빈 issues + summary(0,0,0) 반환 (HTTP 200)
  - 개별 도구 실패: 파이프라인 중단 없이 빈 결과로 진행
  - 분석 전체 예외: make_timeout_result() → status="fail" + error_message,
    빈 issues 반환 (HTTP 200, 파이프라인 비중단). main._run_agent의 try/except.
  - 임시 작업 디렉토리는 분석 후 항상 정리(shutil.rmtree, ignore_errors)

플랫폼 제약:
  - Semgrep은 Windows 네이티브 미지원 → security_scan에서 OWASP 결과 없이 skip
  - 도구 타임아웃: 도구당 30초 (_TOOL_TIMEOUT)
```

> **m1 측 실패 처리**: m2 호출 자체가 실패(연결 불가 등)하면
> m1의 dispatch가 `502 BAD_GATEWAY`로 전체 중단된다(`m1 triggers.py`).
> m2가 정상 200으로 빈 결과를 주면 파이프라인은 계속 진행된다.

---

## 처리 흐름 (analyzer.py)

```text
pr_diff (unified diff)
   │
   ▼ _parse_diff        diff post-image('+'/' ' 라인) → {relpath: 내용}, 삭제파일 제외
   ▼ _materialize       지원 확장자 파일을 임시 디렉토리에 복원
   ▼ _run_tools         agent·언어별 도구 실행 (subprocess, 30s timeout)
   ▼ _summarize         severity별 카운트 집계
   ▼ file 경로 정규화    임시 디렉토리 기준 상대경로로 변환
   │
   ▼ (issues, summary, execution_ms)
```

---

## 모듈 간 연결

```text
GitHub Webhook
   │
   ▼
m1 (Orchestrator)  ── diff_url 1회 fetch → pr_diff
   │
   ├─ POST m2 /analyze/static    (await, 직렬)   → M2AnalyzeResponse(agent=static_analysis)
   ├─ POST m2 /analyze/security  (await, 직렬)   → M2AnalyzeResponse(agent=security_scan)
   │
   ▼ m1이 두 결과를 M3ReviewRequest.static_analysis / .security_scan 에 담아
m3 /review  → 집계·판정·저장 (review_results 테이블)
   │
   ▼
Frontend  ── m3 GET /review/{owner}/{repo}/{pr} 하나로 m2 이슈 포함 결과 수신
            (프론트는 m2를 직접 호출하지 않음. rule_id 접두사로 m2 이슈 식별)
```

---

## 설계안(docs/MODULE_CONTRACT.md)과의 차이

| 항목            | docs 설계안 (이상)                          | 본 문서 / app 실제 구현             |
|-----------------|---------------------------------------------|-------------------------------------|
| 통신 방식       | PlatformState 공유 (필드 추가/갱신)         | REST DTO (M2AnalyzeRequest → AgentResult) |
| 출력 형식       | AgentResult (validation_result/next_agent 등) | **AgentResult 구현 완료** (M2AnalyzeResponse 상위집합) |
| sub-trace ID    | `pr_{12hex}_static_analysis_{4hex}`         | **구현 완료** (contract.make_sub_trace_id) |
| validation_result | pass/fail/skip                            | **구현 완료** (contract.validate_result) |
| status/error    | success/fail + make_timeout_result()        | **구현 완료** (status·error_message·make_timeout_result) |
| rule_id 예시    | `SEC-001 / PERF-001 / STYLE-001`            | `SA- / JS- / SEC- / OWASP-` 접두사   |
| 타임아웃        | 30초 → make_timeout_result()                | 도구당 30초 graceful skip + 전체 예외 시 make_timeout_result |
| 실행 모델       | m1이 asyncio.gather로 m3와 **병렬**          | m1이 **직렬(await)** 순차 호출 (미정합) |
| KMS 사용        | uses_kms: true (컨벤션·과거이슈 조회)        | context 받지만 **미사용** (미정합)   |
| LangSmith       | uses_langsmith: true                        | app/ 스텁 미적용 (미정합)            |

> **남은 미정합(통합 주간 대상)**:
> ① context/developer 실사용(RAG·숙련도 기반 피드백) — analyzer.py 수정,
> ② LangSmith trace 연동(sub_trace_id는 생성되나 LangSmith 미전송),
> ③ m1 직렬 호출 → asyncio.gather 병렬화 (m1 측 변경). (모두 크로스 모듈 — 합의 필요.)
>
> **출력/sub-trace/validation/status는 본 PR에서 구현 완료** (하위호환 유지).

---

## 계약 변경 절차

1. 본 문서 + `backend/_shared/shared/contracts.py`의 m2 DTO를 함께 수정한다.
2. PR description에 `CONTRACT CHANGE: module_2 output 변경` 명시.
3. 영향 모듈(m1 호출부, m3 집계부, FE) 담당자에게 직접 공지.
4. `backend/m2/tests/test_contract.py` 동기 업데이트.
5. 루트 [`docs/MODULE_CONTRACT.md`](../../docs/MODULE_CONTRACT.md) §Module 2도 동기화.
