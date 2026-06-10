# m3 탐지 정확도 벤치마크 — rule별 Precision/Recall/F1 (SESSION 8B)

생성일: 2026-06-09
환경: m3 컨테이너 내 직접 실행 / 무키(휴리스틱·결정적) / RAG off
매칭: (rule_id, file) 멀티셋 (line·severity 는 식별자 아님)
라벨: 사람이 rule 정의로 확정 (탐지기 출력 자동생성 아님 = 순환 금지)

**표본 5건** (양성 3 + 음성 2)
- `pos_coverage_sample` (positive)
- `pos_perf_nplus1_complexity` (positive)
- `pos_memleak` (positive)
- `neg_clean` (negative)
- `neg_edge_handled` (negative)

## rule별 Precision / Recall / F1

| rule | TP | FP | FN | Precision | Recall | F1 |
|------|----|----|----|-----------|--------|----|
| TEST-001 | 1 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| TEST-003 | 5 | 1 | 0 | 0.833 | 1.000 | 0.909 |
| TEST-004 | 2 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| PERF-001 | 2 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| PERF-002 | 2 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| PERF-003 | 2 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| **전체** | 14 | 1 | 0 | **0.933** | **1.000** | **0.966** |

**합격 여부: PASS** (전체 F1 ≥ 0.70 AND rule별 F1 ≥ 0.50)

## 오탐(FP) — 헛다리

- `neg_edge_handled` / TEST-003 / src/pricing.py

## 미탐(FN) — 놓침

- 없음

## 한계

- 표본 5건(양성 3·음성 2) — 통계적 유의성 낮음, 추세·약점 식별용.
- TEST-003·PERF-003 은 무키 휴리스틱 모드 기준. LLM 모드는 결과가 달라질 수 있음(비결정).
- 커버리지 의존 규칙(TEST-001/004)은 사전 생성 coverage.json 기반(실 Docker sandbox 미실행).