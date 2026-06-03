# AI-Native Engineering 보안 온톨로지

> **목적**: PR 코드리뷰 → 취약점 감지 → 개념 연결 → 적응형 학습 자료 생성 → 피드백 수집의 전체 사이클을 그래프 DB로 모델링한다.
> **프레임워크**: Django (Python)
> **참고 문서**: Django Security Guide, OWASP SQL Injection Prevention, OWASP DOM XSS Prevention, OWASP Authorization & Authentication Cheat Sheet

---

## 전체 흐름 요약

```
[지식 저장 흐름]   Document ──HAS_CONCEPT──▶ Concept ──HAS_EXAMPLE──▶ CodeExample
                                                                              │
                                                                        FROM_DOC ──▶ Document
                   Concept ──HAS_CHECKLIST_ITEM──▶ ChecklistItem

[실제 사용 흐름]   User ──SUBMITTED──▶ PR ──HAS_VULN──▶ Concept (하위 실수 유형)
                   PR ──HAS_PATTERN──▶ RecurrencePattern ──DETERMINES──▶ LearningMaterial
                   PR ──TRIGGERED──▶ LearningMaterial ──ABOUT──▶ Concept
                   User ──HAS_FEEDBACK──▶ Feedback ──ABOUT──▶ LearningMaterial
                   User ──MANAGES──▶ User (매니저 → 개발자)

[온톨로지 핵심]    Concept ──PART_OF──▶ Concept          ← 계층 (실수 유형 → 상위 개념)
                   Concept ──MITIGATES──▶ Concept         ← 방어 관계
                   Concept ──CO_OCCURS_WITH──▶ Concept    ← 묶음 학습 (2단계 진화)
```

---

## 에이전트 역할 분리

```
보안 에이전트
  ├── 취약점 탐지 (SQL Injection, XSS, CSRF, AUTH_VULNERABILITY)
  ├── 하위 실수 유형 분류 + confidence_score 산출
  │     ├── confidence 0.8 이상 → 하위 실수 유형 노드 직접 연결
  │     └── confidence 0.8 미만 → 상위 개념 노드에만 연결 (제너럴 체크리스트)
  └── code_snippet 추출 (AI가 필요한 컨텍스트 판단 — GitHub API 활용)
        ↓ HAS_VULN에 저장

커리큘럼 에이전트
  ├── RecurrencePattern 업데이트 (실수 유형 단위로 count 누적)
  ├── 체크리스트 생성 — KMS ChecklistItem에서 꺼내서 제공
  │     ├── level 1 (1회)
  │     │     → 해당 실수 유형의 template 항목만 제공
  │     ├── level 2 (2회)
  │     │     → template 항목 + 이전 PR 참조 문구 추가
  │     └── level 3 (3회+)
  │           → template + reference 항목까지 + 문서 강조
  │
  │   [확장 예정 — MVP에서는 미사용]
  │     → code_snippet 분석으로 AI 맞춤 체크리스트 생성
  │       (is_personalized: true, root_cause 저장)
  │
  ├── 동일 PR 복수 이슈 처리 규칙
  │     ├── 같은 상위 개념 내 여러 하위 실수
  │     │     → 상위 개념 단위로 합쳐서 하나의 체크리스트 (중복 제거)
  │     └── 서로 다른 상위 개념에서 여러 실수
  │           → 개념별로 따로 체크리스트 제공
  │           → 우선순위: 1) severity (critical→high→mid)
  │                       2) severity 같으면 RecurrencePattern.count 높은 것 먼저
  │
  └── 한 번에 생성:
        ├── 문제 설명 (이커머스 도메인 맥락 포함 — severity 높은 것부터)
        ├── 체크리스트 (ChecklistItem에서 level + 우선순위 기준으로 꺼냄)
        ├── CodeExample        (취약 코드 vs 올바른 코드 — Python/Django 우선)
        └── 학습 자료 추천      (Document 노드 기반 — internal 우선)
```

---

## KMS 로드맵

```
1단계 (MVP)
  4개 개념 수동 입력
  SQL Injection, XSS, CSRF, AUTH_VULNERABILITY
  + 각 하위 실수 유형, CodeExample, 체크리스트 항목 수동 세팅
  + CO_OCCURS_WITH expert 초기값 보안 전문가가 직접 설정

2단계 (고도화)
  사내 문서 → KMS 파싱
        ↓
  Document(source: "internal") 노드 생성
        ↓
  AI가 Concept + CodeExample 자동 추출
        ↓
  HAS_CONCEPT, HAS_EXAMPLE 엣지 자동 생성
  + CO_OCCURS_WITH source: "data"로 자연 교체

  KMS 문서 업데이트 시
        ↓
  연결된 CodeExample 자동 갱신
  → code 본문 업데이트
  → django_version 업데이트
  → version 자동 증가 (1.0 → 1.1)
  → updated_at 갱신
```

---

## 노드 정의

### `:Document`
보안 문서, 규격서, 가이드라인 등 원천 지식 소스.
`source`로 외부 문서와 KMS 사내 문서를 구분한다.
사내 문서는 `kms_type` / `kms_doc_id`로 KMS API 연동에 활용한다.

| 속성 | 타입 | 설명 |
|------|------|------|
| `id` | String | 고유 식별자 |
| `title` | String | 문서 제목 |
| `url` | String | 외부: 실제 URL / 내부: KMS 내 경로 |
| `version` | String | 문서 버전 |
| `source` | Enum | `external` (OWASP, Django 공식 등) \| `internal` (KMS 사내 문서) |
| `kms_type` | String | 사내 문서 전용 — `confluence` \| `notion` \| `drive` 등 |
| `kms_doc_id` | String | 사내 문서 전용 — KMS 내부 문서 ID (API 호출용) |
| `last_synced` | DateTime | 사내 문서 전용 — 마지막 KMS 동기화 일시 |
| `created_at` | DateTime | 생성 일시 |

**MVP 초기 Document 목록 (외부 문서 — URL 확정)**

| title | url | 관련 개념 |
|-------|-----|-----------|
| Django Security Guide — CSRF | https://docs.djangoproject.com/en/6.0/topics/security/#cross-site-request-forgery-csrf-protection | CSRF |
| OWASP SQL Injection Prevention Cheat Sheet | https://github.com/OWASP/CheatSheetSeries/blob/master/cheatsheets/SQL_Injection_Prevention_Cheat_Sheet.md | SQL Injection |
| OWASP DOM XSS Prevention Cheat Sheet | https://github.com/OWASP/CheatSheetSeries/blob/master/cheatsheets/DOM_based_XSS_Prevention_Cheat_Sheet.md | XSS |
| OWASP Authentication Cheat Sheet | https://github.com/OWASP/CheatSheetSeries/blob/master/cheatsheets/Authentication_Cheat_Sheet.md | AUTH_VULNERABILITY |
| OWASP Authorization Cheat Sheet | https://github.com/OWASP/CheatSheetSeries/blob/master/cheatsheets/Authorization_Cheat_Sheet.md | AUTH_VULNERABILITY |

**MVP 초기 Document 목록 (사내 문서 — 추후 채움)**

| title | kms_type | kms_doc_id | 관련 개념 |
|-------|----------|------------|-----------|
| 사내 SQL Injection 가이드 | TBD | TBD | SQL Injection |
| 사내 XSS 가이드 | TBD | TBD | XSS |
| 사내 CSRF 가이드 | TBD | TBD | CSRF |
| 사내 인증/인가 가이드 | TBD | TBD | AUTH_VULNERABILITY |

> 사내 문서가 TBD인 동안 Notification이 매니저에게 자동 발송됨.
> KMS에 문서가 추가되고 `kms_doc_id`가 채워지면 Notification `status: "resolved"`로 자동 업데이트.

---

### `:Concept`
보안 개념의 핵심 노드. 상위 개념과 하위 실수 유형을 모두 포함한다.
`PART_OF`로 계층 구조를 표현하며, KMS를 통해 지속적으로 확장된다.
`description`에 이커머스 도메인 맥락(실제 피해 시나리오)이 포함되어
학습 자료 생성 시 "왜 이 실수가 위험한지"를 이커머스 관점에서 설명한다.

| 속성 | 타입 | 설명 |
|------|------|------|
| `id` | String | 고유 식별자 |
| `name` | String | 이름 (예: `SQL Injection`, `raw_query`) |
| `full_name` | String | 전체 이름 |
| `description` | String | 개념 설명 |
| `type` | Enum | `attack` \| `mitigation` |
| `severity` | Enum | `critical` \| `high` \| `mid` \| `low` |
| `source` | Enum | `kms` \| `data` |
| `version` | String | KMS 버전 추적 |
| `updated_at` | DateTime | 마지막 업데이트 일시 |

---

### `:CodeExample`
개념과 연결된 실제 코드 스니펫. 취약 코드와 올바른 코드 쌍으로 제공된다.
Django 프레임워크 기준 Python 코드 우선. 프레임워크 무관한 경우는 언어 그대로 유지.
KMS 사내 문서가 업데이트되면 자동으로 연동되어 코드와 버전 정보가 함께 갱신된다.

| 속성 | 타입 | 설명 |
|------|------|------|
| `id` | String | 고유 식별자 |
| `title` | String | 예제 제목 |
| `language` | String | 프로그래밍 언어 (`python`, `html`, `javascript` 등) |
| `framework` | String | 프레임워크 (`django`, `none` 등) |
| `django_version` | String | 적용 Django 버전 (예: `6.0`, `4.2`) |
| `version` | String | CodeExample 자체 버전 (예: `1.0`, `1.1`) |
| `code` | String | 코드 본문 |
| `context` | String | 사용 컨텍스트 설명 |
| `good_practice` | Boolean | `true` = 올바른 코드, `false` = 취약 코드 |
| `updated_at` | DateTime | 마지막 업데이트 일시 (KMS 연동 시 자동 갱신) |

---

### `:PR`
GitHub PR. 실제 코드 변경을 분석하는 진입점.
`diff_snapshot`은 저장하지 않고 GitHub API에서 실시간으로 가져온다.
PR 상태(open/merged/closed)와 무관하게 분석 결과를 카운트에 반영한다.

| 속성 | 타입 | 설명 |
|------|------|------|
| `id` | String | 고유 식별자 |
| `pr_number` | Integer | PR 번호 |
| `repo` | String | 저장소 이름 (기록용) |
| `status` | Enum | `open` \| `merged` \| `closed` (기록용 — 카운트에 영향 없음) |
| `risk_score` | Float | 위험도 점수 (0.0 ~ 1.0) |
| `analyzed_at` | DateTime | 분석 일시 |

---

### `:RecurrencePattern` ✨ 신규
**같은 사용자가 같은 하위 실수 유형에서 반복 실수하는 패턴을 추적**하는 노드.
키는 `(concept_id, user_id)` 쌍 — 하위 실수 유형 단위, 사람 단위로 추적한다.
repo와 무관하게 같은 사람이 어디서든 같은 실수를 반복하면 count가 올라간다.
같은 PR에서 같은 실수 유형이 여러 줄에서 발생해도 count는 1만 증가한다.

| 속성 | 타입 | 설명 |
|------|------|------|
| `concept_id` | String | 하위 실수 유형 Concept ID |
| `user_id` | String | 사용자 식별자 |
| `count` | Integer | 현재 30일 window 내 카운트 (30일 지나면 리셋) |
| `total_count` | Integer | 전체 누적 카운트 (리셋 안 됨 — 통계용) |
| `window_days` | Integer | 집계 기간 (기본 30일) |
| `last_seen_at` | DateTime | 마지막 발생 일시 |
| `escalation_level` | Integer | 피드백 강도 단계 `1` \| `2` \| `3` |

**escalation_level 기준**

| level | 조건 | difficulty |
|-------|------|------------|
| 1 | 1회 발생 | 1 |
| 2 | 2회 발생 | 2~3 |
| 3 | 3회+ (30일 내) | 4~5 |

**level별 제공 내용 상세**

```
level 1 (1회)
  ├── 문제 설명
  ├── 체크리스트 (기본)
  ├── CodeExample
  └── 사내 문서 링크 (source: "internal" 우선)
        └── 사내 문서 없으면 외부 문서 fallback
              + 매니저에게 즉시 알림 발송
                "SQL Injection 관련 사내 문서가 없습니다. KMS에 추가해주세요"

level 2 (2회)
  ├── 문제 설명 + 이전 PR 참조
  ├── 체크리스트 (개인화 — 반복된 실수 유형 항목 맨 위로)
  ├── CodeExample
  └── 사내 문서 링크 (동일하게 제공, 읽었는지 확인 유도)
        └── 사내 문서 아직 없으면 외부 문서 fallback
              + 매니저에게 리마인드 알림 재발송

level 3 (3회+)
  ├── 문제 설명 + 패턴 경고
  ├── 체크리스트 (강화 — 항목 세분화)
  ├── CodeExample (난이도 상승)
  └── 사내 문서 링크 + "이 문서를 꼭 읽어주세요" 강조
        └── 사내 문서 아직 없으면 외부 문서 fallback
              + 매니저에게 우선순위 높음으로 에스컬레이션 알림
```

> **문서 우선순위**: `internal` 문서 우선 제공. KMS에 사내 문서가 추가되는 순간 자동으로 external에서 internal로 교체되고 Notification `status: "resolved"`로 자동 업데이트.

---

### `:LearningMaterial`
커리큘럼 에이전트가 생성하는 학습 콘텐츠. 항상 세트로 제공된다.
`is_personalized`로 제너럴 버전과 AI 맞춤 버전을 구분한다.

| 속성 | 타입 | 설명 |
|------|------|------|
| `id` | String | 고유 식별자 |
| `explanation` | String | 문제 설명 (PR 있으면 원인 분석 포함) |
| `checklist` | String | 체크리스트 (JSON 배열) |
| `is_personalized` | Boolean | `false` = KMS 제너럴 / `true` = AI 맞춤 생성 |
| `root_cause` | String | AI가 파악한 원인 서술 (is_personalized=true일 때만) |
| `doc_emphasis` | Enum | `link` (level 1~2) \| `required` (level 3, 강조 표시) |
| `difficulty` | Integer | 난이도 1 ~ 5 |
| `version` | String | LearningMaterial 버전 (예: `1.0`, `1.1`) |
| `prompt_version` | String | 생성에 사용된 프롬프트 버전 (예: `v1`, `v2`) |
| `created_at` | DateTime | 생성 일시 |

---

### `:User` ✨ 신규
시스템을 사용하는 개발자 및 매니저 노드.
GitHub 계정과 연동되어 PR 분석 시 자동으로 연결된다.

| 속성 | 타입 | 설명 |
|------|------|------|
| `id` | String | 고유 식별자 |
| `name` | String | 이름 |
| `role` | Enum | `developer` \| `manager` |
| `team_id` | String | 소속 팀 ID |
| `email` | String | 이메일 |
| `github_username` | String | GitHub 계정명 (PR 분석 시 자동 연결) |
| `created_at` | DateTime | 가입 일시 |

---

### `:Feedback`
학습자가 학습 자료에 남긴 반응.

| 속성 | 타입 | 설명 |
|------|------|------|
| `id` | String | 고유 식별자 |
| `user_id` | String | 사용자 식별자 |
| `result` | Enum | `correct` \| `incorrect` \| `skip` |
| `time_spent_sec` | Integer | 소요 시간 (초) |
| `confidence_score` | Float | 자신감 점수 |
| `created_at` | DateTime | 생성 일시 |

---

### `:ChecklistItem` ✨ 신규
KMS에서 관리하는 체크리스트 항목. 두 가지 역할을 한다.
- `purpose: "template"` — level 1~2에서 체크리스트로 그대로 제공
- `purpose: "reference"` — level 3에서 추가로 제공 (MVP) / 확장 시 AI 프롬프트 재료로 활용

**MVP 체크리스트 생성 로직**
```
level 1 → 해당 실수 유형의 template 항목만
level 2 → template 항목 + 이전 PR 참조 문구
level 3 → template + reference 항목 전부 + 문서 강조
```

| 속성 | 타입 | 설명 |
|------|------|------|
| `id` | String | 고유 식별자 |
| `concept_id` | String | 연결된 하위 실수 유형 Concept ID |
| `content` | String | 체크리스트 항목 내용 |
| `purpose` | Enum | `template` (제너럴 제공용) \| `reference` (AI 프롬프트 재료) |
| `order` | Integer | 기본 노출 순서 |
| `source` | Enum | `kms` \| `data` |
| `updated_at` | DateTime | 마지막 업데이트 일시 |

---

### `:Notification` ✨ 신규
사내 문서 공백을 감지하여 매니저에게 알림을 보내고 이력을 추적하는 노드.
`concept_id` 기준으로 `status: "pending"`인 Notification이 이미 존재하면
추가 알림을 보내지 않고 `affected_users`만 올린다.
KMS에 해당 개념의 internal 문서가 추가되면 `status`가 자동으로 `resolved`로 업데이트된다.

| 속성 | 타입 | 설명 |
|------|------|------|
| `id` | String | 고유 식별자 |
| `type` | Enum | `missing_doc` (문서 공백) \| `escalation` (반복 패턴) |
| `concept_id` | String | 문서가 없는 개념 ID |
| `concept_name` | String | 개념 이름 (예: `SQL Injection`) |
| `sent_to` | String | 알림 수신 매니저 user_id |
| `affected_users` | Integer | 이 문서 없이 실수한 개발자 수 |
| `priority` | Enum | `pending` (미임계) \| `critical` (5명 이상 — 알림 발송) |
| `status` | Enum | `pending` (미해결) \| `resolved` (문서 추가 완료) |
| `sent_at` | DateTime | 알림 최초 발송 일시 |
| `resolved_at` | DateTime | 문서 추가 완료 일시 |

**알림 발송 기준 (팀 규모 5명 기준)**

| affected_users | 동작 | 의미 |
|----------------|------|------|
| 1~4명 | 카운트만 누적, 알림 없음 | 일부 개발자 영향 |
| 5명 이상 | `critical` — 매니저 알림 발송 | 팀 전체 수준, 즉시 조치 필요 |

> 팀 규모가 변경되면 critical 기준값은 애플리케이션 로직에서만 수정하면 됨.
> `affected_users` 카운트는 온톨로지에 그대로 누적.

---

## 4개 개념 상세 정의

### 1. SQL Injection

**상위 개념**
```
name: "SQL Injection"
type: attack
severity: critical
description: >
  사용자 입력값이 검증 없이 SQL 쿼리에 직접 사용될 때 발생.
  Django ORM을 사용하면 기본적으로 보호되나,
  raw() / extra() / RawSQL() 사용 시 주의 필요.

  [이커머스 도메인]
  - 상품 가격 조작: 쿼리 변조로 할인율/가격 필드 직접 수정 가능
  - 주문 내역 열람: 타 고객의 주문 상세, 배송지, 구매 이력 접근 가능
  - 결제 정보 유출: 카드번호, 계좌번호 등 민감 결제 데이터 노출
  - 재고 조작: 재고 수량 변조로 품절 상품 강제 구매 또는 재고 소진 가능
```

**하위 실수 유형 (PART_OF)**

| name | severity | description |
|------|----------|-------------|
| `raw_query` | critical | 입력값을 쿼리 문자열에 직접 연결 |
| `no_parameterize` | critical | Parameterized Query / ORM 미사용 |
| `no_escape` | high | 특수문자 이스케이프 누락 |
| `unsafe_extra` | high | Django extra() / RawSQL()에 미검증 입력값 사용 |

**CodeExample**

```python
# [취약] raw_query — good_practice: false
# 사용자 입력을 쿼리 문자열에 직접 연결
def get_user(request):
    username = request.GET['username']
    query = "SELECT * FROM auth_user WHERE username = '%s'" % username
    users = User.objects.raw(query)  # SQL Injection 가능
    return render(request, 'users.html', {'users': users})
```

```python
# [안전] no_parameterize 수정 — good_practice: true
# Django ORM 사용 (자동으로 파라미터화)
def get_user(request):
    username = request.GET['username']
    users = User.objects.filter(username=username)  # 안전
    return render(request, 'users.html', {'users': users})
```

```python
# [취약] unsafe_extra — good_practice: false
# extra()에 미검증 입력값 사용
def search_users(request):
    order = request.GET.get('order', 'username')
    users = User.objects.extra(order_by=[order])  # 위험
    return render(request, 'users.html', {'users': users})
```

```python
# [안전] unsafe_extra 수정 — good_practice: true
# 허용 목록으로 검증 후 사용
ALLOWED_ORDER_FIELDS = ['username', 'email', 'date_joined']

def search_users(request):
    order = request.GET.get('order', 'username')
    if order not in ALLOWED_ORDER_FIELDS:
        order = 'username'
    users = User.objects.order_by(order)  # 안전
    return render(request, 'users.html', {'users': users})
```

**ChecklistItem 항목 (실수 유형별)**

| 실수 유형 | 항목 | purpose | order |
|-----------|------|---------|-------|
| `raw_query` | raw() / extra() / RawSQL() 사용 시 파라미터를 별도 인자로 전달하는가? | template | 1 |
| `raw_query` | 사용자 입력값을 쿼리 문자열에 직접 포맷팅(%, .format, f-string)하지 않는가? | template | 2 |
| `raw_query` | 해당 쿼리를 Django ORM으로 대체할 수 없는지 검토했는가? | reference | 3 |
| `no_parameterize` | Django ORM (filter, get, exclude 등)을 사용하고 있는가? | template | 1 |
| `no_parameterize` | cursor.execute() 사용 시 두 번째 인자로 값을 전달하는가? | template | 2 |
| `no_parameterize` | execute()의 첫 번째 인자에 변수를 직접 넣지 않는가? | template | 3 |
| `no_escape` | 특수문자(', ", ;, --)가 포함된 입력값을 이스케이프 처리하는가? | template | 1 |
| `no_escape` | 입력값 검증 후 허용된 문자만 통과시키는 allowlist를 적용하는가? | template | 2 |
| `unsafe_extra` | 동적으로 정렬/필터 컬럼을 지정할 때 허용 목록(allowlist)으로 검증하는가? | template | 1 |
| `unsafe_extra` | extra()의 where / tables 인자에 사용자 입력을 직접 넣지 않는가? | template | 2 |
| `unsafe_extra` | extra() 대신 ORM annotate() / order_by()로 대체할 수 없는지 검토했는가? | reference | 3 |

> `purpose: "template"` — PR 데이터 없는 초기에 제너럴 체크리스트로 그대로 제공
> `purpose: "reference"` — PR 있을 때 AI 맞춤 체크리스트 생성 시 프롬프트 재료로 활용

**CO_OCCURS_WITH 초기값 (expert)**

| 연결 개념 | weight | 근거 |
|-----------|--------|------|
| `XSS` | 0.60 | 입력값 검증 부재가 공통 원인 |
| `AUTH_VULNERABILITY` | 0.55 | DB 접근 권한 문제 동반 가능성 |

---

### 2. XSS (Cross-Site Scripting)

**상위 개념**
```
name: "XSS"
type: attack
severity: high
description: >
  악성 스크립트가 다른 사용자의 브라우저에서 실행되는 공격.
  Django 템플릿은 기본적으로 이스케이프를 수행하나,
  mark_safe / safe 필터 / autoescape off 사용 시 취약.
  DOM 기반 XSS는 클라이언트 사이드에서 발생.

  [이커머스 도메인]
  - 고객 세션 탈취: 로그인된 고객의 세션 쿠키를 탈취해 계정 접근
  - 피싱 페이지 삽입: 가짜 결제 폼을 삽입해 카드 정보 직접 수집
  - 장바구니/주문 조작: 스크립트로 수량, 금액, 배송지 변조
  - 리뷰 악용: 상품 리뷰에 악성 스크립트 삽입해 다른 고객에게 전파
```

**하위 실수 유형 (PART_OF)**

| name | severity | description |
|------|----------|-------------|
| `mark_safe_misuse` | high | mark_safe()로 미검증 사용자 입력을 안전하다고 표시 |
| `safe_filter_misuse` | high | 템플릿에서 \|safe 필터를 미검증 입력에 적용 |
| `autoescape_off` | high | {% autoescape off %}로 자동 이스케이프 비활성화 |
| `inner_html_direct` | high | JS에서 innerHTML에 미검증 입력 직접 삽입 |
| `no_csp` | mid | CSP(Content Security Policy) 헤더 미설정 |

**CodeExample**

```python
# [취약] mark_safe_misuse — good_practice: false
from django.utils.safestring import mark_safe

def user_profile(request):
    bio = request.user.bio  # 사용자 입력값
    safe_bio = mark_safe(bio)  # XSS 가능 — 검증 없이 safe 처리
    return render(request, 'profile.html', {'bio': safe_bio})
```

```python
# [안전] mark_safe_misuse 수정 — good_practice: true
# mark_safe 사용 안 함 — Django 템플릿이 자동으로 이스케이프
def user_profile(request):
    bio = request.user.bio
    return render(request, 'profile.html', {'bio': bio})
    # 템플릿에서 {{ bio }}로 출력하면 자동 이스케이프
```

```html
<!-- [취약] safe_filter_misuse — good_practice: false -->
<!-- 템플릿에서 |safe 필터 남용 -->
<div class="bio">{{ user.bio|safe }}</div>

<!-- [안전] safe_filter_misuse 수정 — good_practice: true -->
<!-- |safe 제거 — Django 템플릿 기본 이스케이프 사용 -->
<div class="bio">{{ user.bio }}</div>
```

```javascript
// [취약] inner_html_direct — good_practice: false
// innerHTML에 사용자 입력 직접 삽입
const userInput = new URLSearchParams(window.location.search).get('name');
document.getElementById('greeting').innerHTML = 'Hello, ' + userInput;

// [안전] inner_html_direct 수정 — good_practice: true
// textContent 사용 (코드 실행 없이 텍스트로만 처리)
const userInput = new URLSearchParams(window.location.search).get('name');
document.getElementById('greeting').textContent = 'Hello, ' + userInput;
```

```python
# [안전] no_csp 수정 — Django CSP 설정 (Django 6.0+)
# settings.py
CONTENT_SECURITY_POLICY = {
    "DIRECTIVES": {
        "default-src": ["'self'"],
        "script-src": ["'self'"],
        "style-src": ["'self'"],
        "img-src": ["'self'", "data:"],
    }
}
# Django 6.0 미만은 django-csp 패키지 사용
```

**ChecklistItem 항목 (실수 유형별)**

| 실수 유형 | 항목 | purpose | order |
|-----------|------|---------|-------|
| `mark_safe_misuse` | mark_safe() 사용 시 해당 값이 완전히 신뢰할 수 있는 출처인가? | template | 1 |
| `mark_safe_misuse` | mark_safe() 없이 Django 템플릿 자동 이스케이프로 대체할 수 없는가? | template | 2 |
| `mark_safe_misuse` | DB에 HTML을 저장할 때 bleach 등으로 sanitize하고 있는가? | reference | 3 |
| `safe_filter_misuse` | 템플릿에서 \|safe 필터를 사용자 입력에 적용하고 있지 않은가? | template | 1 |
| `safe_filter_misuse` | \|safe 필터 없이 {{ variable }}로만 출력하고 있는가? | template | 2 |
| `autoescape_off` | {% autoescape off %}를 불필요하게 사용하고 있지 않은가? | template | 1 |
| `autoescape_off` | autoescape off 블록 안에서 출력되는 값이 신뢰할 수 있는 출처인가? | template | 2 |
| `inner_html_direct` | JavaScript에서 innerHTML 대신 textContent를 사용하는가? | template | 1 |
| `inner_html_direct` | eval() / document.write()에 사용자 입력을 전달하고 있지 않은가? | template | 2 |
| `inner_html_direct` | DOM에 삽입 전 DOMPurify 등으로 sanitize하고 있는가? | reference | 3 |
| `no_csp` | CSP(Content Security Policy) 헤더가 설정되어 있는가? | template | 1 |
| `no_csp` | CSP에서 unsafe-inline / unsafe-eval을 허용하고 있지 않은가? | template | 2 |

> `purpose: "template"` — PR 데이터 없는 초기에 제너럴 체크리스트로 그대로 제공
> `purpose: "reference"` — PR 있을 때 AI 맞춤 체크리스트 생성 시 프롬프트 재료로 활용

**CO_OCCURS_WITH 초기값 (expert)**

| 연결 개념 | weight | 근거 |
|-----------|--------|------|
| `CSRF` | 0.70 | Django 문서에서 함께 언급, 클라이언트 공격 패턴 유사 |
| `SQL Injection` | 0.60 | 입력값 검증 부재가 공통 원인 |

---

### 3. CSRF (Cross-Site Request Forgery)

**상위 개념**
```
name: "CSRF"
type: attack
severity: high
description: >
  악성 사이트가 로그인된 사용자의 자격증명을 이용해
  의도치 않은 요청을 실행하는 공격.
  Django는 CsrfViewMiddleware로 기본 보호하나,
  csrf_exempt 데코레이터 남용 시 취약.

  [이커머스 도메인]
  - 무단 주문 생성: 고객 모르게 상품 주문 및 결제 실행
  - 배송지 변경: 진행 중인 주문의 배송지를 공격자 주소로 변경
  - 계정 정보 수정: 이메일, 비밀번호, 결제 수단 무단 변경
  - 포인트/쿠폰 사용: 고객의 포인트나 쿠폰을 무단으로 사용
```

**하위 실수 유형 (PART_OF)**

| name | severity | description |
|------|----------|-------------|
| `csrf_exempt_misuse` | high | @csrf_exempt 데코레이터를 불필요한 뷰에 적용 |
| `no_csrf_token` | high | POST 폼에 {% csrf_token %} 누락 |
| `token_not_verified` | high | CSRF 미들웨어 비활성화 또는 우회 |
| `get_state_change` | high | GET 요청으로 DB 상태 변경 (생성/수정/삭제) |
| `no_https_cookie` | mid | CSRF 쿠키에 Secure/SameSite 속성 미설정 |

**CodeExample**

```python
# [취약] csrf_exempt_misuse — good_practice: false
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse

@csrf_exempt  # CSRF 보호 비활성화 — 위험
def transfer_money(request):
    if request.method == 'POST':
        amount = request.POST.get('amount')
        # 송금 처리...
        return JsonResponse({'status': 'ok'})
```

```python
# [안전] csrf_exempt_misuse 수정 — good_practice: true
# API의 경우 세션 대신 토큰 인증 사용 (DRF 예시)
from rest_framework.decorators import api_view, authentication_classes
from rest_framework.authentication import TokenAuthentication

@api_view(['POST'])
@authentication_classes([TokenAuthentication])
def transfer_money(request):
    amount = request.data.get('amount')
    # 송금 처리...
    return Response({'status': 'ok'})
```

```html
<!-- [취약] no_csrf_token — good_practice: false -->
<form method="post" action="/transfer/">
    <input type="number" name="amount">
    <button type="submit">송금</button>
    <!-- {% csrf_token %} 누락! -->
</form>

<!-- [안전] no_csrf_token 수정 — good_practice: true -->
<form method="post" action="/transfer/">
    {% csrf_token %}
    <input type="number" name="amount">
    <button type="submit">송금</button>
</form>
```

```python
# [취약] get_state_change — good_practice: false
# GET 요청으로 데이터 삭제
def delete_post(request, post_id):
    Post.objects.filter(id=post_id).delete()  # GET으로 상태 변경
    return redirect('post_list')
```

```python
# [안전] get_state_change 수정 — good_practice: true
from django.views.decorators.http import require_POST

@require_POST  # POST 요청만 허용
def delete_post(request, post_id):
    Post.objects.filter(id=post_id, author=request.user).delete()
    return redirect('post_list')
```

```python
# [안전] no_https_cookie 수정 — good_practice: true
# settings.py
CSRF_COOKIE_SECURE = True    # HTTPS에서만 쿠키 전송
CSRF_COOKIE_SAMESITE = 'Strict'  # SameSite 속성 설정
SESSION_COOKIE_SECURE = True
SESSION_COOKIE_SAMESITE = 'Strict'
```

**ChecklistItem 항목 (실수 유형별)**

| 실수 유형 | 항목 | purpose | order |
|-----------|------|---------|-------|
| `csrf_exempt_misuse` | @csrf_exempt 데코레이터 사용이 꼭 필요한 경우인가? | template | 1 |
| `csrf_exempt_misuse` | API라면 세션 대신 토큰 인증(DRF TokenAuthentication)으로 대체했는가? | template | 2 |
| `csrf_exempt_misuse` | CsrfViewMiddleware가 MIDDLEWARE에 포함되어 있는가? | reference | 3 |
| `no_csrf_token` | 모든 POST 폼에 {% csrf_token %}이 포함되어 있는가? | template | 1 |
| `no_csrf_token` | AJAX 요청 시 X-CSRFToken 헤더를 포함하는가? | template | 2 |
| `token_not_verified` | CsrfViewMiddleware가 MIDDLEWARE에서 제거되어 있지 않은가? | template | 1 |
| `token_not_verified` | 특정 뷰에서 CSRF 검증을 우회하는 코드가 없는가? | template | 2 |
| `get_state_change` | DB 상태를 변경하는 작업이 GET이 아닌 POST/PUT/DELETE로 처리되는가? | template | 1 |
| `get_state_change` | @require_POST 데코레이터로 GET 요청을 차단하고 있는가? | template | 2 |
| `no_https_cookie` | CSRF_COOKIE_SECURE = True 설정이 되어 있는가? (HTTPS 환경) | template | 1 |
| `no_https_cookie` | CSRF_COOKIE_SAMESITE 설정이 되어 있는가? | template | 2 |
| `no_https_cookie` | SESSION_COOKIE_SECURE = True 설정이 되어 있는가? | reference | 3 |

> `purpose: "template"` — PR 데이터 없는 초기에 제너럴 체크리스트로 그대로 제공
> `purpose: "reference"` — PR 있을 때 AI 맞춤 체크리스트 생성 시 프롬프트 재료로 활용

**CO_OCCURS_WITH 초기값 (expert)**

| 연결 개념 | weight | 근거 |
|-----------|--------|------|
| `XSS` | 0.70 | Django 문서에서 함께 언급, 클라이언트 공격 패턴 유사 |
| `AUTH_VULNERABILITY` | 0.65 | 세션/인증 관련 동반 가능성 |

---

### 4. AUTH_VULNERABILITY (인증/인가 취약점)

**상위 개념**
```
name: "AUTH_VULNERABILITY"
type: attack
severity: critical
description: >
  인증(Authentication)과 인가(Authorization) 로직의 결함.
  인증은 신원 확인, 인가는 권한 확인.
  Django의 @login_required / permission_required 미사용,
  취약한 비밀번호 정책, 세션 관리 미흡 등이 원인.

  [이커머스 도메인]
  - 타 고객 계정 접근: URL 파라미터 조작으로 다른 고객 주문/개인정보 열람 (IDOR)
  - 관리자 권한 탈취: 인가 검증 누락으로 상품 등록, 가격 수정, 주문 관리 접근
  - 포인트/적립금 조작: 권한 검증 없이 포인트 잔액 직접 수정 가능
  - 결제 우회: 인증 없이 결제 완료 API 직접 호출해 무료 주문 처리
```

**하위 실수 유형 (PART_OF)**

| name | severity | description |
|------|----------|-------------|
| `no_login_required` | critical | @login_required 또는 LoginRequiredMixin 누락 |
| `no_permission_check` | critical | 객체 수준 권한 검증 누락 (본인 소유 확인 안 함) |
| `no_expiry` | high | 세션/토큰 만료 시간 미설정 |
| `weak_password_policy` | high | 최소 비밀번호 강도 정책 미적용 |
| `insecure_direct_object` | high | URL 파라미터로 다른 사용자 리소스 접근 가능 (IDOR) |
| `no_mfa` | mid | 민감한 기능에 MFA(다중 인증) 미적용 |

**CodeExample**

```python
# [취약] no_login_required — good_practice: false
def user_dashboard(request):
    # 로그인 확인 없이 대시보드 접근 가능
    return render(request, 'dashboard.html')
```

```python
# [안전] no_login_required 수정 — good_practice: true
from django.contrib.auth.decorators import login_required

@login_required
def user_dashboard(request):
    return render(request, 'dashboard.html')

# CBV의 경우
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import TemplateView

class DashboardView(LoginRequiredMixin, TemplateView):
    template_name = 'dashboard.html'
```

```python
# [취약] no_permission_check — good_practice: false
# IDOR 취약점: 다른 사용자의 게시글도 수정 가능
@login_required
def edit_post(request, post_id):
    post = get_object_or_404(Post, id=post_id)
    # 작성자 확인 없음 — 누구든 수정 가능
    if request.method == 'POST':
        post.title = request.POST.get('title')
        post.save()
    return render(request, 'edit_post.html', {'post': post})
```

```python
# [안전] no_permission_check 수정 — good_practice: true
from django.core.exceptions import PermissionDenied

@login_required
def edit_post(request, post_id):
    post = get_object_or_404(Post, id=post_id)
    # 작성자 본인인지 확인
    if post.author != request.user:
        raise PermissionDenied
    if request.method == 'POST':
        post.title = request.POST.get('title')
        post.save()
    return render(request, 'edit_post.html', {'post': post})
```

```python
# [취약] no_expiry — good_practice: false
# settings.py — 세션 만료 시간 미설정
SESSION_COOKIE_AGE = 1209600  # Django 기본값: 2주 (너무 김)
SESSION_EXPIRE_AT_BROWSER_CLOSE = False  # 브라우저 닫아도 세션 유지
```

```python
# [안전] no_expiry 수정 — good_practice: true
# settings.py
SESSION_COOKIE_AGE = 3600           # 1시간으로 단축
SESSION_EXPIRE_AT_BROWSER_CLOSE = True  # 브라우저 닫으면 세션 종료
SESSION_COOKIE_SECURE = True        # HTTPS에서만 쿠키 전송
SESSION_COOKIE_HTTPONLY = True      # JS에서 쿠키 접근 차단
```

```python
# [취약] weak_password_policy — good_practice: false
# settings.py — 비밀번호 검증기 미설정
AUTH_PASSWORD_VALIDATORS = []  # 비밀번호 강도 검사 없음
```

```python
# [안전] weak_password_policy 수정 — good_practice: true
# settings.py
AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
        'OPTIONS': {'min_length': 12}  # NIST 권장: MFA 없으면 최소 15자
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]
```

**ChecklistItem 항목 (실수 유형별)**

| 실수 유형 | 항목 | purpose | order |
|-----------|------|---------|-------|
| `no_login_required` | 모든 인증이 필요한 뷰에 @login_required 또는 LoginRequiredMixin이 적용되어 있는가? | template | 1 |
| `no_login_required` | CBV라면 LoginRequiredMixin을 가장 왼쪽에 상속했는가? | template | 2 |
| `no_login_required` | 로그인 없이 접근 가능한 뷰가 의도된 것인지 확인했는가? | reference | 3 |
| `no_permission_check` | 객체 수정/삭제 시 해당 객체가 현재 사용자 소유인지 확인하는가? | template | 1 |
| `no_permission_check` | URL 파라미터(post_id 등)로 다른 사용자 데이터에 접근할 수 없는가? | template | 2 |
| `no_permission_check` | @permission_required 또는 has_perm()으로 역할 기반 권한을 검증하는가? | template | 3 |
| `no_expiry` | SESSION_COOKIE_AGE가 적절히 짧게 설정되어 있는가? (권장: 3600초) | template | 1 |
| `no_expiry` | SESSION_EXPIRE_AT_BROWSER_CLOSE = True로 설정되어 있는가? | template | 2 |
| `no_expiry` | SESSION_COOKIE_SECURE / HTTPONLY가 True로 설정되어 있는가? | template | 3 |
| `weak_password_policy` | AUTH_PASSWORD_VALIDATORS에 최소 길이 검증기가 포함되어 있는가? | template | 1 |
| `weak_password_policy` | 최소 비밀번호 길이가 12자 이상으로 설정되어 있는가? | template | 2 |
| `weak_password_policy` | CommonPasswordValidator로 자주 쓰이는 비밀번호를 차단하는가? | reference | 3 |
| `insecure_direct_object` | URL 파라미터로 다른 사용자 리소스에 접근할 수 없는가? (IDOR) | template | 1 |
| `insecure_direct_object` | get_object_or_404() 시 author=request.user 조건을 함께 거는가? | template | 2 |
| `insecure_direct_object` | 민감한 작업(비밀번호 변경, 이메일 변경) 시 현재 비밀번호를 재확인하는가? | reference | 3 |
| `no_mfa` | 민감한 기능(송금, 계정 삭제 등)에 추가 인증 단계가 있는가? | template | 1 |
| `no_mfa` | django-otp 등 MFA 라이브러리 적용을 검토했는가? | reference | 2 |

> `purpose: "template"` — PR 데이터 없는 초기에 제너럴 체크리스트로 그대로 제공
> `purpose: "reference"` — PR 있을 때 AI 맞춤 체크리스트 생성 시 프롬프트 재료로 활용

**CO_OCCURS_WITH 초기값 (expert)**

| 연결 개념 | weight | 근거 |
|-----------|--------|------|
| `CSRF` | 0.65 | 세션/인증 관련 동반 가능성 |
| `SQL Injection` | 0.55 | DB 접근 권한 문제 동반 가능성 |

---

## 관계 정의

### 흐름 1 — 지식 저장

```cypher
(d:Document)-[:HAS_CONCEPT]->(c:Concept)
```
문서가 어떤 보안 개념을 포함하는지 연결. KMS 고도화 시 자동 생성.

```cypher
(c:Concept)-[:HAS_EXAMPLE]->(e:CodeExample)
```
개념(하위 실수 유형 포함)의 코드 예시 연결.

```cypher
(e:CodeExample)-[:FROM_DOC]->(d:Document)
```
코드 예시의 원문 출처 역추적.

```cypher
(c1:Concept)-[:PART_OF]->(c2:Concept)
```
하위 실수 유형 → 상위 개념 계층 연결.
예: `raw_query -[PART_OF]-> SQL Injection`

---

### 흐름 2 — 실제 사용

```cypher
(u:User)-[:SUBMITTED]->(pr:PR)
```
GitHub username으로 PR 작성자를 자동 연결.

```cypher
(u:User {role: "manager"})-[:MANAGES]->(u2:User {role: "developer"})
```
매니저와 개발자 관계. Notification 발송 시 MANAGES 관계로 매니저를 찾는다.

```cypher
(u:User)-[:HAS_FEEDBACK]->(f:Feedback)
```
사용자가 남긴 피드백 연결.

```cypher
(pr:PR)-[:HAS_VULN {
  severity:         "high",
  line_number:      42,
  mistake_type:     "raw_query",
  code_snippet:     "...",
  confidence_score: 0.92
}]->(c:Concept)
```
PR에서 발견된 취약점을 하위 실수 유형 노드에 직접 연결.
`mistake_type`은 보안 에이전트가 AI로 분류하고,
`code_snippet`은 저장해두되 MVP에서는 체크리스트 생성에 미사용 (확장 예정).
PR 하나에서 여러 이슈 발생 시 각 실수 유형마다 독립 엣지로 연결.

**confidence_score 기준**

| 범위 | 동작 |
|------|------|
| 0.8 이상 | 하위 실수 유형 노드에 직접 연결 → RecurrencePattern 카운트 올림 |
| 0.8 미만 | 상위 개념 노드에만 연결 (예: raw_query 대신 SQL Injection) → 제너럴 체크리스트 제공 |

```cypher
(pr:PR)-[:HAS_PATTERN]->(rp:RecurrencePattern)
(rp:RecurrencePattern)-[:TRACKS]->(c:Concept)
(rp:RecurrencePattern)-[:DETERMINES]->(lm:LearningMaterial)
(pr:PR)-[:TRIGGERED]->(lm:LearningMaterial)
(lm:LearningMaterial)-[:ABOUT]->(c:Concept)
(lm:LearningMaterial)-[:RECOMMENDS]->(d:Document)
(lm:LearningMaterial)-[:HAS_FEEDBACK]->(f:Feedback)
```

---

### 흐름 3 — 온톨로지 핵심

```cypher
(c1:Concept)-[:MITIGATES]->(c2:Concept)
```
예: `Parameterized Query -[MITIGATES]-> SQL Injection`
예: `CsrfViewMiddleware -[MITIGATES]-> CSRF`
예: `LoginRequiredMixin -[MITIGATES]-> AUTH_VULNERABILITY`

```cypher
(c1:Concept)-[:CO_OCCURS_WITH {
  weight: 0.70,
  count:  0,
  source: "expert"
}]->(c2:Concept)
```
- `source: "expert"` — MVP 구간. 보안 전문가 설정값 (위 테이블 참고).
- `source: "data"` — 실제 PR 데이터로 교체. `count >= 10` 이상일 때만 신뢰.

---

## 관계 요약표

| 관계 | 방향 | 속성 | 비고 |
|------|------|------|------|
| `HAS_CONCEPT` | Document → Concept | — | KMS 고도화 시 자동 생성 |
| `HAS_CHECKLIST_ITEM` | Concept → ChecklistItem | — | 실수 유형별 체크리스트 항목 |
| `SUBMITTED` | User → PR | — | GitHub username으로 자동 연결 |
| `MANAGES` | User → User | — | 매니저 → 개발자 |
| `HAS_FEEDBACK` | User → Feedback | — | 사용자가 남긴 피드백 |
| `HAS_EXAMPLE` | Concept → CodeExample | — | |
| `FROM_DOC` | CodeExample → Document | — | |
| `PART_OF` | Concept → Concept | — | 실수 유형 → 상위 개념 |
| `MITIGATES` | Concept → Concept | — | |
| `CO_OCCURS_WITH` | Concept ↔ Concept | `weight`, `count`, `source` | 2단계 진화 |
| `HAS_VULN` | PR → Concept | `severity`, `line_number`, `mistake_type`, `code_snippet`, `confidence_score` | confidence 0.8 이상이면 하위 실수 유형, 미만이면 상위 개념 연결 |
| `HAS_PATTERN` | PR → RecurrencePattern | — | |
| `TRACKS` | RecurrencePattern → Concept | — | 하위 실수 유형 단위 |
| `DETERMINES` | RecurrencePattern → LearningMaterial | — | |
| `TRIGGERED` | PR → LearningMaterial | — | 이력 추적용 |
| `ABOUT` | LearningMaterial → Concept | — | |
| `RECOMMENDS` | LearningMaterial → Document | — | 학습 자료 추천 |
| `HAS_FEEDBACK` | LearningMaterial → Feedback | — | |
| `NOTIFIES` | Concept → Notification | — | 문서 공백 감지 시 알림 생성 |

---

## Neo4j Cypher 예시

### 개발자의 전체 실수 패턴 조회

```cypher
MATCH (u:User {github_username: $github_username})
MATCH (u)-[:SUBMITTED]->(pr:PR)-[:HAS_VULN]->(mt:Concept)-[:PART_OF]->(parent:Concept)
MATCH (rp:RecurrencePattern {user_id: u.id})-[:TRACKS]->(mt)
RETURN parent.name AS 개념, mt.name AS 실수유형,
       rp.count AS 반복횟수, rp.escalation_level AS 레벨
ORDER BY rp.count DESC
```

### 매니저 산하 개발자 실수 패턴 전체 조회

```cypher
MATCH (m:User {role: "manager", id: $manager_id})-[:MANAGES]->(dev:User)
MATCH (rp:RecurrencePattern {user_id: dev.id})-[:TRACKS]->(mt:Concept)-[:PART_OF]->(parent:Concept)
WHERE rp.escalation_level >= 2
RETURN dev.name AS 개발자, parent.name AS 개념,
       mt.name AS 실수유형, rp.count AS 반복횟수, rp.escalation_level AS 레벨
ORDER BY rp.escalation_level DESC, rp.count DESC
```

### Notification 발송 대상 매니저 찾기

```cypher
MATCH (dev:User {id: $user_id})<-[:MANAGES]-(manager:User {role: "manager"})
RETURN manager.id, manager.email, manager.name
```

### RecurrencePattern 업데이트 (PR 분석 시 실행)

```cypher
// PR 단위 중복 방지: 같은 PR에서 같은 실수 유형이 여러 줄 발생해도 1회만 카운트
MATCH (pr:PR {id: $pr_id})-[:HAS_VULN]->(c:Concept {id: $concept_id})
WITH count(pr) AS already_counted
WHERE already_counted <= 1  // 이 PR에서 처음 발생한 경우만 카운트

MERGE (rp:RecurrencePattern {
  concept_id: $mistake_type_concept_id,
  user_id:    $user_id
})
ON CREATE SET
  rp.count            = 1,
  rp.total_count      = 1,
  rp.window_days      = 30,
  rp.last_seen_at     = datetime(),
  rp.escalation_level = 1
ON MATCH SET
  rp.count = CASE
    WHEN rp.last_seen_at > datetime() - duration('P30D')
    THEN rp.count + 1
    ELSE 1  // 30일 초과 시 window count 리셋
  END,
  rp.total_count      = rp.total_count + 1,  // 전체 누적은 리셋 안 됨
  rp.last_seen_at     = datetime(),
  rp.escalation_level = CASE
    WHEN rp.count >= 3 THEN 3
    WHEN rp.count = 2  THEN 2
    ELSE 1
  END
```

### 개인화된 체크리스트 항목 순서 결정

```cypher
MATCH (rp:RecurrencePattern {user_id: $user_id})-[:TRACKS]->(mt:Concept)
MATCH (mt)-[:PART_OF]->(parent:Concept {name: $concept_name})
RETURN mt.name, rp.count, rp.escalation_level
ORDER BY rp.count DESC
```
> count가 높은 실수 유형이 체크리스트 맨 위로.

### CO_OCCURS_WITH weight 누적 (PR 데이터 기반)

```cypher
MATCH (pr:PR)-[:HAS_VULN]->(c1:Concept)-[:PART_OF]->(p1:Concept)
MATCH (pr)-[:HAS_VULN]->(c2:Concept)-[:PART_OF]->(p2:Concept)
WHERE id(p1) < id(p2)
MERGE (p1)-[r:CO_OCCURS_WITH]-(p2)
ON CREATE SET r.weight = 0.1, r.count = 1, r.source = "data"
ON MATCH SET
  r.count  = r.count + 1,
  r.weight = toFloat(r.count) / (r.count + 1),
  r.source = "data"
```
> weight = 실제 공동 출현 비율로 수렴. `count >= 10` 미만은 추천에서 제외.

### 사용자별 반복 실수 패턴 조회

```cypher
MATCH (rp:RecurrencePattern {user_id: $user_id})-[:TRACKS]->(mt:Concept)-[:PART_OF]->(parent:Concept)
WHERE rp.escalation_level >= 2
RETURN parent.name, mt.name, rp.count, rp.escalation_level
ORDER BY rp.escalation_level DESC, rp.count DESC
```

### 묶음 학습 추천

```cypher
MATCH (main:Concept {name: $concept_name})-[r:CO_OCCURS_WITH]->(related:Concept)
WHERE r.weight > 0.6 AND (r.source = "expert" OR r.count >= 10)
RETURN main.name, related.name, r.weight, r.source
ORDER BY r.weight DESC
LIMIT 3
```

### Notification 생성 (사내 문서 없을 때)

```cypher
// 사내 문서 없음 감지 시 Notification 생성 또는 카운트 누적
// 5명 도달 시 최초 1회만 매니저 알림 발송
MATCH (c:Concept {name: $concept_name})
WHERE NOT (:Document {source: "internal"})-[:HAS_CONCEPT]->(c)
MERGE (n:Notification {
  concept_id: c.id,
  status:     "pending"
})
ON CREATE SET
  n.id             = randomUUID(),
  n.type           = "missing_doc",
  n.concept_name   = c.name,
  n.sent_to        = $manager_user_id,
  n.affected_users = 1,
  n.priority       = "pending",
  n.sent_at        = datetime()
ON MATCH SET
  n.affected_users = n.affected_users + 1,
  // 5명 도달 시 critical로 전환 — 애플리케이션에서 이 시점에 알림 발송
  n.priority = CASE
    WHEN n.affected_users + 1 >= 5 THEN "critical"
    ELSE n.priority
  END
RETURN n
```

```cypher
// KMS에 사내 문서 추가 시 Notification 자동 resolved
MATCH (n:Notification {concept_id: $concept_id, status: "pending"})
SET n.status      = "resolved",
    n.resolved_at = datetime()
```

```cypher
// 우선순위별 미해결 Notification 조회 (매니저 대시보드용)
MATCH (n:Notification {status: "pending"})
RETURN n.concept_name, n.affected_users, n.priority, n.sent_at
ORDER BY
  CASE n.priority
    WHEN "critical" THEN 1
    WHEN "high"     THEN 2
    ELSE 3
  END,
  n.affected_users DESC
```

### 문서 추천 (internal 우선, external fallback)

```cypher
MATCH (c:Concept {name: $concept_name})
OPTIONAL MATCH (d_int:Document {source: "internal"})-[:HAS_CONCEPT]->(c)
OPTIONAL MATCH (d_ext:Document {source: "external"})-[:HAS_CONCEPT]->(c)
RETURN
  CASE
    WHEN d_int IS NOT NULL THEN d_int.title
    ELSE d_ext.title
  END AS recommended_title,
  CASE
    WHEN d_int IS NOT NULL THEN d_int.url
    ELSE d_ext.url
  END AS recommended_url,
  CASE
    WHEN d_int IS NOT NULL THEN "internal"
    ELSE "external"
  END AS doc_source
```

> KMS에 사내 문서가 추가되는 순간 자동으로 internal 문서가 우선 반환됨.
> level 3에서 internal 문서가 없으면 external fallback + 팀 리더 에스컬레이션 알림 발송.

---

## 설계 원칙

1. **Concept 중심 설계**: 모든 흐름이 `:Concept`을 경유.
2. **하위 실수 유형 단위 추적**: `RecurrencePattern`은 하위 실수 유형(raw_query 등) 단위로 추적. 체크리스트 개인화의 실질적 근거.
3. **이슈별 독립 추적**: PR 하나에서 여러 이슈 발생 시 각 실수 유형마다 별개의 RecurrencePattern으로 독립 추적.
   - 같은 상위 개념 내 여러 하위 실수 → 상위 개념 단위로 체크리스트 합산 (중복 제거)
   - 서로 다른 상위 개념 → 개념별 체크리스트 분리 제공
   - 우선순위: severity 내림차순 → count 내림차순
4. **세트 제공 원칙**: 모든 level에서 문제 설명 + 체크리스트 + CodeExample + 문서 링크를 항상 세트로 제공. level이 올라갈수록 개인화 수준, 난이도, 문서 강조 수준이 함께 높아짐.
5. **체크리스트 MVP 구조**: ChecklistItem에서 level 기준으로 꺼내서 제공. level 1~2는 template 항목, level 3는 template + reference 항목까지 제공. is_personalized는 항상 false. code_snippet은 저장만 해두고 MVP에서는 미사용. 확장 시 AI가 code_snippet 분석으로 맞춤 체크리스트 생성 가능한 구조를 유지.
6. **문서 우선순위 및 공백 알림**: internal 문서 우선 제공. 사내 문서 없으면 external fallback + Notification affected_users 누적. 5명 이상(팀 전체 수준) 도달 시에만 매니저에게 critical 알림 최초 1회 발송. KMS에 문서 추가 시 Notification 자동 resolved.
7. **에이전트 역할 분리**: 보안 에이전트는 탐지 + 분류 + 코드 추출, 커리큘럼 에이전트는 패턴 업데이트 + 학습 자료 생성.
8. **CO_OCCURS_WITH 2단계 진화**: MVP는 expert 설정값으로 시작, 실데이터 누적 후 data 값으로 자연 교체. count >= 10 임계값 이전까지 data weight 미신뢰.
9. **KMS 확장성**: 1단계 4개 개념 수동 입력 → 2단계 사내 문서 파싱 자동화. 온톨로지 스키마 변경 없이 노드 추가만으로 확장.
10. **GitHub API 활용**: PR diff는 온톨로지에 저장하지 않고 GitHub API에서 실시간 호출.
11. **Django 우선 원칙**: CodeExample은 Python/Django 코드 우선. 프레임워크 무관한 경우(JS DOM 조작 등)는 해당 언어 그대로 유지.
12. **User 중심 추적**: User 노드가 PR, RecurrencePattern, Feedback, Notification을 연결하는 허브 역할. github_username으로 PR 분석 시 자동 연결. MANAGES 관계로 매니저가 팀 전체 실수 패턴을 조회 가능.
13. **PR 단위 카운트**: 같은 PR에서 같은 실수 유형이 여러 줄에서 발생해도 RecurrencePattern count는 1만 증가. HAS_VULN 엣지는 줄 번호별로 독립 생성.
17. **AI 분류 신뢰도 기반 분기**: HAS_VULN.confidence_score가 0.8 이상이면 하위 실수 유형 노드에 직접 연결해 개인화 체크리스트 제공. 0.8 미만이면 상위 개념 노드에만 연결해 제너럴 체크리스트 제공. 별도 검토 프로세스 없이 자동 처리.
18. **LearningMaterial 버전 관리**: version으로 콘텐츠 이력 추적, prompt_version으로 어떤 프롬프트로 생성됐는지 기록. 프롬프트 개선 시 이전 버전과 비교 가능.
14. **사람 단위 추적**: RecurrencePattern은 repo와 무관하게 user_id + concept_id 기준으로 추적. 어느 repo에서든 같은 실수를 반복하면 같은 RecurrencePattern의 count가 올라감.
15. **누적 통계 분리**: RecurrencePattern.count는 30일 window 기준으로 리셋. total_count는 전체 누적으로 리셋 없이 유지. level은 count 기준, 장기 통계는 total_count 기준.
16. **CodeExample 버전 관리**: KMS 사내 문서 업데이트 시 연결된 CodeExample 자동 갱신. django_version으로 적용 버전 명시, version으로 CodeExample 자체 이력 추적.
