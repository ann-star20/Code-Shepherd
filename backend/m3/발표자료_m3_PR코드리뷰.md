# Module 3 — PR 코드리뷰 에이전트 (발표 자료)

> **한 줄 정의**: 개발자가 **PR(코드 변경 제안)을 올리면, 사람 리뷰어 대신 "테스트가 충분한가 / 성능에 문제는 없는가"를 자동으로 검사**해서, **합격/수정요청 판정 + 이슈 목록 + 사람이 읽을 코멘트**를 PR과 웹 화면에 돌려주는 모듈.**
>
> 대상 청중이 m3를 전혀 모른다는 전제로, **처음부터 끝까지** 풀어 썼습니다. 발표 시 §0 → §1 → §2 → §3 → §4 순서로 그대로 말하면 됩니다.

---

## 0. 30초 엘리베이터 피치 (먼저 이걸로 시작하세요)

- **문제**: 신입 개발자가 코드를 올려도, 시니어가 매번 "테스트 짰어? 이 반복문 느리지 않아?"를 일일이 봐주기 힘들다.
- **m3가 하는 일**: PR이 올라오는 **그 순간**, 코드를 자동으로 받아서
  1. **테스트 검증** — 테스트 커버리지가 충분한지, 테스트 안 된 함수가 있는지
  2. **성능 점검** — 반복문 안에서 DB를 N번 부르는지(N+1), 중첩 루프가 너무 깊은지(복잡도)
  를 검사하고,
- **결과물**: **판정(✅통과 / 🔧수정요청 / ⛔시니어검토)** + **이슈 표** + **한국어 코멘트**를 **GitHub PR에 댓글로** 달고 **웹 리뷰 화면**에도 띄운다.
- **핵심 차별점**: 숫자 판정(합격/탈락)은 **AI가 아니라 규칙**으로 정확하게 — **"가짜로 지어내지 않는다(환각 0)"** 가 설계 1원칙.

---

## 1. 설계 기획 (왜 이렇게 만들었나)

### 1-1. 팀 안에서 m3의 위치
우리 플랫폼은 모듈이 분업되어 있고, m3는 **PR 코드리뷰의 "테스트·성능" 담당 + 최종 리뷰 코멘트 소유자**입니다.

```
GitHub PR 이벤트
      │
      ▼
[m1] 오케스트레이터  ── 웹훅 수신·서명검증, 각 모듈에 일감 분배
      │
      ├─→ [m2] 정적분석·보안   (다른 분 담당)
      └─→ [m3] 테스트·성능 ★ 우리 파트
              │
              ▼
        [m3] /review  ── 4개 결과(m2 정적·보안 + m3 테스트·성능)를 모아
                          판정 → 코멘트 작성 → GitHub 게시 → 저장
              │
              ▼
        [Frontend] 리뷰 페이지  ── 사람이 화면으로 결과 확인
```

> **포인트**: m3는 "검사(테스트·성능)"만 하는 게 아니라, **m2까지 포함한 모든 결과를 모아 최종 판정과 코멘트를 내는 "리뷰 종합" 역할**까지 소유합니다. (코멘트·판정의 주인 = m3)

### 1-2. 설계 3원칙 (이게 곧 차별점)
1. **정직성(환각 금지)** — 측정 못 한 값은 빈칸으로 둔다. **가짜 숫자·가짜 인용·가짜 링크를 절대 만들지 않는다.** 실패하면 조용히 빈 결과로 넘어간다(PR 흐름을 막지 않음).
2. **숫자 판정은 규칙으로, 설명은 AI로** — 커버리지 80% 같은 **합격/탈락 기준은 AI가 아니라 구조화된 규칙**으로 본다(AI가 80%를 79%로 잘못 읽으면 재앙). AI는 **"왜 이 판정인지 한 줄 설명"** 같은 **정성적 부분에만** 좁게 쓴다.
3. **부분 실패 허용** — 탐지기 하나가 죽어도 나머지는 돈다. Docker가 없어도 직접 실행으로 우회. DB가 죽어도 로컬 저장으로 우회.

### 1-3. 왜 "완전 자율 AI 에이전트"가 아니라 "규칙 파이프라인 + 좁은 LLM"인가
- 코드리뷰의 합격/탈락은 **재현 가능하고 정확해야** 신뢰받습니다. 그래서 m3의 분석 본체는 **결정적(deterministic) 파이프라인**(AST 분석·커버리지 측정)입니다 — 같은 PR이면 항상 같은 결과.
- LLM은 **(a) 코멘트의 "왜 한 줄" 문장**, **(b) 엣지케이스 추론(확장 기능)** 처럼 **틀려도 안전한 정성 영역에만** 사용합니다.

---

## 2. 실제 작동 방식 (인풋 → 처리 → 아웃풋)

### 2-1. 전체 흐름 (실제 데모로 검증된 경로)

```
① PR 올림 (예: github.com/.../-dev3-demo PR #4)
② m1: 웹훅 수신 → 서명검증 → 즉시 "접수(202)" → 무거운 분석은 백그라운드로
        (GitHub는 10초 안에 답을 원하는데 분석은 13~41초 → 먼저 접수만 하고 뒤에서 처리)
③ m1 → m3 호출:
        - POST /verify/tests          (테스트 검증)
        - POST /analyze/performance   (성능 점검)
④ m3: 레포를 clone → 분석 → 이슈 목록 반환
⑤ m1 → m3 POST /review : m2·m3 결과 4개를 모아 → 판정 → 코멘트 → GitHub 게시 → 저장
⑥ Frontend: GET /review/{owner}/{repo}/{pr} 로 결과를 읽어 화면에 표시
```

### 2-2. 인풋 / 아웃풋 — 명확한 계약(Contract)

#### ▶ 인풋 1: 분석 요청 (m1 → m3, `POST /verify/tests` · `POST /analyze/performance`)
```jsonc
{
  "task_id": "고유 작업 id",
  "pr_id": "4",
  "pr_diff": "diff --git a/src/payment.py ...",   // PR의 변경 내용(본문)
  "clone_url": "https://github.com/kskt1234-netizen/-dev3-demo.git",
  "commit_sha": "27f5c96...",                      // 분석할 정확한 커밋
  "context": { ... },
  "trace_id": "관측(LangSmith) 연동용"
}
```

#### ▶ 아웃풋 1: 분석 결과 (m3 → m1, `M3VerifyResponse`)
```jsonc
{
  "task_id": "...",
  "agent": "test_verification",        // 또는 "performance"
  "issues": [
    {
      "severity": "Major",             // Critical / Major / Minor
      "rule_id": "TEST-001",
      "file": "src/payment.py",
      "line": null,
      "message": "테스트 라인 커버리지 26.7% < 기준 80%.",
      "suggestion": "테스트를 추가해 커버리지를 80% 이상으로 올리세요."
    }
  ],
  "summary": { "critical": 0, "major": 3, "minor": 3 },
  "metrics": { "coverage_line": 0.2667, "coverage_func": 0.3333 },  // 측정값만(가짜 0% 금지)
  "execution_ms": 7291
}
```

#### ▶ 인풋 2: 리뷰 종합 요청 (m1 → m3, `POST /review`)
```jsonc
{
  "repository": "kskt1234-netizen/-dev3-demo",
  "pr_number": 4,
  "static_analysis":  { ...m2 정적 결과... },
  "security_scan":    { ...m2 보안 결과... },
  "test_verification":{ ...m3 테스트 결과... },
  "performance":      { ...m3 성능 결과... }
}
```

#### ▶ 아웃풋 2: 리뷰 결과 (m3 → m1, `M3ReviewResponse`)
```jsonc
{
  "verdict": "rework",                 // lgtm / rework / escalate
  "comment_posted": true,
  "comment_url": "https://github.com/.../pull/4#issuecomment-4655042421",
  "persisted": true
}
```

#### ▶ 아웃풋 3: 화면용 조회 (Frontend ← m3, `GET /review/{owner}/{repo}/{pr}`)
```jsonc
{
  "found": true,
  "verdict": "rework",
  "comment": "## 🤖 코드 리뷰 — 🔧 수정 요청 ...",   // 마크다운 코멘트 전문
  "issues": [ { severity, file, line, rule_id, suggestion, rag_context }, ... ]
}
```

### 2-3. 실제 데모 결과 (이 숫자를 그대로 발표에 쓰세요)
데모 레포 `-dev3-demo` PR #4(일부러 버그를 심어둔 코드)를 실제로 돌린 결과:

| 항목 | 값 |
|---|---|
| 발견 이슈 | **6건** (테스트 4 + 성능 2) |
| 라인 커버리지 | **26.7%** (기준 80% 미달) |
| 최대 복잡도 | 2 |
| **최종 판정** | **🔧 rework (수정 요청)** |
| 코멘트 | GitHub PR에 실제 게시됨 + 웹 화면 표시됨 |

발견된 이슈:
- 🟡 `TEST-001` 커버리지 부족 ×2 (전체 + payment 모듈 사내기준 90%)
- 🔵 `TEST-004` 테스트 없는 함수 `get_payments` / `find_matching_transactions`
- 🟡 `PERF-002` 루프 안 DB 반복 호출(N+1) — `payment.py:8`
- 🔵 `PERF-001` 중첩 루프 복잡도 — `payment.py:21`

> **정직 caveat**: 위 6건은 **탐지기 4개 연결 시점**에 캡처한 실측입니다. 이후 **탐지기 6개 전체가 파이프라인에 연결**됐습니다(아래 §2-4). 추가된 2개(TEST-003 엣지케이스·PERF-003 메모리누수)는 **결정성 보장을 위해 데모/CI에서는 휴리스틱(무키) 모드로 동작**하며, 이 PR #4에는 추가 이슈를 내지 않았습니다. **6탐지기 기준의 정량 정확도(rule별 P/R/F1) 재측정은 다음 단계(SESSION 8B)** 입니다.

### 2-4. 탐지 규칙 카탈로그 — 탐지기 6개 전체 파이프라인 연결됨

**파이프라인에 연결(실제 작동 중) — `main.run()`에서 6개 모두 호출**

| 규칙 | 무엇을 잡나 | 어떻게 | 심각도 |
|---|---|---|---|
| **TEST-001** 커버리지 미충족 | 테스트가 커버하는 코드 비율이 기준 미만 | 실제 `pytest --cov` 측정값 비교 | Major |
| **TEST-003** 엣지케이스 누락 | 경계값·예외 경로 테스트 없음 | LLM 추론(키 있을 때) / 휴리스틱 폴백 | Minor |
| **TEST-004** 테스트 누락 | 한 번도 실행 안 된(=테스트 없는) 함수 | AST로 함수 본문 실행 흔적 확인 | Minor |
| **PERF-001** 시간복잡도 | 깊은 중첩 루프(O(n²)·O(n³)) | AST 루프 중첩 깊이 분석 (2중=Minor, 3중+=Major) | Minor/Major |
| **PERF-002** N+1 쿼리 | 반복문 안에서 DB 호출 반복 | AST로 루프 본문의 DB 메서드 호출 탐지 | Major |
| **PERF-003** 메모리 누수 | 닫히지 않는 리소스·전역 누적 | LLM 추론(키 있을 때) / 휴리스틱 폴백 | Minor |

> **결정성 정책**: 4개(TEST-001/004·PERF-001/002)는 AST·커버리지 기반이라 **항상 결정적**(같은 PR=같은 결과). 새로 연결된 2개(TEST-003·PERF-003)는 LLM 기반이라 키가 있으면 비결정적일 수 있어 — **데모/CI는 `GOOGLE_API_KEY` 없이 실행해 휴리스틱(결정적) 모드로 돌립니다.** "같은 PR이면 같은 판정"이 신뢰의 핵심이기 때문.

> **기준값(80%, 루프 깊이 등)은 "사내 규칙 DB(convention_policies)"에서 읽고, 못 읽으면 안전한 기본값으로 내려갑니다.** 결제(payment)·인증(auth) 모듈은 90%로 더 엄격, 레거시는 70%로 완화 — 팀이 기준을 바꾸면 코드 수정 없이 DB만 바꾸면 됨.

### 2-5. 판정 규칙 (aggregator)
모든 이슈를 모아 **(규칙ID·파일·줄) 기준으로 중복 제거** 후 개수로 판정:

| 조건 | 판정 | 의미 |
|---|---|---|
| Critical ≥ 1 | ⛔ **escalate** | 시니어 검토 필요 |
| Major ≥ 3 | 🔧 **rework** | 머지 전 수정 요청 |
| 그 외 | ✅ **lgtm** | 통과 |

---

## 3. 성능 (속도·자원·신뢰성)

### 3-1. 엔드포인트 통시간 (데모 PR #4, 실 GitHub 웹훅 경로에서 캡처)
| 단계 | 소요 |
|---|---|
| m2 정적 분석 | 63 ms |
| m2 보안 스캔 | 35 ms |
| **m3 테스트 검증** (clone + 커버리지 측정 포함) | **7,291 ms** |
| **m3 성능 점검** | **5,252 ms** |
| m3 /review (집계+코멘트+게시+저장) | 1,452 ms |
| **합계** | **≈ 14초** (레포 크기에 따라 13~41초) |

### 3-1b. 단계별 워터폴 — p50/p95 벤치마크 (SESSION 8A, **6탐지기 실측 완료**)
> ✅ **6탐지기 기준 재측정 완료 (2026-06-09, 컨테이너에서 실제 실행).** 이전 표는 4탐지기 시점이라 폐기. 재측정 결과 `edge_cases`·`memory_leak` 행이 실제로 찍힘 = **6탐지기 라이브 연결 경험적 증명.**
> 측정 환경: m3 컨테이너 내부 직접 실행, **5종 PR(3~90줄) × 3회 = N=15**, RAG ON(실 GCP pgvector), **무키=결정적 모드**. 산출물 `bench/리포트_6탐지기_무키.md`.

**① 무키(결정적) 모드 — 헤드라인 (N=15)**

| 단계 | p50 (ms) | p95 (ms) |
|---|---|---|
| parse_diff (diff 파싱) | 0.1 | 0.3 |
| coverage (커버리지) | 176.0 | 508.6 |
| missing_funcs (TEST-004) | 126.0 | 269.6 |
| **edge_cases (TEST-003)** | **48.4** | **188.5** |
| nplus1 (PERF-002) | 51.6 | 355.0 |
| complexity (PERF-001) | 42.9 | 151.4 |
| **memory_leak (PERF-003)** | **60.7** | **138.3** |
| framework (언어/프레임워크) | 18.6 | 67.8 |
| **rag (사내규칙 인용, 실 GCP)** | **7,677.3** | **22,559.4** |
| **end_to_end (전체)** | **16,530.3** | **36,718.5** |

- **병목 = `rag` (실 GCP pgvector 검색)와 그걸 포함한 `end_to_end`.** 순수 AST·휴리스틱 탐지기 6개(parse/coverage/missing/edge/nplus1/complexity/memory)는 모두 **p50 200ms 이하**로 빠름 — 시간은 거의 **RAG 임베딩+GCP 네트워크**에서 발생.
- **cold→warm 효과 매우 큼**: end_to_end는 **cold 210초**(첫 실행 BGE-M3 모델 로딩 포함) → warm 16.5초. RAG는 cold 105초 → warm 7.7초. 즉 **모델 로딩은 컨테이너당 1회성 비용**이고, 실 비용은 warm 기준으로 봐야 함.

**② LLM 모드 — 실 운영 참고치 (flash-lite, N=5, 쿼터 에러 0)**

| 단계 | p50 (ms) | 비고 |
|---|---|---|
| edge_cases_llm (LLM 호출분) | 1,340.3 | 실제 Gemini 호출 |
| enrich (code_context LLM) | 333.2 | 실제 Gemini 호출 |
| **edge_cases (전체)** | **4,466.7** | 무키 48ms → LLM 4.5초 (LLM 탐지기 실비용) |
| end_to_end (전체) | 19,888.0 | 무키 16.5초 + LLM 호출분 |

- **시사점**: TEST-003·PERF-003을 **LLM 모드로 돌리면 PR당 수 초가 더 붙음**(edge_cases가 48ms→4.5초). 그래서 데모/CI는 무키 휴리스틱(결정적·빠름)을 기본으로, LLM은 실 운영 옵션으로 두는 게 합리적.

- **측정 한계(정직)**: ① 실제 Docker 샌드박스 미실행(fixture coverage.json 사용), ② GitHub 실 clone·코멘트 게시·DB 저장 미포함, ③ **RAG 시간은 실 GCP 네트워크 변동이 커서**(p95가 p50의 3배) 알고리즘 고유 비용이 아니라 환경 의존, ④ N=15(무키)·N=5(LLM)로 통계적 유의성 낮음(추세 참고용). 실 운영 통시간 근거는 §3-1 엔드포인트 수치와 함께 보세요.

### 3-1c. 탐지 정확도 — rule별 Precision/Recall/F1 (SESSION 8B, **실측 완료**)
> ✅ **양성+음성 라벨셋으로 rule별 정확도 측정 완료 (2026-06-09, 컨테이너 실제 실행).** 이전엔 골든 1건으로 recall 100%·오탐 0%만 냈음 → 표본 1개·음성 케이스 없음·rule별 분해 없음이라 "제대로 된 정확도"라 부르기 약했음.
> 측정 환경: m3 컨테이너 내부 직접 실행, **무키(휴리스틱·결정적)·RAG off**. 매칭 = (rule_id, file) 멀티셋. 산출물 `validation/benchmark_report.md`, 재실행 1커맨드(`uv run python validation/benchmark.py`).
> **표본 5건 (양성 3 + 음성 2)** — 양성: 커버리지/N+1/복잡도/메모리누수 결함 코드, 음성: ① 진짜 깨끗한 코드 ② 엣지케이스 *이미 처리*한 코드. 라벨은 **사람이 rule 정의로 확정**(탐지기 출력 자동생성 금지 = 순환·가짜 금지).

| rule | TP | FP | FN | Precision | Recall | F1 |
|---|---|---|---|---|---|---|
| TEST-001 커버리지 | 1 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| **TEST-003 엣지케이스** | 5 | 1 | 0 | **0.833** | 1.000 | **0.909** |
| TEST-004 테스트누락 | 2 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| PERF-001 복잡도 | 2 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| PERF-002 N+1 | 2 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| PERF-003 메모리누수 | 2 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| **전체** | 14 | 1 | 0 | **0.933** | **1.000** | **0.966** |

- **합격 (전체 F1 0.966 ≥ 0.70, rule별 F1 ≥ 0.50)**. 미탐(FN) 0건 — 잡아야 할 결함은 다 잡음.
- **유일한 오탐(FP) = TEST-003 1건**, 음성 케이스 `neg_edge_handled`에서 발생. 이 코드는 0·음수·범위초과를 *이미 검증*하는데, 휴리스틱은 **인자명(price·rate)만 보고** 엣지케이스 누락으로 오판 → precision 0.833. **이게 "정직한 평가"의 핵심**: 약점을 숨기지 않고 rule별 표가 그대로 드러냄(TEST-003 휴리스틱은 보수적으로 많이 쏘는 경향).
- **음성 케이스가 핵심 가치**: 깨끗한 코드(`neg_clean`)엔 6탐지기 모두 0건 — "헛소리 안 한다"의 증거.
- **한계(정직)**: 표본 5건으로 통계적 유의성 낮음(추세·약점 식별용). TEST-003·PERF-003은 무키 휴리스틱 기준(LLM 모드는 비결정). 향후 라벨 확장 시 더 단단해짐.

### 3-1d. verdict(판정) 정확도 — 사람 기대 vs aggregate 산출 (SESSION 8C, **실측 완료**)
> ✅ **사람이 부여한 기대 verdict와 실제 `aggregate()` 산출 verdict의 일치율 측정 (2026-06-09, 컨테이너 실제 실행).** LLM 불필요·결정적·재현 가능(`uv run python validation/verdict_benchmark.py`, 산출물 `validation/verdict_report.md`).
> **표본 10건** = 8B 라벨셋 재사용(5) + 확장(5). expected_verdict는 **사람이 시나리오를 독립 부여**(임계값 공식 역적용 금지 = 순환 금지). severity는 탐지기 정의 매핑. 측정 대상은 **verdict 임계값**(escalate ≥1 Critical · rework ≥3 Major)이며, 탐지 정확도(P/R/F1)는 §3-1c가 별도 측정.

| 케이스 | 출처 | 기대(사람) | 산출(aggregate) | 일치 |
|---|---|---|---|:--:|
| pos_coverage_sample | 8B | rework | lgtm | ❌ |
| pos_perf_nplus1_complexity | 8B | rework | lgtm | ❌ |
| pos_memleak | 8B | lgtm | lgtm | ✅ |
| neg_clean | 8B | lgtm | lgtm | ✅ |
| neg_edge_handled | 8B | lgtm | lgtm | ✅ |
| ext_sqli_critical | 확장(M2 모사) | escalate | escalate | ✅ |
| ext_critical_plus_majors | 확장(M2 모사) | escalate | escalate | ✅ |
| ext_three_nplus1 | 확장 | rework | rework | ✅ |
| ext_minor_only | 확장 | lgtm | lgtm | ✅ |
| ext_many_minor | 확장 | lgtm | lgtm | ✅ |
| **일치율** | | | | **8/10 = 80%** |

- **불일치 2건의 공통 원인(정직)**: m3 6탐지기는 **Critical을 만들지 않아**(전부 Major/Minor) N+1·O(n³) 같은 실제 성능 결함도 Major로 분류된다. 그런데 rework 임계값이 **Major 3건**이라, 현실적 PR(Major 1~2건)이 lgtm으로 통과한다. → `MAJOR_REWORK_THRESHOLD` 하향 또는 PERF-002/PERF-001(deep)의 escalate 승격 검토 권고. **약점을 숨기지 않고 표로 드러냄**(8B와 같은 정직 원칙).
- **escalate는 m3 단독 불가**(Critical 미생성) → 실제로는 **M2(정적/보안)의 Critical로만 도달**. 확장 케이스(ext_*)는 그 교차모듈 상황을 모사.
- **한계(정직)**: 표본 10건(추세·임계값 점검용). expected_verdict는 사람 판단 — pos_memleak(Minor 누수) 등 일부는 리뷰어에 따라 이견 가능.

### 3-1e. '왜 한 줄' 코멘트 품질 — LLM-as-judge (SESSION 8C)
> 🛠 **채점기 구축·검증 완료, 실 채점은 무료쿼터 한계로 조건부.** refine()이 만든 '왜(한 줄)'을 루브릭 4축(1~5)으로 LLM이 채점. judge 호출은 seam으로 분리해 mock 검증(단위 20테스트 green). 산출물 `validation/comment_judge_report.md`.
> **루브릭 4축**: ① consistency(판정 정합성) ② actionable(도움됨) ③ tone(skill_level 적합) ④ no_hallucination(환각 없음). judge 모델 = `gemini-2.5-flash-lite`(JUDGE_MODEL로 교체 가능). 케이스 10건(verdict 라벨셋 이슈 케이스 + skill 변형).
>
> **실 채점 결과: ⏭️ SKIP(정직)** — 2026-06-09 실행 시 Gemini 무료쿼터 소진(`429 RESOURCE_EXHAUSTED`, **flash-lite도 ~20/window**)으로 생성·채점 호출이 전부 막힘(15초 페이싱·5케이스 축소에도 동일) → **가짜 점수 없이 skip**. 채점기 자체는 단위 **24테스트 green**으로 검증(가짜 judge JSON → 집계·항목별 평균·낮은점수·빈응답 skip + 적은-케이스 슬라이스 대표성). **무료티어 대응**: `JUDGE_MAX_CASES=5` 모드 추가 — 5케이스(생성5+채점5≈**10호출**)로 verdict 3종·skill 3종을 모두 덮어 하루 한도(20) 안에 실측 가능. 쿼터 회복(매일 자정 PT≈한국 17시 리셋) 후 1커맨드:
> ```
> docker compose exec m3 sh -lc 'cd /app/service/pr-comment-agent && \
>   LLM_MODEL=gemini-2.5-flash-lite JUDGE_MAX_CASES=5 uv run python validation/comment_judge.py'
> ```
> → 실행되면 표 자리에 **루브릭 4축 평균 + 케이스별 점수**가 채워짐(`validation/comment_judge_report.md`).

### 3-1f. RAG 인용 품질 — RAGAS (SESSION 8D, **Tier A 실측 완료 / Tier B 쿼터 skip**)
> ✅ **RAG 검색 품질을 RAGAS로 측정 (2026-06-10, 컨테이너 실제 실행).** "이슈 message → 그에 맞아야 할 사내규칙" 쌍을 **사람이 12케이스 라벨링**(6규칙 × {탐지기 실제 message, 자연어 paraphrase}). RAGAS 호출부(`run_ragas`)를 seam으로 분리·지연 import → **순수 함수는 ragas 없이 TDD 17테스트 green**. 1커맨드 재실행(`uv run --extra eval python validation/rag_eval.py`). 산출물 `validation/rag_eval_report.md`·평가셋 `validation/rag_evalset.json`.
> 메타: 검색 임베더 BGE-M3·`top_k=3` / RAGAS **0.4.3** / Tier A judge **불필요**(NonLLM·rapidfuzz, 할당량 0) · Tier B judge **gemini-2.5-flash-lite**. 정답은 conventions/*.md 기준으로 사람이 확정(retriever 출력으로 정답 안 만듦 = 순환 금지).

| 지표 | 값 | 비고 |
|---|---|---|
| non_llm_context_recall | **0.917** | 정답 가이드 본문이 검색 청크에 담겨 옴(11/12; 1건은 점수<0.5로 빈 인용=진짜 miss) |
| non_llm_context_precision | **1.000** | 검색된 청크가 정답 청크와 일치 |
| **인용 라벨 정합성** | **4/11 = 36%** | top1 인용 제목(doc_title)이 올바른 규칙을 가리키는 비율 — **RAGAS 청크-단위가 못 잡는 약점** |
| faithfulness / answer_relevancy | **skip** | Gemini 429 쿼터 소진 → 가짜 점수 없이 skip, 회복 후 1커맨드 재산출 |

- **핵심 발견(정직)**: **검색기는 정상인데 적재된 코퍼스가 문제다.** 6개 사내 가이드가 DB에 **단 2개의 과대(over-broad) 청크**로 묶여 들어가 있다(① 커버리지+테스트누락+엣지 → 라벨 `TEST-001`만, ② N+1+복잡도+메모리 → 라벨 `PERF-002`만). 그래서 small-to-big 인용 시 **정답 본문은 거의 닿지만(recall 0.917)**, **인용 제목이 6규칙 중 4규칙에서 틀리고**(예: 메모리 이슈인데 제목이 "N+1 가이드") 한 인용에 무관한 2섹션(~1500자)이 섞여 나온다. → **고칠 곳은 재청킹(적재)이지 검색 코드가 아니다.**
- **왜 RAGAS 점수만 보면 안 되나**: NonLLM context precision/recall은 *청크 단위* 문자열 유사도라 "그 청크가 정답 본문을 담았나"(→ 1.0·0.917)는 잡지만 "라벨이 맞나·과대 청크인가"는 **못 잡는다**. 그래서 결정적·할당량 0짜리 **인용 라벨 정합성(36%)** 지표를 따로 두어 약점을 드러냈다(8B·8C와 같은 정직 원칙).
- **한계(정직)**: ① Tier B(faithfulness/answer_relevancy)는 Gemini 무료쿼터 429로 미산출 → skip(회복 후 1커맨드). ② 평가셋 12건(추세·약점 식별용). ③ ragas 0.4.3이 langchain 1.x에서 `ChatVertexAI` 레거시 import로 깨져 **미사용 Vertex placeholder shim**으로 우회(`_shim_langchain_vertexai`, 점수 무영향).

### 3-2. GitHub 10초 타임아웃 문제 → 비동기 설계로 해결
- GitHub 웹훅은 **10초 안에 응답**을 기대하는데, 우리 분석은 그보다 오래 걸림.
- 그래서 m1은 **서명만 확인하고 즉시 "202 접수"** 를 돌려준 뒤, 무거운 분석은 **백그라운드**에서 수행.
- 결과는 별도 콜백 없이 **`GET /review` 폴링**으로 확인. (= GitHub가 "타임아웃"을 띄워도 정상)

### 3-3. 자원·격리
- 커버리지 측정은 **Docker 샌드박스**에서: `--memory 512m --cpus 1`, 의존성 없으면 `--network none`(완전 격리).
- Docker를 못 쓰는 환경(컨테이너 안의 컨테이너 불가)에서는 **직접 실행으로 자동 우회** — 현업 CI 러너와 같은 방식. 어느 쪽이든 결과 형태는 동일.

### 3-4. 신뢰성(부분 실패 허용)
- **연결된 탐지기 6개는 독립** — 하나가 예외로 죽어도 나머지는 정상 산출.
- LLM 실패·쿼터초과 → **규칙기반 한 줄로 자동 대체**.
- DB(GCP) 다운 → **로컬 SQLite 저장으로 우회** (실제 데모 중 팀 DB가 잠깐 죽었지만 m3 결과는 정상 저장·표시됨).

---

## 4. 서비스 차별화 (UI/UX 흐름)

### 4-1. 사용자가 보는 두 곳

**(A) GitHub PR 댓글** — 개발자가 일하는 곳에서 바로 본다
```
## 🤖 코드 리뷰 — 🔧 수정 요청 (rework)
머지 전에 아래 이슈를 수정해 주세요.
🔴 Critical 0 · 🟡 Major 3 · 🔵 Minor 3
📊 커버리지 27% · 최대 복잡도 2

| 심각도 | 규칙 | 위치 | 고칠 방향 | 사내 규칙 |
|---|---|---|---|---|
| 🟡 | TEST-001 | src/payment.py | 사내 기준 90% 이상 필요... | 📖 (사내규칙 인용) |
| 🟡 | PERF-002 | src/payment.py:8 | 루프 밖에서 조회하세요... | 📖 ... |
...
📊 [리뷰 대시보드에서 전체 보기](링크)
```

**(B) 웹 리뷰 페이지** — 팀이 한눈에 본다
- **판정 뱃지**: 초록(통과)/노랑(수정요청)/빨강(시니어검토)
- **이슈 테이블**: 심각도 · 위치 · 규칙 · 설명·제안 · **📖 사내 규칙**
- **LLM 코멘트** 본문 + "GitHub에서 보기" 링크
- 정직한 빈/로딩/에러 상태(데이터 없으면 "분석 결과 없음", 가짜로 채우지 않음)

### 4-2. 차별점 ① — 📖 사내 규칙 인용 (RAG)
- 일반 린터는 "커버리지 부족"이라고만 함. m3는 거기에 **사내 코딩 가이드 문서의 해당 대목을 찾아 인용**해 붙임.
- 동작: 이슈 문장 → **BGE-M3 임베딩(1024차원)** → 사내 문서 벡터검색(pgvector) → **"작은 조각으로 정밀 매칭하고 큰 문단을 인용"(small-to-big)** → 코멘트/화면의 "사내 규칙" 칸에 표시.
- **환각 방지**: 문서를 못 찾으면 빈칸(—), 출처 링크 없으면 링크 안 만듦. **있는 것만 인용.**
- **정직 caveat (8D 실측)**: 검색 자체는 정상이나, 현재 **적재 코퍼스가 6개 가이드를 2개 과대 청크로 묶어** 인용 *제목*이 6규칙 중 4규칙에서 틀린다(인용 라벨 정합성 36%, §3-1f). 본문은 닿으므로 치명적이진 않지만, **재청킹으로 교정 예정**(source_url 빈값도 함께).

### 4-3. 차별점 ② — 리뷰 앵글 분리
- m3는 **"리뷰 앵글"(판정·규칙·지표)** 만 담당. 개념 설명·학습 추천(커리큘럼)은 **다른 모듈(dev4)** 영역 — 역할이 겹치지 않게 명확히 분리.
- 개발자 **숙련도(junior/mid/senior)** 에 따라 코멘트 톤을 조절하는 기능 → **구현 예정** (코드 구조는 있으나 적용 전, §6-2 참조).

### 4-4. 차별점 ③ — "정직한" 자동 리뷰
- 측정 못 한 지표는 코멘트에서 **줄 자체를 생략**(가짜 0% 안 만듦).
- 토큰/DB/모델이 없으면 **조용히 격을 낮춰** 진행(에러로 PR을 막지 않음).

---

## 5. 에이전트가 "어떤 구조로 행동하는지" (요청하신 부분)

m3는 **두 개의 에이전트 + 한 개의 게이트웨이**로 나뉩니다.

### 5-1. 분석 에이전트 (`test-performance-agent`) — 결정적 파이프라인
`run(입력, 레포경로) → [테스트결과, 성능결과]` 한 줄짜리 체인이고, 내부는 이렇게 흐릅니다:

```
PR diff 파싱 (바뀐 파일·줄 추출)
   │
   ├─ 커버리지 측정 (Docker로 pytest --cov 실행) ─→ TEST-001 + 지표  ┐
   ├─ 미사용 함수 탐지 (AST 본문 실행흔적)        ─→ TEST-004         │
   ├─ 엣지케이스 추론 (LLM/휴리스틱)              ─→ TEST-003         │ 6개 모두 연결
   ├─ N+1 쿼리 탐지 (AST 루프 안 DB호출)          ─→ PERF-002         │
   ├─ 복잡도 탐지 (AST 중첩루프 깊이)             ─→ PERF-001         │
   └─ 메모리누수 추론 (LLM/휴리스틱)              ─→ PERF-003        ┘
   (TEST-003·PERF-003은 데모/CI에서 휴리스틱=결정적 모드로 동작)
   │
   ▼
[diff 교집합 필터]  ← ★ 핵심: "PR에서 실제로 바뀐 줄"의 이슈만 남김 (관계없는 기존 코드 안 건드림)
   │
   ▼
[보강(enrich)]  함수 소스코드(AST=사실) · 언어/프레임워크 · 작성자 GitHub id 채움
   │
   ▼
[사내규칙 RAG]  (켜졌을 때만) 이슈마다 사내 가이드 인용 붙임
   │
   ▼
2개 결과 묶음(AgentOutput): test_verification / performance
```

**행동 특징**
- **결정적(기본)**: AST·커버리지 기반 4개는 같은 PR이면 항상 같은 결과 → 신뢰·재현 가능. LLM 기반 2개(TEST-003·PERF-003)도 데모/CI는 무키 휴리스틱으로 돌려 결정성을 유지.
- **부분 실패 허용**: 탐지기 하나가 예외 → 그것만 빈 결과, 나머지는 진행.
- **변경분에만 집중**: diff 교집합 필터로 "이번 PR이 바꾼 줄"만 지적(노이즈 최소화).

### 5-2. 코멘트 에이전트 (`pr-comment-agent`) — 종합·작성·게시
```
4개 결과 모음 → 중복제거·판정(aggregate) → 사내규칙 RAG 보강
            → 코멘트 작성(refine) → GitHub 게시(post) → 저장(persist)
```
- **코멘트 구조(표·카운트·📊지표·📖인용·대시보드 링크)는 항상 코드가 생성** → 형식 일관성 보장.
- **LLM(Gemini)은 "왜 이 판정인지 한 줄"만 작성** → 실패/쿼터초과면 규칙기반 한 줄로 대체.

### 5-3. 웹훅 게이트웨이 (`webhook-gateway`)
- 독립 실행(m1 없이도) 가능한 GitHub 웹훅 수신구. 같은 분석 어댑터를 재사용.
- 운영 통합 경로는 m1 → m3, 단독 검증 경로는 게이트웨이 직결.

### 5-4. 관측(Observability)
- 모든 단계에 `@instrument` 데코레이터 → **LangSmith trace**로 단계별 시간·입출력 추적. `trace_id`로 m1~m3 한 줄로 추적.

---

## 6. 추출 정리 — **구현됨 / 구현 예정(MVP·확장)**

### ✅ 6-1. 지금 "이 형태로 구현되어 있다"
1. **탐지기 6개 전체 파이프라인 연결** (TEST-001 커버리지 / TEST-003 엣지케이스 / TEST-004 미사용함수 / PERF-001 복잡도 / PERF-002 N+1 / PERF-003 메모리누수) — **실제 작동** (SESSION 8-0b 완료).
2. **실제 레포 clone → Docker 샌드박스 커버리지 측정**, Docker 없으면 직접 실행으로 자동 우회 — **구현됨**.
3. **diff 교집합 필터 + 보강(AST 소스·프레임워크·작성자)** — 구현됨.
4. **집계 → 판정(escalate/rework/lgtm)** — 구현됨.
5. **코멘트 자동 작성**(표 + 📊지표 + 📖사내규칙 + 대시보드 링크) — 구현됨.
6. **GitHub PR 실제 댓글 게시** — 구현·동작 확인됨(데모에서 실제 게시 URL 생성).
7. **결과 저장(로컬 SQLite) + 조회 API** — 구현됨.
8. **프론트 리뷰 페이지**(판정 뱃지·이슈 표·코멘트·📖칸) — 구현됨.
9. **사내규칙 RAG**(BGE-M3 + pgvector small-to-big) — 구현 + 라이브 검증 + **기본 ON 전환 완료**(docker-compose `RAG_ENABLED=1` + HF 캐시 볼륨, SESSION 8-0c).
10. **m1 ↔ m3 실 GitHub 웹훅 E2E** — 통합 검증됨.
11. **LLM SDK 최신화** — 지원종료된 `google.generativeai` → 신 SDK `google.genai`로 전수 교체(llm_refiner·edge_cases·code_context·memory_leak), 키 없으면 휴리스틱 폴백 유지 (SESSION 8-0a 완료).
12. **시스템 성능 벤치마크 (6탐지기 실측 완료)** — `bench/latency.py`로 5 PR×3회 p50/p95 워터폴 + 병목(RAG) 식별, 컨테이너에서 실제 재실행 완료(무키 N=15 + LLM N=5). 병목=RAG(실 GCP), warm e2e 16.5초·cold 210초(모델 로딩 1회성). (SESSION 8A, §3-1b)
13. **탐지 정확도 벤치마크 (rule별 P/R/F1 실측 완료)** — `validation/benchmark.py` 양성3+음성2 라벨셋, rule별 채점기(`evaluate_prf`, TDD 9테스트). 전체 F1 0.966·미탐 0·TEST-003 오탐 1건 정직 노출. (SESSION 8B, §3-1c)
14. **RAG 인용 품질 벤치마크 (RAGAS, Tier A 실측)** — `validation/rag_eval.py` 12케이스 사람-라벨 평가셋, NonLLM context recall 0.917·precision 1.0 + **인용 라벨 정합성 36% 약점 노출**, RAGAS 호출 seam TDD 17테스트. Tier B(faithfulness/relevancy)는 쿼터 skip. (SESSION 8D, §3-1f)

### 🔜 6-2. "이 형태로 구현할 예정 / MVP 범위 / 확장 예정"
1. **LLM 코멘트 문장 + 숙련도 톤 조절** — SDK 교체(8-0a)로 LLM 경로는 복구됨. 데모/CI는 결정성을 위해 무키 휴리스틱으로 돌리므로, 실 키 환경에서 "왜 한 줄"을 규칙기반 → LLM 문장으로 격상하는 **품질 검증은 SESSION 8C**. 숙련도(junior/mid/senior) 톤 조절은 코드 구조 있음, 적용 예정.
2. **DB 저장 경로 정리**:
   - 웹훅 경로(GitHub PR → m1 → m3): **이미 GCP Postgres에 저장** (scan_issues·scan_summaries·review_issue)
   - /review API → 프론트 화면용 조회: 현재 **로컬 SQLite** 사용 → 운영 시 GCP 전환 예정.
3. **dev4 공용 review_issue 라이브 검증** — 코드·테스트 완료(컬럼 매핑·서브쿼리). 실제 GCP 라이브 쓰기는 중복적재 방지·키 합의 후 검증 예정.
4. **정량 성능평가 (SESSION 8 후속)** — "되는가(TDD)"는 끝났고, "**얼마나 잘하는가**"를 3층으로 측정 중. 진행 현황은 아래 §6-3.
5. **RAG 코퍼스 재청킹** — 8D가 드러낸 약점: 6개 사내 가이드가 DB에 2개 과대 청크로 적재돼 인용 제목이 4/6 규칙에서 틀림(§3-1f). `conventions/*.md`를 **가이드(섹션)별로 분리 재적재** → 6개+ 부모 청크·올바른 `section_header`·`source_url` 채움. **검색 코드는 그대로**, 적재만 고치면 됨. (문제·할 일 상세 → `SESSION_8_문제와_TODO.md`)

### 📊 6-3. 성능평가 진행 현황 (SESSION 8)
> 평가를 "되는지(TDD)"에서 "얼마나 잘하는지(정량)"로 끌어올리는 단계. 평가 전 시스템 완성(8-0a/b/c)을 먼저 끝냈습니다.

| 단계 | 내용 | 상태 |
|---|---|---|
| **8-0a** | LLM SDK 교체 (`google.genai`) | ✅ 완료 |
| **8-0b** | 탐지기 6개 전체 파이프라인 연결 | ✅ 완료 |
| **8-0c** | RAG 기본 ON + HF 캐시 볼륨 | ✅ 완료 |
| **8A** | 시스템 성능 단계별 워터폴(p50/p95)·병목 | ✅ **완료** — 6탐지기 기준 실측 완료(무키 N=15 + LLM N=5, §3-1b). 병목=RAG(실 GCP). 라이브 6탐지기 연결도 동시 증명 |
| **8B** | 탐지 정확도 — rule별 Precision/Recall/F1 (양성+음성 라벨셋 ≥5) | ✅ **완료** — 5케이스(양성3+음성2)·6규칙 rule별 P/R/F1 실측(§3-1c). 전체 F1 0.966 PASS, TEST-003 오탐 1건 정직 노출. TDD 채점기 9테스트 green |
| **8C** | 코멘트 품질 — LLM-as-judge 루브릭 + verdict 정확도 | 🟡 **부분완료** — verdict 정확도 **80%(8/10)** 실측(§3-1d, 결정적·LLM불필요). LLM-judge 채점기 TDD **24테스트 green**(seam mock + 적은-케이스 모드). 실 채점은 무료쿼터(429) 소진으로 정직 skip(§3-1e), 쿼터 회복 후 `JUDGE_MAX_CASES=5` 1커맨드 재실행 |
| **8D** | RAG 인용 품질 — RAGAS(context precision/recall·faithfulness) | 🟡 **부분완료** — Tier A(NonLLM·할당량0) 실측: recall **0.917**·precision **1.0** + **인용 라벨 정합성 36%** 약점(§3-1f). RAGAS seam TDD 17테스트·회귀 323 green. Tier B(faithfulness/relevancy)는 Gemini 429로 정직 skip, 회복 후 1커맨드 재산출 |
| **8E** | LangSmith Dataset+Experiment로 통합·회귀추적 | ⬜ 예정 (8B/8C/8D 채점기 존재 → 착수 가능, `LANGCHAIN_API_KEY` 필요) |

- **8A 완료 확인**: `bench/latency.py`를 컨테이너에서 6탐지기 상태로 실제 재실행 → `edge_cases`·`memory_leak` 행이 표에 찍힘(6탐지기 라이브 연결 증명) + 6탐지기+RAG의 실제 비용이 옛 4탐지기 숫자보다 훨씬 큼을 확인(warm e2e 4.2초→16.5초, RAG가 병목).
- **8B 완료 확인**: 채점기를 골든1건 recall/false_alarm → **rule별 P/R/F1**로 TDD 확장(`validation/eval.py:evaluate_prf`, 테스트 9개 RED→GREEN). 양성3+음성2 라벨셋(`validation/benchmark.py`) 컨테이너 실측 → 전체 F1 0.966 PASS, TEST-003 오탐 1건 정직 노출(§3-1c). 회귀 306 테스트 green.
- **8C 진행 확인**: ① **verdict 정확도** — 8B 라벨셋 재사용+확장 10케이스, 사람 기대 vs `aggregate()` 산출 **80%(8/10)** 실측. 불일치 2건은 "rework=Major 3건" 임계값이 N+1·O(n³)(둘 다 Major)를 놓치는 **정직한 약점**(§3-1d, `validation/verdict_benchmark.py`). ② **LLM-as-judge 채점기** — judge 호출 seam 분리(JUDGE_MODEL로 모델 교체 가능)·루브릭 4축·집계·정직 skip, **TDD 20테스트 RED→GREEN**(`validation/comment_judge.py`). 실 채점은 Gemini 무료쿼터(flash-lite도 ~20/window) 소진으로 **정직 skip**(가짜 점수 금지, §3-1e). 무료티어 대응 `JUDGE_MAX_CASES=5`(≈10호출) 모드 추가 — 쿼터 회복 후 1커맨드 실측. pr-comment-agent 회귀 **147 green**(8C 추가 38 = verdict 14 + judge 24).
- **8D 완료 확인**: RAG 검색 품질을 RAGAS로 측정. 선행 점검(검색이 멀쩡한가)부터 통과 — BGE-M3 로드·GCP chunks 접속·스모크·retriever 15테스트 green. 평가셋 12케이스(사람 라벨, conventions 기준·순환 금지), RAGAS 호출 seam 분리·지연 import로 **TDD 17테스트**(가짜 retriever+가짜 RAGAS 점수→집계·표·빈인용 skip/0 정직성). Tier A(NonLLM·할당량0) 실측 → **recall 0.917·precision 1.0** + **인용 라벨 정합성 36%**(`validation/rag_eval.py`·§3-1f). 핵심 발견 = 6가이드가 DB에 2개 과대 청크로 적재 → 검색기 아닌 **코퍼스 문제**(재청킹 권고). Tier B는 Gemini 429로 정직 skip. 신규 의존성은 `[eval]` extra로 격리(런타임 불변), **회귀 323 green**.

---

## 7. 발표용 한 문장 요약들 (슬라이드 헤드라인용)

- "m3는 **PR이 올라오는 순간 자동으로 테스트·성능을 검사**해 **판정·이슈·코멘트**를 GitHub와 웹에 돌려줍니다."
- "합격/탈락 같은 **숫자 판정은 규칙으로 정확하게**, **설명만 AI로** — **환각 0**이 설계 1원칙."
- "린터를 넘어, **사내 코딩 규칙을 RAG로 찾아 인용**해 이슈마다 근거를 붙입니다."
- "실측 **약 14초**에 PR 하나를 끝까지(검사→판정→코멘트→게시) 처리, **부분 실패에도 멈추지 않습니다**."

---

> 작성: m3 구조 직접 분석 + 실측 데모(PR #4) 기반. 숫자·규칙·판정은 코드/실행 결과에서 그대로 추출했습니다.
> **최신화 (2026-06-10)**: SESSION 8-0a/b/c·8A·8B·8C에 더해 **8D(RAG 품질 RAGAS)** 반영. 8D는 컨테이너 실측: `validation/rag_eval.py`(12케이스 사람-라벨 평가셋·RAGAS 호출 seam·TDD 17테스트) → Tier A(NonLLM·할당량0) **context recall 0.917·precision 1.0** + **인용 라벨 정합성 36%** 약점(§3-1f), Tier B(faithfulness/relevancy)는 Gemini 429로 정직 skip. 신규 의존성 `[eval]` extra 격리(런타임 불변)·**회귀 323 green**. 핵심 발견 = 검색기 정상, **코퍼스 6가이드→2 과대청크가 진짜 약점**(재청킹 권고). 다음 순서: **8E(LangSmith 통합)**. 8세션 전체 문제·할 일 → **`SESSION_8_문제와_TODO.md`**. §2-3 데모 수치는 4탐지기 시점 캡처라 caveat 표기.
