# SESSION 7B — /review에서 RAG 인용(rag_context) 채우기 (VS Code 복붙용)

> 목적: m3 `/review` 가 코멘트를 만들 때, **합쳐진 이슈의 message로 사내규칙을 검색(7A 검색기)** 해
> 각 이슈의 `rag_context` 를 채운다. → 코멘트에 **📖 사내 가이드**가 뜨게.

> 범위: **m3 한 곳** — `app/main.py` 의 `/review` 경로(`_review_aggregate` ~ `_review_refine` 사이) + 그 테스트(`tests/test_review_endpoint.py`). **공유 계약(IssueItem·M3VerifyResponse)은 안 건드린다.**

> 선행: **7A**(검색기가 진짜 테이블을 보게 된 뒤). 후속: **7C**(채워진 rag_context 를 코멘트에 예쁘게 렌더).

## 배경 (왜 이렇게)
- 지금 `rag_context` 는 m3 `/verify`→`/review` 의 **IssueItem 경계에서 버려지고**, `RAG_ENABLED` 도 기본 꺼짐 → 코멘트에 📖 안 뜸.
- 가장 깔끔한 해법: **공유 계약을 늘리지 말고**, `/review` 가 이미 들고 있는 합쳐진 이슈의 `message` 로 `search_convention` 을 그 자리에서 호출해 `rag_context` 를 채운다. (검색은 message만 있으면 됨 → 계약 변경 0, 다른 모듈 영향 0)

---

```
너는 우리 팀 시니어 백엔드 엔지니어다. 작업 디렉토리: C:\Users\user\Code-Shepherd\backend\m3
테스트는 m3 가상환경 python으로: .venv\Scripts\python.exe -m pytest tests/test_review_endpoint.py -q
(python.exe 는 Store 스텁이라 직접 호출 금지 / 테스트 안 잡히면 tests/conftest.py·경로 확인)

[작업 방식]
- tdd-workflow 스킬로 테스트부터(TDD는 항상). 검색기(search_convention)는 mock 한다(실제 GCP 안 붙인다).
- '어떻게'(어느 함수에서 채울지)는 코드를 읽고 네가 가장 깔끔하게 정해라.
- 막히면 systematic-debugging / verification-before-completion 스킬 활용 가능.

[배경/문제]
app/main.py 의 /review 는 4개 결과를 모아 aggregate → llm_refiner.refine 으로 코멘트를 만든다.
그런데 거기로 오는 이슈에는 rag_context 가 비어 있다(상류 경계에서 버려짐). 그래서 코멘트에 사내 가이드(📖)가 안 붙는다.

[목표]
/review 가 코멘트를 만들기 '직전'에, 합쳐진(combined) 이슈마다 그 이슈의 message 로
test-performance-agent 의 rag 검색(search_convention)을 호출해 rag_context 를 채운다.
- 검색기/augment 는 7A 에서 고친 것을 재사용한다(retriever 로직 중복 구현 금지).
- 그렇게 채운 rag_context 가 llm_refiner.refine 입력까지 전달되면 끝(렌더 모양은 7C 담당).

[반드시 지킬 것 — 합격 기준]
- 공유 계약(IssueItem / M3VerifyResponse) 변경하지 않는다(이번 범위 안에서 해결).
- RAG_ENABLED/키 없음·DB 실패·검색 예외 → 정직하게 '빈 인용'으로 스킵(가짜 인용 금지). /review 는 그대로 200.
- 기존 /review 동작(판정·GitHub 게시·DB 저장) 회귀 0 — rag_context 만 추가로 채운다.
- 동명 모듈 import 격리(_TP/_PRC sys.path) 패턴이 깨지지 않게 주의.

[TDD]
- search_convention 을 mock(가짜 사내규칙 반환) → 그 rag_context 가 refine 입력 이슈에 실려가는지 검증.
- 검색이 빈 결과/예외일 때 → rag_context 빈 채로, /review 정상(200) 검증.
- 기존 test_review_endpoint.py 회귀 green 유지.

[끝나면]
- [변경 파일 / 테스트 결과] 정리.
- (선택·수동) 진짜 PR 한 번 → 코멘트에 📖 가 뜨는지(7C 전이라 모양은 거칠어도 OK).
- 막히면 멈추고 물어봐라.
```

---

## 참고 (사용자용 메모)
- 바뀌는 건 **"코멘트 만들기 직전에 사내규칙을 한 번 검색해서 붙이기"** 하나.
- **공유 계약을 안 건드려서** 다른 모듈(팀원들)한테 영향 0 — 그래서 알림/협의 필요 없음.
- 7A(검색기) + 7B(여기) 까지 하면 **드디어 코멘트에 📖가 뜸**. 모양 다듬기는 7C.
- 보너스: `combined` 에 채우면 `persist.save_review` → `get_review` 가 그대로 돌려줘서 **리뷰 페이지(7E)에도 📖가 자동으로** 뜸(프론트는 칸만 추가하면 됨). → `rag_context` 는 refine(코멘트)·persist(페이지) 둘 다 쓰는 `combined` 에 채울 것.
