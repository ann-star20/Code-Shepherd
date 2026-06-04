# Task-Link 데이터셋 완료 검증 보고서

- **검증 일시**: 2026-06-04 (M2 mixed 6종에 A커머스 커스텀 규칙 매핑 `ecommerce_custom_issues` 부가 후 재검증)
- **검증 방식**: 읽기/검증 + 자동 정합성 스크립트 + pytest 실행 (`datasets/` 내부에서만 작업)
- **검증 대상 루트**: `datasets/`
- **검증 범위**: 전체 90개 케이스 (manifest 정합성 10항목 + 영역별 + pytest 8건)

---

## 1. 전체 판정

> **PASS**

데이터 측면(필수 폴더/파일, JSON·CSV 파싱, manifest 정합성, expected output rule_id, true/false 균형)은 **모두 통과**.
M2 mixed 보안 케이스 6종(한 파일에 3~5개 보안 이슈 혼합) 추가 후 manifest(90) / expected_issue.json / target_path·expected_output_ref 정합성 전부 통과.

---

## 2. 전체 케이스 수

| 항목 | 수 |
|------|----|
| **전체 등록 케이스 (root manifest)** | **90** |
| M2 custom security (단일) | 6 |
| M2 custom security (mixed) | 6 |
| M2 OWASP BenchmarkPython selected | 50 |
| M3 BugsInPy selected | 8 |
| M3 custom test/performance | 14 (기본 6 + N+1 확장 8) |
| M3 mixed project | 6 |

manifest `module`별 분포: M2 62 / M3 28. `source`별 분포: `Task-Link Custom` 32 (M2 12 + M3 20), `OWASP BenchmarkPython` 50, `BugsInPy` 8.

### M2 mixed 보안 케이스 (`m2_custom_security_cases/mixed_case_0N/`) — ✅ PASS

한 파일(`vulnerable.py`)에 3~5개의 서로 다른 M2 보안 이슈를 혼합한 케이스. 다중 이슈 동시 탐지 검증용.

| 케이스 | case_id | 이슈 수 | rule_ids |
|--------|---------|---------|----------|
| mixed_case_01 | m2_custom_mixed_001 | 3 | SEC-006, SEC-005, SEC-001 |
| mixed_case_02 | m2_custom_mixed_002 | 3 | SEC-003, SEC-004, AUTH-001 |
| mixed_case_03 | m2_custom_mixed_003 | 4 | SEC-006, SEC-001, SEC-005, AUTH-001 |
| mixed_case_04 | m2_custom_mixed_004 | 3 | SEC-006, SEC-003, SEC-004 |
| mixed_case_05 | m2_custom_mixed_005 | 3 | SEC-005, SEC-001, SEC-004 |
| mixed_case_06 | m2_custom_mixed_006 | 5 | SEC-006, SEC-001, SEC-003, SEC-005, AUTH-001 |

- 6개 모두 `vulnerable.py` / `expected_issue.json` / `README.md` 존재 ✓
- 각 `expected_issue.json`의 `rule_id` 집합 = manifest `rule_ids` 완전 일치 ✓
- manifest `target_path` 6개 전부 실재, `expected_output_ref` 6개 전부 실재 ✓
- 기존 단일 보안 케이스 6종 미수정 ✓

### M2 mixed 케이스 — A커머스 전용 커스텀 규칙 매핑 (`ecommerce_custom_issues`) — ✅ PASS

기존 mixed_case_01~06 의 `expected_issue.json` 에 A커머스(e-commerce) 전용 커스텀 규칙
탐지 기대값을 **추가 필드** `ecommerce_custom_issues` 로 부가했다. 기존 `expected_issues`
(SEC-*/AUTH-*) 배열과 manifest 는 **전혀 수정하지 않은 비파괴(additive) 변경**이며,
케이스 수는 90 그대로다. 근거 규칙: `docs/dev2-custom-rules-security-scan.md`,
`docs/dev2-custom-rules-static-analysis.md`.

| 케이스 | 추가 e-commerce 규칙 (rule_id) | concept_id 매핑 |
|--------|-------------------------------|------------------|
| mixed_case_01 | ASEC-005, ASEC-001, ASA-007 | SEC-006, SEC-001, — |
| mixed_case_02 | ASEC-007, ASEC-008 | SEC-003, SEC-004 |
| mixed_case_03 | ASEC-005, ASEC-001, ASA-007 | SEC-006, SEC-001, — |
| mixed_case_04 | ASEC-005, ASEC-008, ASA-007 | SEC-006, SEC-004, — |
| mixed_case_05 | ASEC-001, ASEC-008 | SEC-001, SEC-004 |
| mixed_case_06 | ASEC-001, ASEC-007 | SEC-001, SEC-003 |

- 각 케이스에 도메인 매칭되는 e-commerce 규칙 2~3개씩 부가 (총 15개 매핑) ✓
- 6개 `expected_issue.json` 전부 JSON 파싱 정상, 기존 `expected_issues` 배열 보존 ✓
- `ASEC-*`/`AAUTH-*` 는 평가셋 `SEC-*`/`AUTH-*` 와 `concept_id` 로 개념 매핑 (M4 학습 연계) ✓
- `ASA-007`(외부 키/URL 하드코딩)은 정적분석 커스텀 규칙으로 concept 매핑 없음(—) ✓
- manifest `rule_ids`(SEC-*/AUTH-*)·`target_path`·`expected_output_ref` 미변경 → 정합성 영향 없음 ✓

### N+1 확장 케이스 (`n_plus_one_extended_cases/`) — ✅ PASS

| 케이스 | case_id | 종류 | 기대 |
|--------|---------|------|------|
| positive_repository_find_by_id | m3_custom_n_plus_one_repository_001 | positive | PERF-002 |
| positive_db_execute_in_loop | m3_custom_n_plus_one_db_execute_001 | positive | PERF-002 |
| positive_sqlalchemy_query_in_loop | m3_custom_n_plus_one_sqlalchemy_001 | positive | PERF-002 |
| positive_nested_loop_db_call | m3_custom_n_plus_one_nested_loop_001 | positive | PERF-002 |
| negative_bulk_fetch_before_loop | m3_custom_n_plus_one_negative_bulk_fetch_001 | negative | [] |
| negative_loop_without_db_call | m3_custom_n_plus_one_negative_no_db_001 | negative | [] |
| negative_local_dict_get | m3_custom_n_plus_one_negative_dict_get_001 | negative | [] |
| negative_self_query_method | m3_custom_n_plus_one_negative_self_query_001 | negative | [] |

- 8개 모두 `app/` / `tests/` / `expected_issue.json` / `README.md` 존재 ✓
- positive 4개 `expected_issues`에 PERF-002 1건, negative 4개 빈 배열 ✓
- manifest `target_path` 8개 전부 실재, `expected_m3_issues.json` 8개 등록 일치 ✓
- 8개 케이스 pytest **전부 통과** (8 passed) ✓
- 기존 `n_plus_one_case` 및 M2/BugsInPy/OWASP 원본 미수정 ✓

---

## 2-1. 전체 매니페스트 재검증 (자동 스크립트, 2026-06-04)

`dataset_manifest.json` 90개 케이스 전체를 대상으로 자동 정합성 스크립트를 실행한 결과 **10개 항목 전부 PASS**.

| # | 검증 항목 | 방법 | 결과 |
|---|-----------|------|------|
| 1 | 카운트 정합성 | `total_case_count` vs 실제 `cases` 길이 | `90 == 90` ✅ |
| 2 | case_id 중복 | 전체 case_id 유일성 | 중복 없음 ✅ |
| 3 | source 분포 | 그룹 카운트 | Task-Link Custom 32 / OWASP 50 / BugsInPy 8 ✅ |
| 4 | module 분포 | 그룹 카운트 | M2 62 / M3 28 ✅ |
| 5 | target_path 실재 | 90개 경로 `os.path.exists` | 누락 없음 (전부 실재) ✅ |
| 6 | expected_output_ref 실재 | 참조 파일 존재 확인 | 누락 없음 ✅ |
| 7 | module/source 허용값 | M2/M3 · 3개 source 화이트리스트 | 위반 없음 ✅ |
| 8 | M3 custom ↔ expected_m3 교차 | 14 vs 14, 누락/잉여 | 완전 일치 ✅ |
| 9 | manifest rule_id ↔ expected issue_ids | positive=rule_id, negative=[], mixed=rule_ids 집합 비교 | 불일치 없음 ✅ |
| 10 | 각 case `expected_issue.json` ↔ manifest | issue id 집합 비교 (M2/M3 mixed 포함) | 불일치 없음 ✅ |

추가 확인:
- **OWASP true/false 균형**: cmdi·hash·pathtraver·sqli·xss 모두 `true=5 / false=5` (전체 true 25 / false 25) ✅
- **정답 JSON 파싱**: `expected_m2_issues.json`, `expected_owasp_m2_issues.json` 정상 파싱 ✅

> 콘솔 출력의 한글 깨짐은 Windows 콘솔 인코딩(cp949) 표시 문제일 뿐 검증 로직·결과에는 영향 없음.

---

## 3~6. 영역별 검증 결과

### 3. M2 custom security — ✅ PASS
- 단일 6개 + mixed 6개 = **12개** 케이스 폴더 모두 존재
- 단일 케이스: `vulnerable.py` / `fixed.py` / `expected_issue.json` / `README.md` 존재
- mixed 케이스: `vulnerable.py` / `expected_issue.json` / `README.md` 존재 (섹션 2 참고)
- `expected_issue.json` Dev2 Output Contract 9개 필드 충족
- rule_id 매핑 일치: auth_missing→AUTH-001, command_injection→SEC-004, hardcoded_secret→SEC-006, insecure_password_hash→SEC-005, path_traversal→SEC-003, sqli→SEC-001
- mixed 케이스 `rule_ids` 집합 = 각 `expected_issue.json` rule_id 집합 완전 일치

### 4. M2 OWASP BenchmarkPython selected — ✅ PASS
- 필수 파일 모두 존재 (`testcode/`, `dataset_manifest.json`, `expectedresults_selected.csv`, `expected_owasp_m2_issues.json`, `source_info.md`, `README.md`, `LICENSE`)
- `testcode/` BenchmarkTest*.py **50개**, CSV `test_name`과 1:1 완전 일치 (CSV에만 있거나 testcode에만 있는 파일 없음)
- CSV 4개 컬럼 존재, `real_vulnerability` 모두 true/false, `cwe` 모두 숫자
- category→rule_id 매핑 일치 (sqli→SEC-001, xss→SEC-002, pathtraver→SEC-003, cmdi→SEC-004, hash→SEC-005)
- category→CWE 매핑 일치 (89/79/22/78/328)
- `expected_owasp_m2_issues.json` cases 50개 = CSV 50행 일치
- true 25개 → expected_issues ≥1, false 25개 → expected_issues = []
- true case issue 객체 9개 필드 충족

**category별 true/false 분포 (균형 완전):**

| category | true | false |
|----------|------|-------|
| sqli | 5 | 5 |
| xss | 5 | 5 |
| pathtraver | 5 | 5 |
| cmdi | 5 | 5 |
| hash | 5 | 5 |

### 5. M3 BugsInPy selected — ✅ PASS
- 8개 케이스 모두 존재 (black_3, black_4, cookiecutter_1, cookiecutter_2, fastapi_2, fastapi_5, tqdm_1, tqdm_4)
- 각 케이스 `buggy/` / `fixed/` / `metadata/` / `expected_m3_issues.json` 존재
- `buggy/`·`fixed/` 비어있지 않음
- `metadata/` 필수 5개 파일 존재 (bug.info, bug_patch.txt, project.info, requirements.txt, run_test.sh)
- `bug_patch.txt`·`run_test.sh` 비어있지 않음
- `expected_m3_issues.json` JSON 파싱 정상

### 6. M3 custom test/performance — ✅ PASS
- 기본 6개 케이스 모두 존재 (complexity_case, edge_case_missing_case, low_coverage_case, memory_leak_case, missing_test_function_case, n_plus_one_case)
- N+1 확장 8개 케이스 추가 (`n_plus_one_extended_cases/`, 섹션 2 참고)
- 각 케이스 `app/` / `tests/` / `expected_issue.json` / `README.md` 존재
- rule_id 매핑 일치: complexity→PERF-001, edge_case_missing→TEST-003, low_coverage→TEST-001, memory_leak→PERF-003, missing_test_function→TEST-004, n_plus_one→PERF-002
- N+1 확장 positive 4→PERF-002, negative 4→[] 일치

---

## 7. 누락 파일 목록

없음.

## 8. 경로 불일치 목록

없음. (root manifest 90개 `target_path` 전부 실재, `expected_output_ref` 전부 실재)

## 9. JSON/CSV 파싱 오류 목록

없음. (`dataset_manifest.json`, `expected_m2_issues.json`, `expected_m3_issues.json`, `expected_owasp_m2_issues.json`, OWASP 내부 `dataset_manifest.json`, 각 case JSON, CSV 모두 정상)

## 10. manifest target_path 오류 목록

없음. case_id 중복 없음, module 값 모두 M2/M3, source 값 모두 허용값(Task-Link Custom / OWASP BenchmarkPython / BugsInPy).

등록 수 검증: M2 custom 단일=6 ✓, M2 custom mixed=6 ✓, OWASP=50 ✓, BugsInPy=8 ✓, M3 perf=14 (기본 6 + N+1 확장 8) ✓, M3 mixed=6 ✓.

## 11. expected output 불일치 목록

없음.
- M2 rule_id 모두 `SEC-*` / `AUTH-*` 형식
- M3 rule_id 모두 `TEST-*` / `PERF-*` 형식
- OWASP true case rule_id가 category 매핑과 일치

## 12. true/false 라벨 불균형 여부

불균형 없음. OWASP 5개 카테고리 모두 true 5 / false 5로 완전 균형 (전체 true 25 / false 25).

---

## 13. 최종 수정 필요 작업 목록

> 모든 항목 처리 완료. 잔여 작업 없음.

| # | 구분 | 위치 | 내용 | 조치 결과 |
|---|------|------|------|-----------|
| W-1 | 문서 불일치 | `datasets/FILE_STRUCTURE.md` (line 50, 71) | M3 custom test/performance를 **"7종 / 7"** 로 표기했으나 실제 폴더·manifest는 **6개** | ✅ **수정 완료** — "6종 / 6"으로 정정 (2026-06-03) |

---

## 부록: 검증 항목 대비 결과 요약

| 섹션 | 항목 | 결과 |
|------|------|------|
| 1 | 루트 필수 파일 + 3개 JSON 파싱 | ✅ |
| 2 | M2 custom 폴더/파일/필드/rule_id (단일 6 + mixed 6) | ✅ |
| 2-a | M2 mixed 6종 A커머스 커스텀 규칙 매핑(`ecommerce_custom_issues`, 비파괴) | ✅ |
| 2-1 | 전체 매니페스트 자동 재검증 10항목 (90 케이스) | ✅ |
| 3 | M2 OWASP 폴더·파일·CSV·testcode·매핑·정답 | ✅ |
| 4 | M3 BugsInPy 폴더·metadata·비어있지 않음 | ✅ |
| 5 | M3 custom perf 폴더/파일/rule_id (+ N+1 확장 8) | ✅ |
| 6 | root manifest 정합성 (target_path/중복/module/source) | ✅ |
| 7 | expected_outputs rule_id 형식 + OWASP 별도 정답 | ✅ |
| 8 | N+1 확장 8 케이스 pytest (8 passed) | ✅ |
