# m3 파이프라인 단계별 소요 시간 벤치마크

생성일: 2026-06-09
환경: m3 컨테이너 내 직접 실행 (sandbox=fixture coverage.json 사용)
sandbox(Docker pytest): fixture coverage.json 사용 — 실제 Docker sandbox 미실행(생략)
RAG: on

**측정 PR (5종 × 1회 = 5회)**

- PR1: fixtures/tiny (3줄)
- PR2: fixtures/small (22줄, N+1+복잡도)
- PR3: fixtures/medium (45줄, 2파일)
- PR4: fixtures/large (65줄, 2파일·중첩루프)
- PR5: fixtures/xlarge (90줄, 2파일·3중루프)

**N=5**, PR: PR1, PR2, PR3, PR4, PR5
환경: m3 컨테이너 내 직접 실행 (sandbox=fixture coverage.json 사용)

### 단계별 소요 시간 (warm 실행)

| 단계 | p50 (ms) | p95 (ms) | min | max | N |
|------|----------|----------|-----|-----|---|
| parse_diff | 0.2 | 0.3 | 0.1 | 0.3 | 4 |
| coverage (sandbox/pytest) | 56.5 | 57.7 | 40.3 | 57.9 | 4 |
| missing_funcs | 56.7 | 101.9 | 35.4 | 108.6 | 4 |
| nplus1 | 39.0 | 109.0 | 19.0 | 121.0 | 4 |
| complexity | 41.1 | 46.6 | 20.4 | 47.5 | 4 |
| enrich (code_context LLM) | 333.2 | 1244.2 | 249.9 | 1265.0 | 11 |
| framework | 23.3 | 32.6 | 11.9 | 33.8 | 4 |
| rag | 6639.5 | 11263.7 | 2654.0 | 11597.9 | 8 |
| end_to_end | 19888.0 | 23406.9 | 18380.2 | 23833.2 | 4 |
| edge_cases_llm | 1340.3 | 1646.2 | 277.2 | 1684.5 | 15 |
| edge_cases | 4466.7 | 5483.1 | 4091.7 | 5596.6 | 4 |
| memory_leak | 43.1 | 96.9 | 19.5 | 105.8 | 4 |

### cold vs warm 비교

| 단계 | cold p50 | warm p50 | 차이 |
|------|----------|----------|------|
| enrich (code_context LLM) | - | 333.2 | - |
| complexity | 10.4 | 41.1 | -30.7 |
| coverage (sandbox/pytest) | 301.9 | 56.5 | +245.4 |
| end_to_end | 28750.9 | 19888.0 | +8862.9 |
| edge_cases | 6455.5 | 4466.7 | +1988.8 |
| edge_cases_llm | 1232.3 | 1340.3 | -108.0 |
| framework | 7.2 | 23.3 | -16.1 |
| memory_leak | 9.0 | 43.1 | -34.1 |
| missing_funcs | 30.0 | 56.7 | -26.7 |
| nplus1 | 14.6 | 39.0 | -24.4 |
| parse_diff | 0.2 | 0.2 | 0.0 |
| rag | 10951.6 | 6639.5 | +4312.1 |

**병목**: end_to_end, rag

## 한계

- **sandbox**: Docker-in-Docker 격리 실행은 미포함. 실제 환경에서는 sandbox 단계가 가장 큰 병목일 가능성 있음.
- **LLM(code_context)**: LLM 호출은 `USE_MOCK_LLM` 또는 키 상태에 따라 달라짐. 키 없는 환경에서는 heuristic fallback.
- **GitHub post/persist**: 이 벤치마크에서는 pr-comment-agent(refine/post/persist)를 포함하지 않음.
- **clone**: GitHub 실 clone은 별도 측정 필요 (네트워크 가변).
- 표본 N=5 (크기별 1회), 통계적 유의성 낮음 — 추세 참고용.