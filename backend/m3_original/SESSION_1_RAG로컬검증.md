# SESSION 1 — RAG 로컬 적재·검색 검증 (VS Code 클로드코드 복붙용)

> 아래 블록을 통째로 VS Code 클로드코드 새 세션에 붙여넣어 실행하세요.
> 목적: 컨벤션 6종을 로컬 pgvector에 임베딩 적재하고, `search_convention()`이 관련 문서를 실제로 돌려주는지 검증. (KMS가 나중에 같은 테이블을 채우면 코드 변경 없이 그대로 동작)

---

```
너는 우리 팀 시니어 백엔드 엔지니어다. 작업 디렉토리: C:\Users\user\Code-Shepherd\backend\m3\test-performance-agent

[배경]
- 이 폴더의 RAG는 "B안 자급자족": 컨벤션 문서를 BGE-M3(1024차원)로 임베딩해 GCP/로컬 Postgres의
  convention_embeddings 테이블에 넣고, 런타임에 이슈 message를 같은 모델로 임베딩해 pgvector 코사인 검색한다.
- 관련 코드는 이미 구현돼 있다: rag/embedder.py(embed), rag/store.py(DDL·벡터리터럴),
  rag/load_conventions.py(문서→청크→embed→INSERT, __main__ 제공), rag/retriever.py(search_convention).
- 컨벤션 문서 6종이 conventions/ 에 있다(01~06). 01·05는 맨 위 YAML 프론트매터에 숫자 정책이 있는데,
  load_conventions가 프론트매터(정책)는 떼어 convention_policies로, 본문 산문만 임베딩한다.
- 절대규칙: 저장=검색 임베딩 모델 동일(BGE-M3). embed()는 rag/embedder.py 한 곳만 쓴다.

[해줄 일 — 순서대로, 각 단계 결과를 보고]
1. 로컬 pgvector 준비:
   - 루트(C:\Users\user\Code-Shepherd)의 docker-compose.yml에 pgvector 가능한 Postgres 서비스가 있는지 확인.
   - 없으면 로컬 검증용으로 pgvector/pgvector:pg16 컨테이너를 5432로 띄우는 방법을 제시(기존 DB와 포트 충돌 주의).
   - test-performance-agent/.env(또는 환경변수)에 POSTGRES_URL을 설정. persist._pg_url()이 무엇을 읽는지 먼저 확인하고 그 이름에 맞춰라.
2. 적재 실행: `python -m rag.load_conventions`
   - 첫 실행이면 BGE-M3(~2GB) 다운로드로 수 분 걸릴 수 있음(정상).
   - 스크립트가 테이블 생성 + 전체 새로고침(DELETE 후 재적재)까지 한다. "적재 완료: N청크, 총 M행" 로그 확인.
3. 검색 검증(짧은 파이썬 스니펫 실행):
   - from rag.retriever import search_convention
   - search_convention("테스트 라인 커버리지 26.7% < 기준 80%")  → 커버리지 가이드가 score≥0.5로 상위에 오는지
   - search_convention("N+1 쿼리: 루프 안에서 DB 호출이 반복됩니다")  → N+1 가이드가 오는지
   - search_convention("중첩 루프로 O(n^2) 시간복잡도")  → 복잡도 가이드가 오는지
   - 각 호출의 doc_title·score를 출력해 사람이 눈으로 확인.
4. 단위테스트 green 확인:
   - pytest tests/test_retriever.py tests/test_load_conventions.py tests/test_convention_store.py
   - 이 테스트들은 모델·DB를 Mock으로 고립하므로 컨테이너 없이도 돌아야 한다.

[지킬 것]
- 코드 로직을 함부로 바꾸지 마라. 환경/설정(.env, 포트) 외에 소스 수정이 필요하면 먼저 이유를 말하고 멈춰서 물어봐라.
- 막히면(모델 다운로드 실패, 연결 실패 등) 추측으로 우회하지 말고 정확한 에러와 원인을 보고하라.
- 마지막에 표로 요약: [단계 / 명령 / 결과(OK·FAIL) / 비고].
```

---

## 참고 (사용자용 메모)
- 이 검증이 통과하면 RAG는 "내 로컬 임베딩"으로 완전 동작. 이후 KMS가 동일 `convention_embeddings` 테이블에 적재만 하면 **retriever 코드 변경 없이** KMS 데이터를 검색하게 됨.
- 실제 분석 파이프라인에서 RAG를 켜려면 환경변수 `RAG_ENABLED=1` (없으면 평소엔 RAG 비활성 — `main.py` 참고).
