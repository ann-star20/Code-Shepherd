# Task-Link 데이터셋 완료 검증 보고서

- **검증 일시**: 2026-06-03
- **검증 방식**: 읽기/검증 전용 (파일 생성·수정·이동·삭제 없음)
- **검증 대상 루트**: `datasets/`

---

## 1. 전체 판정

> **PASS** (초기 PASS_WITH_WARNINGS → 문서 표기 수정 후 PASS)

데이터 측면(필수 폴더/파일, JSON·CSV 파싱, manifest 정합성, expected output rule_id, true/false 균형)은 **모두 통과**.
초기 검증에서 발견된 문서(`FILE_STRUCTURE.md`) 케이스 수 표기 오류 1건(W-1)은 사용자 요청으로 **수정 완료**.

---

## 2. 전체 케이스 수

| 항목 | 수 |
|------|----|
| **전체 등록 케이스 (root manifest)** | **70** |
| M2 custom security | 6 |
| M2 OWASP BenchmarkPython selected | 50 |
| M3 BugsInPy selected | 8 |
| M3 custom test/performance | 6 |

manifest `source`별 분포: `Task-Link Custom` 12 (M2 6 + M3 6), `OWASP BenchmarkPython` 50, `BugsInPy` 8.

---

## 3~6. 영역별 검증 결과

### 3. M2 custom security — ✅ PASS
- 6개 케이스 폴더 모두 존재
- 각 케이스 `vulnerable.py` / `fixed.py` / `expected_issue.json` / `README.md` 존재
- `expected_issue.json` Dev2 Output Contract 9개 필드 충족
- rule_id 매핑 일치: auth_missing→AUTH-001, command_injection→SEC-004, hardcoded_secret→SEC-006, insecure_password_hash→SEC-005, path_traversal→SEC-003, sqli→SEC-001

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

### 6. M3 custom test/performance — ✅ PASS (문서 표기 W-1 수정 완료)
- 6개 케이스 모두 존재 (complexity_case, edge_case_missing_case, low_coverage_case, memory_leak_case, missing_test_function_case, n_plus_one_case)
- 각 케이스 `app/` / `tests/` / `expected_issue.json` / `README.md` 존재
- rule_id 매핑 일치: complexity→PERF-001, edge_case_missing→TEST-003, low_coverage→TEST-001, memory_leak→PERF-003, missing_test_function→TEST-004, n_plus_one→PERF-002

---

## 7. 누락 파일 목록

없음.

## 8. 경로 불일치 목록

없음. (root manifest 70개 `target_path` 전부 실재, `expected_output_ref` 전부 실재)

## 9. JSON/CSV 파싱 오류 목록

없음. (`dataset_manifest.json`, `expected_m2_issues.json`, `expected_m3_issues.json`, `expected_owasp_m2_issues.json`, OWASP 내부 `dataset_manifest.json`, 각 case JSON, CSV 모두 정상)

## 10. manifest target_path 오류 목록

없음. case_id 중복 없음, module 값 모두 M2/M3, source 값 모두 허용값(Task-Link Custom / OWASP BenchmarkPython / BugsInPy).

등록 수 검증: M2 custom=6 ✓, OWASP=50 ✓, BugsInPy=8 ✓, M3 perf=6 ✓.

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
| 2 | M2 custom 폴더/파일/필드/rule_id | ✅ |
| 3 | M2 OWASP 폴더·파일·CSV·testcode·매핑·정답 | ✅ |
| 4 | M3 BugsInPy 폴더·metadata·비어있지 않음 | ✅ |
| 5 | M3 custom perf 폴더/파일/rule_id | ✅ (문서 표기만 ⚠️) |
| 6 | root manifest 정합성 (target_path/중복/module/source) | ✅ |
| 7 | expected_outputs rule_id 형식 + OWASP 별도 정답 | ✅ |
