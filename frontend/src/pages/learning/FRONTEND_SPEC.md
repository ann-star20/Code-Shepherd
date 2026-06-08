# CodeSheppard — Frontend Specification
# Phase 1: MVP → Phase 2: Multi-Agent
# 이 파일은 프론트엔드 구현에 필요한 모든 사양을 담고 있습니다.

---

## 전제 조건 — 반드시 읽고 시작할 것

> **작업 경로 제한**
> 프론트엔드 파일은 아래 경로 안에서만 생성하거나 수정한다.
>
> ```
> frontend/src/pages/learning/
> ```
>
> 이 경로 밖의 파일(다른 pages, components, contexts, layouts 등)은
> 절대 수정하지 않는다.
> 단, 기존 라우터나 네비게이션에 learning 페이지를 등록해야 할 경우
> 사용자에게 먼저 확인 후 진행한다.

---

## 0. 개발 전 필수 확인 — m4 API 연결 방법

### API 베이스 URL
- m4 서비스는 **별도 포트(8005)**에서 실행됨
- `frontend/src/lib/api.ts`의 `apiClient`는 api-core(포트 8000) 전용 → **사용 금지**
- `pages/learning/` 내에서 별도 API 클라이언트 또는 `fetch` 직접 사용

```typescript
// pages/learning/ 내에서만 사용하는 m4 API 클라이언트 예시
// ASSUMPTION: .env에 VITE_M4_URL 추가 필요
//   개발: VITE_M4_URL=http://localhost:8005
//   docker-compose 내부: VITE_M4_URL=http://m4:8005
const M4_BASE = import.meta.env.VITE_M4_URL ?? 'http://localhost:8005';

const m4Api = axios.create({
  baseURL: M4_BASE,
  headers: { 'Content-Type': 'application/json' },
});

// JWT Bearer 토큰 자동 첨부 (localStorage에서 가져옴 — api.ts와 동일 방식)
m4Api.interceptors.request.use((config) => {
  const token = localStorage.getItem('access_token');
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});
```

### 프론트엔드 라우팅
- `/learning` 라우트는 `frontend/src/App.tsx:82`에 **이미 등록됨**
- `frontend/src/pages/learning/Placeholder.tsx`를 실제 구현 컴포넌트로 **교체**하면 됨
- App.tsx 수정 불필요

---

## 1. 페이지 진입 트리거 (D10, D20)

개발자가 웹페이지에 접속하면 팝업 모달을 즉시 표시한다.

```
웹페이지 접속
    │
    ▼
팝업 모달 표시: "학습을 시작하겠습니까?"
    ├── "예" 클릭  → POST /api/learn {}
    └── "아니오"   → 팝업 닫기 (아무 동작 없음)
```

- scan_id를 직접 넘기지 않음 — 서버가 JWT에서 user_id를 추출하여 최신 PR 자동 조회 (D19)
- 팝업은 페이지 로드 시 1회만 표시

---

## 2. 프론트엔드가 호출하는 API

### POST /api/learn
```
엔드포인트: m4 서비스 (M4_BASE/api/learn)
Request:  {}   (body 없음 — user_id는 서버가 JWT에서 추출)

Response 202: { "scan_id": "uuid", "plan_ids": ["uuid1", "uuid2", "uuid3"] }
  → scan_id = pull_requests.id (polling URL 조립에 사용)
  → 카드 3개 생성 시작. 즉시 반환 (BackgroundTask 비동기)

Response 200 (중복): { "scan_id": "uuid", "plan_ids": ["uuid1", "uuid2", "uuid3"] }
  → 이미 생성된 카드가 있으면 기존 scan_id + plan_ids 반환
```

### GET /api/pr/{scan_id}
```
엔드포인트: m4 서비스 (M4_BASE/api/pr/{scan_id})
Response 200:
{
  "issues": [
    {
      "id": "uuid",
      "keyword": "SQL Injection",
      "severity": "critical",
      "plan": {
        "id": "uuid",
        "status": "pending|running|completed|failed",
        "llm_fallback": false,
        "error_message": null,
        "card_content": { ... },   // status=completed일 때 존재
        "ragas_reason": "low_faithfulness|low_relevancy|null",
        "attempt_count": 2
      }
    }
  ]
}
```

### POST /api/complete
```
엔드포인트: m4 서비스 (M4_BASE/api/complete)
Request:  { "plan_id": "uuid" }

Response 200: { "id": "uuid", "completed_at": "2026-06-05T..." }
  → 중복 호출 허용 (idempotent) — 동일 plan_id 재호출 시 기존 데이터 반환
```

---

## 3. Status Polling 흐름 (D2)

POST /api/learn → 202 수신 후 plan_ids를 가지고 polling 시작.

```
POST /api/learn → 202 { scan_id, plan_ids }
    │
    └── scan_id로 GET /api/pr/{scan_id} 2초마다 polling
            │
            issues 배열 3개를 순회 (카드별 개별 처리):
            ├── issue.plan.status = "pending" | "running"  → 로딩 스피너 표시
            ├── issue.plan.status = "completed"            → 해당 카드 즉시 렌더링 (점진적)
            └── issue.plan.status = "failed"              → 해당 카드 에러 메시지 표시
            
            polling 중지 조건: issues 배열의 모든 plan.status가
            "completed" 또는 "failed"가 되면 polling 중지
            (일부 완료, 일부 실패 혼합도 모두 terminal 상태이면 중지)
```

---

## 4. 카드 자동 완료 처리 (D11)

- 별도 "완료" 버튼 없음
- 카드 페이지 로드 시 자동으로 POST /api/complete 호출
- 중복 호출 걱정 없음 (idempotent)

---

## 5. 카드 UI 레이아웃

**정상 (before_code 있음):**
```
┌─────────────────────────────────────────────────────────────────────┐
│ 헤더                                                                 │
│  [{keyword}] — [{name_of_function}]                                 │
│  {programming_language} / {framework} {framework_version}           │
├──────────────────────────────┬──────────────────────────────────────┤
│ Before (문제 코드)            │ After (수정 코드)                    │
│  다크 테마, 신택스 하이라이팅  │  다크 테마, 신택스 하이라이팅         │
│  {before_code}               │  서버가 생성한 수정 코드              │
│  ← 인풋 그대로 표시           │  (RAG 또는 LLM 생성)                │
├──────────────────────────────┴──────────────────────────────────────┤
│ 설명                                                                 │
│  개념 설명 본문 (e-commerce 맥락 기반)                               │
│  인라인 코드 칩 포함 (예: `Optional`, `null`)                        │
│                                                                      │
│  왜 위험한가 (e-commerce 맥락):                                      │
│    서버가 e-commerce 도메인 기반으로 생성                             │
│                                                                      │
│ 학습 추천                                                            │
│  이 이슈를 더 깊게 이해하려면 공부해보세요:                           │
│  · {title_1} — {description_1}                                      │
│  · {title_2} — {description_2}                                      │
│  (RAG 가 안될시 LLM으로 일반 추천 / 섹션은 항상 표시)                       │
│                                                                      │
│ ┌─────────────────────────────────────────────────────────────────┐ │
│ │ 핵심 요약 (하이라이트 박스)                                        │ │
│ │  {keyword}: {sub_category} 핵심 규칙 한 줄 요약                   │ │
│ └─────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────┘
```

**before_code = null인 경우 (code_snippet 없음):**
```
┌─────────────────────────────────────────────────────────────────────┐
│ 헤더                                                                 │
│  [{keyword}] — [{name_of_function}]                                 │
│  {programming_language} / {framework} {framework_version}           │
├─────────────────────────────────────────────────────────────────────┤
│ After (권장 코드 예제) — 전체 너비                                   │
│  다크 테마, 신택스 하이라이팅                                         │
│  RAG 검색된 사내 문서 기반 LLM 생성 코드                             │
├─────────────────────────────────────────────────────────────────────┤
```
- Before 패널 숨김 (안내 문구 없음, 그냥 조용히 숨김)
- After 코드 전체 너비 렌더링
- `if (card_content.before_code) { 2컬럼 } else { 단일컬럼 }` 분기

---

## 6. QUICK vs DEEP 카드 차이

| 섹션 | QUICK | DEEP |
|------|-------|------|
| 헤더 | keyword + name_of_function | keyword + name_of_function + sub_category |
| Before | code_snippet 그대로 | code_snippet 그대로 |
| After | 수정 코드 (짧게) | 수정 코드 (상세, 주석 포함) |
| 설명 | 개념 요약 + e-commerce 맥락 위험 | 개념 원리 상세 + e-commerce 맥락 위험 + (Phase 2) 실제 장애 사례 |
| 핵심 요약 박스 | 한 줄 규칙 | 한 줄 규칙 + 사내 컨벤션 명시 |
| 학습 추천 | 2개 이내 추천 | 3개 이내 추천 |

- depth는 서버가 결정해서 card_content에 포함시켜 반환 — 프론트에서 직접 계산하지 않음

---

## 6-1. card_content JSON 구조

서버가 `curriculum_plan.card_content`에 저장하는 전체 구조:

```json
{
  "header": {
    "keyword": "SQL Injection",
    "name_of_function": "search_products",
    "sub_category": "input validation",
    "language": "Python",
    "framework": "FastAPI",
    "framework_version": "0.104.0",
    "depth": "deep"
  },
  "before_code": "def search_products(keyword):\n    ...",  // null 가능 — code_snippet 없으면 null, 프론트는 단일컬럼 렌더링
  "after_code": "def search_products(keyword):\n    ...",
  "explanation": "e-commerce 맥락 기반 개념 설명 본문",
  "why_dangerous": "상품 검색에 SQL Injection 발생 시 전체 DB 노출 가능",
  "core_summary": "SQL Injection: 사용자 입력은 Parameterized Query로만 처리한다",
  "learning_recommendations": [
    {
      "title": "Parameterized Query 패턴",
      "description": "FastAPI + SQLAlchemy 안전한 쿼리 작성법"
    },
    {
      "title": "OWASP Input Validation Guide",
      "description": "사용자 입력 처리 보안 원칙"
    }
  ]
}
```

- `learning_recommendations` 빈 배열이어도 섹션은 표시 (LLM fallback 내용으로)
- 프론트는 각 필드 null 체크 후 렌더링

---

## 7. llm_fallback 라벨

`plan.llm_fallback === true`이면 카드에 라벨 표시:
- 예: "사내 문서 기반 아님 (LLM 자체 생성)"
- 카드 품질 신호로 활용

---

## 8. 에러 상태 처리

| status | 표시 |
|--------|------|
| `pending` | 로딩 스피너 |
| `running` | 로딩 스피너 |
| `completed` | 카드 렌더링 |
| `failed` | 아래 "카드 생성 실패 안내" 참조 — `plan.error_message`를 화면에 그대로 노출하지 않음 |

### 카드 생성 실패 안내 (T6 — 사용자 친화 메시지 분리)

`plan.error_message`는 `str(exception)` 원본(예: `"Gemini API 오류: 429 rate limit exceeded"`,
`"connection lost"`)이 그대로 담긴 **디버깅용 텍스트**다. 기술 용어가 섞여 있어 일반 사용자에게는
혼란스러우므로, 화면에는 카드 자리에 고정된 친절한 안내만 표시한다:

```
┌─────────────────────────────────────────┐
│                                         │
│   카드를 생성하는 중 문제가 발생했어요     │
│   잠시 후 다시 시도해주세요               │
│                                         │
└─────────────────────────────────────────┘
```

- `plan.error_message`는 화면에 노출하지 않는다 — 원본 예외 메시지는 디버깅 목적으로만 존재
- 개발 중 확인이 필요하면 `console.error("[learn] plan failed:", plan.error_message)` 정도로만 기록
- 카드별로 독립적으로 표시 — 3개 중 하나만 실패해도 나머지 completed 카드는 정상 렌더링 (Section 7 "점진적 렌더링" 원칙과 동일)

### PR 없음 안내 (신규)

`POST /api/learn` 응답이 **404**인 경우 (백엔드가 최신 PR을 찾지 못함):
- 팝업 닫고 페이지 전체에 안내 화면 표시
- 에러 메시지 대신 **친절한 가이드** 제공

```
┌─────────────────────────────────────────────────────┐
│                                                     │
│  📋  아직 등록된 PR이 없습니다                        │
│                                                     │
│  PR을 제출하면 자동으로 코드 리뷰가 진행되고           │
│  맞춤형 학습 카드가 생성됩니다.                        │
│                                                     │
│  [ GitHub에서 PR 확인하기 ]  (외부 링크, optional)   │
│                                                     │
└─────────────────────────────────────────────────────┘
```

- 404 외 다른 에러(500, network 등)는 별도 에러 메시지 표시
- 안내 화면은 팝업 닫힌 후 메인 컨텐츠 영역에 렌더링

---

## 9. 보안 주의사항

- `doc_chunk.source_url` 등 서버에서 받은 URL을 렌더링할 때 반드시 이스케이프 처리 (XSS 방지)
- POST /api/learn 요청에 CSRF 토큰 포함 필요 (SameSite 쿠키 설정과 함께)

---

## 10. 프론트엔드 태스크 (T9)

**T9 (Phase 1, ~20min)** — 웹페이지 팝업 모달 구현

**작업 파일**: `frontend/src/pages/learning/Placeholder.tsx` → 실제 컴포넌트로 교체  
(파일명 변경 가능: `LearningPage.tsx` 등, 단 App.tsx import 경로도 변경 필요 — App.tsx는 타 담당자 확인 후 수정)

- 웹페이지 접속 시 팝업 모달: "학습을 시작하겠습니까? 예/아니오"
- 예 클릭 → `m4Api.post('/api/learn', {})` (Section 0의 m4Api 사용) → plan_ids 수신 → polling 시작 → 카드 렌더링
- 아니오 클릭 → 팝업 닫기
- 카드 렌더링 완료 시 자동 `m4Api.post('/api/complete', { plan_id })` × 3

**확인**: 팝업 예 클릭 → 최신 PR severity top 3 이슈 카드 3개 표시  
**Phase 1 개발 중**: Cloud SQL review_issue 테이블에 직접 INSERT한 실제 데이터 기반으로 카드 반환 (D34)

**파일 구조 (생성 대상)**:
```
frontend/src/pages/learning/
├── FRONTEND_SPEC.md       ← 이 파일
├── Placeholder.tsx        ← 현재 플레이스홀더 (교체 대상)
├── LearningPage.tsx       ← 신규 생성: 팝업 + 폴링 + 카드 렌더링
├── components/
│   ├── LearningModal.tsx  ← "학습 시작" 팝업 모달
│   ├── LearningCard.tsx   ← 카드 렌더링 (before/after 코드 + 설명)
│   └── CodeBlock.tsx      ← 신택스 하이라이팅 (기존 라이브러리 재사용 가능)
└── hooks/
    └── useLearningApi.ts  ← m4Api 호출 + polling 로직
```

---

## 11. E2E 테스트 케이스 (Phase 2 이후)

```python
# tests/e2e/test_full_flow.py
test_complete_learning_journey_phase1()
  # 팝업 클릭 → polling → 카드 렌더링 → 자동 완료

test_popup_modal_cancel_does_nothing()
  # 아니오 클릭 → 아무 API 호출 없음

test_navigate_away_and_return_shows_existing_card()
  # 이미 생성된 plan → 재접속 시 기존 카드 표시

test_complete_learning_journey_phase2_multiagent()
  # Phase 2 전체 플로우
```
