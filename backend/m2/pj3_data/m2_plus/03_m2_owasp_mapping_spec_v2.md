# M2 OWASP BenchmarkPython 매핑 명세 v2

## 목적

현재 프로젝트의 실제 `datasets/` 구조에 맞춰 OWASP BenchmarkPython selected cases를 Task-Link M2 Output Contract 형식으로 변환하는 규칙을 정의한다.

---

## 입력 데이터

```text
datasets/m2_owasp_benchmark_python_selected/expectedresults_selected.csv
```

형식:

```csv
test_name,category,real_vulnerability,cwe
BenchmarkTest00283,sqli,true,89
BenchmarkTest00285,sqli,false,89
```

---

## 출력 데이터

```text
datasets/m2_owasp_benchmark_python_selected/expected_owasp_m2_issues.json
```

---

## 전체 manifest

```text
datasets/dataset_manifest.json
```

기존 M2 custom/M3 항목을 유지하고 OWASP case 항목만 추가한다.

---

## OWASP 내부 manifest

```text
datasets/m2_owasp_benchmark_python_selected/dataset_manifest.json
```

OWASP selected subset 내부 전용 manifest다.

---

## category 매핑

| OWASP category | Meaning | CWE | Task-Link rule_id | Severity | Suggestion |
|---|---|---:|---|---|---|
| `sqli` | SQL Injection | 89 | `SEC-001` | Critical | Use parameterized queries. |
| `xss` | Cross-Site Scripting | 79 | `SEC-002` | Critical | Escape or sanitize untrusted output. |
| `pathtraver` | Path Traversal | 22 | `SEC-003` | Critical | Normalize and validate file paths. |
| `cmdi` | Command Injection | 78 | `SEC-004` | Critical | Avoid shell string execution. |
| `hash` | Weak Hash | 328 | `SEC-005` | Major | Use a modern secure hashing algorithm. |

---

## case_id 생성 규칙

```text
m2_owasp_{category}_{test_name}
```

예시:

```text
m2_owasp_sqli_BenchmarkTest00283
m2_owasp_xss_BenchmarkTest00187
m2_owasp_pathtraver_BenchmarkTest00001
```

---

## file 경로 규칙

`expected_owasp_m2_issues.json` 내부의 issue `file` 필드는 파일명만 쓴다.

예시:

```text
BenchmarkTest00283.py
```

`datasets/dataset_manifest.json`의 `target_path`는 `datasets/` 기준 상대 경로를 쓴다.

예시:

```text
m2_owasp_benchmark_python_selected/testcode/BenchmarkTest00283.py
```

`datasets/m2_owasp_benchmark_python_selected/dataset_manifest.json`의 `target_path`는 OWASP 폴더 기준 상대 경로를 쓴다.

예시:

```text
testcode/BenchmarkTest00283.py
```

---

## line 규칙

OWASP selected case는 원본 라벨 중심 평가이므로 line을 정확히 계산하지 못하면 `null`로 둔다.

```json
"line": null
```

---

## real_vulnerability=true 변환 규칙

`real_vulnerability=true`인 경우 expected issue를 생성한다.

```json
{
  "case_id": "m2_owasp_sqli_BenchmarkTest00283",
  "source": "OWASP BenchmarkPython",
  "agent": "security_scan",
  "category": "sqli",
  "cwe": "CWE-89",
  "real_vulnerability": true,
  "expected_issues": [
    {
      "severity": "Critical",
      "issue_type": "Vulnerability",
      "line": null,
      "file": "BenchmarkTest00283.py",
      "message": "OWASP BenchmarkPython labels this case as a real SQL Injection vulnerability.",
      "rule_id": "SEC-001",
      "suggestion": "Use parameterized queries and avoid direct string interpolation in SQL.",
      "resolution_example": "Replace raw SQL string construction with parameterized query execution.",
      "similar_issues": []
    }
  ]
}
```

---

## real_vulnerability=false 변환 규칙

`real_vulnerability=false`인 경우 expected issue를 만들지 않는다.

```json
{
  "case_id": "m2_owasp_sqli_BenchmarkTest00285",
  "source": "OWASP BenchmarkPython",
  "agent": "security_scan",
  "category": "sqli",
  "cwe": "CWE-89",
  "real_vulnerability": false,
  "expected_issues": []
}
```

---

## 카테고리별 message/suggestion/resolution_example

### sqli → SEC-001

```json
{
  "message": "OWASP BenchmarkPython labels this case as a real SQL Injection vulnerability.",
  "suggestion": "Use parameterized queries and avoid direct string interpolation in SQL.",
  "resolution_example": "Replace raw SQL string construction with parameterized query execution."
}
```

### xss → SEC-002

```json
{
  "message": "OWASP BenchmarkPython labels this case as a real Cross-Site Scripting vulnerability.",
  "suggestion": "Escape or sanitize untrusted input before rendering it in HTML or JavaScript contexts.",
  "resolution_example": "Use framework-provided escaping and avoid directly writing user input to responses."
}
```

### pathtraver → SEC-003

```json
{
  "message": "OWASP BenchmarkPython labels this case as a real Path Traversal vulnerability.",
  "suggestion": "Normalize the path and verify it stays within the allowed base directory.",
  "resolution_example": "Resolve the target path and reject it if it escapes the configured base directory."
}
```

### cmdi → SEC-004

```json
{
  "message": "OWASP BenchmarkPython labels this case as a real Command Injection vulnerability.",
  "suggestion": "Avoid building shell command strings from user input.",
  "resolution_example": "Use subprocess with an argument list and shell=False."
}
```

### hash → SEC-005

```json
{
  "message": "OWASP BenchmarkPython labels this case as a real Weak Hash vulnerability.",
  "suggestion": "Use a modern secure hashing algorithm appropriate for the data being protected.",
  "resolution_example": "Replace MD5/SHA1 with SHA-256 for integrity or bcrypt/Argon2/PBKDF2 for passwords."
}
```

---

## 전체 manifest 항목 예시

경로:

```text
datasets/dataset_manifest.json
```

```json
{
  "case_id": "m2_owasp_sqli_BenchmarkTest00283",
  "module": "M2",
  "source": "OWASP BenchmarkPython",
  "agent": "security_scan",
  "case_type": "security",
  "category": "sqli",
  "cwe": "CWE-89",
  "real_vulnerability": true,
  "target_path": "m2_owasp_benchmark_python_selected/testcode/BenchmarkTest00283.py",
  "expected_output_ref": "m2_owasp_benchmark_python_selected/expected_owasp_m2_issues.json",
  "expected_rule_ids": ["SEC-001"]
}
```

---

## OWASP 내부 manifest 항목 예시

경로:

```text
datasets/m2_owasp_benchmark_python_selected/dataset_manifest.json
```

```json
{
  "case_id": "m2_owasp_sqli_BenchmarkTest00283",
  "category": "sqli",
  "cwe": "CWE-89",
  "real_vulnerability": true,
  "target_path": "testcode/BenchmarkTest00283.py",
  "expected_rule_ids": ["SEC-001"]
}
```

---

## 검증 기준

- CSV의 selected case 수와 JSON의 case 수가 일치해야 한다.
- true case는 expected_issues 길이가 1 이상이어야 한다.
- false case는 expected_issues 길이가 0이어야 한다.
- category와 rule_id 매핑이 정확해야 한다.
- root manifest의 target_path가 실제 파일과 일치해야 한다.
- OWASP 내부 manifest의 target_path가 testcode 기준 실제 파일과 일치해야 한다.
