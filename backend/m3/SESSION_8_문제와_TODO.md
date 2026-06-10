# SESSION 8 — 문제점 & 할 일 (8A~8E 종합)

> SESSION 8(성능평가 "제대로") 진행하면서 **정직하게 드러난 약점**과 **남은 작업**을 한곳에 모았다.
> 원칙: 약점을 숨기지 않는다. 각 항목 = [문제 / 영향 / 어디를 고치나 / 우선순위 / 출처].
> 발표자료 본문 = `발표자료_m3_PR코드리뷰.md`(§3-1b~f 실측표), 8D 상세 = `SESSION_8_결과_RAGAS.md`.

## 한눈에 (우선순위)
| # | 문제 | 분류 | 우선 | 어디를 고치나 |
|---|---|---|:--:|---|
| A1 | RAG 코퍼스 6가이드→**2 과대청크** → 인용 제목 4/6 오라벨 | 제품 약점 | **높음** | 적재(load_conventions) 재청킹 |
| A2 | `source_url` 전부 빈값(가짜 링크 금지의 부작용) | 제품 약점 | 높음 | 적재 시 문서 URL 세팅 |
| A3 | verdict 80% — `rework=Major 3건` 임계가 N+1·O(n³) 놓침 | 제품 약점 | 중 | settings 임계값 / severity 매핑 |
| A4 | TEST-004 짧은 message 검색 점수<0.5 → 빈 인용 | 제품 약점 | 중 | 검색 쿼리 보강 |
| A5 | TEST-003 휴리스틱 오탐(precision 0.833, 인자명만 보고 오판) | 제품 약점 | 중 | edge_cases 규칙 정교화 / LLM 모드 |
| A6 | RAG가 지연 병목(warm 7.7s·p95 22.5s, cold 210s) | 성능 | 중 | 캐시·타임아웃·예열 |
| B1 | **Gemini 무료쿼터 429**가 LLM 평가(8C·8D Tier B) 반복 차단 | 인프라 | **높음** | 유료키 or 쿼터 관리 |
| B2 | ragas 0.4.3 × langchain 1.x 비호환(Vertex shim 우회 중) | 인프라 | 낮음 | 버전 고정·업그레이드 추적 |
| C1 | 8D Tier B(faithfulness/answer_relevancy) 미산출 | 남은평가 | 중 | 쿼터 회복 후 1커맨드 |
| C2 | 8C LLM-judge 실채점 미산출 | 남은평가 | 중 | 쿼터 회복 후 1커맨드 |
| C3 | 8E LangSmith 통합 미착수 | 남은평가 | 중 | 캡스톤 세션 |
| D1 | /review→프론트 조회 DB가 로컬 SQLite | 미완 | 중 | GCP Postgres 전환 |
| D2 | dev4 공용 review_issue 라이브 GCP 쓰기 미검증 | 미완 | 중 | 중복적재·키 합의 후 |
| D3 | 숙련도(junior/mid/senior) 톤 조절 미적용 | 미완 | 낮음 | refine 적용 |

---

## A. 평가로 드러난 제품 약점 (고쳐야 할 것)

### A1. RAG 코퍼스가 6개 가이드를 2개 과대 청크로 적재 ★핵심
- **문제**: 사내 가이드 6개(커버리지·테스트누락·엣지·N+1·복잡도·메모리)가 DB `chunks`에 **단 2개의 과대 부모 청크**로 들어가 있다. ① `3f4d6aca` = 커버리지+테스트누락+엣지 (라벨 `TEST-001`만), ② `70ace3ef` = N+1+복잡도+메모리 (라벨 `PERF-002`만).
- **영향**: small-to-big 인용 시 정답 본문은 거의 닿지만(recall 0.917), **인용 제목(doc_title)이 6규칙 중 4규칙에서 틀린다**(인용 라벨 정합성 **36%**). 예: 메모리 이슈인데 인용 제목이 "N+1 가이드". 한 인용에 무관한 2섹션(~1500자)도 섞임.
- **어디를 고치나**: **검색 코드 아님 — 적재(`rag/load_conventions.py` + 재적재)**. `conventions/*.md`를 가이드(섹션)별로 분리해 6개+ 부모 청크로, 각자 올바른 `section_header`로 적재.
- **검증**: 재적재 후 `uv run --extra eval python validation/rag_eval.py` → 인용 라벨 정합성이 36%→100% 근처로 오르는지. (평가셋 `reference_chunk_id`도 새 청크로 갱신 필요 — `rag_evalset.json` meta.reference_chunk_map)
- **출처**: SESSION 8D, 발표자료 §3-1f / `SESSION_8_결과_RAGAS.md`.

### A2. source_url 전부 빈값
- **문제**: 인용에 출처 링크가 없음(전부 `""`). "가짜 링크 금지" 정책상 비우는 게 맞지만, **애초에 URL이 적재 안 됨**.
- **영향**: 코멘트·화면의 "📖 사내 규칙" 칸에 제목만 있고 클릭 링크 없음.
- **어디를 고치나**: 적재 시 `documents.source_url` 채우기(A1 재청킹과 함께).
- **출처**: 8D, `m3-rag-live-verified` 메모.

### A3. verdict 임계값이 현실 PR을 놓침 (정확도 80%)
- **문제**: 사람 기대 vs `aggregate()` 산출 verdict 일치율 **8/10**. 불일치 2건은 N+1·O(n³)(둘 다 Major)뿐인 PR이 `lgtm`으로 통과. 원인 = **m3는 Critical을 안 만들고(전부 Major/Minor)**, `rework` 임계가 **Major 3건**이라 Major 1~2건짜리 실제 결함 PR이 통과.
- **어디를 고치나**: `config/settings.py`의 `MAJOR_REWORK_THRESHOLD` 하향(예 3→2) **또는** PERF-002/PERF-001(deep)를 escalate로 승격하는 severity 매핑. (트레이드오프: 너무 낮추면 과민)
- **출처**: SESSION 8C, 발표자료 §3-1d (`validation/verdict_benchmark.py`).

### A4. escalate는 m3 단독 불가 (설계상 한계)
- **문제**: m3 6탐지기는 Critical을 생성하지 않아, `escalate`(Critical ≥1)는 **M2(정적/보안)의 Critical로만** 도달.
- **영향**: m3만 보면 escalate가 절대 안 뜸. 통합 경로에선 정상이나, 단독 데모 시 오해 소지.
- **어디를 고치나**: (선택) 심각한 PERF/보안성 이슈를 Critical로 승격할지 정책 결정. 안 바꾸면 "교차모듈 설계"로 발표에 명시.
- **출처**: 8C, §3-1d.

### A5. TEST-004 짧은 message → 검색 점수 미달 → 빈 인용
- **문제**: "함수 'create_order'에 대한 테스트 실행 흔적이 없습니다" 같은 짧은 message는 코사인 점수가 `RAG_SCORE_MIN`(0.5) 미만이라 전부 필터→빈 인용(8D에서 1건 발생, recall 0).
- **어디를 고치나**: 검색 쿼리에 rule 설명/키워드를 결합해 보강, 또는 rule별 임계 차등.
- **출처**: 8D, §3-1f (TEST-004-msg 케이스).

### A6. TEST-003 휴리스틱 오탐
- **문제**: 엣지케이스 *이미 처리*한 코드인데 **인자명(price·rate)만 보고** 누락으로 오판 → precision 0.833.
- **어디를 고치나**: edge_cases 휴리스틱 정교화(검증 코드 존재 여부 확인) 또는 실 운영 LLM 모드.
- **출처**: SESSION 8B, §3-1c.

### A7. RAG가 지연 병목
- **문제**: 순수 탐지기 6개는 p50 200ms 이하인데, **RAG(실 GCP pgvector+BGE-M3)**가 warm p50 7.7s·p95 22.5s, cold 210s(모델 로딩 1회성).
- **어디를 고치나**: HF 캐시 볼륨(완료)·임베딩 결과 캐시·GCP 근접/풀링·RAG 타임아웃 가드.
- **출처**: SESSION 8A, §3-1b.

---

## B. 평가 인프라 / 쿼터 이슈

### B1. Gemini 무료쿼터 429가 LLM 평가를 반복 차단 ★
- **문제**: 8C(코멘트 LLM-judge)·8D(RAG Tier B faithfulness/relevancy) 둘 다 실행 시 `429 RESOURCE_EXHAUSTED`로 막힘. flash-lite도 일일 한도 작음.
- **영향**: LLM 의존 평가는 "코드·채점기는 검증됐으나 실 점수는 정직 skip" 상태. (가짜 점수 안 만듦)
- **대응**: ① 유료 키 or 별도 쿼터 프로젝트, ② 쿼터 회복(매일 자정 PT≈한국 17시 리셋) 후 1커맨드 재실행(C1·C2), ③ `JUDGE_MAX_CASES`/`max_workers=1` 등 호출 절약 모드 이미 구비.
- **출처**: 8C §3-1e, 8D §3-1f, `m3-gemini-free-tier-quota` 메모.

### B2. ragas 0.4.3 × langchain 1.x 비호환 (shim 우회 중)
- **문제**: ragas 0.4.3이 `langchain_community.chat_models.vertexai.ChatVertexAI`를 모듈 로드 시 import하는데 langchain-community 0.4.x엔 없음.
- **대응**: 미사용 Vertex placeholder shim(`validation/rag_eval.py:_shim_langchain_vertexai`)으로 우회(점수 무영향). ragas 신버전 나오면 shim 제거 검토.
- **출처**: 8D.

### B3. 평가셋 표본 작음
- **문제**: 8B 5건·8C 10건·8D 12건 — 추세·약점 식별엔 충분하나 통계적 유의성은 낮음.
- **대응**: 라벨셋 점진 확장(사람 라벨 유지, 순환 금지). LangSmith Dataset(8E)에 누적하면 자연 확장.

---

## C. 남은 평가 작업

### C1. 8D Tier B 재산출 (쿼터 회복 후)
```bash
docker compose exec m3 sh -c 'cd /app/service/test-performance-agent && uv run --extra eval python validation/rag_eval.py'
```
→ faithfulness/answer_relevancy 칸이 채워짐(`validation/rag_eval_report.md`). 코드·평가셋 변경 불필요.

### C2. 8C LLM-judge 실채점 재산출 (쿼터 회복 후)
```bash
docker compose exec m3 sh -lc 'cd /app/service/pr-comment-agent && \
  LLM_MODEL=gemini-2.5-flash-lite JUDGE_MAX_CASES=5 uv run python validation/comment_judge.py'
```
→ 루브릭 4축 평균 + 케이스별 점수(`validation/comment_judge_report.md`).

### C3. 8E LangSmith 통합 (마지막 캡스톤)
- **할 일**: 8B/8C/8D 평가셋→Dataset, m3 실행→Experiment, 기존 채점기→Evaluator로 래핑(복붙·재구현 금지, 함수 그대로 호출). 대시보드에서 회귀 추적.
- **선행**: `LANGCHAIN_API_KEY`/`LANGCHAIN_PROJECT`(.env). 없으면 정직 skip. langsmith 이미 설치됨.
- **착수 가능**: 8B 채점기 이미 존재 → 탐지 P/R/F1부터 올리고 8C/8D 추가.
- **출처**: `SESSION_8E_LangSmith_통합평가.md`.

---

## D. 기존 미완 (제품, SESSION 8 이전부터)
- **D1. /review→프론트 조회 DB**: 웹훅 경로는 이미 GCP Postgres 저장이나, `/review` API의 프론트 조회용은 **로컬 SQLite** → 운영 시 GCP 전환.
- **D2. dev4 공용 review_issue 라이브 쓰기**: 코드·테스트 완료(컬럼 매핑·서브쿼리). 실 GCP 라이브 쓰기는 중복적재 방지·키 합의 후 검증. (`session6-review-issue-done` 메모)
- **D3. 숙련도 톤 조절**: junior/mid/senior 코멘트 톤 조절 — 코드 구조 있음, 적용 전.

---

> 작성 2026-06-10. SESSION 8A~8D 실측 + 8E 계획 기준. 항목별 "어디를 고치나"는 코드/적재/설정 위치를 가리킴.
> **가장 임팩트 큰 1건**: A1(RAG 재청킹) — 검색기는 멀쩡하니 **적재만 고치면** 인용 라벨 36%→대폭 개선 + A2(source_url) 동시 해결.
