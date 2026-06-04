# BugsInPy M3 데이터 수집 요청서 — Claude Code용

> 목적: Task-Link의 M3 `test-performance-agent` 검증을 위해 BugsInPy에서 필요한 파일과 buggy/fixed 소스코드만 선별 수집한다.  
> 이 문서는 Claude Code에 그대로 전달하기 위한 작업 지시서다.  
> 이번 단계에서는 **BugsInPy 수집만 수행**하고, Custom M3 cases는 BugsInPy 수집 이후 별도 작업으로 진행한다.

---

## 1. 작업 목표

BugsInPy 원본 레포에서 M3 검증에 필요한 버그 케이스를 선별하고, 각 케이스별로 다음 구조를 만든다.

```text
datasets/
└── m3_bugsinpy_selected/
    ├── {project}_{bug_id}/
    │   ├── metadata/
    │   │   ├── project.info
    │   │   ├── bug.info
    │   │   ├── bug_patch.txt
    │   │   ├── requirements.txt
    │   │   └── run_test.sh
    │   │
    │   ├── buggy/
    │   │   └── buggy 버전으로 체크아웃된 실제 프로젝트 코드
    │   │
    │   ├── fixed/
    │   │   └── fixed 버전으로 체크아웃된 실제 프로젝트 코드
    │   │
    │   └── expected_m3_issues.json
    │
    └── dataset_manifest.json
```

---

## 2. 왜 BugsInPy를 쓰는가

BugsInPy는 실제 오픈소스 Python 프로젝트의 버그를 모은 공개 데이터셋이다. 각 버그는 buggy 버전과 fixed 버전, 버그 관련 테스트 실행 정보, 수정 패치 정보를 포함한다.

Task-Link M3는 다음 기능을 가진다.

```text
- Docker 샌드박스에서 pytest --cov 실측
- 커버리지 측정: TEST-001
- 테스트 누락 함수 탐지: TEST-004
- diff 교집합 필터
- 표준 AgentOutput JSON 생성
- scan_issues, scan_summaries, agent_traces 저장용 결과 생성
```

BugsInPy는 특히 아래 기능 검증에 적합하다.

| M3 기능 | BugsInPy 적용 가능 여부 | 이유 |
|---|---:|---|
| buggy/fixed 코드 비교 | 가능 | 버그 버전과 수정 버전을 제공 |
| 테스트 실패 재현 | 가능 | run_test.sh 또는 관련 테스트 정보 제공 |
| diff 교집합 필터 | 가능 | bug_patch.txt로 수정 파일/라인 확인 가능 |
| 커버리지 측정 | 부분 가능 | pytest/coverage 실행 대상이 있음 |
| 테스트 누락 함수 탐지 | 부분 가능 | AST와 coverage 결과를 결합해 확인 가능 |
| N+1 쿼리 탐지 | 제한적 | BugsInPy 목적이 ORM 성능 케이스가 아님 |
| 시간복잡도 탐지 | 제한적 | 알고리즘/성능 케이스가 보장되지 않음 |
| 엣지케이스/메모리누수 | 제한적 | 케이스별로 보장되지 않음 |

따라서 이번 단계에서는 BugsInPy로 **실제 버그 기반 M3 검증 데이터**를 먼저 만들고, 부족한 N+1·복잡도·엣지케이스·메모리누수 케이스는 이후 Custom M3 cases로 보완한다.

---

## 3. BugsInPy 원본 루트

Claude Code는 아래 원본 레포를 기준으로 작업한다.

Users/user/Documents/pj3_data/BugsInPy-master


원본 레포를 프로젝트 안에 둘 경우 권장 루트는 다음과 같다.

```text
external/
└── BugsInPy/
    ├── framework/
    │   └── bin/
    │       ├── bugsinpy-checkout
    │       ├── bugsinpy-compile
    │       ├── bugsinpy-test
    │       └── bugsinpy-coverage
    │
    └── projects/
        ├── fastapi/
        ├── black/
        ├── cookiecutter/
        ├── tqdm/
        └── ...
```

주의:

```text
external/BugsInPy/는 원본 데이터셋/도구 보관용이다.
datasets/m3_bugsinpy_selected/는 Task-Link M3가 실제로 읽을 선별 데이터셋이다.
```

---

## 4. BugsInPy에서 가져와야 하는 파일 목록

각 버그 케이스마다 반드시 아래 파일을 수집한다.

### 4.1 필수 메타데이터 파일

원본 위치:

```text
external/BugsInPy/projects/{project}/project.info
external/BugsInPy/projects/{project}/bugs/{bug_id}/bug.info
external/BugsInPy/projects/{project}/bugs/{bug_id}/bug_patch.txt
external/BugsInPy/projects/{project}/bugs/{bug_id}/requirements.txt
external/BugsInPy/projects/{project}/bugs/{bug_id}/run_test.sh
```

수집 후 저장 위치:

```text
datasets/m3_bugsinpy_selected/{project}_{bug_id}/metadata/project.info
datasets/m3_bugsinpy_selected/{project}_{bug_id}/metadata/bug.info
datasets/m3_bugsinpy_selected/{project}_{bug_id}/metadata/bug_patch.txt
datasets/m3_bugsinpy_selected/{project}_{bug_id}/metadata/requirements.txt
datasets/m3_bugsinpy_selected/{project}_{bug_id}/metadata/run_test.sh
```

### 4.2 필수 소스코드 폴더

BugsInPy의 checkout 도구를 이용해 생성해야 한다.

```text
datasets/m3_bugsinpy_selected/{project}_{bug_id}/buggy/
datasets/m3_bugsinpy_selected/{project}_{bug_id}/fixed/
```

의미:

```text
buggy/ = 버그가 존재하는 실제 프로젝트 코드
fixed/ = 해당 버그가 수정된 실제 프로젝트 코드
```

### 4.3 Task-Link가 직접 생성해야 하는 파일

BugsInPy 원본에 없는 파일이므로 Claude Code가 생성해야 한다.

```text
datasets/m3_bugsinpy_selected/{project}_{bug_id}/expected_m3_issues.json
datasets/m3_bugsinpy_selected/dataset_manifest.json
```

---

## 5. 파일별 역할

| 파일/폴더 | 역할 | M3에서 쓰는 방식 |
|---|---|---|
| `project.info` | 원본 프로젝트 GitHub URL, 프로젝트 상태 등 | 데이터 출처 기록 |
| `bug.info` | buggy/fixed commit, Python 버전, 테스트 정보 등 | 케이스 메타데이터 |
| `bug_patch.txt` | buggy → fixed 수정 diff | diff 교집합 필터 검증 |
| `requirements.txt` | 해당 버그 실행 의존성 | 테스트/커버리지 환경 구성 참고 |
| `run_test.sh` | 버그 재현 테스트 실행 스크립트 | 테스트 실패/통과 재현 참고 |
| `buggy/` | 버그가 있는 실제 코드 | M3 분석 대상 |
| `fixed/` | 수정된 실제 코드 | 비교/검증 대상 |
| `expected_m3_issues.json` | M3가 출력해야 하는 기대 결과 | 평가 정답지 |
| `dataset_manifest.json` | 전체 케이스 목록과 상태 | 데이터셋 관리 |

---

## 6. 우선 수집할 프로젝트 후보

처음부터 무거운 프로젝트를 많이 가져오지 말고, 가벼운 프로젝트 위주로 5~8개 케이스만 선별한다.

우선 후보:

```text
fastapi
black
cookiecutter
tqdm
```

피하거나 후순위로 둘 후보:

```text
pandas
matplotlib
keras
spacy
```

이유:

```text
- pandas, matplotlib, keras, spacy는 의존성/테스트 실행이 무거울 수 있음
- 초기 M3 검증 단계에서는 checkout, 테스트 실행, diff 분석이 안정적인 케이스가 더 중요함
```

---

## 7. 케이스 선정 기준

Claude Code는 각 후보 프로젝트에서 아래 조건을 만족하는 버그를 우선 선택한다.

```text
1. bug.info, bug_patch.txt, requirements.txt, run_test.sh가 모두 존재할 것
2. buggy/fixed 버전을 체크아웃할 수 있을 것
3. bug_patch.txt가 너무 크지 않을 것
4. Python 소스코드 수정이 포함되어 있을 것
5. 테스트 실행 정보가 명확할 것
6. M3 분석 결과로 설명 가능한 케이스일 것
```

우선 선택 개수:

```text
초기: 5개 케이스
권장: 8개 케이스
최대: 10개 케이스
```

---

## 8. 최종 산출물 루트

Claude Code는 최종적으로 아래 구조를 만들어야 한다.

  ```text
  datasets/
  └── m3_bugsinpy_selected/
      ├── fastapi_1/
      │   ├── metadata/
      │   │   ├── project.info
      │   │   ├── bug.info
      │   │   ├── bug_patch.txt
      │   │   ├── requirements.txt
      │   │   └── run_test.sh
      │   ├── buggy/
      │   ├── fixed/
      │   └── expected_m3_issues.json
      │
      ├── black_3/
      │   ├── metadata/
      │   ├── buggy/
      │   ├── fixed/
      │   └── expected_m3_issues.json
      │
      ├── cookiecutter_2/
      │   ├── metadata/
      │   ├── buggy/
      │   ├── fixed/
      │   └── expected_m3_issues.json
      │
      └── dataset_manifest.json
```

프로젝트/버그 번호는 실제로 체크아웃 가능한 케이스에 맞춰 변경해도 된다.

---

## 9. `expected_m3_issues.json` 템플릿

각 케이스마다 아래 형식으로 생성한다.

```json
{
  "case_id": "bugsinpy_fastapi_1",
  "source": "BugsInPy",
  "project": "fastapi",
  "bug_id": 1,
  "purpose": "M3 real Python bug validation",
  "paths": {
    "buggy": "datasets/m3_bugsinpy_selected/fastapi_1/buggy",
    "fixed": "datasets/m3_bugsinpy_selected/fastapi_1/fixed",
    "metadata": "datasets/m3_bugsinpy_selected/fastapi_1/metadata"
  },
  "expected_issues": [
    {
      "module": "M3",
      "id": "TEST-FAIL-001",
      "severity": "Major",
      "title": "Bug-revealing test fails on buggy version",
      "evidence_source": "metadata/run_test.sh"
    },
    {
      "module": "M3",
      "id": "PATCH-001",
      "severity": "Info",
      "title": "Buggy and fixed versions differ in patch target files",
      "evidence_source": "metadata/bug_patch.txt"
    }
  ],
  "notes": [
    "BugsInPy does not directly provide Task-Link issue IDs such as TEST-001 or PERF-002.",
    "This expected file maps BugsInPy evidence to Task-Link M3 evaluation format."
  ]
}
```

---

## 10. `dataset_manifest.json` 템플릿

전체 케이스 목록은 아래 형식으로 생성한다.

```json
{
  "dataset_name": "m3_bugsinpy_selected",
  "source": "BugsInPy",
  "source_url": "https://github.com/soarsmu/BugsInPy",
  "purpose": "Task-Link M3 test-performance-agent validation",
  "case_count": 0,
  "cases": [
    {
      "case_id": "bugsinpy_fastapi_1",
      "project": "fastapi",
      "bug_id": 1,
      "has_project_info": true,
      "has_bug_info": true,
      "has_bug_patch": true,
      "has_requirements": true,
      "has_run_test": true,
      "has_buggy_checkout": true,
      "has_fixed_checkout": true,
      "status": "ready"
    }
  ]
}
```

`case_count`는 최종 생성된 케이스 수에 맞게 갱신한다.

---

## 11. Claude Code 작업 프롬프트

아래 프롬프트를 Claude Code에 그대로 전달한다.

```text
너는 Task-Link 프로젝트의 M3 test-performance-agent 평가 데이터셋을 준비하는 역할이다.

목표는 BugsInPy에서 M3 검증에 필요한 실제 Python 버그 케이스만 선별하여 `datasets/m3_bugsinpy_selected/` 아래에 정리하는 것이다.

원본 데이터셋:
- https://github.com/soarsmu/BugsInPy

해야 할 작업:
1. BugsInPy 원본 레포를 `external/BugsInPy/` 기준으로 확인한다.
2. `projects/` 아래에서 우선 후보 프로젝트 `fastapi`, `black`, `cookiecutter`, `tqdm`을 확인한다.
3. 각 프로젝트의 `bugs/{bug_id}/` 폴더를 탐색해서 다음 파일이 모두 있는 케이스를 우선 선택한다.
   - bug.info
   - bug_patch.txt
   - requirements.txt
   - run_test.sh
4. 각 선택 케이스에 대해 buggy 버전과 fixed 버전 소스코드를 체크아웃하여 다음 경로에 저장한다.
   - `datasets/m3_bugsinpy_selected/{project}_{bug_id}/buggy/`
   - `datasets/m3_bugsinpy_selected/{project}_{bug_id}/fixed/`
5. 각 선택 케이스의 메타데이터 파일을 다음 경로에 복사한다.
   - `datasets/m3_bugsinpy_selected/{project}_{bug_id}/metadata/project.info`
   - `datasets/m3_bugsinpy_selected/{project}_{bug_id}/metadata/bug.info`
   - `datasets/m3_bugsinpy_selected/{project}_{bug_id}/metadata/bug_patch.txt`
   - `datasets/m3_bugsinpy_selected/{project}_{bug_id}/metadata/requirements.txt`
   - `datasets/m3_bugsinpy_selected/{project}_{bug_id}/metadata/run_test.sh`
6. 각 케이스마다 `expected_m3_issues.json`을 생성한다.
7. 전체 케이스 목록을 `datasets/m3_bugsinpy_selected/dataset_manifest.json`에 정리한다.

선정 기준:
- 초기에는 5개 케이스만 선택한다.
- 가능하면 `fastapi`, `black`, `cookiecutter`, `tqdm`에서 고르게 선택한다.
- 의존성이 너무 무겁거나 체크아웃/테스트 실행이 불안정한 케이스는 제외한다.
- bug_patch.txt가 Python 소스코드 수정을 포함하는 케이스를 우선한다.

주의사항:
- 이번 작업에서는 Custom M3 cases를 만들지 않는다.
- 이번 작업은 BugsInPy 데이터 수집까지만 한다.
- OWASP, NIST, QuixBugs는 건드리지 않는다.
- 서비스 본코드 `app/` 또는 `src/`에 BugsInPy 코드를 섞지 않는다.
- BugsInPy 코드는 반드시 `datasets/m3_bugsinpy_selected/` 아래에 분석 대상 데이터로만 둔다.

완료 후 다음을 보고하라.
1. 선택한 케이스 목록
2. 각 케이스의 project, bug_id
3. 수집된 파일 목록
4. buggy/fixed 체크아웃 성공 여부
5. 제외한 케이스가 있다면 제외 사유
6. 다음 단계에서 Custom M3 cases로 보완해야 할 기능 목록
```

---

## 12. Claude Code 검증 프롬프트

수집이 끝난 뒤 Claude Code에 아래 검증을 요청한다.

```text
`datasets/m3_bugsinpy_selected/` 구조를 검증해줘.

각 케이스에 대해 아래 항목을 체크해줘.

1. metadata/project.info 존재 여부
2. metadata/bug.info 존재 여부
3. metadata/bug_patch.txt 존재 여부
4. metadata/requirements.txt 존재 여부
5. metadata/run_test.sh 존재 여부
6. buggy/ 폴더 존재 여부
7. fixed/ 폴더 존재 여부
8. expected_m3_issues.json 존재 여부
9. bug_patch.txt에 Python 소스코드 수정이 포함되어 있는지
10. dataset_manifest.json에 해당 케이스가 등록되어 있는지

검증 결과를 표로 출력하고, 누락된 항목이 있으면 수정 제안까지 작성해줘.
```

---

## 13. Claude Code 결과 정리 프롬프트

```text
수집된 BugsInPy 케이스를 Task-Link M3 아키텍처 기준으로 분류해줘.

분류 기준:
- 테스트 실패 재현 가능
- coverage 측정 가능
- diff 교집합 필터 검증 가능
- TEST-001 커버리지 이슈 후보
- TEST-004 테스트 누락 함수 후보
- PERF 계열 분석에는 부적합한 케이스

각 케이스별로 다음 형식으로 정리해줘.

| case_id | project | bug_id | 적용 가능한 M3 기능 | 부족한 기능 | 비고 |

마지막에 BugsInPy만으로 부족해서 Custom M3 cases로 보완해야 하는 항목을 정리해줘.
```

---

## 14. 이번 단계에서 하지 않는 일

이번 문서의 범위는 BugsInPy 수집이다. 아래 작업은 아직 하지 않는다.

```text
- Custom M3 cases 생성
- N+1 전용 샘플 코드 생성
- 시간복잡도 전용 샘플 코드 생성
- 메모리누수 전용 샘플 코드 생성
- OWASP BenchmarkPython 수집
- M2 보안 데이터셋 수집
- M4 커리큘럼 매핑 생성
```

BugsInPy 수집이 끝난 뒤, M3 아키텍처에서 부족한 기능을 기준으로 Custom M3 cases를 별도 생성한다.

---

## 15. 완료 기준

Claude Code 작업 완료 기준은 다음과 같다.

```text
- datasets/m3_bugsinpy_selected/ 폴더가 생성됨
- 최소 5개 BugsInPy 케이스가 수집됨
- 각 케이스에 metadata/, buggy/, fixed/가 존재함
- 각 케이스에 expected_m3_issues.json이 존재함
- dataset_manifest.json이 존재함
- BugsInPy 코드가 서비스 본코드에 섞이지 않음
- 다음 단계에서 필요한 Custom M3 cases 목록이 정리됨
```

---

## 16. 발표용 설명 문장

```text
M3 테스트·성능 분석 모듈의 실제 버그 기반 검증을 위해 BugsInPy 데이터셋에서 일부 Python 버그 케이스를 선별했습니다. 각 케이스는 buggy/fixed 버전, 수정 패치, 테스트 실행 스크립트, 의존성 파일을 포함하며, 이를 통해 테스트 실패 재현, 커버리지 측정, diff 교집합 필터 검증을 수행할 수 있도록 구성했습니다. BugsInPy만으로 부족한 N+1 쿼리, 시간복잡도, 엣지케이스, 메모리누수 검증은 이후 Custom M3 cases로 보완할 예정입니다.
```
