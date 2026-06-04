# Claude Code 작업 프롬프트: M2 Security Cases 데이터셋 생성 v2

## 목적

Task-Link 프로젝트의 M2 코드 리뷰 모듈을 평가하기 위한 보안 데이터셋을 생성한다.

이번 v2의 핵심 변경점:

```text
expected_issue.json과 expected_m2_issues.json을 Dev2 Output Contract에 맞춰 확장한다.
```

Dev2 Output Contract의 issues[] 필드는 아래 필드를 포함해야 한다.

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

따라서 각 custom case의 `expected_issue.json`도 위 필드를 포함해야 한다.

---

## Claude Code에게 요청할 작업

아래 작업을 그대로 수행해줘.

---

## 1. 폴더 구조 생성

프로젝트 루트 기준으로 아래 구조를 생성해줘.

```text
datasets/
    ├── dataset_manifest.json
    ├── m2_owasp_benchmark_python_selected/
    │   ├── owasp_benchmarkpython_selected/
    │   │   ├── testcode/
    │   │   ├── expectedresults_selected.csv
    │   │   └── source_info.md
    │   │
    ├── m2_custom_security_cases/
    │       ├── sqli_case/
    │       ├── path_traversal_case/
    │       ├── command_injection_case/
    │       ├── auth_missing_case/
    │       ├── insecure_password_hash_case/
    │       └── hardcoded_secret_case/
    │
    └── expected_outputs/
        └── expected_m2_issues.json
```

---

## 2. OWASP BenchmarkPython selected 구성

OWASP BenchmarkPython 전체 레포를 통째로 복사하지 말고, M2 검증에 필요한 일부 파일만 선택해서 넣어줘.

대상 저장 위치:

```text
datasets/m2_owasp_benchmark_python_selected/
```

필요한 파일:

```text
testcode/
expectedresults_selected.csv
source_info.md
```

`testcode/`에는 OWASP BenchmarkPython의 `BenchmarkTest*.py` 파일 중 selected case만 복사한다.

선택 기준:

```text
SQL Injection        4개 이상
XSS                  4개 이상
Path Traversal       4개 이상
Command Injection    4개 이상
Weak Hash            4개 이상
```

각 카테고리는 가능하면 `real_vulnerability=true`와 `real_vulnerability=false`가 섞이도록 구성한다.

`expectedresults_selected.csv`는 아래 형식으로 만든다.

```csv
test_name,category,real_vulnerability,cwe
BenchmarkTest00283,sqli,true,89
BenchmarkTest00285,sqli,false,89
```

`source_info.md`에는 다음 내용을 포함한다.

```md
# OWASP BenchmarkPython Selected Cases

- Source: OWASP BenchmarkPython
- Purpose: M2 security code review validation
- Usage: SQL Injection, XSS, Path Traversal, Command Injection, Weak Hash detection
- Note: This folder contains only selected test cases, not the full benchmark repository.
```

---

## 3. Custom Security Cases 생성

아래 6개 케이스 폴더를 생성한다.

```text
m2_custom_security_cases/
├── sqli_case/
├── path_traversal_case/
├── command_injection_case/
├── auth_missing_case/
├── insecure_password_hash_case/
└── hardcoded_secret_case/
```

각 케이스 폴더 안에는 아래 4개 파일을 만든다.

```text
vulnerable.py
fixed.py
README.md
expected_issue.json
```

각 케이스의 코드는 `03_m2_custom_security_code_spec_v2.md`의 내용을 따른다.

---

## 4. expected_issue.json 필드 규칙

각 custom case의 `expected_issue.json`는 반드시 아래 구조를 따른다.

```json
{
  "case_id": "m2_custom_sqli_001",
  "module": "M2",
  "source": "Task-Link Custom",
  "agent": "security_scan",
  "expected_issues": [
    {
      "severity": "Critical",
      "issue_type": "Vulnerability",
      "line": 7,
      "file": "vulnerable.py",
      "message": "SQL Injection 가능성: 사용자 입력이 SQL 쿼리에 직접 삽입됩니다.",
      "rule_id": "SEC-001",
      "suggestion": "파라미터화된 쿼리를 사용하세요.",
      "resolution_example": "f-string SQL 조합 대신 db.execute(query, {\"keyword\": keyword}) 형태를 사용하세요.",
      "similar_issues": []
    }
  ]
}
```

주의:

```text
id 필드만 쓰지 말고 rule_id를 사용한다.
title/evidence/recommendation만 쓰지 말고 Dev2 Output Contract 필드를 사용한다.
similar_issues는 실제 RAG 결과가 없으므로 []로 둔다.
line은 vulnerable.py 기준 문제 발생 라인으로 작성한다.
file은 반드시 vulnerable.py로 작성한다.
```

---

## 5. expected_outputs 생성

다음 파일을 생성한다.

```text
datasets/expected_outputs/expected_m2_issues.json
```

이 파일에는 OWASP selected case와 custom case의 expected issue를 통합해서 작성한다.

최소한 custom 6개 케이스는 반드시 포함한다.

형식:

```json
{
  "module": "M2",
  "dataset": "m2_owasp_benchmark_python_selected",
  "cases": [
    {
      "case_id": "m2_custom_sqli_001",
      "source": "Task-Link Custom",
      "agent": "security_scan",
      "expected_issues": [
        {
          "severity": "Critical",
          "issue_type": "Vulnerability",
          "line": 7,
          "file": "m2_custom_security_cases/sqli_case/vulnerable.py",
          "message": "SQL Injection 가능성: 사용자 입력이 SQL 쿼리에 직접 삽입됩니다.",
          "rule_id": "SEC-001",
          "suggestion": "파라미터화된 쿼리를 사용하세요.",
          "resolution_example": "f-string SQL 조합 대신 db.execute(query, {\"keyword\": keyword}) 형태를 사용하세요.",
          "similar_issues": []
        }
      ]
    }
  ]
}
```

---

## 6. dataset_manifest.json 생성 또는 업데이트

다음 파일을 생성한다.

```text
datasets/dataset_manifest.json
```

각 case별로 아래 정보를 넣는다.

```json
{
  "case_id": "m2_custom_sqli_001",
  "module": "M2",
  "source": "Task-Link Custom",
  "agent": "security_scan",
  "case_type": "security",
  "category": "sqli",
  "cwe": "CWE-89",
  "target_path": "m2_custom_security_cases/sqli_case/vulnerable.py",
  "fixed_path": "m2_custom_security_cases/sqli_case/fixed.py",
  "expected_output_ref": "expected_outputs/expected_m2_issues.json",
  "expected_rule_ids": ["SEC-001"]
}
```

---

## 7. 완료 조건

작업 완료 후 아래를 확인해줘.

1. `datasets/m2_owasp_benchmark_python_selected/`가 존재한다.
2. `datasets/m2_custom_security_cases/`가 존재한다.
3. custom case 6개가 모두 존재한다.
4. 각 custom case 안에 `vulnerable.py`, `fixed.py`, `README.md`, `expected_issue.json`가 존재한다.
5. `expected_outputs/expected_m2_issues.json`가 존재한다.
6. `dataset_manifest.json`가 존재한다.
7. manifest의 `target_path`가 실제 파일 경로와 일치한다.
8. 각 `expected_issue.json`의 issue 객체가 아래 필드를 모두 가진다.

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

9. Custom case의 expected rule_id는 아래와 맞아야 한다.

```text
sqli_case                     → SEC-001
path_traversal_case           → SEC-003
command_injection_case        → SEC-004
auth_missing_case             → AUTH-001
insecure_password_hash_case   → SEC-005
hardcoded_secret_case         → SEC-006
```

---

## 8. 이번 작업에서 하지 말 것

- M3 데이터셋은 만들지 않는다.
- BugsInPy는 건드리지 않는다.
- M4 curriculum 데이터는 만들지 않는다.
- OWASP BenchmarkPython 전체 레포를 통째로 복사하지 않는다.
- 실제 운영 서비스 코드 `app/`에는 데이터를 넣지 않는다.
