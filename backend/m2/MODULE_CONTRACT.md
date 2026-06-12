# MODULE_CONTRACT.md — Module 2 (정적 분석 + 보안 분석) 실제 구현 계약

**버전**: v1.1 (as-built + mini-orchestrator 설계) | **작성일**: 2026-06-11 | **개정**: 2026-06-12
**기준 소스(as-built)**: `backend/m2/app/main.py`, `backend/m2/app/analyzer.py`, `backend/m2/app/contract.py`, `backend/_shared/shared/contracts.py`
**기준 소스(설계, 미구현)**: `backend/m2/app/orchestrator.py`, `decision.py`, `clients/{m0,kms,m4}_client.py`, `services/{context_builder,result_mapper}.py` (→ [`m2_orchestrator_prompt.md`](m2_orchestrator_prompt.md))

> 이 문서는 **현재 운영 중인 m2 스텁(`backend/m2/app/`)의 실제 입출력 계약**이며,
> 추가로 **m2 내부 mini-orchestrator 설계 계약**(아직 코드 미구현)을 함께 담는다.
> 루트 [`docs/MODULE_CONTRACT.md`](../../docs/MODULE_CONTRACT.md) §Module 2는
> PlatformState/LangGraph/AgentResult 기반의 **이상적 설계안**으로, 아래 실제 구현과 다르다.
> 차이는 본 문서 끝 「설계안과의 차이」 절에 정리한다. **통합 시 기준은 본 문서다.**
>
> **설계 변경(2026-06-12)**: 기존 "m1 중앙 오케스트레이터" 구조에서
> **각 모듈이 자기 도메인의 end-to-end 흐름을 자체 수행**하는 구조로 전환한다.
> m2는 단순 분석기에서 **"정적분석/보안분석 도메인 end-to-end agent"** 역할을 추가로 갖는다.
> m2 내부 mini-orchestrator가 `m0` / `KMS` / `m4`를 **직접** 호출한다(m1 경유 X).
> 기존 `/analyze/static`·`/analyze/security`는 그대로 유지하고, 새 흐름은 그 위에 얹는다.
> mini-orchestrator 표기: 본 문서에서 **[설계]** 마크가 붙은 절은 미구현 계약이다.

---

## 모듈 개요

```yaml
module_id:    module_2_static_security
module_name:  정적 분석 + 보안 분석
service:      m2-analysis (FastAPI)
port:         8003
responsibility: >
  PR unified diff를 받아 정적 분석(pylint / radon / eslint)과
  보안 스캔(bandit / semgrep — OWASP Top 10)을 수행하고
  IssueItem 목록 + 심각도 요약을 반환한다(as-built 분석부).
  [설계] 추가로 m2 내부 mini-orchestrator가 분석 필요 여부를 판단(decision)하고,
  m0/KMS context를 조합한 뒤 m4에 리뷰 생성을 위임하여 최종 응답을 반환한다.
  코멘트 생성·DB 저장·LLM·RAG는 현재 app/ 스텁에 없다(분석부 전용).

orchestration: >
  [as-built] m1이 PR 트리거 시 diff_url을 1회 fetch하여 pr_diff에 담아
  /analyze/static → /analyze/security 순서로 직렬(await) 호출한다.
  (병렬 아님. 클라이언트 httpx async, timeout 60초.)
  두 응답을 m1이 M3ReviewRequest로 묶어 m3 /review로 전달 → 집계·저장.
  [설계] m1 중앙 오케스트레이션을 대체하는 m2 내부 mini-orchestrator를 추가한다.
  POST /orchestrate/review 가 decision → (m0/KMS context) → analyzer 재사용
  → result_mapper → m4 호출까지 m2 내부에서 end-to-end로 수행한다.
  mini-orchestrator는 m0/KMS/m4를 직접 호출하며 m1을 경유하지 않는다.

uses_db:        false   # app/ 스텁은 DB 미연결
uses_llm:       false   # LLM/RAG 없음 (도구 기반 결정적 분석)
uses_kms:       false   # [as-built] context 미사용. [설계] mini-orchestrator가 KMS 직접 조회 예정
uses_m0:        false   # [설계] mini-orchestrator가 M0_BASE_URL로 직접 조회 예정 (graceful fallback)
uses_m4:        false   # [설계] mini-orchestrator가 M4_BASE_URL로 리뷰 생성 위임 예정 (graceful fallback)
uses_langsmith: false   # app/ 스텁 미적용
```

---

## 엔드포인트

| Method | Path                  | 설명                                  |
|--------|-----------------------|---------------------------------------|
| GET    | `/health`             | 헬스체크 → `{"status":"ok","service":"m2-analysis"}` |
| POST   | `/analyze/static`     | 정적 분석 (pylint / radon / eslint)   |
| POST   | `/analyze/security`   | 보안 스캔 (bandit / semgrep)          |
| POST   | `/orchestrate/review` | **[설계]** m2 내부 end-to-end: decision → analyzer 재사용 → m0/KMS context → m4 위임 |

`/analyze/*` 두 POST 엔드포인트는 **요청/응답 스키마가 동일**하며, 응답 `agent` 필드 값만 다르다.
`/orchestrate/review`는 mini-orchestrator 진입점으로 입출력 DTO가 별도다(아래 「mini-orchestrator 계약」 절).
**[as-built/설계 유지 원칙]**: `/health`·`/analyze/static`·`/analyze/security`는 삭제·재작성하지 않는다.
`/orchestrate/review`는 기존 `analyzer.py`를 **재사용**하며 기존 분석 동작 결과를 바꾸지 않는다.

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

## mini-orchestrator 계약 [설계 — 미구현]

> 아래는 [`m2_orchestrator_prompt.md`](m2_orchestrator_prompt.md) 기준 **m2 내부 mini-orchestrator** 계약이다.
> 코드는 아직 없으며(신규 파일 `orchestrator.py`·`decision.py`·`clients/`·`services/`),
> 기존 `analyzer.py`를 **재사용**하는 방식으로 분석부 위에 얹는다.
> `analyzer.py`에는 m0/KMS/m4 호출 로직을 넣지 않으며, orchestration 책임은 `orchestrator.py`가 진다.

### 신규/수정 파일

```text
[신규] app/orchestrator.py            # run_m2_orchestration(payload) 진입점
[신규] app/decision.py                # 분석 필요 여부 판단
[신규] app/clients/m0_client.py       # M0_BASE_URL (graceful fallback)
[신규] app/clients/kms_client.py      # KMS_BASE_URL (컨벤션/보안규칙/과거이슈/아키텍처)
[신규] app/clients/m4_client.py       # M4_BASE_URL (리뷰 생성 위임, fallback/stub)
[신규] app/services/context_builder.py  # m0+KMS context 조합
[신규] app/services/result_mapper.py    # m2 결과 → m4 요청 payload 변환
[수정] app/main.py                    # POST /orchestrate/review 추가 (기존 엔드포인트 유지)
[수정] app/contract.py                # M2OrchestrateRequest/Response DTO 추가
```

### 입력 — `M2OrchestrateRequest`

```yaml
M2OrchestrateRequest:
  task_id:      str         # 필수 — 트리거 단위 추적 키
  pr_id:        str         # 필수 — PR 번호 (문자열)
  pr_diff:      str         # 필수 — unified diff 본문
  owner:        str | null  # 선택 — repo owner
  repo:         str | null  # 선택 — repo 이름
  developer_id: str | null  # 선택 — 개발자 식별
  trace_id:     str | null  # 선택
```

### 출력 — `M2OrchestrateResponse`

```yaml
M2OrchestrateResponse:
  task_id:         str
  pr_id:           str
  trace_id:        str | null
  module_id:       "module_2"                  # 고정
  status:          "success | fail | skip"     # Literal
  decision:        dict                         # decision.py 판단 결과 (아래)
  context:         dict | null                  # m0 + KMS 조합 context (없으면 null)
  static_analysis: AgentResult | null           # 필요 시 기존 analyzer 결과 재사용
  security_scan:   AgentResult | null           # 필요 시 기존 analyzer 결과 재사용
  m4_review:       dict | null                  # m4 응답 (실패/fallback 시 null)
  error_message:   str | null                   # 외부 연결 스킵/실패 사유 누적
```

> `static_analysis`·`security_scan`은 기존 `AgentResult`(위 출력 계약 절)를 **그대로** 담는다.
> 즉 기존 분석 계약은 깨지지 않으며 mini-orchestrator는 그 결과를 래핑만 한다.

### decision (decision.py)

```yaml
needs_static_analysis: bool   # .py/.js/.jsx/.ts/.tsx 변경이 있으면 true
needs_security_scan:   bool   # 보안 키워드 또는 의존성 파일 변경이 있으면 true
reason:                str    # 판단 근거 문자열
```

- `needs_static_analysis` 트리거 확장자: `.py .js .jsx .ts .tsx`
- `needs_security_scan` 트리거 키워드(diff 내 등장):
  `auth, login, password, token, secret, jwt, sql, query, subprocess, eval, exec, os.system`
- `needs_security_scan` 트리거 의존성 파일 변경:
  `requirements.txt, pyproject.toml, package.json, package-lock.json, poetry.lock`
- `README` / `docs` / `.md` 파일만 변경 → 둘 다 false → orchestrator `status="skip"`

### clients (외부 연결 규약)

| client | 환경변수 | 용도 | 미설정/실패 시 |
|--------|----------|------|----------------|
| `m0_client`  | `M0_BASE_URL`  | m0 context 조회 | graceful fallback (전체 실패 X) |
| `kms_client` | `KMS_BASE_URL` | 컨벤션·보안규칙·이전 PR 이슈·아키텍처 문서 | graceful fallback (전체 실패 X) |
| `m4_client`  | `M4_BASE_URL`  | 리뷰 생성 위임 | graceful fallback 또는 stub 응답 |

> **불변식**: 외부 연결 실패로 **기존 m2 분석 자체가 중단되지 않는다.**
> 어떤 외부 연결이 스킵되었는지는 `error_message`(또는 warnings)에 남긴다.

### 실행 흐름 (run_m2_orchestration)

```text
M2OrchestrateRequest
   ▼ decision.py        분석 필요 여부 판단
   ▼ skip이면           분석 없이 status="skip" 반환
   ▼ m0_client          m0 context 조회 시도 (실패 시 skip 기록)
   ▼ kms_client         KMS context 조회 시도 (실패 시 skip 기록)
   ▼ analyzer 재사용    needs_static_analysis → static_analysis(AgentResult)
   ▼ analyzer 재사용    needs_security_scan   → security_scan(AgentResult)
   ▼ result_mapper      m2 결과 → m4 요청 payload 생성
   ▼ m4_client          m4 호출 (실패해도 분석 결과는 응답에 포함)
   ▼ M2OrchestrateResponse 반환
```

> m4 호출이 실패해도 `static_analysis`/`security_scan` 결과는 응답에 포함한다.
> 복구 불가 예외는 `status="fail"` + `error_message`로 반환한다(`status` Literal 제약).

### orchestrate 검증/에러 규약

```yaml
status 산출:
  - "skip"    — decision이 둘 다 false (분석 불필요)
  - "success" — 흐름 정상 완료 (m4 fallback 포함 가능)
  - "fail"    — 복구 불가 예외 → error_message 동반
error_message:
  - 외부 연결(m0/KMS/m4) 스킵·실패 사유를 누적 기록
  - 분석 자체는 중단하지 않음 (불변식)
```

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

### [as-built] m1 중앙 오케스트레이션 경로

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

### [설계] m2 mini-orchestrator end-to-end 경로

```text
호출자 (m1 또는 트리거)
   │
   ▼ POST m2 /orchestrate/review  (M2OrchestrateRequest)
m2 mini-orchestrator (orchestrator.py)
   │  decision.py → 분석 필요 판단 (skip 가능)
   ├─ m0_client   ── M0_BASE_URL  → m0 context        (graceful fallback)
   ├─ kms_client  ── KMS_BASE_URL → 컨벤션/보안규칙/과거이슈/아키텍처 (graceful fallback)
   ├─ analyzer.py 재사용 → static_analysis / security_scan (AgentResult)
   │  result_mapper → m4 요청 payload
   └─ m4_client   ── M4_BASE_URL  → 리뷰 생성 위임      (실패해도 분석결과 포함)
   │
   ▼ M2OrchestrateResponse (decision · context · static/security · m4_review)
```

> 두 경로는 공존한다. mini-orchestrator는 m0/KMS/m4를 **직접** 호출하며 m1을 경유하지 않는다.
> m2 코드는 m3에 의존하지 않는다(m3도 별도 end-to-end 구조를 자체 구현 예정).

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
| 실행 모델       | m1이 asyncio.gather로 m3와 **병렬**          | [as-built] m1 **직렬(await)** / [설계] m2 mini-orchestrator end-to-end |
| 오케스트레이션  | m1 중앙 오케스트레이터                        | [설계] 모듈별 자체 end-to-end (m2가 m0/KMS/m4 직접 호출) |
| KMS 사용        | uses_kms: true (컨벤션·과거이슈 조회)        | [as-built] context 미사용 / [설계] kms_client 직접 조회 |
| LangSmith       | uses_langsmith: true                        | app/ 스텁 미적용 (미정합)            |

> **남은 미정합(통합 주간 대상)**:
> ① context/developer 실사용(RAG·숙련도 기반 피드백) — [설계] mini-orchestrator의 context_builder + KMS로 해소 예정,
> ② LangSmith trace 연동(sub_trace_id는 생성되나 LangSmith 미전송),
> ③ m1 직렬 호출 → asyncio.gather 병렬화 (m1 측 변경) 또는 mini-orchestrator로 m1 경로 자체 대체.
> (모두 크로스 모듈 — 합의 필요.)
>
> **as-built 구현 완료**: 출력/sub-trace/validation/status (하위호환 유지).
> **설계(미구현)**: mini-orchestrator (`/orchestrate/review`, decision/clients/services) — 코드 추가 대기.

---

## GLOBAL_AGENT_RULE 준수 매핑

> 팀 공통 강제 규칙 [`docs/GLOBAL_AGENT_RULE.md`](../../docs/GLOBAL_AGENT_RULE.md) 대비
> 현재 m2 `app/` 스텁의 준수 현황. **PR 머지 전 이 표로 점검한다.**
> (GLOBAL_AGENT_RULE §532 체크리스트 13항을 m2 기준으로 매핑.)

| 규칙 | 상태 | m2 근거 / 비고 |
|------|------|----------------|
| §1 Agent/Tool 분류 | ✅ | [as-built] 분석부는 LLM·반복·분기 없는 **결정적 Tool** → StateGraph 불요. [설계] mini-orchestrator는 decision 분기 + 외부 호출을 갖는 **Workflow** 계층(여전히 LLM 루프 없음 → 결정적 오케스트레이션) |
| §2 Clean Architecture | ✅ | main(Presentation) / analyzer·contract(Domain+Tool) 분리 |
| §3 PlatformState 공통 필드 | N/A | REST DTO 방식, LangGraph State 미사용 (설계안과의 차이 참조) |
| §4 Output Contract 10필드 | ✅ | AgentResult가 task_id·trace_id·agent_name·module_id·status·issues·summary·validation_result·execution_ms·next_agent 전부 포함 |
| §5 Validation 3단계 | ⚠️ 부분 | 1차 Pydantic·2차 business rule(validate_result) 구현, 3차 품질평가 Agent 없음(LLM 부재로 N/A) |
| §6-1 Pydantic 모델 필수 | ✅ | 입출력 전부 BaseModel |
| §6-3 Enum 사용 의무 | ⚠️ 부분 | 현재 `Literal` 사용 (Enum 아님 — 통합 시 공통 Enum 정렬 검토) |
| §6-4 strict=True | ❌ | 미적용 (FastAPI 기본 검증 의존) |
| §7 LangSmith / AgentHarness | ❌ 보류 | sub_trace_id는 생성하나 LangSmith 미전송. 아래 보류 방침 참조 |
| §8 테스트(정상/실패/경계/타임아웃) | ✅ | test_contract·test_contract_model에 커버. HITL 케이스는 m2에 HITL 없어 N/A |
| §9 HITL | N/A | m2는 분석 종단, HITL 판단 없음 (`status=hitl_pending`은 스키마만 보유) |
| §10 Retry | ✅ | 도구 부재/타임아웃 graceful skip, 전체 예외 make_timeout_result (retry_rule 절 참조) |
| §11 agent_traces 로깅 | ❌ 보류 | app/ 스텁 DB 미연결. 아래 보류 방침 참조 |
| §12 Error Handling(에러 미삼킴) | ✅ | 전체 예외를 error_message에 기록 후 fail 반환 (삼키지 않음) |

### 보류 항목 처리 방침 (통합 주간 대상)

미적용(❌) 3건은 **app/ 스텁이 무상태 분석 전용**이라 발생하며, 의도적 보류다.
누락이 아니라 통합 시점에 적용한다.

| 보류 규칙 | 보류 사유 | 통합 시 적용 계획 |
|-----------|-----------|-------------------|
| §7 LangSmith/AgentHarness | analyze()가 LangGraph 노드가 아닌 sync 함수(to_thread)라 trace 미포착 | `_shared/shared/harness.py`의 AgentHarness로 래핑 + `LANGCHAIN_PROJECT=module2-{githubId}` |
| §11 agent_traces 로깅 | app/ 스텁에 DB 세션 없음 (sub2_new에만 store 존재) | AgentHarness 도입 시 자동 기록(§11 11필드). DB 연결은 통합 환경에서 |
| §6-4 strict=True | 현재 입력 신뢰 경계가 m1뿐이라 영향 적음 | 공통 Enum/strict 정책 합의 후 일괄 적용 |

> 이 표는 **m2 내부 문서**다. 공통 `docs/GLOBAL_AGENT_RULE.md`는 수정하지 않는다.
> m2 코드 변경 시 위 상태를 갱신하여 준수 현황을 항상 최신으로 유지한다.

---

## 계약 변경 절차

1. `/analyze/*` (AgentResult) 계약 변경 시: 본 문서 + `backend/_shared/shared/contracts.py`의 m2 DTO를 함께 수정한다.
2. `/orchestrate/review` (M2Orchestrate*) 계약 변경 시: 본 문서 + `backend/m2/app/contract.py`만 수정한다.
   **공통 `backend/_shared/shared/contracts.py`는 수정하지 않는다**(m2 내부 신규 DTO이므로 app/ 안에 둔다).
3. PR description에 `CONTRACT CHANGE: module_2 output 변경` 명시.
4. 영향 모듈(m1 호출부, m3 집계부, FE) 담당자에게 직접 공지. mini-orchestrator는 m0/KMS/m4 담당자에게도 공지.
5. `backend/m2/tests/test_contract.py` 동기 업데이트(+ orchestrate/decision/clients fallback 테스트).
6. 루트 [`docs/MODULE_CONTRACT.md`](../../docs/MODULE_CONTRACT.md) §Module 2도 동기화.

---

## 문서 반영 필요 사항 (공통 문서 — 본 PR 범위 아님)

> 아래는 [`m2_orchestrator_prompt.md`](m2_orchestrator_prompt.md)의 "공유 문서 수정 금지" 원칙에 따라
> 본 m2 내부 문서에만 기록하고, 공통 `docs/`는 **수정하지 않는다**. 통합 주간 합의 대상.

- 루트 `docs/MODULE_CONTRACT.md`: m1 중앙 오케스트레이션 → 모듈별 end-to-end 전환 반영 필요.
- `docs/GLOBAL_AGENT_RULE.md`: m2 mini-orchestrator를 Workflow 계층으로 분류하는 항목 정렬 필요.
- m0/KMS/m4 계약: m2가 직접 호출하는 인터페이스(요청/응답 스키마) 확정 필요(현재 graceful fallback 전제).
