# M3 Test/Performance Custom Cases 폴더 구조 설계

## 목적

이 문서는 Task-Link M3 테스트 검증 + 성능 분석 모듈 평가용 custom 데이터셋의 폴더 구조를 정의한다.

M3는 다음 기능을 검증해야 한다.

```text
TEST-001  커버리지 80% 미만
TEST-003  엣지케이스 누락
TEST-004  테스트 누락 함수
PERF-001  시간복잡도 / 중첩 루프
PERF-002  N+1 쿼리
PERF-003  메모리 누수 패턴
```

---

## 최종 폴더 구조

```text
datasets/
    ├── dataset_manifest.json
    ├── m3_test_performance_cases/
    │   └── custom_performance_cases/
    │       ├── low_coverage_case/
    │       │   ├── app/
    │       │   │   └── order_service.py
    │       │   ├── tests/
    │       │   │   └── test_order_service.py
    │       │   ├── README.md
    │       │   └── expected_issue.json
    │       │
    │       ├── missing_test_function_case/
    │       │   ├── app/
    │       │   │   └── user_metrics.py
    │       │   ├── tests/
    │       │   │   └── test_user_metrics.py
    │       │   ├── README.md
    │       │   └── expected_issue.json
    │       │
    │       ├── n_plus_one_case/
    │       │   ├── app/
    │       │   │   ├── post_service.py
    │       │   │   └── repositories.py
    │       │   ├── tests/
    │       │   │   └── test_post_service.py
    │       │   ├── README.md
    │       │   └── expected_issue.json
    │       │
    │       ├── complexity_case/
    │       │   ├── app/
    │       │   │   └── report_service.py
    │       │   ├── tests/
    │       │   │   └── test_report_service.py
    │       │   ├── README.md
    │       │   └── expected_issue.json
    │       │
    │       ├── edge_case_missing_case/
    │       │   ├── app/
    │       │   │   └── payment_service.py
    │       │   ├── tests/
    │       │   │   └── test_payment_service.py
    │       │   ├── README.md
    │       │   └── expected_issue.json
    │       │
    │       └── memory_leak_case/
    │           ├── app/
    │           │   └── event_logger.py
    │           ├── tests/
    │           │   └── test_event_logger.py
    │           ├── README.md
    │           └── expected_issue.json
    │
    └── expected_outputs/
        └── expected_m3_issues.json
```

---

## 폴더별 역할

### `datasets/`

Task-Link가 분석할 평가 데이터셋을 보관하는 최상위 폴더다.

서비스 코드가 아니다.  
M3가 분석할 입력 데이터다.

---

### `datasets/`

Task-Link 전체 평가 데이터셋의 루트다.

이번 문서는 이 중 M3 custom 데이터만 정의한다.

---

### `m3_test_performance_cases/`

M3 테스트 검증 + 성능 분석 케이스가 들어가는 폴더다.

하위에 `custom_performance_cases/`를 둔다.

---

### `custom_performance_cases/`

M3 기능별로 직접 제작한 custom case 6개를 저장한다.

```text
low_coverage_case/
missing_test_function_case/
n_plus_one_case/
complexity_case/
edge_case_missing_case/
memory_leak_case/
```

---

## 각 case 폴더 공통 구조

각 case는 다음 구조를 따른다.

```text
case_name/
├── app/
│   └── 분석 대상 Python 코드
├── tests/
│   └── pytest 테스트 코드
├── README.md
└── expected_issue.json
```

### `app/`

M3가 분석할 대상 코드가 들어간다.

예:

```text
order_service.py
post_service.py
report_service.py
```

### `tests/`

pytest 테스트 코드가 들어간다.

커버리지 측정, 테스트 누락 함수 탐지, 엣지케이스 누락 탐지를 위해 의도적으로 일부 테스트를 부족하게 둔다.

### `README.md`

각 케이스의 목적과 M3가 잡아야 하는 rule_id를 설명한다.

### `expected_issue.json`

해당 케이스에서 M3가 출력해야 하는 정답 issue를 정의한다.

---

## case_id 규칙

Custom case는 다음 규칙을 사용한다.

```text
m3_custom_{category}_{number}
```

예시:

```text
m3_custom_low_coverage_001
m3_custom_missing_test_function_001
m3_custom_n_plus_one_001
m3_custom_complexity_001
m3_custom_edge_case_missing_001
m3_custom_memory_leak_001
```

---

## M3 issue ID 규칙

```text
TEST-001  Coverage below threshold
TEST-003  Missing edge case tests
TEST-004  Function missing test coverage
PERF-001  Time complexity issue
PERF-002  N+1 query pattern
PERF-003  Memory leak pattern
```

---

## expected_outputs/expected_m3_issues.json

M3가 맞혀야 할 정답 JSON을 저장한다.

예시:

```json
{
  "module": "M3",
  "dataset": "m3_custom_performance_cases",
  "cases": [
    {
      "case_id": "m3_custom_low_coverage_001",
      "expected_issue_ids": ["TEST-001"]
    },
    {
      "case_id": "m3_custom_n_plus_one_001",
      "expected_issue_ids": ["PERF-002"]
    }
  ]
}
```

---

## dataset_manifest.json

전체 데이터셋 목차 파일이다.

M3 custom case는 아래 형태로 등록한다.

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

## M3 custom case 6개 요약

| Case | 목적 | Expected rule_id |
|---|---|---|
| `low_coverage_case/` | coverage line < 80% | `TEST-001` |
| `missing_test_function_case/` | 함수 본문 실행 누락 | `TEST-004` |
| `n_plus_one_case/` | 루프 내부 DB 호출 | `PERF-002` |
| `complexity_case/` | 중첩 루프 O(n²) 이상 | `PERF-001` |
| `edge_case_missing_case/` | null/0/음수/빈 리스트 테스트 누락 | `TEST-003` |
| `memory_leak_case/` | 전역 컨테이너 무제한 누적 | `PERF-003` |

---

## 최종 체크리스트

- [ ] `m3_test_performance_cases/`가 존재한다.
- [ ] `custom_performance_cases/`가 존재한다.
- [ ] custom case 6개가 존재한다.
- [ ] 각 custom case에 `app/`, `tests/`, `README.md`, `expected_issue.json`가 존재한다.
- [ ] `expected_outputs/expected_m3_issues.json`가 존재한다.
- [ ] `dataset_manifest.json`에 M3 custom case 6개가 등록되어 있다.
- [ ] rule_id가 PRD와 일치한다.
