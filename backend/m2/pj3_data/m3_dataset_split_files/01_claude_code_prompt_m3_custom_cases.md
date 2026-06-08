# Claude Code 작업 프롬프트: M3 Test/Performance Custom Cases 데이터셋 생성

## 목적

Task-Link 프로젝트의 M3 테스트 검증 + 성능 분석 모듈을 평가하기 위한 custom 데이터셋을 생성한다.

M3는 보안 리뷰가 아니라 다음 기능을 검증한다.

```text
TEST-001  커버리지 80% 미만 탐지
TEST-003  엣지케이스 누락 탐지
TEST-004  테스트 누락 함수 탐지
PERF-001  시간복잡도 / 중첩 루프 탐지
PERF-002  N+1 쿼리 탐지
PERF-003  메모리 누수 패턴 탐지
```

이번 작업은 `datasets/m3_test_performance_cases/custom_performance_cases/` 아래에 M3 custom case 6개를 생성하는 것이다.

---

## Claude Code에게 요청할 작업

아래 작업을 그대로 수행해줘.

---

## 1. 폴더 구조 생성

프로젝트 루트 기준으로 아래 구조를 생성해줘.

```text
datasets/
    ├── dataset_manifest.json
    ├── m3_test_performance_cases/
    │   └── custom_performance_cases/
    │       ├── low_coverage_case/
    │       ├── missing_test_function_case/
    │       ├── n_plus_one_case/
    │       ├── complexity_case/
    │       ├── edge_case_missing_case/
    │       └── memory_leak_case/
    │
    └── expected_outputs/
        └── expected_m3_issues.json
```

각 custom case 폴더 안에는 최소한 아래 파일을 만들어줘.

```text
app/
tests/
README.md
expected_issue.json
```

필요한 경우 `requirements.txt` 또는 `pyproject.toml`도 포함해도 된다.

---

## 2. Custom Performance Cases 6개 생성

아래 6개 케이스를 반드시 모두 생성한다.

```text
low_coverage_case/
missing_test_function_case/
n_plus_one_case/
complexity_case/
edge_case_missing_case/
memory_leak_case/
```

각 케이스의 코드는 `03_m3_custom_performance_code_spec.md`의 내용을 따른다.

---

## 3. 각 케이스의 목적

### 3.1 `low_coverage_case/`

목적:

```text
pytest --cov 실행 시 라인 커버리지가 80% 미만이 되도록 구성
```

M3 expected issue:

```text
TEST-001
```

---

### 3.2 `missing_test_function_case/`

목적:

```text
소스 파일에는 함수가 여러 개 있지만 tests에서는 일부 함수만 실행하도록 구성
```

M3 expected issue:

```text
TEST-004
```

주의:

```text
def 라인만 실행됐다고 covered로 보면 안 된다.
함수 본문 실행 라인과 coverage executed_lines의 교집합으로 판단해야 한다.
```

---

### 3.3 `n_plus_one_case/`

목적:

```text
for 루프 안에서 repository.find_by_id(), db.execute(), session.query() 같은 DB 호출이 발생하도록 구성
```

M3 expected issue:

```text
PERF-002
```

---

### 3.4 `complexity_case/`

목적:

```text
중첩 루프 2단계 이상 또는 3단계 이상이 존재하도록 구성
```

M3 expected issue:

```text
PERF-001
```

---

### 3.5 `edge_case_missing_case/`

목적:

```text
정상 입력 테스트만 있고 None, 0, 음수, 빈 리스트, 경계값 테스트가 빠지도록 구성
```

M3 expected issue:

```text
TEST-003
```

---

### 3.6 `memory_leak_case/`

목적:

```text
전역 리스트/딕셔너리에 요청 데이터를 계속 append하거나, 전역 캐시가 무제한 증가하는 패턴을 구성
```

M3 expected issue:

```text
PERF-003
```

주의:

```text
with open(...) as f: 패턴은 메모리 누수로 잡지 않는다.
로컬 list/dict append는 함수 종료 시 해제되므로 잡지 않는다.
전역 컨테이너 누적 패턴만 의심 케이스로 둔다.
```

---

## 4. expected_outputs 생성

아래 파일을 생성한다.

```text
datasets/expected_outputs/expected_m3_issues.json
```

이 파일에는 custom case 6개의 expected issue를 통합해서 작성한다.

최소 형식:

```json
{
  "module": "M3",
  "dataset": "m3_custom_performance_cases",
  "cases": [
    {
      "case_id": "m3_custom_low_coverage_001",
      "expected_issue_ids": ["TEST-001"]
    }
  ]
}
```

---

## 5. dataset_manifest.json 업데이트

이미 `dataset_manifest.json`이 존재하면 유지하면서 M3 custom cases를 추가한다.  
없으면 새로 생성한다.

각 case는 아래 정보를 포함해야 한다.

```json
{
  "case_id": "m3_custom_n_plus_one_001",
  "module": "M3",
  "source": "Task-Link Custom",
  "case_type": "test_performance",
  "category": "n_plus_one",
  "rule_id": "PERF-002",
  "target_path": "m3_test_performance_cases/custom_performance_cases/n_plus_one_case",
  "expected_output_ref": "expected_outputs/expected_m3_issues.json"
}
```

---

## 6. 완료 조건

작업 완료 후 아래를 확인해줘.

1. `datasets/m3_test_performance_cases/custom_performance_cases/`가 존재한다.
2. custom case 6개가 모두 존재한다.
3. 각 case 안에 `app/`, `tests/`, `README.md`, `expected_issue.json`가 존재한다.
4. `expected_outputs/expected_m3_issues.json`가 존재한다.
5. `dataset_manifest.json`에 M3 custom case 6개가 모두 등록되어 있다.
6. 각 case의 expected issue ID가 아래와 일치한다.

```text
low_coverage_case             → TEST-001
missing_test_function_case    → TEST-004
n_plus_one_case               → PERF-002
complexity_case               → PERF-001
edge_case_missing_case        → TEST-003
memory_leak_case              → PERF-003
```

---

## 7. 이번 작업에서 하지 말 것

- M2 데이터셋은 수정하지 않는다.
- OWASP BenchmarkPython은 건드리지 않는다.
- BugsInPy는 건드리지 않는다.
- M4 curriculum 데이터는 만들지 않는다.
- 실제 운영 서비스 코드 `app/`에는 custom case를 넣지 않는다.
- custom case 코드는 반드시 `datasets/` 아래에만 만든다.
