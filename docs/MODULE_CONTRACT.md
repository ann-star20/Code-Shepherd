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

## Module 6 — 외부 문서 지식 그래프 (M6, HTTP API)

```yaml
module_id:    module_6_knowledge_graph
module_name:  외부 문서 지식 그래프 파이프라인 (FastAPI + Celery + Neo4j)
responsibility: >
  외부 문서 URL을 입력받아 Prescan→Crawl→Extract→HITL→WriteGraph
  5단계 파이프라인을 비동기로 수행하고, HITL 승인 후 Neo4j에
  Concept 그래프를 구축한다. PlatformState와 독립된 별도 FastAPI
  서비스이며, 프론트엔드는 Vite 프록시 `/m6-api` → `m6:8007`로 접근한다.

# PlatformState 기반이 아닌 독립 HTTP 서비스이므로
# input/output은 PlatformState 필드가 아닌 HTTP 요청/응답 형식으로 정의한다.
endpoints:
  - POST /documents/check-duplicate
      request:  { url: HttpUrl }
      response: { is_duplicate: bool, doc_id: str | null }

  - POST /documents/metadata/learn
      request:  { framework: str, pattern: str, supported_langs: [str], default_lang: str | null }
      response: { framework: str, status: "learned" }

  - POST /pipeline/trigger          (202)
      request:  { doc_id: HttpUrl }   # 문서 원본 URL
      response: { session_id: str, message: str }
      side_effect: Celery chain (prescan|crawl|extract) 비동기 시작

  - GET /pipeline/stream/{session_id}   (SSE, text/event-stream)
      events: connected | log | step_update | heartbeat | finished
      channel: Redis pub/sub "pipeline:{session_id}"

  - GET /staging/{session_id}
      response: { items: [StagingConcept] }
      # StagingConcept = GraphNode + { staging_id, state }
      # GraphNode = { id, name, status, domains, infer_action?, infer_confidence?,
      #               target_concept_name?, cwe_id?, owasp_id?, severity?,
      #               description_ko?, aliases?, mechanisms? }
      # status: infer_action in (MERGE, RELATED_TO) → "MERGE_PENDING", else "DRAFT"

  - GET /staging/{session_id}/diff
      response: { draft: int, approved: int, committed: int }   # DiffSummary

  - POST /staging/{id}/approve      (200)
      # id가 staging_concepts.id로 존재 → 단일 승인 (FOR UPDATE SKIP LOCKED)
      single_response: { id: str, state: "APPROVED" }   # 409 처리중, 400 DRAFT 아님
      # id가 존재하지 않으면 session_id로 간주 → 세션 일괄 승인
      bulk_response:   { session_id: str, approved: int }

  - POST /staging/{id}/reject       (200)
      single_response: { id: str, state: "REJECTED" }   # 400 DRAFT 아님
      bulk_response:   { session_id: str, rejected: int }

  - POST /staging/{session_id}/commit   (202)
      response: { session_id: str, status: "write_graph_triggered" }
      side_effect: write_graph_task.apply_async(args=[session_id])

  - GET /graph/topology
      response: { nodes: [GraphNode (status="COMMITTED")], edges: [{source, target, type}] }
      source: Neo4jConceptRepo.get_topology() — Concept 노드 + RELATED_TO 엣지

required_state_fields: []   # 독립 서비스, PlatformState 불사용
uses_kms: false
uses_langsmith: true        # LANGCHAIN_PROJECT=module6-{githubId}

validation_rule:
  - SQL은 전부 asyncpg 파라미터 바인딩 ($1, $2 ...) — f-string 조합 금지
  - staging 승인은 SELECT FOR UPDATE SKIP LOCKED로 이중 승인 방지
  - 3-Factor 점수(score_jaro_winkler/name_vector/desc_vector) 0.0 전부인 채로
    state=APPROVED 전이 금지 (schema.sql ★ 주의)

error_rule:
  - approve 409: 이미 처리 중이거나 존재하지 않는 staging 항목
  - approve/reject 400: DRAFT 상태가 아닌 항목
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
