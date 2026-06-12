# MODULE_CONTRACT.md — Module 2 (정적 분석 + 보안 분석) 실제 구현 계약

**버전**: v1.2 (안 A — comment_body 추가) | **작성일**: 2026-06-12
**기준 소스**: `backend/m2/app/main.py`, `backend/m2/app/analyzer.py`, `backend/m2/app/contract.py`, `backend/m2/app/comment_generator.py`

> 이 문서는 **현재 운영 중인 m2(`backend/m2/app/`)의 실제 입출력 계약**이다.
> 루트 [`docs/MODULE_CONTRACT.md`](../../docs/MODULE_CONTRACT.md) §Module 2는
> PlatformState/LangGraph 기반의 **이상적 설계안**으로, 아래 실제 구현과 다르다.
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
  보안 스캔(bandit / semgrep — OWASP Top 10)을 수행한다.
  분석 결과(IssueItem 목록 + 심각도 요약)를 마크다운 코멘트(comment_body)로 변환하여
  AgentResult에 포함시킨다.
  Module 4가 m2·m3의 comment_body를 취합하여 최종 GitHub 코멘트를 생성·게시한다.

orchestration: >
  m1이 단일 오케스트레이터. PR 트리거 시 m1이 diff_url을 1회 fetch하여
  pr_diff에 담아 asyncio.gather로 m2·m3를 병렬 호출한다.
  (m1 구현 예정 — 현재는 직렬 await. m1 담당자에게 공지 필요.)
  m1이 m2·m3 결과를 취합하여 m4로 전달한다.
  m4가 comment_body 취합·판정·GitHub 코멘트 게시를 담당한다.

uses_db:        false
uses_llm:       false   # 도구 기반 결정적 분석 + 템플릿 코멘트
uses_kms:       false   # context 필드는 받지만 현재 미사용
uses_langsmith: false   # 통합 주간 대상
```

---

## 엔드포인트

| Method | Path                | 설명                                                     |
|--------|---------------------|----------------------------------------------------------|
| GET    | `/health`           | 헬스체크 → `{"status":"ok","service":"m2-analysis"}`    |
| POST   | `/analyze/static`   | 정적 분석 (pylint / radon / eslint) + comment_body 생성  |
| POST   | `/analyze/security` | 보안 스캔 (bandit / semgrep) + comment_body 생성         |

두 POST 엔드포인트는 **요청/응답 스키마가 동일**하며 `agent` / `agent_name` / `comment_body` 헤더 섹션만 다르다.

---

## 입력 — `M2AnalyzeRequest`

```yaml
M2AnalyzeRequest:
  task_id:   str              # 필수 — 트리거 단위 추적 키
  pr_id:     str              # 필수 — PR 번호 (문자열)
  pr_diff:   str              # 필수 — unified diff 본문 (m1이 diff_url fetch한 결과)
  context:   AnalysisContext  # 선택 — 기본 빈 객체 (현재 미사용)
  developer: DeveloperProfile | null   # 선택 — 현재 미사용
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

> `context`와 `developer`는 수신하지만 현재 분석에 미사용.
> RAG/숙련도 기반 피드백은 통합 주간 대상.

### required_state_fields

```yaml
- task_id
- pr_id
- pr_diff
```

`pr_diff`가 비었거나 지원 확장자 파일이 없으면 빈 결과를 반환한다(오류 아님).

---

## 출력 — `AgentResult`

엔드포인트는 `app/contract.py`의 **`AgentResult`** 를 반환한다.
기존 `M2AnalyzeResponse`(task_id/agent/issues/summary/execution_ms)의 **상위집합**이다.

> **하위호환**: m1은 `M2AnalyzeResponse(**resp.json())`로 역직렬화하며
> Pydantic v2 기본값(`extra="ignore"`)으로 추가 필드를 무시한다.

```yaml
AgentResult:
  # ── M2AnalyzeResponse 호환 필드 ──
  task_id:           str
  agent:             "static_analysis | security_scan"
  issues:            list[IssueItem]       # 기본 []
  summary:           IssueSummary          # 심각도별 카운트
  execution_ms:      int                   # 항상 >= 1

  # ── MODULE_CONTRACT 계약 필드 ──
  trace_id:          str | null
  sub_trace_id:      str                   # pr_{12hex}_{agent}_{4hex}
  agent_name:        "StaticAnalysisAgent | SecurityScanAgent"
  module_id:         "module_2"            # 고정
  status:            "success | fail | hitl_pending"
  validation_result: "pass | fail | skip"
  error_message:     str | null
  next_agent:        null

  # ── 안 A 신규 필드 ──
  comment_body:      str | null            # m2 섹션 마크다운 코멘트
                                           # Module 4가 취합 → 최종 GitHub 코멘트 생성
                                           # 이슈 없으면 null

IssueItem:
  severity:   "Critical | Major | Minor"
  line:       int | null
  file:       str | null     # 임시 작업 디렉토리 기준 상대경로
  message:    str
  rule_id:    str | null     # 접두사로 도구 구분
  suggestion: str | null

IssueSummary:
  critical: int   # 기본 0
  major:    int
  minor:    int
```

### comment_body 형식 (comment_generator.py)

```markdown
## 🔍 정적 분석 결과   ← static_analysis
## 🔒 보안 스캔 결과   ← security_scan

| 심각도 | 파일 | 라인 | 규칙 | 설명 | 제안 |
|--------|------|------|------|------|------|
| 🔴 Critical | auth.py | 42 | SEC-B601 | ... | ... |
| 🟡 Major    | api.py  | 10 | SA-W0611 | ... | ... |

> Critical N건 / Major N건 / Minor N건
```

- 이슈 없으면 `comment_body = null` (m4가 해당 섹션 생략)
- 심각도 이모지: Critical=🔴, Major=🟡, Minor=🔵

---

## rule_id 접두사 → 도구 매핑

| 접두사   | 도구                    | agent           | 대상 언어        |
|----------|-------------------------|-----------------|------------------|
| `SA-`    | pylint / radon          | static_analysis | Python           |
| `JS-`    | eslint                  | static_analysis | JS / TS          |
| `SEC-`   | bandit                  | security_scan   | Python           |
| `OWASP-` | semgrep (owasp-top-ten) | security_scan   | Python / JS / TS |

특수 rule_id: `SA-COMPLEXITY` (radon 순환복잡도 > 10 → Major).

### 도구 라우팅

```text
static_analysis:
  python         → pylint + radon
  javascript/ts  → eslint
security_scan:
  python         → bandit + semgrep
  javascript/ts  → semgrep
```

지원 확장자: `.py .js .jsx .ts .tsx`

### severity 매핑

```yaml
pylint:  {E,F → Critical,  W → Major,  C,R → Minor}
bandit:  {HIGH → Critical, MEDIUM → Major, LOW → Minor}
semgrep: {ERROR → Critical, WARNING → Major, INFO → Minor}
eslint:  {2 → Critical, 1 → Major, 0 → Minor}
radon:   {complexity > 10 → Major}
```

---

## validation_rule

```yaml
- 1차: AgentResult Pydantic 검증 (response_model)
- 2차: execution_ms > 0 (max(_, 1) 보장), issues 목록 타입 검증
- 3차: rule_id 접두사 형식 확인 (SA-/JS-/SEC-/OWASP-)

validation_result:
  "skip" — 이슈 없음
  "fail" — execution_ms <= 0 또는 형식 위반 rule_id
  "pass" — 이슈 존재 + 모든 rule_id 형식 유효
```

---

## retry_rule / error_rule

```yaml
retry_rule:
  - 도구 부재(FileNotFoundError/OSError): graceful skip
  - 도구 타임아웃(30초): graceful skip
  - 도구 출력 JSON 파싱 실패: 해당 도구만 빈 결과

error_rule:
  - pr_diff 비었거나 지원 파일 없음: 빈 issues + comment_body=null (HTTP 200)
  - 개별 도구 실패: 파이프라인 중단 없이 빈 결과
  - 분석 전체 예외: make_timeout_result() → status="fail" + comment_body=null (HTTP 200)
  - 임시 작업 디렉토리 항상 정리 (shutil.rmtree)

플랫폼 제약:
  - Semgrep Windows 네이티브 미지원 → OWASP 결과 없이 skip
  - 도구 타임아웃: 30초 (_TOOL_TIMEOUT)
```

> **m1 측 실패 처리**: m2 호출 자체가 실패하면 m1 dispatch가 `502 BAD_GATEWAY`로 전체 중단.
> m2가 정상 200으로 빈 결과를 주면 파이프라인은 계속 진행된다.

---

## 처리 흐름

```text
pr_diff (unified diff)
   │
   ▼ analyzer.py
   ├─ _parse_diff     → {relpath: post-image 내용}
   ├─ _materialize    → 임시 디렉토리에 파일 복원
   ├─ _run_tools      → 도구 실행 (subprocess, 30s)
   ├─ _summarize      → severity별 카운트
   └─ file 경로 정규화
   │
   ▼ (issues, summary, execution_ms)
   │
   ▼ comment_generator.py
   └─ generate_comment → 마크다운 코멘트 (이슈 없으면 null)
   │
   ▼ contract.py
   └─ build_agent_result → AgentResult (comment_body 포함)
```

---

## 모듈 간 연결 (안 A)

```text
GitHub Webhook
   │
   ▼
m1 (Orchestrator)  ── diff_url 1회 fetch → pr_diff
   │
   ├─ asyncio.gather([
   │     POST m2 /analyze/static    → AgentResult(comment_body=정적분석 마크다운)
   │     POST m2 /analyze/security  → AgentResult(comment_body=보안스캔 마크다운)
   │     POST m3 ...                → m3 AgentResult(comment_body=테스트·성능 마크다운)
   │  ])
   │
   ▼ m1이 전체 결과를 취합하여
m4 (판정·코멘트·커리큘럼)
   ├── m2.comment_body + m3.comment_body 취합 → 최종 GitHub 코멘트 게시
   ├── analysis_results → 3-Way 판정 (lgtm/rework/escalate)
   ├── Slack 에스컬레이션 (Critical 시)
   └── 학습 커리큘럼 생성

Frontend  ── m4 결과로 최종 리뷰 화면 표시
           (프론트는 m2 직접 호출 없음)
```

> **현재 상태**: m1 직렬 await + m3가 집계·판정 수행 중.
> 안 A 전환은 m1 구현 시 반영. **m4 담당자에게 `comment_body` 필드 추가 공지 필요.**

---

## 설계안(docs/MODULE_CONTRACT.md)과의 차이

| 항목           | docs 설계안                         | 본 문서 / 실제 구현                       |
|----------------|-------------------------------------|-------------------------------------------|
| 통신 방식      | PlatformState 공유                  | REST DTO (M2AnalyzeRequest → AgentResult) |
| comment_body   | m4가 전체 코멘트 생성               | **m2가 자기 섹션 생성 → m4 취합** (안 A) |
| 출력 형식      | AgentResult                         | **구현 완료** (M2AnalyzeResponse 상위집합)|
| sub-trace ID   | `pr_{12hex}_static_analysis_{4hex}` | **구현 완료**                             |
| validation     | pass/fail/skip                      | **구현 완료**                             |
| status/error   | success/fail + make_timeout_result  | **구현 완료**                             |
| 실행 모델      | asyncio.gather 병렬                 | 직렬 await — m1 구현 시 변경 예정         |
| 다운스트림     | m4가 판정·코멘트                    | **안 A: m4가 취합** (m1 구현 후 전환)     |
| KMS 사용       | uses_kms: true                      | context 수신하나 미사용 (통합 주간 대상)  |
| LangSmith      | uses_langsmith: true                | 미적용 (통합 주간 대상)                   |

---

## GLOBAL_AGENT_RULE 준수 매핑

| 규칙 | 상태 | 비고 |
|------|------|------|
| §1 Agent/Tool 분류 | ✅ | 결정적 Tool — StateGraph 불요 |
| §2 Clean Architecture | ✅ | main / analyzer·contract·comment_generator 분리 |
| §3 PlatformState | N/A | REST DTO 방식 |
| §4 Output Contract 10필드 | ✅ | AgentResult 전 필드 + comment_body |
| §5 Validation 3단계 | ⚠️ 부분 | 1·2차 구현, 3차 LLM 부재로 N/A |
| §6-1 Pydantic 필수 | ✅ | 입출력 전부 BaseModel |
| §6-3 Enum | ⚠️ 부분 | Literal 사용 — 통합 시 검토 |
| §6-4 strict=True | ❌ | 통합 주간 대상 |
| §7 LangSmith | ❌ 보류 | sub_trace_id 생성하나 미전송 |
| §8 테스트 | ✅ | test_contract·test_contract_model 커버 |
| §9 HITL | N/A | m2 분석 종단, HITL 없음 |
| §10 Retry | ✅ | graceful skip + make_timeout_result |
| §11 agent_traces | ❌ 보류 | DB 미연결 |
| §12 Error Handling | ✅ | error_message 기록 후 fail 반환 |

### 보류 항목 (통합 주간 대상)

| 규칙 | 사유 | 계획 |
|------|------|------|
| §7 LangSmith | analyze()가 sync 함수(to_thread) | AgentHarness 래핑 |
| §11 agent_traces | DB 세션 없음 | AgentHarness 도입 시 자동 기록 |
| §6-4 strict=True | 입력 신뢰 경계 m1뿐 | 공통 정책 합의 후 일괄 적용 |

> 이 표는 **m2 내부 문서**다. 공통 `docs/GLOBAL_AGENT_RULE.md`는 수정하지 않는다.

---

## 계약 변경 절차

1. 본 문서 수정.
2. PR description에 `CONTRACT CHANGE: module_2 output 변경` 명시.
3. 영향 모듈(m1, **m4**) 담당자에게 직접 공지.
4. `backend/m2/tests/test_contract.py` 동기 업데이트.
