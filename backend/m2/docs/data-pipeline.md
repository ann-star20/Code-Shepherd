# m2 데이터 파이프라인 — webhook 진입부터 출력까지

> 작성일: 2026-06-13
> 대상 코드: `backend/m2/app/`
> 현재 채택 경로: **m2 mini-orchestrator** (m1 오케스트레이터 미채택)

---

## 1. 전체 흐름 개요

```
GitHub
  │  PR 이벤트(opened/synchronize 등)
  │  HMAC-SHA256 서명 포함
  ▼
POST /webhook/github          webhook.py:70
  │  서명 검증 → action 필터
  │  _build_request()  → M2OrchestrateRequest (pr_diff="")
  │
  ├─ github_client.fetch_diff(diff_url)
  │    └─ GET <diff_url>  헤더: Accept: application/vnd.github.v3.diff
  │       Authorization: Bearer $GITHUB_TOKEN  (있으면)
  │       → unified diff 문자열 주입
  │
  ▼
run_m2_orchestration(req)     orchestrator.py:77
  │
  ├─ decision.decide(pr_diff)
  │    입력: unified diff 전체
  │    출력: AnalysisDecision
  │          needs_static / needs_security / skip
  │          판단 기준:
  │            ① 지원 소스(.py/.js/.ts/.tsx/.jsx) 없음 → skip
  │            ② 보안 키워드/의존성 파일 변경 감지 → security_signal=True
  │            ③ 지원 소스 있음 → 정적+보안 모두 실행(기본)
  │
  ├─ [순차 실행]
  │   ├─ needs_static  → run_single_agent(payload, "static_analysis")
  │   │     analyzer.analyze(pr_diff, "static_analysis")
  │   │       └─ _parse_diff() → 임시 파일 기록
  │   │       └─ Python: Pylint(SA-) + Radon(SA-)
  │   │          JS/TS:  ESLint(JS-)
  │   │          (타임아웃 30s, 도구 없으면 graceful skip)
  │   │     → (issues, summary, execution_ms)
  │   │     → DB: scan_executions INSERT → scan_id
  │   │            scan_issues   INSERT (이슈별 1행)
  │   │            scan_summaries INSERT/UPSERT
  │   │
  │   └─ needs_security → run_single_agent(payload, "security_scan")
  │         analyzer.analyze(pr_diff, "security_scan")
  │           └─ Python: Bandit(SEC-) + Semgrep(OWASP-)
  │              JS/TS:  Semgrep(OWASP-)
  │              ※ Semgrep은 Windows 미지원 → graceful skip
  │         → DB: 동일 패턴 (scan_executions / scan_issues / scan_summaries)
  │
  ├─ result_persist.persist_issues()      services/result_persist.py
  │    조건: M2_PERSIST_ENABLED=true + DATABASE_URL 설정 시에만 활성
  │    대상: review_issue 테이블 (m4 소유)
  │    매핑:
  │      severity:  Critical→critical / Major→high / Minor→medium
  │      keyword:   SEC-/OWASP-→"security" / SA-/JS-→"static"
  │      pull_request_id: users.github_id 서브쿼리로 JOIN 해소
  │    실패 시: 0 반환, 분석 결과에 영향 없음 (graceful)
  │
  ├─ result_mapper.build_m4_request()     services/result_mapper.py
  │    AgentResult × 2 → M4EvaluateRequest
  │      static_analysis  = M2AnalyzeResponse(static 결과)
  │      security_scan    = M2AnalyzeResponse(security 결과)
  │      test_verification = None  (m3 자리, Phase 2 전)
  │      performance       = None  (m3 자리, Phase 2 전)
  │
  ├─ m4_client.evaluate(m4_req)           clients/m4_client.py
  │    POST {M4_URL}/evaluate  timeout=30s
  │    M4_URL / M4_BASE_URL 환경변수로 지정
  │    → M4EvaluateResponse { verdict, comment_body }
  │    실패·미설정 시: None 반환 (graceful, m4_called=False)
  │
  └─ M2OrchestrateResponse 반환
       { task_id, pr_id, status,
         ran_agents, static_analysis, security_scan,
         m4_called, verdict, comment_body, persisted, trace_id }
```

---

## 2. m0 (KMS) ↔ m2 연결 현황

| 항목 | 현재 상태 |
|------|-----------|
| 직접 연결 | **없음** |
| 설계상 연결 채널 | `M2AnalyzeRequest.context: AnalysisContext` |
| AnalysisContext 필드 | `architecture_docs[]`, `coding_conventions`, `previous_pr_issues[]` |
| 현재 app/ 사용 여부 | **미사용** — `analyzer.py`는 `pr_diff`만 사용, context 무시 |

### 향후 연결 시나리오 (미구현)

```
m0 KMS (pgVector)
  └─ 아키텍처 문서 유사도 검색 (context: architecture_docs)
  └─ 과거 PR 이슈 조회         (context: previous_pr_issues)
        │
        ▼ M2OrchestrateRequest.context 주입
  m2 mini-orchestrator
        │
        ▼ analyzer.py 수정 필요
  RAG 보강 분석 (현재: pr_diff만, 미래: context 활용)
```

> m0→m2 연결을 구현하려면 `app/analyzer.py`에서 `context` 필드를 실제로 읽도록 수정 필요.

---

## 3. 입력 데이터 구조

### 3-1. webhook 경로 입력 (GitHub → m2)

```
GitHub PR 웹훅 payload
├── action:          "opened" | "reopened" | "synchronize" | "ready_for_review"
├── pull_request
│   ├── id           → M2OrchestrateRequest.pr_id
│   ├── number       → M2OrchestrateRequest.pr_number
│   ├── diff_url     → github_client.fetch_diff() 호출
│   └── user.login   → DeveloperProfile.id
└── repository
    └── full_name    → M2OrchestrateRequest.repository
```

### 3-2. 직접 호출 경로 입력 (POST /orchestrate/review)

```python
M2OrchestrateRequest {
    task_id:    str          # UUID
    pr_id:      str          # GitHub PR ID
    pr_diff:    str          # unified diff 본문 (호출자가 직접 제공)
    repository: str | None   # "owner/repo"
    pr_number:  int | None
    context:    AnalysisContext    # 현재 미사용 (m0 연결 예정)
    developer:  DeveloperProfile | None
    trace_id:   str | None
}
```

---

## 4. DB 쓰기 테이블 목록

| 테이블 | 소유 모듈 | 쓰기 조건 | 파일 |
|--------|----------|----------|------|
| `scan_executions` | m2 | 항상 (분석 실행 시) | `app/db.py` |
| `scan_issues` | m2 | 이슈 있을 때 | `app/db.py` |
| `scan_summaries` | m2 | 항상 (UPSERT) | `app/db.py` |
| `review_issue` | m4 | `M2_PERSIST_ENABLED=true` 시만 | `app/services/result_persist.py` |

---

## 5. 외부 연결 요약

| 방향 | 프로토콜 | 엔드포인트 | 인증 | 실패 처리 |
|------|---------|-----------|------|----------|
| m2 ← GitHub | HTTPS (webhook) | `POST /webhook/github` | HMAC-SHA256 `GITHUB_WEBHOOK_SECRET` | 401 반환 |
| m2 → GitHub | HTTPS GET | `{diff_url}` | `Authorization: Bearer $GITHUB_TOKEN` | status="skip" |
| m2 → m4 | HTTP POST | `{M4_URL}/evaluate` | 없음 (내부망) | m4_called=False |
| m2 → PostgreSQL | asyncpg | `DATABASE_URL` | 연결문자열 내 자격증명 | graceful (로그만) |

---

## 6. 환경변수 참조

| 변수 | 용도 | 없을 때 동작 |
|------|------|------------|
| `GITHUB_WEBHOOK_SECRET` | 웹훅 서명 검증 | 검증 생략 (개발모드) |
| `GITHUB_TOKEN` | diff fetch 인증 | 미인증 요청 (퍼블릭 repo만 가능) |
| `M4_URL` / `M4_BASE_URL` | m4 evaluate 호출 | m4 호출 건너뜀 |
| `DATABASE_URL` | scan 테이블 저장 | DB 저장 실패 (로그만) |
| `M2_PERSIST_ENABLED` | review_issue 저장 활성 | 기본 비활성 |
