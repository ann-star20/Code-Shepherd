# M3 담당자 온보딩 (요약판)

> M3 = **테스트 품질 + 성능 이슈**를 잡는 에이전트. 보안(M2)은 신경 안 써도 됨.
> 이 문서 하나만 보면 됨. 데이터 위치 → 적용 방법 → 프롬프트 순서로 읽으면 됨.

---

## 0. 표시 약속 (먼저 읽기)

| 표시 | 의미 |
|------|------|
| 🔴 **문제 코드** | M3가 분석할 대상. 일부러 이슈를 심어둔 파일 |
| 🟢 **정답** | M3 결과와 비교할 채점 기준. 여기에 적힌 이슈를 잡으면 정답 |
| ⚪ **무시** | M3 담당자가 안 봐도 되는 파일/폴더 |

---

## 1. M3가 잡아야 하는 이슈 6종

| rule_id | 이름 | 한 줄 설명 |
|---------|------|-----------|
| `TEST-001` | 낮은 커버리지 | 테스트 안 된 함수가 많아 커버리지 80% 미만 |
| `TEST-003` | 엣지케이스 누락 | None·0·음수·빈 값·경계값 테스트가 없음 |
| `TEST-004` | 테스트 없는 함수 | 함수는 있는데 테스트가 아예 없음 |
| `PERF-001` | 복잡도 | 중첩 루프 2단계 이상 (O(n²)) |
| `PERF-002` | N+1 쿼리 | for 루프 안에서 DB 호출 반복 |
| `PERF-003` | 메모리 누수 | 전역 리스트/딕셔너리에 데이터 무한 누적 |

---

## 2. 데이터는 딱 3종류 (`datasets/` 안)

```
datasets/
├── m3_mixed_project_cases/        ← ① 추천 시작점 (한 파일에 이슈 여러 개)
├── m3_test_performance_cases/     ← ② rule_id 1개씩 검증용
└── m3_bugsinpy_selected/          ← ③ 실제 오픈소스 버그 (실행 필요, 어려움)

⚪ 무시해도 되는 것:
  - bugsinpy_claude_code_request.md, m3_dataset_split_files/  (제작용 스펙 문서)
  - m2_*, owasp_* 로 시작하는 폴더 전부  (M2 보안 담당 몫)
  - expected_outputs/expected_m2_issues.json  (M2 정답)
```

각 케이스 폴더 구조는 셋 다 거의 같음:

```
케이스폴더/
├── app/xxx_service.py       🔴 문제 코드 (이걸 분석)
├── tests/test_xxx.py        🔴 부족한 테스트 (일부러 빈 부분 있음)
├── conftest.py              ⚪ pytest 경로 설정 (그냥 둠)
├── README.md               ⚪ 케이스 설명 (참고용)
└── expected_issue.json      🟢 정답 (이걸로 채점)
```

---

## 3. ① m3_mixed_project_cases (여기서 시작)

한 파일에 이슈가 3~4개씩 섞여 있어 실전과 가장 비슷함. 6개 케이스.

| 케이스 | 🔴 문제 코드 | 🟢 정답 | 심어둔 이슈 |
|--------|-------------|---------|------------|
| mixed_case_001 | app/order_service.py | expected_issue.json | PERF-001, PERF-002, TEST-001 |
| mixed_case_002 | app/profile_service.py | expected_issue.json | TEST-003, TEST-004, PERF-003 |
| mixed_case_003 | app/report_service.py | expected_issue.json | PERF-002, TEST-001, PERF-003 |
| mixed_case_004 | app/pipeline_service.py | expected_issue.json | PERF-001, TEST-003, TEST-004 |
| mixed_case_005 | app/notification_service.py | expected_issue.json | PERF-002, PERF-003, TEST-001, TEST-003 |
| mixed_case_006 | app/dashboard_service.py | expected_issue.json | PERF-001, PERF-002, TEST-004, PERF-003 |

---

## 4. ② m3_test_performance_cases (rule_id 1개씩)

이슈를 종류별로 따로 보고 싶을 때. `custom_performance_cases/` 안.

| 폴더 | 🟢 정답 rule_id |
|------|----------------|
| low_coverage_case | TEST-001 |
| edge_case_missing_case | TEST-003 |
| missing_test_function_case | TEST-004 |
| complexity_case | PERF-001 |
| n_plus_one_case | PERF-002 |
| memory_leak_case | PERF-003 |

추가로 `n_plus_one_extended_cases/` 8개 — N+1 오탐 검증용:
- `positive_*` 4개 → **PERF-002 잡아야 정답**
- `negative_*` 4개 → **아무것도 안 잡아야 정답** (잡으면 오탐)

---

## 5. ③ m3_bugsinpy_selected (실제 버그, 난이도 높음)

실제 오픈소스 버그 8개 (black, cookiecutter, fastapi, tqdm). 코드 실행이 필요해서 가장 어려움. **시간 없으면 ①②만 해도 됨.**

```
black_3/
├── buggy/      🔴 버그 버전 (테스트 돌리면 실패해야 정상)
├── fixed/      ⚪ 수정 버전 (테스트 통과해야 정상)
├── metadata/   ⚪ 실행 정보 (run_test.sh, bug_patch.txt 등)
└── expected_m3_issues.json   🟢 정답
```

정답 rule_id가 다름: `TEST-FAIL-001`(buggy에서 테스트 실패), `PATCH-001`(패치 diff 확인).

---

## 6. 통합 정답 한곳에서 보기

케이스별 `expected_issue.json`을 모아둔 인덱스:

```
datasets/expected_outputs/expected_m3_issues.json   🟢 (custom 14 + mixed 6)
datasets/dataset_manifest.json                      ⚪ 전체 케이스 목록·경로
```

> 통합 정답 = **케이스마다 잡아야 할 rule_id 목록**. 상세 내용은 각 케이스 `expected_issue.json`이 원본.

---

## 7. M3 작업에 적용하는 방법 (실전 순서)

```
1. 케이스 폴더 하나 고른다 (mixed_case_001 추천)
2. app/*.py (🔴) 를 M3 에이전트에 입력으로 넣는다
3. M3가 이슈 목록을 뱉는다  → [{rule_id, 함수, 근거}, ...]
4. expected_issue.json (🟢) 과 비교한다
5. 정답 rule_id를 다 잡았으면 PASS, 놓치거나 오탐이면 FAIL
```

커버리지 계열(TEST-001/003/004)은 pytest로 직접 측정도 가능:

```bash
cd datasets/m3_mixed_project_cases/mixed_case_001
pip install pytest pytest-cov
pytest tests/ --cov=app --cov-report=term-missing
# → 커버리지 80% 미만이면 TEST-001 발생이 맞음
```

PERF 계열(001/002/003)은 코드를 **정적 분석**(읽어서 패턴 탐지):
- 중첩 for 루프 → PERF-001
- for 루프 안 `repo.find_*()` 같은 DB 호출 → PERF-002
- 전역 `list/dict`에 `.append()` / `[key]=` 누적 → PERF-003

---

## 8. 바로 쓰는 프롬프트 (복붙용)

데이터 루트(이 경로 기준으로 케이스를 가리킴):

```
datasets/m3_mixed_project_cases/    ← mixed 케이스 6개 (시작점)
datasets/m3_test_performance_cases/ ← rule 1개짜리 케이스
datasets/m3_bugsinpy_selected/      ← 실제 버그 케이스
```

M3 에이전트(또는 Claude)에 아래처럼 넣으면 됨. `[분석 대상]`에
위 데이터 루트의 실제 파일 경로를 적거나, 그 파일 내용을 붙여넣으면 됨.

```
너는 Python 코드의 테스트 품질과 성능 이슈만 찾는 분석기다.
아래 6가지 rule_id 중 해당되는 것만 보고하라. 보안은 무시한다.

[분석 대상]
- 소스: datasets/m3_mixed_project_cases/mixed_case_001/app/order_service.py
- 테스트: datasets/m3_mixed_project_cases/mixed_case_001/tests/test_order_service.py
  (소스 함수 중 테스트에 없는 것 = TEST-001/004 판단 근거)

[탐지 규칙]
- TEST-001: 테스트되지 않은 함수가 많아 커버리지 80% 미만으로 추정
- TEST-003: None/0/음수/빈 값/경계값 엣지케이스 테스트 누락
- TEST-004: 소스에 함수는 있으나 테스트가 전혀 없음
- PERF-001: 중첩 루프 2단계 이상 (O(n^2))
- PERF-002: for 루프 안에서 DB 호출(repo/session/db.execute 등) 반복 (N+1)
- PERF-003: 전역 list/dict에 데이터가 무한 누적 (메모리 누수)

[출력 형식] JSON 배열만 출력. 설명 금지.
[
  {
    "rule_id": "PERF-002",
    "target_function": "load_orders_with_items",
    "evidence": "for 루프 안에서 repo.find_by_id() 반복 호출"
  }
]
```

> 다른 케이스를 보려면 위 `[분석 대상]`의 `mixed_case_001` 부분과
> 파일명(`order_service.py`)만 해당 케이스 것으로 바꾸면 됨.

채점까지 자동화하려면 이어서:

```
위 결과의 rule_id 집합을, 같은 케이스 폴더의 expected_issue.json 안
expected_issues[].id 집합과 비교하라.
(예: datasets/m3_mixed_project_cases/mixed_case_001/expected_issue.json)
- 정답을 모두 포함하면 PASS
- 정답을 놓치면 누락(FN), 정답에 없는 걸 보고하면 오탐(FP)
PASS/FAIL과 FN·FP 목록을 출력하라.
```

---

## 9. 한 줄 요약

> 🔴 `app/*.py`(또는 `buggy/`)를 분석 → 🟢 `expected_issue.json`과 비교 → 일치하면 통과.
> ⚪ M2·OWASP·스펙 문서는 안 봐도 됨. `mixed_case_001`부터 시작.
