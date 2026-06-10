# SESSION 7A — RAG 검색기를 진짜 chunks(parent-child)로 교체 (VS Code 복붙용)

> 목적: m3 RAG 검색을 **목업 `convention_embeddings` → 진짜 `chunk_embeddings`+`chunks`(parent-child)** 로 바꾼다.
> 잘게 쪼갠 **child로 정밀 매칭** → 그 child의 **parent 본문을 통째로 인용**으로 반환(small-to-big).

> 범위: **m3 한 곳** — `test-performance-agent/rag/retriever.py` + 그 테스트 `tests/test_retriever.py`.
> (`store.py`의 `to_vector_literal` 재사용 가능.) **`search_convention(query_text, top_k)` 시그니처·반환형 유지** → 소비처(`augment`·`llm_refiner`) 무수정.

> 선행: 없음. 후속: **7B**(이 검색 결과를 /review 코멘트에 채움).

## 배경 (확인된 사실)
- 진짜 데이터: 공유 GCP DB(`34.22.101.111`, `POSTGRES_URL`은 `.env`, m3 컨테이너에서 닿음 — 읽기전용 확인).
  - `chunks`(child 58 + parent 19): `chunk_id`, `parent_chunk_id`(자기참조), `chunk_type`('parent'|'child'), `content`, `section_header`, `doc_id`
  - `chunk_embeddings`(57행): `chunk_id`, `embedding vector(1024)`, `model_name='bge-m3'`, `content`
  - ⚠️ `docs/ddl.md`의 `vector(2000)`은 **옛 계획(틀림)**. 실제 1024 bge-m3 = **m3 임베더와 동일** → 모델·차원 변경 **없음**.

---

```
너는 우리 팀 시니어 백엔드 엔지니어다. 작업 디렉토리: C:\Users\user\Code-Shepherd\backend\m3
테스트는 m3 가상환경 python으로: .venv\Scripts\python.exe -m pytest test-performance-agent/tests/test_retriever.py -q
(python.exe 는 Store 스텁이라 직접 호출 금지)

[작업 방식]
- tdd-workflow 스킬로 테스트부터(TDD는 항상). DB는 mock 한다(실제 GCP 안 붙인다).
- '어떻게'(쿼리 구조·join 방식)는 정해주지 않는다. 현재 retriever.py 를 읽고 가장 깔끔하게 네가 설계해라.
- 막히면 systematic-debugging / verification-before-completion 스킬 활용 가능.

[배경/문제]
지금 search_convention() 은 목업 테이블 convention_embeddings 를 코사인 검색한다.
진짜 사내규칙은 chunks / chunk_embeddings 에 parent-child 로 들어있다(위 배경 참고). 임베딩 모델은
양쪽 다 bge-m3(1024)라 m3 임베더(embedder.embed)는 그대로 쓴다.

[목표]
search_convention(query_text, top_k) 가:
1) query_text 를 bge-m3 로 임베딩(기존 embedder 재사용),
2) chunk_embeddings 를 코사인 검색해 가장 가까운 child 청크를 찾고,
3) 그 child 의 chunks.parent_chunk_id 로 부모 청크의 content(+section_header)를 인용으로 반환한다.
   (부모가 없으면 child 본문으로 fallback.)
반환형은 기존 소비처가 읽는 dict 리스트 형태를 유지한다([{content, doc_title, source_url, score}, ...]).
 - content = 인용으로 쓸 본문(부모 본문)
 - doc_title = section_header 또는 documents.title 에서 적절히 매핑
 - source_url = 있으면 채우고, 없으면 빈 문자열(가짜 링크 절대 금지)
 - score = 1 - 코사인거리

[반드시 지킬 것 — 합격 기준]
- SQL 은 파라미터 바인딩만(f-string SQL 금지).
- DB 미설정(POSTGRES_URL 없음)/연결 실패/모델 실패/예외 → 빈 리스트(가짜 인용 지어내지 않음).
- score < RAG_SCORE_MIN 결과 제거(기존 환각 방지 규칙 유지).
- 시그니처·반환 dict 키는 그대로 → augment·llm_refiner 안 고쳐도 동작.

[TDD]
- 기존 test_retriever.py 가 _connect / cursor 를 mock 하는 방식을 재사용한다.
- 신규 최소: ① child 매칭 → 부모 본문 반환 ② 부모 없으면 child fallback ③ DB None → [] ④ score 컷.
- 위는 최소선. 경계(여러 child, parent_chunk_id NULL, 빈 결과 등)는 더 생각해서 테스트.

[끝나면]
- [변경 파일 / 테스트 결과] 정리.
- (선택·수동) POSTGRES_URL 이 진짜 DB면: N+1 이슈 메시지로 한 번 호출 → 네이밍 말고 N+1/복잡도 규칙 chunk 가 top 인지 눈으로 확인(= RAG sanity).
- 막히면 멈추고 물어봐라.
```

---

## 참고 (사용자용 메모)
- 바뀌는 건 **"RAG가 어느 표를 뒤지냐" + "정밀하게 찾고 통째로 인용"** 두 가지. 파일은 **retriever 1개**.
- 모델·차원·키 **안 바뀜**(bge-m3 그대로) — 그래서 작아요.
- 이거 혼자선 코멘트에 아직 안 보여요. **7B**까지 해야 📖가 코멘트에 떠요.
