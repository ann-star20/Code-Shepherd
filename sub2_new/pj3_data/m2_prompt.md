## 13. Claude Code 작업 프롬프트

아래 프롬프트를 Claude Code에 그대로 전달하세요.

```text
너는 Task-Link 팀프로젝트의 데이터셋 구축 담당자다.

목표:
OWASP BenchmarkPython에서 M2 코드 리뷰 모듈 검증용 selected dataset을 만들어라.

원본 레포:
https://github.com/OWASP-Benchmark/BenchmarkPython

최종 저장 루트:
datasets/m2_owasp_benchmark_python_selected/

해야 할 일:
1. OWASP BenchmarkPython 원본 레포 구조를 확인한다.
2. expectedresults-0.1.csv를 읽는다.
3. 아래 5개 카테고리에서 취약 true / 비취약 false 케이스를 균형 있게 선택한다.
   - sqli
   - xss
   - pathtraver
   - cmdi
   - hash
4. 우선 최소 20개를 선택한다.
   - 각 카테고리별 true 2개, false 2개
5. 가능하면 발표 안정권으로 50개까지 확장할 수 있게 구조를 만든다.
   - 각 카테고리별 true 5개, false 5개
6. 선택된 테스트 파일만 복사한다.
   원본: testcode/BenchmarkTestXXXXX.py
   대상: datasets/m2_owasp_benchmark_python_selected/testcode/
7. expectedresults-0.1.csv에서 선택된 파일에 해당하는 row만 필터링해서 저장한다.
   대상: datasets/m2_owasp_benchmark_python_selected/expectedresults_selected.csv
8. README.md와 LICENSE를 복사한다.
9. source_info.md를 생성한다.
10. dataset_manifest.json을 생성한다.
11. 전체 레포를 통째로 복사하지 마라.
12. results/, scripts/, runBenchmark.sh, runCrawler.sh, createScorecards.sh는 복사하지 마라.
13. app.py, helpers/, data/, templates/, testfiles/, requirements.txt는 이번 단계에서는 복사하지 마라.
14. 최종 결과에서 카테고리별 개수와 true/false 개수를 요약해라.

최종 산출물:
datasets/m2_owasp_benchmark_python_selected/
├── testcode/
├── expectedresults_selected.csv
├── dataset_manifest.json
├── source_info.md
├── README.md
└── LICENSE

검증 조건:
- selected testcode 파일 수와 expectedresults_selected.csv row 수가 일치해야 한다.
- 각 row의 test_name에 해당하는 .py 파일이 testcode/ 안에 존재해야 한다.
- true/false 케이스가 모두 포함되어야 한다.
- sqli, xss, pathtraver, cmdi, hash 카테고리가 모두 포함되어야 한다.
- 전체 OWASP BenchmarkPython 레포를 datasets 안에 통째로 넣으면 안 된다.
```

---

## 14. Claude Code 검증 프롬프트

수집 후 아래 프롬프트로 검증하세요.

```text
방금 생성한 datasets/m2_owasp_benchmark_python_selected/ 데이터셋을 검증해라.

검증할 것:
1. testcode/ 안의 .py 파일 개수를 세어라.
2. expectedresults_selected.csv의 row 수를 세어라.
3. 두 개수가 일치하는지 확인해라.
4. CSV의 모든 test_name에 해당하는 BenchmarkTestXXXXX.py 파일이 존재하는지 확인해라.
5. 카테고리별 개수를 출력해라.
6. true/false 라벨 개수를 출력해라.
7. sqli, xss, pathtraver, cmdi, hash가 모두 포함되었는지 확인해라.
8. dataset_manifest.json의 summary가 실제 파일 개수와 일치하는지 확인해라.
9. 전체 레포가 통째로 복사되지 않았는지 확인해라.
10. 문제가 있으면 수정하고, 수정 내역을 요약해라.
```

---

## 15. Claude Code M2 분석 실행 프롬프트

M2 모듈을 데이터셋에 적용할 때는 아래 프롬프트를 사용합니다.

```text
Task-Link M2 코드 리뷰 모듈을 아래 데이터셋에 실행해라.

대상 데이터셋:
datasets/m2_owasp_benchmark_python_selected/

입력:
- testcode/*.py
- expectedresults_selected.csv

해야 할 일:
1. 각 BenchmarkTestXXXXX.py 파일을 M2 코드 리뷰 모듈로 분석한다.
2. SQL Injection, XSS, Path Traversal, Command Injection, Weak Hash 취약점을 탐지한다.
3. 탐지 결과를 expectedresults_selected.csv의 real_vulnerability 값과 비교한다.
4. 각 케이스를 TP, TN, FP, FN으로 분류한다.
5. 결과를 outputs/m2_owasp_result.json으로 저장한다.
6. precision, recall, f1을 계산한다.
7. 카테고리별 탐지 결과도 함께 저장한다.
8. PR 코멘트 예시를 outputs/m2_owasp_pr_comment.md로 생성한다.

출력:
outputs/m2_owasp_result.json
outputs/m2_owasp_pr_comment.md
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

## 17. 교수님 발표용 설명 문장

```text
M2 코드 리뷰 모듈의 보안 취약점 탐지 검증에는 OWASP BenchmarkPython의 selected cases를 사용했습니다. 전체 레포를 그대로 사용하지 않고, SQL Injection, XSS, Path Traversal, Command Injection, Weak Hash 등 주요 CWE 카테고리에서 취약/비취약 샘플을 균형 있게 선별했습니다. 각 샘플은 expectedresults-0.1.csv의 정답 라벨을 기준으로 TP, FP, TN, FN을 계산해 탐지 성능을 평가했습니다.
```

---
