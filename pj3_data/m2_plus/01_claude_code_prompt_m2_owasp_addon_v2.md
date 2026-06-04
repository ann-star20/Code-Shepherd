# Claude Code 작업 프롬프트: 기존 datasets 구조에 OWASP BenchmarkPython Selected 보완

## 목적

현재 프로젝트의 실제 `datasets/` 폴더 구조에 맞춰 **M2 OWASP BenchmarkPython selected 데이터셋**을 보완한다.

중요: 이 프로젝트는 `datasets/task_link_eval_dataset/` 구조를 사용하지 않는다.  
현재 실제 루트는 `datasets/` 자체다.

---

## 실제 기존 데이터 기준 경로

기존 데이터셋 루트:

```text
datasets/
```

기존 M2 custom 데이터:

```text
datasets/m2_custom_security_cases/
```

OWASP BenchmarkPython selected 위치:

```text
datasets/m2_owasp_benchmark_python_selected/
```

수정할 파일:

```text
datasets/dataset_manifest.json
```

유지할 파일:

```text
datasets/expected_outputs/expected_m2_issues.json
```

주의:

```text
- datasets/m2_custom_security_cases/는 수정하지 않는다.
- datasets/expected_outputs/expected_m2_issues.json은 삭제하거나 덮어쓰지 않는다.
- OWASP 정답은 별도 파일로 datasets/m2_owasp_benchmark_python_selected/expected_owasp_m2_issues.json에 저장한다.
```

---

## 현재 기대 구조

```text
datasets/
├── dataset_manifest.json
├── expected_outputs/
│   ├── expected_m2_issues.json
│   └── expected_m3_issues.json
│
├── m2_custom_security_cases/
│   ├── auth_missing_case/
│   ├── command_injection_case/
│   ├── hardcoded_secret_case/
│   ├── insecure_password_hash_case/
│   ├── path_traversal_case/
│   └── sqli_case/
│
└── m2_owasp_benchmark_python_selected/
    ├── dataset_manifest.json
    ├── expectedresults_selected.csv
    ├── expected_owasp_m2_issues.json
    ├── source_info.md
    ├── README.md
    ├── LICENSE
    └── testcode/
        ├── BenchmarkTest00001.py
        └── ...
```

---

## Claude Code에게 요청할 작업

### 1. 기존 custom 데이터는 수정하지 말 것

아래 폴더는 건드리지 않는다.

```text
datasets/m2_custom_security_cases/
```

---

### 2. OWASP BenchmarkPython selected 폴더 확인 또는 생성

아래 경로를 확인한다.

```text
datasets/m2_owasp_benchmark_python_selected/
```

없으면 생성한다.

필수 구성:

```text
dataset_manifest.json
expectedresults_selected.csv
expected_owasp_m2_issues.json
source_info.md
README.md
LICENSE
testcode/
```

`README.md`와 `LICENSE`는 원본 출처 보존용이다.  
없으면 가능한 범위에서 생성 또는 보존한다.

---

### 3. OWASP BenchmarkPython selected case 검증

`testcode/`에는 selected `BenchmarkTest*.py` 파일이 있어야 한다.

대상 카테고리:

```text
sqli          SQL Injection
xss           Cross-Site Scripting
pathtraver    Path Traversal
cmdi          Command Injection
hash          Weak Hash
```

각 카테고리는 가능하면 true/false를 균형 있게 포함한다.

---

### 4. expectedresults_selected.csv 확인 또는 생성

아래 경로를 확인한다.

```text
datasets/m2_owasp_benchmark_python_selected/expectedresults_selected.csv
```

형식:

```csv
test_name,category,real_vulnerability,cwe
BenchmarkTest00283,sqli,true,89
BenchmarkTest00285,sqli,false,89
BenchmarkTest00187,xss,true,79
BenchmarkTest00001,pathtraver,true,22
```

주의:

```text
test_name은 확장자 없이 작성한다.
real_vulnerability는 true 또는 false로 작성한다.
cwe는 숫자만 작성한다.
```

---

### 5. expected_owasp_m2_issues.json 생성 또는 갱신

아래 파일을 생성하거나 갱신한다.

```text
datasets/m2_owasp_benchmark_python_selected/expected_owasp_m2_issues.json
```

OWASP 라벨을 Task-Link M2 rule_id로 매핑한다.

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

`real_vulnerability=true`인 경우 `expected_issues`에 Dev2 Output Contract 형식의 issue를 넣는다.

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

true 예시:

```json
{
  "case_id": "m2_owasp_sqli_BenchmarkTest00283",
  "source": "OWASP BenchmarkPython",
  "agent": "security_scan",
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

`real_vulnerability=false`인 경우:

```json
{
  "case_id": "m2_owasp_sqli_BenchmarkTest00285",
  "source": "OWASP BenchmarkPython",
  "agent": "security_scan",
  "expected_issues": []
}
```

---

### 6. datasets/dataset_manifest.json 업데이트

아래 파일을 업데이트한다.

```text
datasets/dataset_manifest.json
```

기존 custom/M3 항목을 삭제하거나 변경하지 않는다.  
OWASP case 항목만 추가 또는 보완한다.

OWASP case manifest 예시:

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

false case 예시:

```json
{
  "case_id": "m2_owasp_sqli_BenchmarkTest00285",
  "module": "M2",
  "source": "OWASP BenchmarkPython",
  "agent": "security_scan",
  "case_type": "security",
  "category": "sqli",
  "cwe": "CWE-89",
  "real_vulnerability": false,
  "target_path": "m2_owasp_benchmark_python_selected/testcode/BenchmarkTest00285.py",
  "expected_output_ref": "m2_owasp_benchmark_python_selected/expected_owasp_m2_issues.json",
  "expected_rule_ids": []
}
```

---

### 7. datasets/m2_owasp_benchmark_python_selected/dataset_manifest.json 생성 또는 보완

OWASP 폴더 내부에도 로컬 manifest가 있으면 유지하고, 아래 정보를 포함하도록 보완한다.

```json
{
  "dataset": "m2_owasp_benchmark_python_selected",
  "source": "OWASP BenchmarkPython",
  "cases": [
    {
      "case_id": "m2_owasp_sqli_BenchmarkTest00283",
      "category": "sqli",
      "cwe": "CWE-89",
      "real_vulnerability": true,
      "target_path": "testcode/BenchmarkTest00283.py",
      "expected_rule_ids": ["SEC-001"]
    }
  ]
}
```

---

## 완료 조건

1. `datasets/m2_custom_security_cases/`는 수정되지 않았다.
2. `datasets/m2_owasp_benchmark_python_selected/`가 존재한다.
3. `datasets/m2_owasp_benchmark_python_selected/testcode/`에 selected `BenchmarkTest*.py` 파일이 있다.
4. `datasets/m2_owasp_benchmark_python_selected/expectedresults_selected.csv`가 존재한다.
5. `datasets/m2_owasp_benchmark_python_selected/expected_owasp_m2_issues.json`가 존재한다.
6. `datasets/m2_owasp_benchmark_python_selected/source_info.md`가 존재한다.
7. `datasets/dataset_manifest.json`에 OWASP case가 추가 또는 보완되었다.
8. `datasets/expected_outputs/expected_m2_issues.json`는 삭제/덮어쓰기 되지 않았다.
9. true case는 `expected_issues`에 issue가 있다.
10. false case는 `expected_issues`가 빈 배열이다.

---

## 이번 작업에서 하지 말 것

- `datasets/m2_custom_security_cases/`를 수정하지 않는다.
- `datasets/expected_outputs/expected_m2_issues.json`를 삭제하거나 덮어쓰지 않는다.
- M3 데이터셋을 만들지 않는다.
- BugsInPy를 건드리지 않는다.
- M4 curriculum 데이터를 만들지 않는다.
- 실제 서비스 코드 `app/`에는 아무것도 넣지 않는다.
