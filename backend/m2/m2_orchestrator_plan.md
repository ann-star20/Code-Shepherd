# m2 오케스트레이터 구현 플랜 (vendoring 방식)

**작성일**: 2026-06-12 | **브랜치**: `feature/module2-static-security`
**기준 프롬프트**: [`m2_orchestrator_prompt.md`](m2_orchestrator_prompt.md)

## 구현 현황 (2026-06-12)

| Phase | 내용 | 상태 |
|-------|------|------|
| Phase 1 | m2 오케스트레이터 → m4 | ✅ 구현·테스트 완료 |
| Phase 0 | PR 웹훅 진입점 | ✅ 구현·테스트 완료 |
| Phase 3 | review_issue 영속화 | ✅ 구현·테스트 완료 (기본 비활성 opt-in, m4 매핑 합의 대기) |
| Phase 2 | m3 탐지기 vendoring 와이어링 | ⏳ 보류 (vendoring 스냅샷만 `d80611ae`로 고정됨) |

- 테스트: `pytest` 46 passed (decision/orchestrator/webhook/persist + 기존 contract/analyzer).
- 기존 `/analyze/static`·`/analyze/security`·`/health` 동작·계약 불변 확인.
- 영속화는 `M2_PERSIST_ENABLED` truthy + `DATABASE_URL` 있을 때만 실제 INSERT(공유 DB 보호).

---

## 0. 핵심 결정 사항 (확정)

| 항목 | 결정 | 이유 |
|------|------|------|
| m3 연결 방식 | **client 호출 ❌ → vendoring(스냅샷 포크) ✅** | m3가 폴더를 재구현 예정 → `/verify/tests`·`/analyze/performance` 엔드포인트가 바뀌면 client가 깨짐. m2가 사본을 소유하면 m3 변경과 무관해짐 |
| 구현 순서 | **Phase 1 먼저(m2→m4), Phase 2에서 m3 vendoring** | 무거운 m3/Docker를 뒤로 미뤄, 오케스트레이터 골격부터 정상 검증 |
| m4 전달 형식 | 기존 **`M4EvaluateRequest`(named 필드)** → `/evaluate` | 공유 계약(`shared/contracts.py`) 무수정·가장 안전. `analysis_results` 배열 ❌ |
| m3 백업 | **별도 백업 불필요** | git이 보존(현재 clean, 마지막 커밋 `87b1d1af`). vendoring 시 m2 트리로 복사+커밋하면 영구 고정 |
| 결과 영속화 타깃 | **`review_issue` 테이블 (m4 소유)** | m4가 INSERT 코드를 직접 제공 → 사실상 합의됨. FK는 `github_id` 서브쿼리로 해결 |
| PR 트리거 진입점 | **(b) m2가 PR 웹훅을 직접 수신 ✅** | 설계가 "모듈별 end-to-end"로 전환 → m1 미경유. m2에 webhook/trigger 엔드포인트 신설 |

### 불변식 (절대 깨지 않음)
- 기존 `/health`, `/analyze/static`, `/analyze/security` 유지·동작 결과 불변
- 기존 `AgentResult` 계약·기존 테스트 보존
- `shared/contracts.py`, `docs/`, m1/m3/m4 코드 **수정 금지**
- 외부 연결(m0/KMS/m4) 실패로 m2 분석 자체가 중단되지 않음 (graceful fallback)

---

## Phase 1 — m2 오케스트레이터 → m4 구동 (m3 없이)

목표: `pr_diff` 입력 → m2 자체 2개 분석 → m4 `/evaluate` 응답까지 end-to-end로 도는 뼈대 확인.
m3 자리(`test_verification`/`performance`)는 `None`으로 비워둠.

### 신규 파일
```text
app/orchestrator.py            # run_m2_orchestration(): decision → analyzer 2개 → mapper → m4
app/decision.py                # 확장자/보안키워드/의존성파일 판단 + skip
app/clients/m0_client.py       # M0_BASE_URL, 없으면 graceful fallback (지금은 빈 context)
app/clients/kms_client.py      # KMS_BASE_URL, 없으면 graceful fallback (지금은 빈 context)
app/clients/m4_client.py       # M4_BASE_URL → POST /evaluate, 실패 시 분석결과만 반환
app/services/context_builder.py  # m0+KMS 조합 (지금은 패스스루)
app/services/result_mapper.py    # AgentResult 2개 → M4EvaluateRequest(named 필드) 변환
```

### 수정 파일
```text
app/main.py        # POST /orchestrate/review 추가 (기존 엔드포인트 보존)
app/contract.py    # M2OrchestrateRequest / M2OrchestrateResponse 추가
```

### 실행 흐름 (run_m2_orchestration)
```text
M2OrchestrateRequest
  ▼ decision.py            분석 필요 여부 (skip 가능)
  ▼ skip → status="skip" 반환
  ▼ m0_client / kms_client context 시도 (실패 시 error_message에 기록)
  ▼ analyzer.analyze() 재사용 → static_analysis (AgentResult)
  ▼ analyzer.analyze() 재사용 → security_scan (AgentResult)
  ▼ result_mapper → M4EvaluateRequest (test/perf = None)
  ▼ m4_client → /evaluate (실패해도 분석결과는 응답 포함)
  ▼ M2OrchestrateResponse 반환
```

### 테스트
1. Python 파일 변경 → `needs_static_analysis=true`
2. 보안 키워드 → `needs_security_scan=true`
3. `docs`/`README`/`.md`만 → `status="skip"`
4. `/orchestrate/review`가 analyzer 호출 + m4 응답 포함 반환
5. `M0/KMS/M4_BASE_URL` 미설정 시 graceful fallback
6. 기존 `/analyze/static`·`/analyze/security` 테스트 계속 통과

### 완료 기준
- `/orchestrate/review`에 `pr_diff`만 줘도 static/security 채워지고 m4 verdict 포함 응답
- `M4_BASE_URL` 없을 때 분석결과만으로 정상 반환(fallback)

---

## Phase 2 — m3 탐지기 vendoring (m2로 스냅샷 복사)

목표: 현재 m3 탐지기 로직을 m2 트리로 복사해 `test_verification`/`performance` 2개를 m2 내부에서 직접 실행.
m3 폴더와 완전히 독립.

### 0) 스냅샷 고정 (선행, 안전장치)
- 필요한 m3 파일을 `backend/m2/app/vendor/m3_detectors/`(가칭)로 복사 + **m2 브랜치에 커밋**
- 복사 출처 SHA `87b1d1af` 기록

### vendoring 범위 (가벼운 것부터)
| 단계 | 탐지기 | 필요 인프라 | 비고 |
|------|--------|-------------|------|
| 2a (권장 시작) | `performance/complexity`, `performance/nplus1` | repo 파일 AST | **Docker 불필요** |
| 2b | `test_verification/missing_funcs` | coverage.json | Docker 권장 |
| 2c (선택·최후) | `test_verification/coverage` | **Docker 샌드박스 pytest** | 가장 무거움 |
| 제외 | `rag/*`, `enrich/code_context`(LLM) | BGE-M3·LLM | 기본 off / 빈 값 degrade |

함께 가져와야 할 보조 모듈: `contracts.py`(AgentOutput/Issue), `assemble/output.py`,
`filter/diff_filter.py`, `enrich/framework.py`, `harness.py`(stub 가능).

### repo_path 확보 (git clone 회피 검토)
- m2 `analyzer.py`의 `_materialize`(diff → 변경파일 temp 디렉토리 복원)를 재사용해
  그 디렉토리를 탐지기 `repo_path`로 전달 → **git clone 생략 가능 (검증 필요)**
- 단 `coverage`(2c)는 전체 repo + 테스트 실행이라 clone+Docker 필요 → 도입 시점에만

### 의존성/충돌 처리
- `app/contract.py` vs vendored `contracts.py` **동명 충돌** → 패키지 네임스페이스로 격리(`vendor/m3_detectors/contracts.py`를 상대 import로만 사용)
- 신규 파이썬 의존성은 vendoring한 탐지기가 실제 쓰는 것만 추가(2a는 표준 라이브러리/AST 위주 → 최소)

### 연결
- `orchestrator.py`에서 `needs_*`에 따라 vendored `run()` 호출 → `AgentResult`로 매핑
- 결과를 `result_mapper`가 `M4EvaluateRequest.test_verification`/`.performance`에 채움

### 완료 기준
- m3 폴더를 건드리지 않고 m2 단독으로 4개(static/security/test/performance) 결과 산출
- m3 폴더가 바뀌어도 m2 동작 불변

---

## Phase 3 — 결과 영속화: `review_issue` INSERT (m4 제공)

목표: m2 분석 결과(IssueItem)를 m4 소유 `review_issue` 테이블에 저장 → m4 학습카드/프론트가 읽음.
m4가 INSERT 패턴을 직접 제공 → 타깃·FK 해결 방식 확정.

### m4 제공 INSERT (FK는 github_id 서브쿼리로 해결)
```sql
INSERT INTO review_issue (
    id, pull_request_id, user_id, github_id, agent,
    severity, keyword, sub_category, code_context,
    code_snippet, suggestion, programming_language,
    framework, framework_version, name_of_function
)
VALUES (
    :id,
    (SELECT pr.id FROM pull_requests pr
     JOIN users u ON u.user_id = pr.user_id
     WHERE u.github_id = :github_id ORDER BY pr.submitted_at DESC LIMIT 1),
    (SELECT user_id FROM users WHERE github_id = :github_id),
    :github_id, :agent, :severity, :keyword, :sub_category, :code_context,
    :code_snippet, :suggestion, :programming_language,
    :framework, :framework_version, :name_of_function
)
```
> **반드시 파라미터 바인딩** (`:name`). 팀 규칙(f-string SQL 금지) + code_snippet/suggestion에
> 따옴표·개행·PII가 포함되어 문자열 조합 시 깨지거나 인젝션 위험.

### m2가 채울 컬럼 매핑 (IssueItem → review_issue)
| review_issue | 출처 | 비고 |
|--------------|------|------|
| `id` | `uuid4()` | m2 생성 |
| `pull_request_id` | 서브쿼리(github_id) | m2는 값 안 만듦 |
| `user_id` | 서브쿼리(github_id) | m2는 값 안 만듦 |
| `github_id` | `developer_id` | M2OrchestrateRequest.developer_id |
| `agent` | `static_analysis` / `security_scan` | m2 agent |
| `severity` ⚠️ | **매핑 필요** | Critical/Major/Minor → critical/high/medium/low (CHECK 제약) |
| `keyword` ⚠️ NOT NULL | **규칙 필요** | 예: security_scan→`security`, static_analysis→`static`(또는 rule_id 접두사별) |
| `sub_category` | IssueItem.message(요약) 또는 rule_id | 선택 |
| `suggestion` | IssueItem.suggestion | 그대로 |
| `code_context` `code_snippet` `programming_language` `framework` `framework_version` `name_of_function` | (m2 미보유) | nullable → null 허용 |

> NOT NULL은 `severity`·`keyword`(+`id`)뿐. 나머지는 null 가능 → m2가 못 만드는 필드는 비움.

### 미결 결정 (구현은 잠정값으로 진행 — m4 합의 후 고정)
1. **severity 매핑**: 잠정 `Critical→critical / Major→high / Minor→medium` (low 미사용)으로 구현됨.
   `result_persist._SEVERITY_MAP` 한 곳. **m4 통계 기준과 합의 후 확정**.
2. **keyword 규칙**: 잠정 rule_id 접두사 기반 — `SEC-/OWASP-→security`, `SA-/JS-→static`,
   fallback은 agent 도메인. `result_persist._KEYWORD_BY_PREFIX`. **m4 통계 키와 정렬 필요**.
3. **DB 연결**: `DATABASE_URL`(asyncpg) 사용, async SQLAlchemy. **기본 비활성** —
   `M2_PERSIST_ENABLED`=truthy일 때만 실제 INSERT(공유 클라우드 DB 사고 방지).

### 신규/수정 (예정)
```text
[신규] app/clients/db_client.py 또는 app/services/result_persist.py  # review_issue INSERT (파라미터 바인딩)
[수정] app/orchestrator.py   # 분석 후 persist 호출 (실패해도 분석결과 반환 — graceful)
[수정] m2/pyproject.toml      # psycopg2-binary 등 DB 드라이버 추가
```

> **크로스모듈 주의**: review_issue·pull_requests·users는 타 모듈 소유. m4가 INSERT를 제공했더라도
> severity 매핑·keyword 규칙은 m4와 문서로 합의 후 고정한다(통계 깨짐 방지).

---

## Phase 0 — PR 웹훅 트리거 진입점 신설 (확정: (b))

설계가 "모듈별 end-to-end"로 전환 → m1을 안 거치고 **m2가 GitHub PR 웹훅을 직접 수신**한다.
즉 m2가 "정적분석/보안분석 도메인의 독립 진입점"이 된다. Phase 1의 오케스트레이터를 호출하는 **입구**.

### 신규 엔드포인트
```http
POST /webhook/github     # GitHub PR 웹훅 수신 (또는 /triggers/pr)
```
역할:
1. GitHub PR 이벤트 수신 (`opened`/`synchronize` 등 action 필터 — 그 외 무시)
2. **웹훅 서명 검증** (`X-Hub-Signature-256`, `GITHUB_WEBHOOK_SECRET`) — 인증 경계
3. payload에서 `pr_id`/`repository`/`developer(github_id)`/`diff_url` 추출
4. **diff 본문 fetch** (diff_url 1회 — 기존 m1이 하던 역할을 m2가 흡수)
5. `M2OrchestrateRequest` 구성 → `run_m2_orchestration()` 호출 (Phase 1)
6. 응답: 즉시 accepted(202) 또는 동기 결과 — 처리 모델 결정 필요

### 신규/수정 (예정)
```text
[신규] app/routers/webhook.py 또는 main.py 내 라우트   # 웹훅 수신·서명검증·diff fetch·orchestrator 호출
[수정] app/main.py                                      # 라우트 등록
[수정] m2/pyproject.toml                                # diff fetch용 httpx (이미 test extra에 있음 — 런타임 의존 승격 검토)
[설정] docker-compose / GitHub repo 웹훅 URL            # m2(8003)로 웹훅 전달되게 등록
```

### 미결 결정 (구현 전)
1. **payload 형식**: GitHub 원본 웹훅 JSON을 직접 받나, 아니면 게이트웨이가 정규화한 `PRTriggerPayload` 형태인가? (m3 webhook-gateway 참고)
2. **처리 모델**: 웹훅에 즉시 202 반환 후 백그라운드 처리 vs 동기 처리 후 결과 반환.
3. **diff 소스**: `diff_url` fetch(원본 웹훅엔 diff 본문 없음) vs payload에 본문 포함.
4. **인증**: `GITHUB_WEBHOOK_SECRET` env로 서명 검증 (필수 — 외부 입력 경계).

> **순서**: Phase 1(오케스트레이터)이 먼저 있어야 웹훅이 호출할 대상이 생긴다.
> 따라서 **Phase 1 → Phase 0(웹훅 입구) → Phase 3(영속화)** 순으로 얹는 게 자연스럽다.

---

## 리스크 / 메모
- vendoring = **현재 시점 포크**. 이후 m3 탐지기 개선은 m2에 자동 반영 안 됨(= 의도된 decoupling).
- `coverage`(2c)의 Docker-in-Docker·권한(컨테이너 root가 만든 `coverage.json` 회수) 이슈가 최대 난관 → 최후에, 선택적으로.
- 무거운 부분은 전부 Phase 2c에 격리됨. Phase 1·2a는 Docker/ML 없이 동작.

## 문서 반영 필요 사항 (공통 문서 — 본 작업 범위 아님)
- 공통 `docs/`는 수정하지 않음. 변경 필요사항은 본 m2 내부 문서/`MODULE_CONTRACT.md`에만 기록 후 통합 주간 합의.
