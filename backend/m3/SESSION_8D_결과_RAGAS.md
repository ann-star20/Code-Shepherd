# SESSION_8D 결과 — RAG 검색/인용 품질 (RAGAS 도입)

> 작업 디렉토리: `backend/m3/test-performance-agent`
> 실행: docker compose m3 컨테이너(uv), `RAG_ENABLED=1`, 실 GCP `chunks/chunk_embeddings` + BGE‑M3.

## 한 줄 결론
검색(retriever)은 **의미적으로 잘 동작**한다(이슈 → 관련 가이드 청크를 점수와 함께 가져옴).
진짜 약점은 **검색기 알고리즘이 아니라 적재된 코퍼스**다 — 6개 사내 가이드가 DB에 **단 2개의 과대(over‑broad) 청크**로 들어가 있어, **인용 라벨이 6규칙 중 4규칙에서 틀리고**(정확도 36%), 한 인용에 무관한 2개 섹션이 섞여 나온다. 고칠 곳은 **재청킹(적재)** 이지 검색 코드가 아니다.

---

## 1. 선행 점검 (RAGAS 전 "검색이 멀쩡한가") — 통과 ✅
- `RAG_ENABLED=1`, BGE‑M3(1024) 로드 OK, GCP `tasklink` 접속 OK.
- 적재량: documents 129 / chunks 647 / chunk_embeddings 485.
- 스모크(커버리지·N+1·복잡도 이슈 문장) → 빈 결과 아님, 점수(0.5~0.75)와 함께 관련 청크 반환.
- `tests/test_retriever.py` 15개 green. → **여기서 멈출 사유 없음, RAGAS 진행.**

## 2. 무엇을 만들었나
| 산출물 | 설명 |
|---|---|
| `validation/rag_evalset.json` | 사람이 라벨링한 평가셋 **12케이스**(6규칙 × {탐지기 실제 message, 자연어 paraphrase}). 정답은 conventions/*.md 기준으로 사람이 고른 청크의 **본문 전체**(verbatim). retriever 출력으로 정답을 만들지 않음(순환 금지). |
| `validation/rag_eval.py` | 평가 파이프라인. **RAGAS 호출부(`run_ragas`)는 seam 으로 분리·지연 import** → 순수 함수는 ragas 없이 단위테스트됨. 1커맨드 재실행. |
| `tests/test_rag_eval.py` | TDD 단위테스트 **17개**(가짜 retriever + 가짜 RAGAS 점수로 집계·표·정직성 검증, 빈 인용 skip/0 규칙 검증). |
| `validation/rag_eval_report.md` / `.json` | 매 실행 시 자동 저장되는 결과 표. |

**재실행 (1커맨드):**
```bash
docker compose exec m3 sh -c 'cd /app/service/test-performance-agent && uv run --extra eval python validation/rag_eval.py'
```

## 3. 측정 메타 (재현용)
- 평가셋: **12케이스** (빈 인용 1건)
- 검색 임베더: **BAAI/bge-m3** (1024), `top_k=3`, `RAG_SCORE_MIN=0.5`
- RAGAS: **0.4.3** / rapidfuzz 3.14.5 / langchain-google-genai 4.2.4
- Tier A judge: **불필요**(NonLLM, 할당량 0) · Tier B judge: **gemini-2.5-flash-lite**

## 4. 지표 표
### Tier A — 검색 품질 (NonLLM, 할당량 0)
| metric | mean | scored | skip |
|---|---|---|---|
| non_llm_context_recall | **0.917** | 12 | 0 |
| non_llm_context_precision_with_reference | **1.000** | 11 | 1 |

### 인용 라벨 정합성 (RAGAS 청크-단위 점수가 못 잡는 약점)
| | 값 |
|---|---|
| top1 doc_title 이 올바른 규칙을 가리킴 | **4 / 11 = 36.4%** |

### Tier B — 인용 충실/관련 (Gemini judge)
| metric | 상태 |
|---|---|
| faithfulness | **skip** — Gemini 429 RESOURCE_EXHAUSTED (할당량 소진) |
| answer_relevancy | **skip** — 동일 |

> 정직성: 할당량 소진은 가짜 점수로 채우지 않고 skip(사유)로 남김. 할당량 회복 후 위 1커맨드로 재산출.

## 5. 약점 사례 + 원인 (핵심 발견)
**증상**: 복잡도/메모리 이슈로 검색하면 인용 제목이 `4) N+1 쿼리 가이드 — PERF-002`로 뜨고, 테스트누락/엣지 이슈는 `1) 커버리지 가이드 — TEST-001`로 뜬다(= 오라벨).

**원인(실측)**: 6개 가이드가 적재 시 **2개의 과대 청크**로 묶였다.
- `3f4d6aca` = 커버리지(TEST-001) **+ 테스트누락(TEST-004) + 엣지(TEST-003)** 3섹션을 한 청크에. 라벨은 첫 섹션(`TEST-001`)만.
- `70ace3ef` = N+1(PERF-002) **+ 복잡도(PERF-001) + 메모리(PERF-003)** 3섹션을 한 청크에. 라벨은 `PERF-002`만.

그래서 small‑to‑big 인용 시:
- 정답 가이드 "본문"은 거의 항상 그 청크 안에 들어 있어 **recall 0.917**(=내용은 닿는다).
- 하지만 `doc_title`(인용 라벨)은 첫 섹션 것만 붙어 **4/6 규칙이 오라벨**, 한 인용에 무관한 2섹션(약 1500자)이 섞임 → 사용자가 "왜 N+1 이슈에 복잡도/메모리 얘기가?"를 겪는다.
- 추가로 `TEST-004-msg`("…테스트 실행 흔적이 없습니다")는 코사인 점수가 전부 0.5 미만이라 필터링되어 **빈 인용**(recall 0).

**왜 RAGAS 점수만 보면 안 되나**: NonLLM context precision/recall 은 *청크 단위* 문자열 유사도라, "그 청크가 정답 본문을 담고 있나?"는 잡지만(→ 1.0/0.917) "라벨이 맞나·과대 청크인가"는 **못 잡는다**. 그래서 결정적·할당량 0짜리 **인용 라벨 정합성(36%)** 지표를 따로 두어 약점을 드러냈다.

## 6. 권고 (다음 작업 — 본 세션 범위 밖)
1. **재청킹/재적재**: `conventions/*.md` 를 가이드(섹션)별로 분리 적재해 6개 가이드 = 6개(이상) 부모 청크 + 각자 올바른 `section_header`. → 오라벨·과대 청크 동시 해소.
2. **`source_url` 채우기**: 현재 전부 빈 문자열(가짜 링크 금지 정책의 부작용) — 적재 시 문서 URL 세팅.
3. (점수 임계) `TEST-004` 류 짧은 message 의 검색 점수 미달 → 쿼리 보강(rule 설명 결합) 검토.

## 7. 한계
- **Tier B(faithfulness/answer_relevancy)**: 오늘 Gemini 할당량 소진(429)으로 미산출 → skip. 할당량 회복 시 1커맨드 재산출(코드/평가셋 그대로).
- **NonLLM 지표의 청크-단위 한계**(위 §5) — LLM judge 변형이 의미 단위로 더 정확하나 할당량 필요.
- **정답 청크 결합(coupling)**: 평가셋의 reference 는 현재 DB 청크 본문 전체로 고정 → 재청킹하면 평가셋도 갱신 필요(meta.reference_chunk_map 으로 추적).
- **의존성 우회**: ragas 0.4.3 이 langchain 1.x(`langchain-community` 0.4.x)에서 `ChatVertexAI` 레거시 import 로 깨짐 → 미사용 Vertex placeholder shim 으로 우회(`_shim_langchain_vertexai`, 점수 무영향).

## 8. 검증
- `tests/test_rag_eval.py` 17개 + 전체 `tests/` **323개 green** (회귀 없음).
- 신규 의존성은 `[eval]` extra 로 격리(런타임 이미지·기존 `test` extra 불변), pydantic 2.13.4 유지(충돌 없음).
