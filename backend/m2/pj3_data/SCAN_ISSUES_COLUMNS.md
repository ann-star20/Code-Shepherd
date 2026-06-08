# scan_issues 컬럼 정의

> 실제 코드 기준: `sub2_new/dev2/db.py` (M2), `test-performance-agent/persist.py` (M3)

---

## 1. 공통 컬럼 (M2/M3 둘 다 적재)

| 컬럼 | 타입 | 예시 값 | 설명 |
|------|------|---------|------|
| `scan_id` | BIGINT | `1` | scan_executions FK |
| `agent` | TEXT | `security_scan` \| `test_verification` | 어느 에이전트 결과인지 |
| `severity` | TEXT | `Critical` \| `Major` \| `Minor` | 심각도 |
| `rule_id` | TEXT | `SEC-001` \| `PERF-002` | 이슈 규칙 ID |
| `file` | TEXT | `vulnerable.py` | 이슈 발생 파일 |
| `line` | INTEGER | `7` | 이슈 발생 라인 (M3는 null 가능) |
| `message` | TEXT | `SQL Injection via f-string` | 이슈 설명 |
| `suggestion` | TEXT | `Use parameterized queries` | 수정 방법 |

---

## 2. M2 전용 컬럼 (M3는 null)

> `sub2_new/dev2/schema.py` Issue 모델 기준

| 컬럼 | 타입 | 예시 값 | 설명 |
|------|------|---------|------|
| `similar_issues` | JSONB | `[{"rule_id": "SEC-002"}]` | 연관 이슈 목록 |
| `issue_type` | TEXT | `Bug` \| `Vulnerability` \| `Code Smell` | 이슈 유형 |
| `resolution_example` | TEXT | `sql = 'SELECT * WHERE id = ?'` | 수정 예시 코드 |
| `status` | TEXT | `Open` \| `Accepted` \| `False Positive` | 이슈 상태 |
| `keyword` | TEXT | `SQL Injection` | 상위 보안 개념명 (M4용) |
| `sub_category` | TEXT | `raw_query` | 하위 실수 유형 (M4용) |
| `concept_id` | TEXT | `sql_injection` | Neo4j 그래프 DB 노드 ID (M4용) |
| `mistake_type_concept_id` | TEXT | `sql_injection.raw_query` | 하위 노드 ID (M4용) |
| `confidence_score` | FLOAT | `0.97` | 분류 신뢰도 0.0~1.0 (M4용) |
| `code_snippet` | TEXT | `sql = f"SELECT * WHERE name='{username}'"` | 문제 코드 조각 (M4용) |
| `name_of_function` | TEXT | `get_user_by_name` | 이슈 발생 라인을 감싸는 함수명, 함수 밖이면 `""` (M4용) |
| `learning_context` | JSONB | `{"framework":"fastapi","language":"python","domain_context":"ecommerce"}` | 학습 맥락 (M4용) |
| `code_context` | JSONB | `{"context_before":[...],"issue_line":"...","context_after":[...],"context_summary":"..."}` | 이슈 라인 주변 코드 (M4용) |
| `taxonomy` | JSONB | `{"category":"Security","subcategory":"Injection","issue_type":"SQL Injection","sub_issue_type":"Raw Query String Formatting"}` | 보안 분류 체계 (M4용) |

---

## 3. M3 전용 컬럼 (M2는 null)

> 현재 M3 `contracts.py` 기준 — M3는 공통 컬럼 8개만 적재하며 전용 컬럼 없음.
> 아래는 M4 요청으로 M3에 **추가가 필요한** 컬럼이다.

| 컬럼 | 타입 | 예시 값 | 설명 | 상태 |
|------|------|---------|------|------|
| `keyword` | TEXT | `N+1 쿼리` | 대분류 고정 라벨 (rule_id 변환) | ❌ 추가 필요 |
| `sub_keyword` | TEXT | `load_cart_items` | 탐지된 실제 함수명 | ❌ 추가 필요 |
| `metric_value` | TEXT | `15회` \| `45.5%` \| `O(N²)` | 구체적 수치/지표 | ❌ 추가 필요 |
| `sub_category` | TEXT | `Database/API Loop Call` | 커리큘럼 트리 매핑 코드 | ❌ 추가 필요 |
| `code_context_summary` | TEXT | `"장바구니 항목을 DB에서 불러오는 함수"` | LLM 한 줄 설명 | ❌ 추가 필요 |

---

## 4. keyword 변환 테이블 (rule_id → keyword)

> M4 `keyword` 컬럼 생성 시 아래 매핑을 사용한다.

| rule_id | keyword |
|---------|---------|
| `PERF-002` | N+1 쿼리 |
| `PERF-001` | 시간복잡도 |
| `TEST-001` | 커버리지 미충족 |
| `TEST-003` | 엣지케이스 누락 |
| `PERF-003` | 메모리 누수 |
| `TEST-004` | 테스트 누락 |
| `SEC-001` | SQL Injection |
| `SEC-002` | XSS |
| `SEC-003` | Path Traversal |
| `SEC-004` | Command Injection |
| `SEC-005` | Insecure Password Hash |
| `SEC-006` | Hardcoded Secret |
| `AUTH-001` | Auth Missing |

---

## 5. 전체 컬럼 한눈에 보기

```
scan_issues
│
├── 공통 (M2+M3)
│   ├── scan_id
│   ├── agent
│   ├── severity
│   ├── rule_id
│   ├── file
│   ├── line
│   ├── message
│   └── suggestion
│
├── M2 전용 (M3는 null)
│   ├── similar_issues
│   ├── issue_type
│   ├── resolution_example
│   ├── status
│   ├── keyword              ← M4용
│   ├── sub_category         ← M4용
│   ├── concept_id           ← M4용
│   ├── mistake_type_concept_id ← M4용
│   ├── confidence_score     ← M4용
│   ├── code_snippet         ← M4용
│   ├── name_of_function     ← M4용
│   ├── learning_context     ← M4용
│   ├── code_context         ← M4용
│   └── taxonomy             ← M4용
│
└── M3 전용 (M2는 null) — 현재 미구현, M4 요청으로 추가 필요
    ├── keyword
    ├── sub_keyword
    ├── metric_value
    ├── sub_category
    └── code_context_summary
```
    