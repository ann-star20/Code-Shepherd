# Task-Link 데이터셋 구축 이후 추가 작업 목록

## 목적

이 문서는 Task-Link 프로젝트에서 데이터셋 구축이 끝난 뒤 추가로 해야 할 작업을 정리한다.

현재 데이터셋은 아래 영역까지 준비된 상태로 가정한다.

```text
datasets/
├── dataset_manifest.json
├── expected_outputs/
│   ├── expected_m2_issues.json
│   └── expected_m3_issues.json
├── m2_custom_security_cases/
├── m2_owasp_benchmark_python_selected/
├── m3_bugsinpy_selected/
└── m3_test_performance_cases/
```

이제 해야 할 일은 **데이터를 더 만드는 것**이 아니라,  
데이터셋을 실제 M2/M3 분석 모듈에 연결하고 Dev4에 넘길 수 있는 결과 형식으로 만드는 것이다.

---

# 1. 현재 상태 정리

## 완료된 것

```text
M2 custom security cases 생성
M2 OWASP BenchmarkPython selected 추가
M3 BugsInPy selected 구성
M3 custom performance cases 구성
dataset validation 실행
```

## 이제 해야 할 것

```text
1. M2/M3 분석기가 datasets/를 읽게 만들기
2. M2/M3 분석 결과를 expected_outputs와 비교하는 eval 스크립트 만들기
3. Dev2/Dev3 Output Contract를 통일하기
4. Dev4가 받을 merge input 형식 만들기
5. 최종 평가 리포트 생성하기
```

---

# 2. 추가 데이터셋은 더 필요한가?

현재 단계에서는 **추가 데이터셋을 더 만들 필요는 없다.**

현재 데이터셋은 아래 목적을 이미 충족한다.

| 영역 | 데이터 | 목적 |
|---|---|---|
| M2 | custom security cases | 서비스 시나리오 기반 보안 탐지 시연 |
| M2 | OWASP BenchmarkPython selected | 공식 보안 벤치마크 기반 검증 |
| M3 | BugsInPy selected | 실제 Python 버그 기반 검증 |
| M3 | custom performance cases | 커버리지, N+1, 복잡도, 엣지케이스, 메모리누수 검증 |

따라서 다음 작업은 **데이터 확장**이 아니라 **실행/평가/연동**이다.

---

# 3. 1순위 작업: M2 Eval 스크립트

## 목적

M2 분석기가 데이터셋을 읽고, 탐지 결과가 정답과 맞는지 평가한다.

## 만들 파일 예시

```text
scripts/
└── eval_m2_dataset.py
```

## 입력

```text
datasets/dataset_manifest.json
datasets/expected_outputs/expected_m2_issues.json
datasets/m2_custom_security_cases/
datasets/m2_owasp_benchmark_python_selected/
```

## 출력

```text
outputs/
└── m2_evaluation_report.json
```

## 해야 할 일

```text
1. dataset_manifest.json에서 module == "M2"인 케이스만 읽는다.
2. target_path의 파일을 M2 분석기에 전달한다.
3. M2 분석 결과 issues[]를 받는다.
4. expected issue와 rule_id 기준으로 비교한다.
5. TP / FP / TN / FN을 계산한다.
6. precision / recall / false positive rate를 계산한다.
7. m2_evaluation_report.json으로 저장한다.
```

## 평가 기준

```text
true_positive:
실제 이슈가 있고 M2도 잡음

false_positive:
실제 이슈가 없는데 M2가 잡음

true_negative:
실제 이슈가 없고 M2도 잡지 않음

false_negative:
실제 이슈가 있는데 M2가 못 잡음
```

## 결과 예시

```json
{
  "module": "M2",
  "total_cases": 58,
  "true_positive": 41,
  "true_negative": 12,
  "false_positive": 3,
  "false_negative": 2,
  "precision": 0.93,
  "recall": 0.95,
  "false_positive_rate": 0.20
}
```

---

# 4. 2순위 작업: M3 Eval 스크립트

## 목적

M3 분석기가 BugsInPy와 custom performance cases를 읽고, 테스트/성능 이슈를 제대로 탐지하는지 평가한다.

## 만들 파일 예시

```text
scripts/
└── eval_m3_dataset.py
```

## 입력

```text
datasets/dataset_manifest.json
datasets/expected_outputs/expected_m3_issues.json
datasets/m3_bugsinpy_selected/
datasets/m3_test_performance_cases/
```

## 출력

```text
outputs/
└── m3_evaluation_report.json
```

## 해야 할 일

```text
1. dataset_manifest.json에서 module == "M3"인 케이스만 읽는다.
2. BugsInPy case는 buggy/와 fixed/ 구조를 확인한다.
3. custom performance case는 app/와 tests/를 기준으로 분석한다.
4. M3 분석 결과 issues[]와 metrics를 받는다.
5. expected issue와 rule_id 기준으로 비교한다.
6. 커버리지 측정 결과가 있는 경우 coverage_line을 함께 기록한다.
7. m3_evaluation_report.json으로 저장한다.
```

## M3 평가 대상 rule_id

```text
TEST-001  커버리지 80% 미만
TEST-003  엣지케이스 누락
TEST-004  테스트 누락 함수
PERF-001  시간복잡도 / 중첩 루프
PERF-002  N+1 쿼리
PERF-003  메모리 누수 패턴
```

## 결과 예시

```json
{
  "module": "M3",
  "total_cases": 14,
  "detected": 12,
  "missed": 2,
  "recall": 0.86,
  "coverage_cases": {
    "measured": 3,
    "failed_to_measure": 0
  }
}
```

---

# 5. 3순위 작업: 전체 Eval 스크립트

## 목적

M2와 M3 평가 결과를 하나로 합쳐서 발표용 최종 평가 리포트를 만든다.

## 만들 파일 예시

```text
scripts/
└── eval_all_datasets.py
```

## 입력

```text
outputs/m2_evaluation_report.json
outputs/m3_evaluation_report.json
```

## 출력

```text
outputs/final_dataset_evaluation_report.json
outputs/final_dataset_evaluation_report.md
```

## 해야 할 일

```text
1. M2 평가 결과를 읽는다.
2. M3 평가 결과를 읽는다.
3. 전체 케이스 수를 합산한다.
4. 모듈별 precision / recall을 정리한다.
5. 미탐/오탐 case_id를 정리한다.
6. 발표용 Markdown 리포트를 생성한다.
```

## Markdown 리포트 예시 목차

```text
# Task-Link Dataset Evaluation Report

## 1. Dataset Summary
## 2. M2 Security Evaluation
## 3. M3 Test/Performance Evaluation
## 4. False Positives
## 5. False Negatives
## 6. Limitations
## 7. Next Improvements
```

---

# 6. Dev2/Dev3 Output Contract 통일

Dev2와 Dev3는 서로 직접 합치는 게 아니라, 같은 `scan_id`를 기준으로 Dev4가 취합한다.

## Dev2 Output 예시

```json
{
  "task_id": "uuid-1234",
  "scan_id": 42,
  "pr_id": "PR-001",
  "agent": "security_scan",
  "issues": [
    {
      "severity": "Critical",
      "issue_type": "Vulnerability",
      "line": 7,
      "file": "src/search_service.py",
      "message": "SQL Injection 가능성",
      "rule_id": "SEC-001",
      "suggestion": "파라미터화된 쿼리를 사용하세요.",
      "resolution_example": "db.execute(query, {"keyword": keyword})",
      "similar_issues": []
    }
  ],
  "summary": {
    "critical": 1,
    "major": 0,
    "minor": 0
  },
  "execution_ms": 1200
}
```

## Dev3 Output 예시

```json
{
  "task_id": "uuid-1234",
  "scan_id": 42,
  "pr_id": "PR-001",
  "agent": "performance",
  "issues": [
    {
      "severity": "Major",
      "file": "src/post_service.py",
      "line": 8,
      "message": "N+1 쿼리 가능성: 루프 내부에서 DB 호출이 반복됩니다.",
      "rule_id": "PERF-002",
      "suggestion": "루프 밖에서 bulk 조회를 수행하세요."
    }
  ],
  "summary": {
    "critical": 0,
    "major": 1,
    "minor": 0
  },
  "metrics": null,
  "execution_ms": 900
}
```

## 통일해야 할 공통 필드

```text
task_id
scan_id
pr_id
agent
issues
summary
execution_ms
```

## issues[] 공통 필드

```text
severity
file
line
message
rule_id
suggestion
```

Dev2는 추가로 아래 필드를 가질 수 있다.

```text
issue_type
resolution_example
similar_issues
```

Dev3는 추가로 아래 필드를 가질 수 있다.

```text
metrics
```

---

# 7. Dev4 전달용 Merge Contract 만들기

## 목적

Dev4가 Dev2와 Dev3 결과를 하나의 scan 결과로 받아 판단할 수 있게 한다.

## 만들 문서

```text
docs/
└── dev2_dev3_to_dev4_contract.md
```

## Dev4 입력 예시

```json
{
  "scan_id": 42,
  "task_id": "uuid-1234",
  "pr_id": "PR-001",
  "agent_outputs": [
    {
      "agent": "security_scan",
      "issues": [
        {
          "severity": "Critical",
          "rule_id": "SEC-001",
          "file": "src/search_service.py",
          "line": 7,
          "message": "SQL Injection 가능성"
        }
      ],
      "summary": {
        "critical": 1,
        "major": 0,
        "minor": 0
      }
    },
    {
      "agent": "performance",
      "issues": [
        {
          "severity": "Major",
          "rule_id": "PERF-002",
          "file": "src/post_service.py",
          "line": 8,
          "message": "N+1 쿼리 가능성"
        }
      ],
      "summary": {
        "critical": 0,
        "major": 1,
        "minor": 0
      }
    }
  ]
}
```

## Merge 규칙

```text
1. scan_id가 같은 Dev2/Dev3 결과만 합친다.
2. agent_outputs 배열에 agent별 결과를 넣는다.
3. summary는 agent별 summary를 유지한다.
4. 필요하면 total_summary를 추가한다.
5. Dev4가 verdict를 결정한다.
```

## total_summary 예시

```json
{
  "total_summary": {
    "critical": 1,
    "major": 1,
    "minor": 0
  }
}
```

---

# 8. Dev4 Verdict 기준 초안

Dev4는 Dev2/Dev3의 이슈 사실을 받아 최종 판단한다.

## 기본 규칙

```text
Critical 1개 이상
→ 재작업 또는 시니어 에스컬레이션

Major 2개 이상
→ 재작업 권고

Major 1개 이하 + Minor만 있음
→ 수정 권고 코멘트

Minor만 있음
→ LGTM with comments 가능

이슈 없음
→ LGTM
```

## 예시

```text
SEC-001 Critical SQL Injection
→ REWORK_REQUIRED

PERF-002 Major N+1 + TEST-001 Major coverage below threshold
→ REWORK_RECOMMENDED

TEST-003 Minor edge case missing
→ LGTM_WITH_COMMENTS

No issues
→ LGTM
```

---

# 9. 추천 파일 구조

데이터셋 이후 추가로 만들면 좋은 파일 구조는 아래와 같다.

```text
scripts/
├── eval_m2_dataset.py
├── eval_m3_dataset.py
└── eval_all_datasets.py

docs/
└── dev2_dev3_to_dev4_contract.md

outputs/
├── m2_evaluation_report.json
├── m3_evaluation_report.json
├── final_dataset_evaluation_report.json
└── final_dataset_evaluation_report.md
```

---

# 10. 작업 우선순위

## P0: 반드시 해야 함

```text
1. eval_m2_dataset.py
2. eval_m3_dataset.py
3. dev2_dev3_to_dev4_contract.md
```

## P1: 하면 좋음

```text
4. eval_all_datasets.py
5. final_dataset_evaluation_report.md
6. sample_dev4_input.json
```

## P2: 나중에 해도 됨

```text
7. GitHub PR comment rendering sample
8. Slack escalation payload sample
9. Dev5 learning recommendation mapping sample
```

---

# 11. Claude Code 요청 프롬프트

아래 프롬프트를 Claude Code에 전달하면 된다.

```text
현재 datasets/ 구축은 완료되었습니다.

이제 데이터셋을 실제 분석 모듈과 연결하기 위한 추가 작업을 진행해주세요.

작업 범위:
1. scripts/eval_m2_dataset.py 생성
2. scripts/eval_m3_dataset.py 생성
3. scripts/eval_all_datasets.py 생성
4. docs/dev2_dev3_to_dev4_contract.md 생성
5. outputs/ 리포트 저장 구조 생성

중요:
- 새로운 데이터셋을 만들지 마세요.
- datasets/ 안의 기존 파일을 임의로 수정하지 마세요.
- dataset_manifest.json을 읽어서 평가 대상을 찾으세요.
- M2는 rule_id 기준으로 expected와 actual을 비교하세요.
- M3도 rule_id 기준으로 expected와 actual을 비교하세요.
- Dev2/Dev3 결과는 scan_id 기준으로 Dev4가 합친다는 전제로 문서를 작성하세요.
- 실제 분석기가 아직 완성되지 않았다면 mock actual result를 받을 수 있는 인터페이스로 작성하세요.
```

---

# 12. 최종 판단

지금부터 필요한 것은 데이터 추가가 아니다.

필요한 것은 아래 3개다.

```text
1. evaluation
2. output contract
3. Dev4 merge contract
```

이 3개가 끝나면 Task-Link는 데이터셋을 실제 발표/시연에 사용할 수 있는 상태가 된다.
