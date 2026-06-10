# m3 verdict 정확도 벤치마크 (SESSION 8C)

생성일: 2026-06-10
대상: aggregator.aggregate() 의 verdict 임계값(escalate≥1 Critical · rework≥3 Major)
라벨: 8B 라벨셋(5) 재사용 + 확장(5). expected_verdict 는 사람이 독립 부여(순환 금지).
severity: 탐지기 정의 매핑(TEST-001=Major, TEST-003/004=Minor, PERF-001=depth별, PERF-002=Major, PERF-003=Minor).
LLM 불필요 — 결정적·재현 가능.

**verdict 일치율: 10/10 = 100%**

| 케이스 | 출처 | 기대(사람) | 산출(aggregate) | 일치 | 근거 |
|---|---|---|---|:--:|---|
| `pos_coverage_sample` | 8B | 수정요청(rework) | 수정요청(rework) | ✅ | 커버리지 20% + 미테스트 함수 + N+1 + O(n²) → 머지 전 수정 요청이 타당. |
| `pos_perf_nplus1_complexity` | 8B | 수정요청(rework) | 수정요청(rework) | ✅ | N+1 쿼리 + O(n³) 3중 중첩루프 → 실제 성능 결함, 머지 전 수정 요청이 타당. |
| `pos_memleak` | 8B | 통과(lgtm) | 통과(lgtm) | ✅ | 메모리 누수 의심 2건이나 탐지기 정의상 Minor(권고) → 참고 후 머지 가능. |
| `neg_clean` | 8B | 통과(lgtm) | 통과(lgtm) | ✅ | 진짜 깨끗한 코드 — 이슈 0건. |
| `neg_edge_handled` | 8B | 통과(lgtm) | 통과(lgtm) | ✅ | 엣지케이스 이미 처리(정답 0건). 휴리스틱 FP 는 8B 의 precision 측정 대상이지 verdict 대상 아님. |
| `ext_sqli_critical` | extended (M2 모사) | 시니어검토(escalate) | 시니어검토(escalate) | ✅ | SQL 인젝션(Critical) — 시니어 검토 필요. m3 단독 불가, M2 정적/보안 출력으로만 도달. |
| `ext_critical_plus_majors` | extended (M2 모사) | 시니어검토(escalate) | 시니어검토(escalate) | ✅ | 하드코딩 시크릿(Critical)이 있으면 Major 수와 무관하게 escalate. |
| `ext_three_nplus1` | extended | 수정요청(rework) | 수정요청(rework) | ✅ | N+1 3건(Major 3) — 임계값 도달, 수정 요청. |
| `ext_minor_only` | extended | 통과(lgtm) | 통과(lgtm) | ✅ | 권고성 Minor 만 — 머지 가능. |
| `ext_many_minor` | extended | 통과(lgtm) | 통과(lgtm) | ✅ | Minor 5건이어도 Major/Critical 0 → 머지 가능(Minor 는 verdict 를 올리지 않음). |

## 한계

- 표본 10건(8B 5 + 확장 5) — 추세·임계값 점검용(통계적 유의성 아님).
- escalate 는 m3 단독 불가(Critical 미생성) → ext_* 는 M2 교차모듈 상황 모사.
- expected_verdict 는 사람 판단 — pos_memleak(Minor 누수) 등 일부는 리뷰어에 따라 이견 가능.