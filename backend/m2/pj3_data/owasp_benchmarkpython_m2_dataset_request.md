# OWASP BenchmarkPython M2 데이터셋 수집 요청서

> 목적: Claude Code에게 전달해서 **OWASP BenchmarkPython에서 M2 코드 리뷰 모듈 검증용 데이터만 선별 수집**하도록 요청하기 위한 문서입니다.  
> 범위: **M2 보안 취약점 탐지 검증용**입니다.  
> 주의: OWASP BenchmarkPython 레포 전체를 우리 프로젝트 코드에 섞어 넣지 않습니다. 필요한 `testcode` 일부와 정답 라벨 CSV만 `datasets/` 아래에 별도로 저장합니다.

---

## 1. 왜 OWASP BenchmarkPython을 쓰는가

OWASP BenchmarkPython은 Python 보안 취약점 탐지 도구의 정확도를 검증하기 위한 공개 벤치마크입니다.

우리 프로젝트에서는 이 데이터를 **M2 코드 리뷰 모듈의 보안 취약점 탐지 검증용**으로 사용합니다.

즉, OWASP 코드는 우리 서비스 구현 코드가 아니라 **M2가 분석할 시험지**입니다.

```text
Task-Link M2 모듈 = 채점기
OWASP BenchmarkPython testcode = 시험지
expectedresults-0.1.csv = 정답지
m2_owasp_result.json = 채점 결과
```

---

## 2. 적용 대상 모듈

| 모듈 | 적용 여부 | 설명 |
|---|---:|---|
| M2 코드 리뷰 | 직접 적용 | SQL Injection, XSS, Path Traversal 등 보안 취약점 탐지 검증 |
| M3 테스트/성능 분석 | 직접 적용 아님 | 커버리지, N+1, 복잡도는 별도 BugsInPy/Custom 데이터 필요 |
| M4 학습 커리큘럼 | 간접 적용 | M2 결과 JSON을 받아 학습 추천 생성 |

이번 문서는 **M2용 OWASP BenchmarkPython 데이터 수집만** 다룹니다.

---

## 3. 원본 레포 정보

Users/user/Documents/pj3_data/BenchmarkPython-main
주요 원본 루트:

```text
BenchmarkPython/
├── testcode/                    # 취약/비취약 테스트 코드 파일들
├── expectedresults-0.1.csv       # 각 테스트 파일의 정답 라벨
├── app.py                        # 전체 웹앱 실행용. 정적 분석만 할 때는 필수 아님
├── helpers/                      # 전체 웹앱 실행용 보조 코드
├── data/                         # 전체 웹앱 실행용 데이터
├── templates/                    # 전체 웹앱 실행용 템플릿
├── testfiles/                    # 일부 취약점 실행용 테스트 파일
├── requirements.txt              # 전체 웹앱 실행용 의존성
├── README.md                     # 출처 설명
└── LICENSE                       # 라이선스
```

---

## 4. 우리 프로젝트에 저장할 최종 루트

우리 프로젝트에서는 아래 경로에 저장합니다.

```text
datasets/
└── m2_owasp_benchmark_python_selected/
    ├── testcode/
    │   ├── BenchmarkTestXXXXX.py
    │   └── ...
    │
    ├── expectedresults_selected.csv
    ├── dataset_manifest.json
    ├── source_info.md
    └── README.md
```

선택적으로 전체 웹앱 실행이 필요할 경우에만 아래 폴더를 추가합니다.

```text
datasets/
└── m2_owasp_benchmark_python_selected/
    ├── runtime_optional/
    │   ├── app.py
    │   ├── helpers/
    │   ├── data/
    │   ├── templates/
    │   ├── testfiles/
    │   └── requirements.txt
```

MVP 단계에서는 `runtime_optional/`은 만들지 않아도 됩니다.  
M2 정적 분석 검증에는 `testcode/`와 `expectedresults_selected.csv`가 핵심입니다.

---

## 5. 반드시 가져와야 하는 파일

### 필수

```text
1. selected testcode files
   원본: BenchmarkPython/testcode/BenchmarkTestXXXXX.py
   저장: datasets/m2_owasp_benchmark_python_selected/testcode/

2. expectedresults-0.1.csv에서 선택 파일에 해당하는 row만 필터링
   원본: BenchmarkPython/expectedresults-0.1.csv
   저장: datasets/m2_owasp_benchmark_python_selected/expectedresults_selected.csv

3. README.md
   원본: BenchmarkPython/README.md
   저장: datasets/m2_owasp_benchmark_python_selected/README.md

4. LICENSE
   원본: BenchmarkPython/LICENSE
   저장: datasets/m2_owasp_benchmark_python_selected/LICENSE

5. source_info.md
   직접 생성
   저장: datasets/m2_owasp_benchmark_python_selected/source_info.md

6. dataset_manifest.json
   직접 생성
   저장: datasets/m2_owasp_benchmark_python_selected/dataset_manifest.json
```

### 선택

전체 웹앱 실행이나 DAST/IAST까지 할 경우에만 가져옵니다.

```text
app.py
helpers/
data/
templates/
testfiles/
requirements.txt
```

이번 단계에서는 **선택 파일은 가져오지 않아도 됩니다.**

---

## 6. 가져오지 말아야 하는 것

처음 MVP에서는 아래 항목을 가져오지 않습니다.

```text
results/
scripts/
createScorecards.sh
runBenchmark.sh
runRemoteAccessibleBenchmark.sh
runCrawler.sh
runCrawler.bat
scoringconfigfile.yaml
전체 testcode 1000개 이상
```

이유:

```text
- M2 정적 분석 검증에는 필요 없음
- 데이터셋이 너무 커져 관리가 어려움
- 발표용 검증에는 selected cases로 충분함
- 전체 실행 환경은 추후 확장 단계에서만 필요함
```

---

## 7. 선별 기준

M2 보안 코드 리뷰 모듈 검증에 적합한 카테고리만 가져옵니다.

우선순위 카테고리:

| 카테고리 | CWE | Task-Link 이슈 코드 | 설명 |
|---|---:|---|---|
| sqli | CWE-89 | SEC-001 | SQL Injection |
| xss | CWE-79 | SEC-002 | Cross-Site Scripting |
| pathtraver | CWE-22 | SEC-003 | Path Traversal |
| cmdi | CWE-78 | SEC-004 | Command Injection |
| hash | CWE-328 | SEC-005 | Weak Hash / Weak Crypto |

가능하면 추가할 수 있는 보조 카테고리:

| 카테고리 | 예시 역할 |
|---|---|
| securecookie | 보안 쿠키 설정 검증 |
| trustbound | Trust Boundary Violation 검증 |
| crypto | 암호화 관련 취약점 검증 |

---

## 8. 권장 수집 개수

### 최소 MVP

```text
총 20개
- sqli: true 2개 / false 2개
- xss: true 2개 / false 2개
- pathtraver: true 2개 / false 2개
- cmdi: true 2개 / false 2개
- hash: true 2개 / false 2개
```

### 발표 안정권

```text
총 50개
- sqli: true 5개 / false 5개
- xss: true 5개 / false 5개
- pathtraver: true 5개 / false 5개
- cmdi: true 5개 / false 5개
- hash: true 5개 / false 5개
```

처음에는 20개로 시작하고, M2가 안정되면 50개로 확장합니다.

---

## 9. expectedresults_selected.csv 형식

원본 `expectedresults-0.1.csv`에서 선택된 파일만 필터링해서 만듭니다.

권장 형식:

```csv
test_name,category,real_vulnerability,cwe
BenchmarkTest00001,pathtraver,true,22
BenchmarkTest00004,pathtraver,false,22
BenchmarkTest00283,sqli,true,89
BenchmarkTest00285,sqli,false,89
```

주의:

```text
- test_name은 확장자 없이 저장하거나, 기존 원본 형식을 따르되 일관되게 유지한다.
- real_vulnerability는 true/false로 통일한다.
- cwe는 숫자만 저장해도 되고, CWE-89 형식으로 저장해도 된다.
- M2 평가 스크립트에서 읽기 쉬운 형식을 우선한다.
```

---

## 10. dataset_manifest.json 템플릿

Claude Code가 아래 파일을 생성해야 합니다.

```json
{
  "dataset_name": "OWASP BenchmarkPython Selected for Task-Link M2",
  "source_repository": "https://github.com/OWASP-Benchmark/BenchmarkPython",
  "purpose": "M2 security code review validation",
  "selection_policy": {
    "categories": ["sqli", "xss", "pathtraver", "cmdi", "hash"],
    "target_total_cases": 50,
    "balance": "For each category, select both vulnerable(true) and non-vulnerable(false) cases."
  },
  "cases": [
    {
      "test_name": "BenchmarkTest00001",
      "file": "testcode/BenchmarkTest00001.py",
      "category": "pathtraver",
      "real_vulnerability": true,
      "cwe": "CWE-22",
      "target_module": "M2"
    }
  ],
  "summary": {
    "total_cases": 0,
    "by_category": {},
    "by_label": {
      "true": 0,
      "false": 0
    }
  }
}
```

---

## 11. source_info.md 템플릿

Claude Code가 아래 파일을 생성해야 합니다.

```md
# OWASP BenchmarkPython Selected Dataset

## Source

- Repository: https://github.com/OWASP-Benchmark/BenchmarkPython
- Project: OWASP Benchmark for Python
- Purpose: Evaluate the accuracy of Python software vulnerability detection tools.

## Usage in Task-Link

This selected subset is used to validate the M2 Code Review Agent.

The selected cases focus on:

- SQL Injection
- Cross-Site Scripting
- Path Traversal
- Command Injection
- Weak Hash / Weak Crypto

## Selection Policy

The full repository was not copied into the Task-Link dataset.

Only selected `testcode/BenchmarkTestXXXXX.py` files and matching rows from `expectedresults-0.1.csv` were copied.

Both vulnerable and non-vulnerable cases were included to evaluate true positives, false positives, true negatives, and false negatives.

## Target Module

- M2 Code Review Agent

## Not Used For

This dataset is not the primary dataset for M3 test coverage, N+1 query, time complexity, or performance analysis.
```

---

## 12. M2 평가 결과 파일 형식

M2 분석 후 아래 결과를 생성할 수 있어야 합니다.

```json
{
  "dataset": "OWASP BenchmarkPython Selected",
  "target_module": "M2",
  "total_cases": 50,
  "results": [
    {
      "test_name": "BenchmarkTest00283",
      "category": "sqli",
      "cwe": "CWE-89",
      "expected": true,
      "detected": true,
      "outcome": "TP",
      "issues": [
        {
          "id": "SEC-001",
          "severity": "Critical",
          "title": "SQL Injection risk detected",
          "file": "testcode/BenchmarkTest00283.py"
        }
      ]
    }
  ],
  "summary": {
    "true_positive": 0,
    "true_negative": 0,
    "false_positive": 0,
    "false_negative": 0,
    "precision": 0.0,
    "recall": 0.0,
    "f1": 0.0
  }
}
```

---


## 18. 최종 요약

```text
OWASP BenchmarkPython selected
= M2 보안 코드 리뷰 검증용 데이터셋

가져오는 것:
- 선택된 testcode/*.py
- expectedresults_selected.csv
- README.md
- LICENSE
- source_info.md
- dataset_manifest.json

가져오지 않는 것:
- 전체 레포
- results/
- scripts/
- runBenchmark.sh
- runCrawler.sh
- app.py/helpers/templates 등 실행 환경
```
---

## 16. 이번 단계에서 하지 말아야 할 것

```text
- OWASP BenchmarkPython 전체 레포를 datasets에 복사하지 말 것
- M3 커버리지/N+1/복잡도 데이터로 사용하려고 하지 말 것
- BugsInPy와 한 폴더에 섞지 말 것
- Custom M3 cases를 이번 작업에서 만들지 말 것
- selected CSV 없이 testcode 파일만 복사하지 말 것
- true 케이스만 가져오지 말 것
```

---