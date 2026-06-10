# MODULE_CONTRACT.md — 모듈별 입출력 계약

**버전**: v1.0 | **작성일**: 2026-06-04  
**이 문서는 모듈 간 통신의 유일한 계약서다. 변경 시 영향받는 모든 모듈에 공지 필수.**

---

## 계약 읽는 법

각 모듈 계약에서:
- **input**: 이 모듈이 받기를 기대하는 State 필드
- **output**: 이 모듈이 반환하는 State 필드 (기존 필드에 추가/갱신)
- **required_state_fields**: 이 모듈 실행 전 반드시 채워져 있어야 하는 필드
- **uses_kms**: Module 0 pgVector 검색을 호출하는지 여부

---

## Module 0 — KMS 사내 지식 파이프라인

```yaml
module_id:    module_0_kms
module_name:  KMS 사내 지식 파이프라인
responsibility: >
  사내 문서(PDF/DOCX/PPTX/TXT)를 Markdown으로 변환하고
  청킹·메타데이터 추출 후 pgVector/PostgreSQL/GraphDB에 저장한다.
  다른 모듈의 KMS 검색 소스를 생성하는 역할.

input:
  - file: multipart/form-data
  - source: "upload | notion | confluence | slack"
  - uploaded_by: str (user_id)

output:
  - doc_id: str (UUID)
  - status: "stored | hitl_pending | failed"
  - quality_score: float
  - chunk_count: int
  - trace_id: str (trc_000{stage}_{doc_id_8hex})

required_state_fields: []   # 독립 파이프라인, PlatformState 불사용

uses_kms: false             # 자체가 KMS 소스
uses_langsmith: true

validation_rule:
  - Stage 2: quality_score >= 0.8 (미달 시 HITL)
  - Stage 4: chunk 길이 100~1500 토큰 (초과 시 HITL)
  - Stage 5b: 메타데이터 필수 필드 존재 여부 검증

retry_rule:
  - Stage 2: max 2회 (STAGE2_MAX_FIX_ATTEMPTS env)
  - Stage 1: Upstage 실패 시 Gemini Multimodal 폴백 1회
  - 그 외 Stage: 재시도 없음 → HITL

error_rule:
  - quality_score < 0.8: HITL 큐 등록
  - 표/이미지 구조 손실: HITL 큐 등록
  - Parent-Child 연결 실패: HITL 큐 등록
  - DB 저장 실패: status=failed, agent_traces 기록
```

**Stage별 Trace ID:**
```
Stage 1: trc_0001_{doc_id_8hex}
Stage 2: trc_0002_{doc_id_8hex}
Stage 3: trc_0003_{doc_id_8hex}
Stage 4: trc_0004_{doc_id_8hex}
Stage 5: trc_0005_{doc_id_8hex}
Stage 6: trc_0006_{doc_id_8hex}
```

---

## Module 1 — 오케스트레이터

```yaml
module_id:    module_1_orchestrator
module_name:  오케스트레이터
responsibility: >
  GitHub Webhook을 수신하고 요청 유형을 분류한 뒤
  Module 2/3을 병렬 호출하고 결과를 취합하여 Module 4로 전달.
  KMS 컨텍스트 검색(pgVector)도 담당.

input:
  # GitHub Webhook 페이로드
  - X-Hub-Signature-256: str (HMAC-SHA256 서명, 없으면 403)
  - payload:
      action: str
      pull_request:
        number: int
        diff_url: str
        user.login: str
      repository.full_name: str

output:  # PlatformState 초기화
  - task_id: str (UUID, 신규 생성)
  - trace_id: str (pr_{12자리 hex}, 신규 생성)
  - request_type: RequestType
  - module_id: "module_1"
  - developer: DeveloperInfo (users 테이블 조회)
  - pr_context: PRContext
  - kms_context: KMSContext (pgVector 검색 결과)
  - analysis_results: []  # 초기값 빈 리스트
  - issues: []
  - retry_count: 0
  - status: "running"

required_state_fields: []  # 최초 진입점, State 초기화 담당

uses_kms: true             # pgVector 코사인 유사도 검색
uses_langsmith: true

validation_rule:
  - GitHub Webhook HMAC-SHA256 서명 검증 (X-Hub-Signature-256)
  - users 테이블에 user_id 존재 여부 (없으면 skill_level="junior" 기본값)
  - request_type 분류 결과 유효성 확인

retry_rule:
  - KMS 검색 0건: 빈 리스트 반환, 오류 없이 진행
  - GitHub API 429: 60초 대기 후 1회 재시도
  - 의도 분류 실패: "pr_review" 기본값으로 진행

error_rule:
  - X-Hub-Signature-256 없음: 403 즉시 반환
  - GitHub API 401/403: Slack 에스컬레이션 + status=fail
  - user_id 없음: skill_level="junior" 기본값, 경고 로그
```

**라우팅 로직:**
```python
def route(state: PlatformState) -> str:
    if state["request_type"] == RequestType.PR_REVIEW:
        return "parallel_analysis"    # Module 2 + 3 동시 실행
    elif state["request_type"] == RequestType.KMS_QUERY:
        return "kms_chat"             # Module 0 Chat API
    return "end"
```

---

## Module 2 — 정적 분석 + 보안 분석

```yaml
module_id:    module_2_static_security
module_name:  정적 분석 + 보안 분석
responsibility: >
  PR diff를 정적 분석(ESLint/Pylint/순환복잡도)하고
  보안 취약점(SQL Injection/XSS/CSRF/CVE)을 탐지한다.
  Module 1에서 asyncio.gather로 Module 3과 병렬 실행.

input:  # PlatformState에서 읽기
  - task_id: str
  - trace_id: str
  - pr_context.pr_diff: str       (분석 대상)
  - kms_context: KMSContext        (코딩 컨벤션, 이전 이슈 참조)
  - developer.skill_level: str     (피드백 수준 조정)

output:  # PlatformState에 추가
  - analysis_results: [AgentResult]   (기존 목록에 추가)
  - issues: [IssueItem]               (기존 목록에 추가)
  - module_id: "module_2"
  - status: AgentStatus

# Output Contract (AgentResult 형식)
agent_result:
  task_id: str
  trace_id: str
  agent_name: "StaticAnalysisAgent | SecurityScanAgent"
  module_id: "module_2"
  status: "success | fail | hitl_pending"
  issues:
    - severity: "Critical | Major | Minor"
      line: int
      file: str
      message: str
      rule_id: str     # 예: "SEC-001", "PERF-001", "STYLE-001"
      suggestion: str
  summary:
    critical: int
    major: int
    minor: int
  validation_result: "pass | fail | skip"
  execution_ms: int
  next_agent: null

required_state_fields:
  - task_id
  - trace_id
  - pr_context

uses_kms: true      # KMS에서 보안 가이드, 코딩 컨벤션 chunk 조회
uses_langsmith: true

validation_rule:
  - 1차: AgentResult Pydantic 검증
  - 2차: execution_ms > 0, issues 목록 타입 검증
  - 3차: rule_id 형식 확인 (예: "SEC-001")

retry_rule:
  - 타임아웃(30초): make_timeout_result() 반환, agent_traces status=fail
  - LLM JSON 파싱 실패: 1회 재시도 후 {"issues": [], "error": "parse_failed"}
  - 그 외: 재시도 없음

error_rule:
  - 타임아웃: 빈 AgentResult 반환 (파이프라인 중단 없음)
  - 분석 실패: status=fail + error_message 기록, Module 4에 빈 결과 전달
```

**Sub-trace ID 패턴:**
```
pr_{12자리 hex}_static_analysis_{4자리 hex}
pr_{12자리 hex}_security_scan_{4자리 hex}
```

---

## Module 3 — 테스트 검증 + 성능 분석

```yaml
module_id:    module_3_test_performance
module_name:  테스트 검증 + 성능 분석
responsibility: >
  테스트 커버리지 분석(80% 미달 시 Major)과
  N+1 쿼리, 시간복잡도 이슈를 탐지한다.
  Module 2와 asyncio.gather로 병렬 실행.

input:  # Module 2와 동일 구조
  - task_id: str
  - trace_id: str
  - pr_context.pr_diff: str
  - kms_context: KMSContext
  - developer.skill_level: str

output:  # Module 2와 동일 패턴
  - analysis_results: [AgentResult]   (기존 목록에 추가)
  - issues: [IssueItem]               (기존 목록에 추가)
  - module_id: "module_3"
  - status: AgentStatus

# Output Contract (AgentResult 형식)
agent_result:
  agent_name: "TestVerificationAgent | PerformanceAgent"
  module_id: "module_3"
  # 나머지 필드는 Module 2와 동일 구조

# M3VerifyResponse 추가 필드 (additive · optional · 기본 None — 2026-06-09, 7D)
#   metrics: dict | None = None
#   - test_verification 응답에 측정 지표를 담는다. 예: {"coverage_line": 0.72}
#     (coverage_line/branch/func 는 0~1 분수). PR 코멘트 '📊 지표 줄' 렌더용.
#   - 하위호환: 미설정(None)이면 기존 소비자(m1 오케스트레이터·m4)는 그냥 무시.
#     기존 호출자 회귀 없음 — 새 필드를 안 읽으면 동작 동일.

required_state_fields:
  - task_id
  - trace_id
  - pr_context

uses_kms: true       # KMS에서 테스트 가이드, 성능 패턴 chunk 조회
uses_langsmith: true

validation_rule:
  - 1차: AgentResult Pydantic 검증
  - 2차: 커버리지 수치 0~100 범위 확인
  - 3차: N+1 감지 근거 라인 번호 존재 여부

retry_rule:  # Module 2와 동일
  - 타임아웃(30초): make_timeout_result() 반환
  - LLM JSON 파싱 실패: 1회 재시도

error_rule:  # Module 2와 동일
  - 타임아웃: 빈 AgentResult 반환
  - 분석 실패: status=fail + error_message 기록
```

---

## Module 4 — 커리큘럼 에이전트

```yaml
module_id:    module_4_curriculum
module_name:  커리큘럼 에이전트 (Evaluator + Feedback Loop)
responsibility: >
  Module 2/3 결과를 취합하여 3-Way 판정(lgtm/rework/escalate)을 내리고
  GitHub 코멘트 작성, Slack 에스컬레이션, 커리큘럼 생성을 수행한다.
  반복 실수 패턴을 감지하여 pr_reviews에 기록하고 학습 자료를 추천한다.

input:  # PlatformState에서 읽기
  - task_id: str
  - trace_id: str
  - analysis_results: List[AgentResult]   (Module 2/3 결과 목록)
  - issues: List[IssueItem]               (전체 이슈 목록)
  - developer: DeveloperInfo              (학습 추천 개인화)
  - kms_context: KMSContext               (이전 PR 이슈 참조)

output:
  - verdict: "lgtm | rework | escalate"
  - comment_body: str                     (GitHub 코멘트 마크다운)
  - learning_resources: List[dict]        (학습 자료 목록)
  - onboarding_update: dict               (pr_reviews 갱신 데이터)
  - escalation:
      required: bool
      slack_channel: str | null
      message: str | null
  - module_id: "module_4"
  - status: AgentStatus
  - next_agent: null

# 판정 로직 (고정 규칙, LLM 임의 변경 금지)
verdict_rule:
  - analysis_results.summary.critical >= 1  →  escalate
  - analysis_results.summary.major >= 3     →  rework
  - 나머지                                   →  lgtm

required_state_fields:
  - task_id
  - trace_id
  - analysis_results
  - developer

uses_kms: true       # 학습 자료 chunk 조회, 이전 PR 이슈 패턴 검색
uses_langsmith: true

validation_rule:
  - 1차: verdict 값이 "lgtm | rework | escalate" 중 하나인지 확인
  - 2차: Critical >= 1인데 verdict != "escalate"이면 강제 수정
  - 3차: comment_body 마크다운 형식 최소 검증 (빈 문자열 금지)

retry_rule:
  - LLM 코멘트 생성 실패: 기본 템플릿으로 대체 (재시도 없음)
  - Slack 알림 실패: 로그만 남기고 계속 진행
  - GitHub 코멘트 작성 429: 60초 대기 후 1회 재시도

error_rule:
  - GitHub API 401/403: Slack 에스컬레이션 + status=fail
  - Slack 알림 실패: 경고 로그만, 파이프라인 중단 없음
  - pr_reviews INSERT 실패: 경고 로그, 계속 진행 (비필수 기록)

# 자동 머지 절대 금지
auto_merge: false    # 시니어 최종 승인은 항상 사람이 한다
```

**→ Frontend / GitHub / Slack 출력 형식:**
```json
{
  "task_id": "uuid",
  "pr_id": "42",
  "verdict": "lgtm | rework | escalate",
  "comment_body": "## 코드 리뷰 결과\n...",
  "learning_resources": [
    { "title": "N+1 쿼리 방지 가이드", "url": "notion://..." }
  ],
  "escalation": {
    "required": true,
    "slack_channel": "#team-security",
    "message": "Critical: SQL 인젝션 발견 — PR #42"
  },
  "onboarding_update": {
    "issue_pattern": "N+1 쿼리",
    "occurrence_count": 3
  }
}
```

---

## Module 5 — 독립 GraphDB + YouTube 추천

```yaml
module_id:    module_5_graph_youtube
module_name:  독립 GraphDB + YouTube 추천
responsibility: >
  별도 웹 UI에서 문서를 업로드받아 엔티티/관계를 추출하고
  Neo4j Aura에 저장한다. 키워드 기반 YouTube 영상을 추천한다.
  현재 Module 0~4와 독립적으로 동작하나, doc_id/file_hash를
  공통 키로 보존하여 향후 KMS 연결이 가능하도록 설계한다.

input:
  - file: multipart/form-data
  - source_system: "graph_youtube"  (고정값)

output:  # Module5State 형식 (PlatformState와 독립)
  - doc_id: str (UUID, 반드시 생성)
  - file_hash: str (SHA-256)
  - source_system: "graph_youtube"
  - original_filename: str
  - entities: List[dict]
  - relations: List[dict]
  - keywords: List[str]
  - recommend_query: List[str]
  - youtube_results: List[dict]
  - status: "stored | failed"

required_state_fields: []  # 독립 파이프라인

uses_kms: false            # MVP에서 KMS 연결 없음
                           # 향후: doc_id/file_hash로 KMS 매칭 가능
uses_langsmith: true

validation_rule:
  - 1차: doc_id, source_system, original_filename 존재 여부
  - 2차: entities 목록이 비어있지 않은지 확인
  - 3차: youtube_results URL 형식 유효성 확인

retry_rule:
  - 엔티티 추출 실패: 1회 재시도 후 빈 목록 반환
  - Neo4j 저장 실패: 1회 재시도 후 status=failed
  - YouTube API 실패: 빈 목록 반환, 파이프라인 중단 없음

error_rule:
  - Neo4j 연결 실패: status=failed, error_message 기록
  - YouTube API 429: 빈 목록 반환 (알림 없음)
  - 파일 파싱 실패: status=failed 즉시 반환

kms_extension_points:
  - doc_id: 향후 KMS documents 테이블의 doc_id와 매칭 가능
  - file_hash: KMS의 동일 문서 중복 감지 + 연결 기준
  - 향후 추가 예정: chunk_id, embedding, pgVector 연결
```

---

## 모듈 간 연결 흐름 요약

```
GitHub Webhook
    │
    ▼
Module 1 (Orchestrator)
    ├── pgVector 검색 (Module 0 KMS 활용)
    │
    ├── asyncio.gather([
    │       Module 2 (정적분석 + 보안),
    │       Module 3 (테스트 + 성능)
    │   ])
    │       각 모듈이 analysis_results에 AgentResult 추가
    │
    └── Module 4 (커리큘럼)
            ├── analysis_results 취합 → 3-Way 판정
            ├── GitHub 코멘트 작성
            ├── Slack 에스컬레이션 (Critical 시)
            └── pr_reviews + 학습 추천

Module 5 (독립)
    ← 별도 웹 UI에서 독립 실행
    → Neo4j Aura 저장
    → YouTube 추천
    → doc_id / file_hash 보존 (향후 KMS 연결 준비)
```

---

## 계약 변경 절차

1. 이 문서의 해당 모듈 계약을 수정한다.
2. PR description에 "CONTRACT CHANGE: module_{N} output 변경" 명시.
3. 영향받는 모듈 담당자에게 직접 공지한다.
4. 영향받는 모듈의 테스트를 함께 업데이트한다.
5. CLAUDE.md 섹션 5 (Output Contracts)도 동기화한다.
