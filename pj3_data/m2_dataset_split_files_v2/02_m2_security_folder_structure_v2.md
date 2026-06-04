# M2 Security Cases 폴더 구조 설계 v2

## 목적

이 문서는 Task-Link M2 코드 리뷰 모듈 평가용 데이터셋의 폴더 구조를 정의한다.

v2 변경점:

```text
expected_issue.json과 expected_m2_issues.json을 Dev2 Output Contract 필드에 맞춰 확장한다.
```

Dev2 Output Contract의 issue 객체 필드:

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

## 최종 폴더 구조

```text
datasets/
    ├── dataset_manifest.json
    ├── m2_owasp_benchmark_python_selected/
    │   ├── owasp_benchmarkpython_selected/
    │   │   ├── testcode/
    │   │   │   ├── BenchmarkTest00001.py
    │   │   │   ├── BenchmarkTest00187.py
    │   │   │   ├── BenchmarkTest00283.py
    │   │   │   └── ...
    │   │   ├── expectedresults_selected.csv
    │   │   └── source_info.md
    │   │
    ├── m2_custom_security_cases/
    │       ├── sqli_case/
    │       │   ├── vulnerable.py
    │       │   ├── fixed.py
    │       │   ├── README.md
    │       │   └── expected_issue.json
    │       │
    │       ├── path_traversal_case/
    │       │   ├── vulnerable.py
    │       │   ├── fixed.py
    │       │   ├── README.md
    │       │   └── expected_issue.json
    │       │
    │       ├── command_injection_case/
    │       │   ├── vulnerable.py
    │       │   ├── fixed.py
    │       │   ├── README.md
    │       │   └── expected_issue.json
    │       │
    │       ├── auth_missing_case/
    │       │   ├── vulnerable.py
    │       │   ├── fixed.py
    │       │   ├── README.md
    │       │   └── expected_issue.json
    │       │
    │       ├── insecure_password_hash_case/
    │       │   ├── vulnerable.py
    │       │   ├── fixed.py
    │       │   ├── README.md
    │       │   └── expected_issue.json
    │       │
    │       └── hardcoded_secret_case/
    │           ├── vulnerable.py
    │           ├── fixed.py
    │           ├── README.md
    │           └── expected_issue.json
    │
    └── expected_outputs/
        └── expected_m2_issues.json
```

---

## 폴더별 역할

### `datasets/`

Task-Link가 분석할 평가 데이터셋을 보관하는 최상위 폴더다.

서비스 코드가 아니다.  
M2가 분석할 입력 데이터다.

---

### `datasets/`

Task-Link 전체 평가 데이터셋의 루트다.

나중에 M3, M4 데이터가 추가될 수 있지만, 현재 단계에서는 M2 데이터만 구성한다.

---

### `dataset_manifest.json`

전체 데이터셋의 목차 파일이다.

각 케이스가 다음 정보를 갖도록 작성한다.

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

### `m2_owasp_benchmark_python_selected/` and `m2_custom_security_cases/`

M2 코드 리뷰 모듈이 분석할 보안 케이스가 들어간다.

하위 폴더는 두 개다.

```text
owasp_benchmarkpython_selected/
m2_custom_security_cases/
```

---

### `owasp_benchmarkpython_selected/`

OWASP BenchmarkPython에서 선택한 공식 보안 케이스를 저장한다.

목적:

- M2 보안 취약점 탐지 룰의 공신력 보강
- CWE 기반 expected label과 비교
- false positive / false negative 평가 가능

포함 파일:

```text
testcode/
expectedresults_selected.csv
source_info.md
```

---

### `m2_custom_security_cases/`

Task-Link 서비스 시나리오에 맞춰 직접 만든 M2 보안 케이스를 저장한다.

목적:

- M2 데모 안정화
- 신입 PR 리뷰 시나리오 반영
- OWASP에 없는 서비스형 취약 케이스 보완
- M4 학습 추천으로 연결하기 쉬운 expected issue 제공

포함 케이스:

```text
sqli_case/
path_traversal_case/
command_injection_case/
auth_missing_case/
insecure_password_hash_case/
hardcoded_secret_case/
```

---

### `expected_outputs/`

M2가 맞혀야 할 정답 JSON을 저장한다.

대표 파일:

```text
expected_m2_issues.json
```

이 파일은 M2 분석 결과와 비교하는 기준 정답이다.

---

## expected_issue.json 공통 스키마

각 custom case의 `expected_issue.json`은 아래 스키마를 따른다.

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

---

## case_id 규칙

Custom case는 다음 규칙을 사용한다.

```text
m2_custom_{category}_{number}
```

예시:

```text
m2_custom_sqli_001
m2_custom_path_traversal_001
m2_custom_command_injection_001
m2_custom_auth_missing_001
m2_custom_weak_hash_001
m2_custom_hardcoded_secret_001
```

OWASP case는 다음 규칙을 사용한다.

```text
m2_owasp_{category}_{benchmark_test_id}
```

예시:

```text
m2_owasp_sqli_BenchmarkTest00283
m2_owasp_xss_BenchmarkTest00187
```

---

## M2 issue ID 규칙

```text
SEC-001  SQL Injection
SEC-002  Cross-Site Scripting
SEC-003  Path Traversal
SEC-004  Command Injection
SEC-005  Weak Hash
SEC-006  Hardcoded Secret
AUTH-001 Authorization Missing
```

---

## 최종 체크리스트

- [ ] `m2_owasp_benchmark_python_selected/`와 `m2_custom_security_cases/`가 존재한다.
- [ ] `owasp_benchmarkpython_selected/`가 존재한다.
- [ ] `m2_custom_security_cases/`가 존재한다.
- [ ] custom case 6개가 존재한다.
- [ ] 각 custom case에 `vulnerable.py`, `fixed.py`, `README.md`, `expected_issue.json`가 존재한다.
- [ ] 각 `expected_issue.json`의 issue 객체가 Dev2 Output Contract 필드를 모두 가진다.
- [ ] `expected_outputs/expected_m2_issues.json`가 존재한다.
- [ ] `dataset_manifest.json`가 존재한다.
- [ ] manifest의 `target_path`와 실제 파일 경로가 일치한다.
