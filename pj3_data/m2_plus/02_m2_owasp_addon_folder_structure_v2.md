# M2 OWASP BenchmarkPython Add-on 폴더 구조 설계 v2

## 목적

현재 프로젝트의 실제 `datasets/` 구조에 맞춰 OWASP BenchmarkPython selected cases를 붙이는 구조를 정의한다.

이 프로젝트는 아래 구조를 사용한다.

```text
datasets/
├── dataset_manifest.json
├── expected_outputs/
├── m2_custom_security_cases/
├── m2_owasp_benchmark_python_selected/
├── m3_bugsinpy_selected/
└── m3_test_performance_cases/
```

따라서 이전 문서의 `datasets/task_link_eval_dataset/` 경로는 사용하지 않는다.

---

## 기존 M2 custom 구조

```text
datasets/
├── dataset_manifest.json
├── expected_outputs/
│   └── expected_m2_issues.json
│
└── m2_custom_security_cases/
    ├── auth_missing_case/
    ├── command_injection_case/
    ├── hardcoded_secret_case/
    ├── insecure_password_hash_case/
    ├── path_traversal_case/
    └── sqli_case/
```

---

## OWASP 추가 후 구조

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
        ├── BenchmarkTest00187.py
        ├── BenchmarkTest00283.py
        └── ...
```

---

## 폴더별 역할

### `datasets/`

전체 평가 데이터셋 루트다.

M2, M3, expected outputs, 전체 manifest가 모두 이 아래에 존재한다.

---

### `datasets/dataset_manifest.json`

전체 데이터셋 통합 매니페스트다.

M2 custom, M2 OWASP, M3 BugsInPy, M3 custom case를 모두 한 곳에서 관리한다.

이번 작업에서는 기존 내용을 유지하고 OWASP case 항목만 추가 또는 보완한다.

---

### `datasets/expected_outputs/expected_m2_issues.json`

기존 M2 custom case 정답 파일이다.

이번 OWASP add-on 작업에서는 삭제하거나 덮어쓰지 않는다.

OWASP 정답은 별도 파일인 아래 경로에 둔다.

```text
datasets/m2_owasp_benchmark_python_selected/expected_owasp_m2_issues.json
```

---

### `datasets/m2_custom_security_cases/`

기존 M2 custom security cases 폴더다.

역할:

```text
Task-Link 서비스 시나리오 기반 M2 보안 탐지 검증
```

이번 작업에서는 수정하지 않는다.

---

### `datasets/m2_owasp_benchmark_python_selected/`

OWASP BenchmarkPython에서 선택한 공식 보안 케이스를 저장한다.

역할:

```text
공식 benchmark label 기반 M2 보안 탐지 검증
오탐/미탐 평가
교수님 발표용 공신력 확보
```

---

### `testcode/`

선택된 OWASP `BenchmarkTest*.py` 파일이 들어간다.

주의:

```text
OWASP BenchmarkPython 전체 testcode를 전부 복사하지 않는다.
선택한 파일만 넣는다.
```

---

### `expectedresults_selected.csv`

OWASP 원본 expected results 중 선택한 case만 모은 CSV다.

형식:

```csv
test_name,category,real_vulnerability,cwe
BenchmarkTest00283,sqli,true,89
BenchmarkTest00285,sqli,false,89
```

---

### `expected_owasp_m2_issues.json`

OWASP CSV 라벨을 Task-Link M2 Output Contract 형식으로 변환한 정답 JSON이다.

true case는 expected issue를 포함한다.  
false case는 expected issue를 빈 배열로 둔다.

---

### `source_info.md`

출처와 사용 목적을 설명하는 파일이다.

교수님 발표나 문서 검토 시 데이터 출처 설명에 사용한다.

---

## OWASP category → Task-Link rule_id 매핑

| OWASP category | CWE | Task-Link rule_id | Severity |
|---|---:|---|---|
| `sqli` | CWE-89 | `SEC-001` | Critical |
| `xss` | CWE-79 | `SEC-002` | Critical |
| `pathtraver` | CWE-22 | `SEC-003` | Critical |
| `cmdi` | CWE-78 | `SEC-004` | Critical |
| `hash` | CWE-328 | `SEC-005` | Major |

---

## manifest 경로 규칙

전체 manifest 기준 경로:

```text
datasets/dataset_manifest.json
```

전체 manifest의 `target_path`는 `datasets/` 기준 상대 경로로 작성한다.

예시:

```text
m2_owasp_benchmark_python_selected/testcode/BenchmarkTest00283.py
```

OWASP 내부 manifest 기준 경로:

```text
datasets/m2_owasp_benchmark_python_selected/dataset_manifest.json
```

내부 manifest의 `target_path`는 OWASP 폴더 기준 상대 경로로 작성한다.

예시:

```text
testcode/BenchmarkTest00283.py
```

---

## 최종 체크리스트

- [ ] `datasets/m2_custom_security_cases/`가 유지된다.
- [ ] `datasets/m2_owasp_benchmark_python_selected/`가 존재한다.
- [ ] `testcode/`에 selected OWASP 파일이 들어간다.
- [ ] `expectedresults_selected.csv`가 존재한다.
- [ ] `expected_owasp_m2_issues.json`가 존재한다.
- [ ] `source_info.md`가 존재한다.
- [ ] `datasets/dataset_manifest.json`에 OWASP case가 추가된다.
- [ ] `datasets/expected_outputs/expected_m2_issues.json`가 유지된다.
- [ ] true case는 expected issue가 있다.
- [ ] false case는 expected issue가 없다.
