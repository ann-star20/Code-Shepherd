# `datasets` 파일 구조

평가용 데이터셋 디렉토리. 크게 **M2(보안)** 와 **M3(버그/테스트/성능)** 영역으로 나뉜다.

```
datasets/
├── dataset_manifest.json              # 전체 데이터셋 매니페스트
├── expected_outputs/                  # 통합 기대 출력(정답) 모음
│   ├── expected_m2_issues.json        #   M2 보안 이슈 정답
│   └── expected_m3_issues.json        #   M3 버그 이슈 정답
│
├── m2_custom_security_cases/          # [M2] 직접 제작한 보안 취약점 케이스 (6종)
│   ├── auth_missing_case/             #   인증 누락
│   ├── command_injection_case/        #   커맨드 인젝션
│   ├── hardcoded_secret_case/         #   하드코딩된 시크릿
│   ├── insecure_password_hash_case/   #   취약한 비밀번호 해시
│   ├── path_traversal_case/           #   경로 탐색(Path Traversal)
│   └── sqli_case/                     #   SQL 인젝션
│       └── (각 케이스 공통 구성)
│           ├── vulnerable.py          #     취약 코드
│           ├── fixed.py               #     수정 코드
│           ├── expected_issue.json    #     기대 이슈(정답)
│           └── README.md              #     케이스 설명
│
├── m2_owasp_benchmark_python_selected/ # [M2] OWASP Benchmark Python 선별본 (50 케이스)
│   ├── dataset_manifest.json          #   OWASP 내부 manifest (폴더 기준 상대경로)
│   ├── expectedresults_selected.csv   #   선별 케이스 원본 라벨 (test_name,category,real_vulnerability,cwe)
│   ├── expected_owasp_m2_issues.json  #   OWASP 정답(Dev2 Output Contract) — 별도 정답 파일
│   ├── source_info.md                 #   데이터 출처/사용목적
│   ├── README.md                      #   원본 출처 보존
│   ├── LICENSE                        #   원본 라이선스 보존
│   └── testcode/                      #   selected BenchmarkTestXXXXX.py (50개)
│       ├── BenchmarkTest00001.py
│       ├── ...
│       └── BenchmarkTest01097.py
│
├── m3_bugsinpy_selected/             # [M3] BugsInPy 선별 버그 케이스 (8종)
│   ├── black_3/                      #   각 케이스 공통 구성:
│   ├── black_4/                      #     ├── buggy/      버그 버전 전체 저장소
│   ├── cookiecutter_1/               #     ├── fixed/      수정 버전 전체 저장소
│   ├── cookiecutter_2/               #     ├── metadata/   버그 메타데이터
│   ├── fastapi_2/                    #     │     ├── bug.info
│   ├── fastapi_5/                    #     │     ├── bug_patch.txt
│   ├── tqdm_1/                       #     │     ├── project.info
│   └── tqdm_4/                       #     │     ├── requirements.txt
│                                     #     │     └── run_test.sh
│                                     #     └── expected_m3_issues.json
│
└── m3_test_performance_cases/        # [M3] 테스트/성능 케이스
    └── custom_performance_cases/     #   직접 제작한 성능/테스트 케이스 (6종)
        ├── complexity_case/          #     높은 복잡도
        ├── edge_case_missing_case/   #     엣지 케이스 누락
        ├── low_coverage_case/        #     낮은 커버리지
        ├── memory_leak_case/         #     메모리 누수
        ├── missing_test_function_case/ #   테스트 함수 누락
        ├── n_plus_one_case/          #     N+1 쿼리 문제 (기존)
        │   └── (각 케이스 공통 구성)
        │       ├── app/              #       대상 애플리케이션 코드
        │       ├── tests/            #       테스트 코드
        │       ├── expected_issue.json #     기대 이슈(정답)
        │       └── README.md         #       케이스 설명
        └── n_plus_one_extended_cases/ #   N+1 전용 확장 케이스 (8종: positive 4 + negative 4)
            ├── positive_repository_find_by_id/  # for 루프 내 repository.find_by_id → PERF-002
            ├── positive_db_execute_in_loop/     # for 루프 내 db.execute → PERF-002
            ├── positive_sqlalchemy_query_in_loop/ # for 루프 내 session.query().filter().first() → PERF-002
            ├── positive_nested_loop_db_call/    # 중첩 루프 내 repository.find_by_id → PERF-002
            ├── negative_bulk_fetch_before_loop/ # 루프 전 bulk 조회 + 루프 내 dict lookup → 정상
            ├── negative_loop_without_db_call/   # DB 호출 없는 단순 반복 → 정상
            ├── negative_local_dict_get/         # 루프 내 dict.get (DB 아님) → 정상
            └── negative_self_query_method/      # 로컬 self.query (DB 아님) → 정상
                └── (각 케이스 공통 구성: app/ tests/ expected_issue.json README.md)
```

## 영역별 요약

| 영역 | 디렉토리 | 케이스 수 | 용도 |
|------|----------|-----------|------|
| M2 보안(커스텀) | `m2_custom_security_cases/` | 6 | 직접 제작한 보안 취약점 탐지 평가 |
| M2 보안(OWASP) | `m2_owasp_benchmark_python_selected/` | 50 | OWASP Benchmark 표준 케이스 평가 (오탐/미탐) |
| M3 버그 | `m3_bugsinpy_selected/` | 8 | BugsInPy 실제 버그 탐지 평가 |
| M3 테스트/성능 | `m3_test_performance_cases/custom_performance_cases/` | 14 | 성능·테스트 품질 이슈 탐지 평가 (기본 6 + N+1 확장 8) |

## OWASP BenchmarkPython 케이스 상세

5개 카테고리 × (취약 5 + 정상 5) = **50 케이스**. 카테고리는 Task-Link M2 `rule_id`로 매핑된다.

| 카테고리 | 의미 | CWE | rule_id | Severity | true | false |
|----------|------|-----|---------|----------|------|-------|
| `sqli` | SQL Injection | CWE-89 | `SEC-001` | Critical | 5 | 5 |
| `xss` | Cross-Site Scripting | CWE-79 | `SEC-002` | Critical | 5 | 5 |
| `pathtraver` | Path Traversal | CWE-22 | `SEC-003` | Critical | 5 | 5 |
| `cmdi` | Command Injection | CWE-78 | `SEC-004` | Critical | 5 | 5 |
| `hash` | Weak Hash | CWE-328 | `SEC-005` | Major | 5 | 5 |

- `case_id` 규칙: `m2_owasp_{category}_{test_name}` (예: `m2_owasp_sqli_BenchmarkTest00283`)
- `real_vulnerability=true` → `expected_issues`에 issue 1개 / `false` → 빈 배열
- OWASP 정답은 `expected_owasp_m2_issues.json`(별도 파일)에 저장 — 기존 `expected_outputs/expected_m2_issues.json`(custom 전용)과 분리
- 전체 `dataset_manifest.json`에도 50개 OWASP case가 등록됨 (전체 case 수: 20 → 70 → 78, N+1 확장 8종 추가)

## N+1 확장 케이스 상세 (`n_plus_one_extended_cases/`)

N+1 탐지기의 **recall**(positive 4)과 **false positive 방어**(negative 4)를 함께 검증한다.
positive는 `expected_issues`에 `PERF-002` 1건, negative는 빈 배열.

| 케이스 | 종류 | 패턴 | 기대 |
|--------|------|------|------|
| `positive_repository_find_by_id` | positive | for 루프 내 `repository.find_by_id(...)` | PERF-002 |
| `positive_db_execute_in_loop` | positive | for 루프 내 `db.execute(...)` | PERF-002 |
| `positive_sqlalchemy_query_in_loop` | positive | for 루프 내 `session.query(...).filter(...).first()` | PERF-002 |
| `positive_nested_loop_db_call` | positive | 중첩 루프 내 `repository.find_by_id(...)` | PERF-002 |
| `negative_bulk_fetch_before_loop` | negative | 루프 전 bulk 조회, 루프 내 dict lookup | 없음 |
| `negative_loop_without_db_call` | negative | DB 호출 없는 문자열/숫자 처리 | 없음 |
| `negative_local_dict_get` | negative | 루프 내 `dict.get(...)` (DB 아님) | 없음 |
| `negative_self_query_method` | negative | 로컬 `self.query(...)` (DB 아님) | 없음 |

## BugsInPy 케이스 상세

각 케이스는 `buggy/`(버그 버전)와 `fixed/`(수정 버전) 전체 저장소 스냅샷을 포함한다.

| 케이스 | 프로젝트 | buggy 파일 수 | fixed 파일 수 |
|--------|----------|---------------|----------------|
| `black_3` | black | 129 | 129 |
| `black_4` | black | 128 | 129 |
| `cookiecutter_1` | cookiecutter | 241 | 242 |
| `cookiecutter_2` | cookiecutter | 241 | 241 |
| `fastapi_2` | fastapi | 689 | 689 |
| `fastapi_5` | fastapi | 629 | 630 |
| `tqdm_1` | tqdm | 60 | 60 |
| `tqdm_4` | tqdm | 40 | 40 |

> `metadata/`의 `bug_patch.txt`는 버그→수정 패치 diff, `run_test.sh`는 재현용 테스트 실행 스크립트를 담는다.
