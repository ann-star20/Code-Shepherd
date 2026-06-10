# RAGAS — RAG 검색/인용 품질 리포트

## 실행 메타 (재현용)
- 평가셋 케이스 수: **12** (빈 인용 1건)
- judge 모델: **gemini-2.5-flash-lite**
- 임베딩(judge): —
- RAGAS 버전: **0.4.3**
- 검색 임베더: BAAI/bge-m3, top_k=3
- Tier B(faithfulness/answer_relevancy): skip (ChatGoogleGenerativeAIError: Error calling model 'gemini-2.5-flash-lite' (RESOURCE_EXHAUSTED): 429 RESOURCE_EXHAUSTED. {'error': {'code': 429, 'messa)

## 지표 (평균은 미산출 skip 제외)
| metric | mean | scored | skip(미산출) |
|---|---|---|---|
| non_llm_context_precision_with_reference | 1.000 | 11 | 1 |
| non_llm_context_recall | 0.917 | 12 | 0 |
| faithfulness | —(skip) | 0 | 12 |
| answer_relevancy | —(skip) | 0 | 12 |

## 인용 라벨 정합성 (doc_title 이 올바른 규칙을 가리키나)
- 정확: **4 / 11** (정확도 0.364) — RAGAS 청크-단위 점수가 못 잡는 약점

## 케이스별
| id | rule | 인용? | 라벨 | non_llm_context_precision_with_reference | non_llm_context_recall | faithfulness | answer_relevancy | top1 검색결과 |
|---|---|---|---|---|---|---|---|---|
| TEST-001-msg | TEST-001 | ○ | ✓ | 1.000 | 1.000 | —(skip) | —(skip) | 1) 테스트 커버리지 가이드 — TEST-001 (커버 (0.63) |
| TEST-001-para | TEST-001 | ○ | ✓ | 1.000 | 1.000 | —(skip) | —(skip) | 1) 테스트 커버리지 가이드 — TEST-001 (커버 (0.60) |
| PERF-002-msg | PERF-002 | ○ | ✓ | 1.000 | 1.000 | —(skip) | —(skip) | 4) N+1 쿼리 가이드 — PERF-002 (N+1  (0.67) |
| PERF-002-para | PERF-002 | ○ | ✓ | 1.000 | 1.000 | —(skip) | —(skip) | 4) N+1 쿼리 가이드 — PERF-002 (N+1  (0.63) |
| PERF-001-msg | PERF-001 | ○ | ✗(오라벨) | 1.000 | 1.000 | —(skip) | —(skip) | 4) N+1 쿼리 가이드 — PERF-002 (N+1  (0.60) |
| PERF-001-para | PERF-001 | ○ | ✗(오라벨) | 1.000 | 1.000 | —(skip) | —(skip) | 4) N+1 쿼리 가이드 — PERF-002 (N+1  (0.75) |
| PERF-003-msg | PERF-003 | ○ | ✗(오라벨) | 1.000 | 1.000 | —(skip) | —(skip) | 4) N+1 쿼리 가이드 — PERF-002 (N+1  (0.51) |
| PERF-003-para | PERF-003 | ○ | ✗(오라벨) | 1.000 | 1.000 | —(skip) | —(skip) | 4) N+1 쿼리 가이드 — PERF-002 (N+1  (0.57) |
| TEST-004-msg | TEST-004 | ✗(빈결과) | — | —(skip) | 0.000 | —(skip) | —(skip) |  |
| TEST-004-para | TEST-004 | ○ | ✗(오라벨) | 1.000 | 1.000 | —(skip) | —(skip) | 1) 테스트 커버리지 가이드 — TEST-001 (커버 (0.59) |
| TEST-003-msg | TEST-003 | ○ | ✗(오라벨) | 1.000 | 1.000 | —(skip) | —(skip) | 1) 테스트 커버리지 가이드 — TEST-001 (커버 (0.61) |
| TEST-003-para | TEST-003 | ○ | ✗(오라벨) | 1.000 | 1.000 | —(skip) | —(skip) | 1) 테스트 커버리지 가이드 — TEST-001 (커버 (0.59) |
