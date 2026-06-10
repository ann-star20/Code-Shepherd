# M2 피드백 필드 점검 — `code_snippet` 경로 버그 수정 + `name_of_function` 추가

**날짜**: 2026-06-06
**범위**: Dev2(M2) 코드 리뷰 모듈 — `nodes/concept_mapper.py`, `schema.py`, `nodes/store.py`, `db.py`
**목적**: M4 개인화 학습 피드백이 소비하는 필드 점검 중 발견한 두 가지를 처리한다.
(1) 정적분석 이슈의 `code_snippet`이 항상 `"snippet_unavailable"`로 나오는 버그 수정,
(2) M4가 요청한 `name_of_function`(이슈 발생 함수명) 신규 구현.

---

## 1. `code_snippet` 버그 — Windows 경로 구분자 불일치

### 증상

`security_scan`(bandit) 이슈는 `code_snippet`이 정상인데, `static_analysis`(pylint) 이슈는
**전부 `"snippet_unavailable"`** 로 나왔다.

### 원인

도구별로 이슈 `file` 경로의 **구분자가 다르다**.

| 도구 | 보고하는 file 경로 | diff 헤더(`+++ b/...`)와 비교 |
|------|--------------------|-------------------------------|
| bandit | `C:/proj/vulnerable.py` (forward slash) | 일치 → snippet OK |
| pylint | `C:\proj\vulnerable.py` (**backslash**) | 불일치 → 매칭 실패 → `snippet_unavailable` |

`extract_snippet()` / `_collect_file_lines()`가 diff 헤더 경로와 이슈 `file`을
**문자열 그대로** 비교해서, 구분자만 달라도 "다른 파일"로 판정한 것이 원인이다.

```python
# 기존 — 구분자 차이로 매칭 실패
in_target_file = (
    target_file == file_path
    or file_path.endswith(target_file)
    or target_file.endswith(file_path)
)
```

### 수정

두 함수 모두 비교 직전에 경로 구분자를 `/`로 정규화한다.

```python
target_file = target_file.replace("\\", "/")   # pylint('C:\\..') vs bandit('C:/..')
...
file_path = raw_line[6:].replace("\\", "/")
```

> `_collect_file_lines()`는 `code_context`도 채우므로, 같은 수정으로 **`code_context`까지 함께 복구**된다.

---

## 2. `name_of_function` — 이슈 발생 함수명 추출

`concept_mapper.py`에 `extract_function_name(pr_diff, file, line)`을 추가했다.

- **Python**: `ast`로 `target_line`을 포함하는 **가장 안쪽** `FunctionDef`/`AsyncFunctionDef`를
  찾는다 (`lineno..end_lineno` 범위). 중첩 함수는 innermost를 선택.
- **함수 밖**(모듈 본문 / 클래스 본문): `""` 반환 (빈 문자열 = 유효한 결과).
- **비-Python 또는 ast 파싱 실패**: 언어별 정규식으로 이슈 라인 **위쪽을 역탐색**
  (`def` / `function` / 메서드 패턴). Python이 SyntaxError여도 fallback이 함수명을 찾는다.

`enrich_with_concept_mapping()`에서 `enriched["name_of_function"]`을 부여 →
`final_output` JSON + `scan_issues` 적재까지 흐른다.

```json
{
  "rule_id": "SEC-B608",
  "line": 10,
  "code_snippet": "sql = f\"SELECT * FROM users WHERE name = '{username}'\"",
  "name_of_function": "get_user_by_name"
}
```

---

## 3. 변경 파일

| 파일 | 변경 내용 |
|------|-----------|
| `dev2/nodes/concept_mapper.py` | 경로 정규화(`extract_snippet`, `_collect_file_lines`) + `extract_function_name()` 및 헬퍼(`_py_enclosing_function`, `_regex_enclosing_function`) 추가, `enrich_with_concept_mapping()`에 통합 |
| `dev2/schema.py` | `Issue.name_of_function: str = ""` 필드 추가 |
| `dev2/nodes/store.py` | `_ISSUE_FIELDS` 화이트리스트에 `name_of_function` 추가 (Pydantic 경계 통과용) |
| `dev2/db.py` | `insert_scan_issues` INSERT문에 `name_of_function` 컬럼 추가 |
| `pj3_data/DB_SCHEMA.md` | `scan_issues` DDL에 `name_of_function TEXT` 추가 |
| `pj3_data/SCAN_ISSUES_COLUMNS.md` | 컬럼 정의 문서에 `name_of_function` 행 추가 |
| `dev2/tests/test_concept_mapper.py` | 테스트 10건 추가 (경로 정규화 2 + `name_of_function` 8) |
| `docs/plans/2026-05-22-dev2-implementation-plan.md` | Task 4-i 섹션 추가 |

---

## 4. DB 마이그레이션 (라이브 Cloud SQL)

라이브 인스턴스에는 `name_of_function` 컬럼이 없어 INSERT가 실패했다.
**additive · 비파괴** 마이그레이션을 1회 적용했다(신규 환경은 `DB_SCHEMA.md` DDL에 반영됨).

```sql
ALTER TABLE scan_issues ADD COLUMN IF NOT EXISTS name_of_function TEXT;
```

> ⚠️ **별도 점검 필요(이번 범위 외)**: `db.py` INSERT는 `mistake_type_concept_id` 컬럼도
> 참조하지만 `DB_SCHEMA.md` DDL에는 누락돼 있다. 라이브 테이블엔 존재해 현재는 동작하나,
> 신규 환경 구축 시 깨진다.

---

## 5. 검증 결과

`run_dev2()` 전체 파이프라인을 **6개 케이스**에 대해 실행하고 모든 M4 필드를 집계했다.

```
total issues          : 34
code_snippet empty/NA : 0      ← snippet_unavailable 0건
language empty        : 0
name_of_function key  : missing=0
VERDICT: ALL OK
```

### 케이스별 실제 값 (샘플)

| 케이스 | rule_id | line | `name_of_function` | `code_snippet` | `keyword` |
|--------|---------|------|--------------------|----------------|-----------|
| sqli | SEC-B608 | 10 | `get_user_by_name` | `sql = f"SELECT * FROM users..."` | `SQL Injection` |
| command_injection | SEC-B605 | 5 | `ping_host` | `return os.system(f"ping -c 1 {host}")` | — |
| hardcoded_secret | SEC-B105 | 2 | `""`(모듈 상수) | `JWT_SECRET = "my-hardcoded..."` | `AUTH_VULNERABILITY` |
| path_traversal | SEC-PT001 | 7 | `read_user_file` | `file_path = BASE_DIR / filename` | — |
| auth_missing | SA-C0116 | 9 | `delete_user_account` | `def delete_user_account(...)` | — |

### 정상 동작이지만 헷갈릴 수 있는 부분

1. **`keyword`/`sub_category`가 일반 pylint 이슈(C0114, C0116 등)엔 빈 값** — 의도된 동작.
   보안 개념 매핑이 있는 이슈(B608, B105 등)만 채워진다.
2. **`framework`가 전부 `"none"`** — 이 데이터셋은 `tech_stack=["python"]`뿐이라 그렇다.
   django/fastapi가 있으면 해당 값이 들어간다(`test_django_in_tech_stack_sets_django_framework`로 검증).
3. **`name_of_function`이 모듈/클래스 레벨 이슈엔 `""`** — 함수 밖이라 정확한 동작.

---

## 6. 테스트

```bash
cd sub2_new
python -m pytest dev2/tests/test_concept_mapper.py -q                                   # 62 passed
python -m pytest dev2/tests/test_schema.py dev2/tests/test_nodes.py dev2/tests/test_concept_mapper.py -q   # 88 passed
```

추가 검증 항목:
- pylint backslash 경로 → forward-slash diff 매칭 (`code_snippet` 회귀 방지)
- Python AST: 함수 내부 / 메서드 / 중첩 함수(innermost) / 모듈 레벨(`""`)
- 비-Python(JS) 정규식 fallback / Python SyntaxError 시 정규식 fallback
- 빈 diff → `""` 반환
