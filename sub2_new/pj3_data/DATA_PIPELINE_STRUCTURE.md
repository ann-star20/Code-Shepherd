# Task-Link 데이터 파이프라인 구조

문서 기준 루트: `C:\Users\USER\Desktop\pj3_data`
(실제 콘텐츠 루트: `pj3_data/pj3_data/` — 본 문서는 이 프로젝트 루트를 기준으로 기술한다.)

이 저장소는 **평가용 데이터셋(`datasets/`)을 생산하기 위한 파이프라인**이다.
원천 데이터(OWASP / BugsInPy)를 입력받아, 스펙(프롬프트) 정의에 따라 케이스를 선별·가공하고,
Task-Link M2/M3 평가에 쓰는 큐레이션 데이터셋을 산출한 뒤, 정합성을 검증한다.

---

## 파이프라인 개요 (4단계)

```text
[Stage 0] 원천 소스            [Stage 1] 파이프라인 정의        [Stage 2] 산출물            [Stage 3] 검증
─────────────────────         ──────────────────────────      ──────────────────         ─────────────────
BenchmarkPython-main/  ─┐      m2_dataset_split_files_v2/ ─┐                              task_link_dataset_
 (OWASP 원본 1230건)    │      m3_dataset_split_files/    │                               validation_prompt.md
BugsInPy-master/       ─┼───▶  m2_plus/ (OWASP add-on)    ├──▶  datasets/  ───────────▶        │
 (17 projects)          │      *.md (root 요청 프롬프트)   │     (큐레이션 70 케이스)            ▼
_repo_cache/           ─┘                                 ┘                              DATASET_VALIDATION_
 (clone 캐시)                                                                             REPORT.md
```

| 단계 | 역할 | 입력 | 출력 |
|------|------|------|------|
| **0. 원천(raw)** | 외부 벤치마크 원본 보관 | — | OWASP 1230건, BugsInPy 17 프로젝트 |
| **1. 정의(spec)** | 선별·가공 규칙(프롬프트/스펙) | 원천 + 요구사항 | 케이스 생성 지시서 |
| **2. 산출(curated)** | 선별·변환된 평가 데이터셋 | 원천 + 스펙 | `datasets/` 70 케이스 |
| **3. 검증(validate)** | 정합성·완결성 검사 | 산출물 | 검증 보고서 |

---

## 전체 디렉토리 트리

```text
pj3_data/                                   # ← 문서 기준 루트(C:\Users\USER\Desktop\pj3_data)
└── pj3_data/                               # 프로젝트 루트 (git 저장소)
    │
    ├── ■ Stage 0 — 원천 소스 (raw upstream)
    ├── BenchmarkPython-main/               # OWASP Benchmark for Python 원본
    │   ├── testcode/                        #   BenchmarkTest*.py 전체 1230개
    │   ├── expectedresults-0.1.csv          #   원본 정답 라벨 1230행
    │   ├── data/ helpers/ results/          #   원본 스크립트/리소스
    │   ├── scripts/ templates/ testfiles/
    │   ├── app.py  createScorecards.sh
    │   ├── requirements.txt  README.md  LICENSE
    │   └── OWASP Benchmark for Python.URL
    │
    ├── BugsInPy-master/                    # BugsInPy 실제 버그 벤치마크 원본
    │   ├── framework/                       #   버그 재현 프레임워크(체크아웃/테스트 도구)
    │   └── projects/                        #   17개 프로젝트 (ansible, black, cookiecutter,
    │                                        #   fastapi, httpie, keras, luigi, matplotlib,
    │                                        #   pandas, PySnooper, ...)
    │
    ├── _repo_cache/                        # 파이프라인 작업용 clone 캐시
    │   └── tqdm/                            #   (BugsInPy 케이스 체크아웃 캐시)
    │
    ├── ■ Stage 1 — 파이프라인 정의 (spec / prompt)
    ├── m2_prompt.md                        # M2 보안 데이터 전반 요청 프롬프트
    ├── owasp_benchmarkpython_m2_dataset_request.md  # OWASP→M2 선별 요청
    ├── bugsinpy_claude_code_request.md     # BugsInPy→M3 선별 요청
    ├── task_link_dataset_validation_prompt.md       # ▶ Stage 3 검증 지시서
    │
    ├── m2_dataset_split_files_v2/          # [M2 custom] 보안 케이스 생성 스펙
    │   ├── 01_claude_code_prompt_m2_security_cases_v2.md
    │   ├── 02_m2_security_folder_structure_v2.md
    │   └── 03_m2_custom_security_code_spec_v2.md
    │
    ├── m2_plus/                            # [M2 OWASP add-on] OWASP 매핑 스펙
    │   ├── 01_claude_code_prompt_m2_owasp_addon_v2.md
    │   ├── 02_m2_owasp_addon_folder_structure_v2.md
    │   └── 03_m2_owasp_mapping_spec_v2.md
    │
    ├── m3_dataset_split_files/             # [M3 custom] 테스트/성능 케이스 생성 스펙
    │   ├── 01_claude_code_prompt_m3_custom_cases.md
    │   ├── 02_m3_custom_folder_structure.md
    │   └── 03_m3_custom_performance_code_spec.md
    │
    ├── ■ Stage 2 — 산출물 (curated dataset)
    ├── datasets/                           # ▶▶ 최종 평가 데이터셋 (총 70 케이스)
    │   ├── dataset_manifest.json            #   통합 매니페스트 (70 cases)
    │   ├── expected_outputs/                #   custom 정답 모음 (M2/M3)
    │   ├── m2_custom_security_cases/        #   M2 보안 custom 6
    │   ├── m2_owasp_benchmark_python_selected/  # M2 OWASP 선별 50
    │   ├── m3_bugsinpy_selected/            #   M3 BugsInPy 선별 8
    │   ├── m3_test_performance_cases/       #   M3 테스트/성능 custom 6
    │   ├── FILE_STRUCTURE.md                #   datasets 상세 구조 문서
    │   └── DATASET_VALIDATION_REPORT.md     #   ◀ Stage 3 검증 결과
    │
    ├── ■ 설정 / 작업공간
    ├── .claude/
    │   └── settings.local.json
    └── pj3_data.code-workspace
```

> 상세한 `datasets/` 내부 구조는 [`datasets/FILE_STRUCTURE.md`](datasets/FILE_STRUCTURE.md) 참조.

---

## 단계별 상세

### Stage 0 — 원천 소스 (raw upstream)

수정 금지 원본. 파이프라인 입력으로만 사용한다.

| 소스 | 내용 | 규모 | 다운스트림 |
|------|------|------|------------|
| `BenchmarkPython-main/` | OWASP Benchmark for Python | testcode 1230개 / 라벨 1230행 | → M2 OWASP selected 50 |
| `BugsInPy-master/` | BugsInPy 실버그 벤치마크 | 17 projects + framework | → M3 BugsInPy selected 8 |
| `_repo_cache/` | 버그 재현용 clone 캐시 | (작업 임시) | BugsInPy 체크아웃 보조 |

### Stage 1 — 파이프라인 정의 (spec / prompt)

각 데이터셋을 "어떻게 선별·가공할지" 규정하는 지시서. 3개 스펙 묶음은 동일 패턴
(`01_프롬프트` → `02_폴더구조` → `03_코드/매핑 스펙`)을 따른다.

| 정의 묶음 | 대상 산출물 | 핵심 규칙 |
|-----------|-------------|-----------|
| `m2_dataset_split_files_v2/` | `datasets/m2_custom_security_cases/` | 보안 취약점 6종 직접 작성 (vulnerable/fixed 쌍) |
| `m2_plus/` | `datasets/m2_owasp_benchmark_python_selected/` | OWASP 원본 → 50건 선별, category→rule_id/CWE 매핑 |
| `m3_dataset_split_files/` | `datasets/m3_test_performance_cases/` | 테스트/성능 이슈 6종 직접 작성 |
| `bugsinpy_claude_code_request.md` | `datasets/m3_bugsinpy_selected/` | BugsInPy 8 케이스 선별 (buggy/fixed/metadata) |

### Stage 2 — 산출물 (curated dataset)

`datasets/` = 파이프라인 최종 결과. 4개 영역 합산 **70 케이스**.

| 영역 | 경로 | 케이스 | 출처 |
|------|------|--------|------|
| M2 보안 custom | `m2_custom_security_cases/` | 6 | Stage 1 작성 |
| M2 OWASP selected | `m2_owasp_benchmark_python_selected/` | 50 | Stage 0 OWASP 선별 |
| M3 BugsInPy selected | `m3_bugsinpy_selected/` | 8 | Stage 0 BugsInPy 선별 |
| M3 테스트/성능 custom | `m3_test_performance_cases/custom_performance_cases/` | 6 | Stage 1 작성 |
| **합계** | `dataset_manifest.json` | **70** | — |

### Stage 3 — 검증 (validate)

| 지시서 | 산출 보고서 | 판정 |
|--------|-------------|------|
| `task_link_dataset_validation_prompt.md` | `datasets/DATASET_VALIDATION_REPORT.md` | **PASS** (70/70 정합) |

검증 범위: 필수 폴더/파일 존재 · JSON/CSV 파싱 · manifest `target_path` 실재 ·
expected output rule_id 정합 · OWASP true/false 라벨 균형(25/25).

---

## 데이터 흐름 요약 (출처 → 산출 매핑)

```text
BenchmarkPython-main/testcode/ (1230)  ──[m2_plus 스펙: 50건 선별]──▶  datasets/m2_owasp_benchmark_python_selected/  (50)
BugsInPy-master/projects/      (17)    ──[bugsinpy 요청: 8 케이스]──▶  datasets/m3_bugsinpy_selected/                 (8)
(직접 작성)                            ──[m2_dataset_split_files_v2]─▶  datasets/m2_custom_security_cases/             (6)
(직접 작성)                            ──[m3_dataset_split_files]────▶  datasets/m3_test_performance_cases/            (6)
                                                                        └─▶ dataset_manifest.json (통합 70) ─▶ 검증 ─▶ REPORT
```

---

## 규칙 (rule_id) 매핑 레퍼런스

| 모듈 | 카테고리 | rule_id |
|------|----------|---------|
| M2 | SQL Injection / sqli | `SEC-001` |
| M2 | XSS / xss | `SEC-002` |
| M2 | Path Traversal / pathtraver | `SEC-003` |
| M2 | Command Injection / cmdi | `SEC-004` |
| M2 | Weak Hash / insecure_password_hash / hash | `SEC-005` |
| M2 | Hardcoded Secret | `SEC-006` |
| M2 | Auth Missing | `AUTH-001` |
| M3 | low_coverage | `TEST-001` |
| M3 | edge_case_missing | `TEST-003` |
| M3 | missing_test_function | `TEST-004` |
| M3 | complexity | `PERF-001` |
| M3 | n_plus_one | `PERF-002` |
| M3 | memory_leak | `PERF-003` |
