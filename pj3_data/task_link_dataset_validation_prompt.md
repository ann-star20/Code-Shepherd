# Claude Code 작업 프롬프트: Task-Link 데이터셋 완료 검증

## 목적

현재 `datasets/` 폴더의 데이터 작업이 완료되었는지 검증한다.

검증 대상은 아래 4개 영역이다.

```text
M2 custom security cases
M2 OWASP BenchmarkPython selected cases
M3 BugsInPy selected cases
M3 custom test/performance cases
```

이번 작업은 **데이터를 새로 만들거나 수정하는 작업이 아니라 검증 작업**이다.

---

## 중요 원칙

아래 작업은 반드시 읽기/검증 중심으로 수행한다.

```text
- 파일을 삭제하지 않는다.
- 기존 데이터 파일을 임의로 덮어쓰지 않는다.
- 누락된 파일이 있으면 생성하지 말고 보고서에 missing으로 기록한다.
- 경로가 틀리면 임의로 이동하지 말고 보고서에 path_mismatch로 기록한다.
- JSON/CSV 형식 오류가 있으면 수정하지 말고 보고서에 parse_error로 기록한다.
```

단, 사용자가 명시적으로 “수정까지 해줘”라고 요청하면 그때 수정한다.

---

## 실제 데이터셋 루트

현재 프로젝트의 데이터셋 루트는 아래다.

```text
datasets/
```

이 프로젝트는 아래 구조를 기준으로 검증한다.

```text
datasets/
├── dataset_manifest.json
├── expected_outputs/
│   ├── expected_m2_issues.json
│   └── expected_m3_issues.json
│
├── m2_custom_security_cases/
├── m2_owasp_benchmark_python_selected/
├── m3_bugsinpy_selected/
└── m3_test_performance_cases/
    └── custom_performance_cases/
```

---

# 1. 전체 루트 검증

아래 경로가 존재하는지 확인한다.

```text
datasets/
datasets/dataset_manifest.json
datasets/expected_outputs/
datasets/expected_outputs/expected_m2_issues.json
datasets/expected_outputs/expected_m3_issues.json
```

검증 항목:

```text
- dataset_manifest.json이 JSON으로 파싱 가능한가?
- expected_m2_issues.json이 JSON으로 파싱 가능한가?
- expected_m3_issues.json이 JSON으로 파싱 가능한가?
```

---

# 2. M2 Custom Security Cases 검증

## 2.1 필수 폴더

아래 폴더가 모두 존재해야 한다.

```text
datasets/m2_custom_security_cases/
datasets/m2_custom_security_cases/auth_missing_case/
datasets/m2_custom_security_cases/command_injection_case/
datasets/m2_custom_security_cases/hardcoded_secret_case/
datasets/m2_custom_security_cases/insecure_password_hash_case/
datasets/m2_custom_security_cases/path_traversal_case/
datasets/m2_custom_security_cases/sqli_case/
```

## 2.2 각 케이스 필수 파일

각 case 폴더 안에는 아래 파일이 있어야 한다.

```text
vulnerable.py
fixed.py
expected_issue.json
README.md
```

## 2.3 expected_issue.json 필드 검증

각 `expected_issue.json`의 issue 객체는 Dev2 Output Contract 필드를 포함해야 한다.

필수 필드:

```text
severity
issue_type
line
file
message
rule_id
suggestion
resolution_example
similar_issues
```

## 2.4 M2 Custom expected rule_id 검증

아래 매핑과 일치해야 한다.

```text
auth_missing_case             → AUTH-001
command_injection_case        → SEC-004
hardcoded_secret_case         → SEC-006
insecure_password_hash_case   → SEC-005
path_traversal_case           → SEC-003
sqli_case                     → SEC-001
```

---

# 3. M2 OWASP BenchmarkPython Selected 검증

## 3.1 필수 폴더/파일

아래 경로가 존재해야 한다.

```text
datasets/m2_owasp_benchmark_python_selected/
datasets/m2_owasp_benchmark_python_selected/testcode/
datasets/m2_owasp_benchmark_python_selected/dataset_manifest.json
datasets/m2_owasp_benchmark_python_selected/expectedresults_selected.csv
datasets/m2_owasp_benchmark_python_selected/expected_owasp_m2_issues.json
datasets/m2_owasp_benchmark_python_selected/source_info.md
datasets/m2_owasp_benchmark_python_selected/README.md
datasets/m2_owasp_benchmark_python_selected/LICENSE
```

## 3.2 testcode 검증

`testcode/` 안에 `BenchmarkTest*.py` 파일이 존재해야 한다.

검증 항목:

```text
- BenchmarkTest*.py 파일 개수
- 파일명이 expectedresults_selected.csv의 test_name과 일치하는가?
- CSV에 있는데 testcode에 없는 파일이 있는가?
- testcode에 있는데 CSV에 없는 파일이 있는가?
```

## 3.3 expectedresults_selected.csv 검증

CSV 필수 컬럼:

```text
test_name
category
real_vulnerability
cwe
```

필수 카테고리:

```text
sqli
xss
pathtraver
cmdi
hash
```

각 카테고리에 대해 가능하면 true/false가 모두 존재해야 한다.

검증 항목:

```text
- category별 case 수
- category별 true 수
- category별 false 수
- real_vulnerability 값이 true/false인지
- cwe 값이 숫자인지
```

## 3.4 OWASP category → rule_id 매핑 검증

아래 매핑과 일치해야 한다.

```text
sqli        → SEC-001
xss         → SEC-002
pathtraver  → SEC-003
cmdi        → SEC-004
hash        → SEC-005
```

CWE 매핑:

```text
sqli        → CWE-89
xss         → CWE-79
pathtraver  → CWE-22
cmdi        → CWE-78
hash        → CWE-328
```

## 3.5 expected_owasp_m2_issues.json 검증

검증 항목:

```text
- JSON으로 파싱 가능한가?
- CSV case 수와 JSON cases 수가 일치하는가?
- real_vulnerability=true인 case는 expected_issues 길이가 1 이상인가?
- real_vulnerability=false인 case는 expected_issues가 빈 배열인가?
- true case의 issue 객체가 Dev2 Output Contract 필드를 모두 갖는가?
```

Dev2 Output Contract 필드:

```text
severity
issue_type
line
file
message
rule_id
suggestion
resolution_example
similar_issues
```

---

# 4. M3 BugsInPy Selected 검증

## 4.1 필수 폴더

아래 폴더가 존재해야 한다.

```text
datasets/m3_bugsinpy_selected/
```

기대 케이스:

```text
black_3
black_4
cookiecutter_1
cookiecutter_2
fastapi_2
fastapi_5
tqdm_1
tqdm_4
```

## 4.2 각 BugsInPy 케이스 필수 구조

각 case 폴더 안에 아래 구조가 있어야 한다.

```text
buggy/
fixed/
metadata/
expected_m3_issues.json
```

`metadata/` 안에는 아래 파일이 있어야 한다.

```text
bug.info
bug_patch.txt
project.info
requirements.txt
run_test.sh
```

## 4.3 검증 항목

각 BugsInPy case에 대해 아래를 확인한다.

```text
- buggy/ 폴더가 비어 있지 않은가?
- fixed/ 폴더가 비어 있지 않은가?
- metadata/ 필수 파일이 모두 존재하는가?
- expected_m3_issues.json이 JSON으로 파싱 가능한가?
- bug_patch.txt가 비어 있지 않은가?
- run_test.sh가 비어 있지 않은가?
```

---

# 5. M3 Custom Test/Performance Cases 검증

## 5.1 필수 폴더

아래 폴더가 존재해야 한다.

```text
datasets/m3_test_performance_cases/
datasets/m3_test_performance_cases/custom_performance_cases/
```

필수 custom case:

```text
complexity_case
edge_case_missing_case
low_coverage_case
memory_leak_case
missing_test_function_case
n_plus_one_case
```

주의:

`FILE_STRUCTURE.md`에는 “7종”이라고 적혀 있지만 실제 목록은 6개다.  
검증 시에는 실제 폴더 목록과 문서 설명의 불일치도 보고서에 기록한다.

## 5.2 각 케이스 필수 파일

각 custom performance case 안에는 아래 파일/폴더가 있어야 한다.

```text
app/
tests/
expected_issue.json
README.md
```

## 5.3 expected_issue.json rule_id 검증

아래 매핑과 일치해야 한다.

```text
complexity_case               → PERF-001
edge_case_missing_case        → TEST-003
low_coverage_case             → TEST-001
memory_leak_case              → PERF-003
missing_test_function_case    → TEST-004
n_plus_one_case               → PERF-002
```

---

# 6. dataset_manifest.json 정합성 검증

대상 파일:

```text
datasets/dataset_manifest.json
```

검증 항목:

```text
- JSON으로 파싱 가능한가?
- M2 custom case 6개가 등록되어 있는가?
- M2 OWASP selected case가 등록되어 있는가?
- M3 BugsInPy selected case 8개가 등록되어 있는가?
- M3 custom performance case 6개가 등록되어 있는가?
- 각 manifest item의 target_path가 실제 존재하는가?
- 각 manifest item의 expected_output_ref가 실제 존재하는가?
- case_id가 중복되지 않는가?
- module 값이 M2 또는 M3로 올바른가?
- source 값이 Task-Link Custom / OWASP BenchmarkPython / BugsInPy 중 하나로 일관되는가?
```

---

# 7. expected_outputs 정합성 검증

대상:

```text
datasets/expected_outputs/expected_m2_issues.json
datasets/expected_outputs/expected_m3_issues.json
```

검증 항목:

```text
- JSON으로 파싱 가능한가?
- case_id가 실제 case 폴더 또는 manifest case_id와 연결되는가?
- rule_id가 각 케이스의 expected_issue.json과 일치하는가?
- M2 rule_id가 SEC-* 또는 AUTH-* 형식을 따르는가?
- M3 rule_id가 TEST-* 또는 PERF-* 형식을 따르는가?
```

주의:

OWASP 전용 expected 파일은 아래 별도 위치에 있을 수 있다.

```text
datasets/m2_owasp_benchmark_python_selected/expected_owasp_m2_issues.json
```

이 파일도 함께 검증한다.

---

# 8. 최종 보고서 생성

검증 결과를 아래 파일로 저장한다.

```text
datasets/DATASET_VALIDATION_REPORT.md
```

보고서에는 아래 내용을 포함한다.

```text
1. 전체 판정: PASS / FAIL / PASS_WITH_WARNINGS
2. 전체 케이스 수
3. M2 custom case 수
4. M2 OWASP case 수
5. M3 BugsInPy case 수
6. M3 custom performance case 수
7. 누락 파일 목록
8. 경로 불일치 목록
9. JSON/CSV 파싱 오류 목록
10. manifest target_path 오류 목록
11. expected output 불일치 목록
12. true/false 라벨 불균형 여부
13. 최종 수정 필요 작업 목록
```

판정 기준:

```text
PASS:
- 필수 폴더/파일이 모두 존재
- JSON/CSV 파싱 오류 없음
- manifest target_path 모두 유효
- expected output rule_id 정합성 OK

PASS_WITH_WARNINGS:
- 필수 기능은 동작 가능하지만 true/false 불균형, 문서상 케이스 수 오타, 선택적 파일 누락 등이 있음

FAIL:
- 필수 폴더/파일 누락
- JSON/CSV 파싱 실패
- manifest target_path 다수 불일치
- expected output 핵심 rule_id 불일치
```

---

# 9. 출력 형식

작업 완료 후 대화창에 아래 형식으로 요약해줘.

```text
DATASET VALIDATION RESULT

Overall: PASS / FAIL / PASS_WITH_WARNINGS

Counts:
- M2 custom:
- M2 OWASP:
- M3 BugsInPy:
- M3 custom performance:

Critical Problems:
- ...

Warnings:
- ...

Report:
- datasets/DATASET_VALIDATION_REPORT.md
```

---

# 10. 이번 작업에서 하지 말 것

```text
- 누락 파일을 임의 생성하지 않는다.
- JSON/CSV를 임의 수정하지 않는다.
- 폴더를 이동하지 않는다.
- custom case를 새로 만들지 않는다.
- OWASP/BugsInPy를 새로 다운로드하지 않는다.
- 서비스 코드 app/를 수정하지 않는다.
```

검증만 수행하고, 수정이 필요한 부분은 보고서에 정리한다.
