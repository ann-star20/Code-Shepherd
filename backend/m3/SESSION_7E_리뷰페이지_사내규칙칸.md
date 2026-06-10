# SESSION 7E — 리뷰 페이지에 📖 사내 규칙(RAG) 칸 추가 (VS Code 복붙용)

> 목적: `ReviewPage` 이슈 테이블에 **`rag_context`(사내 규칙 인용) 칸**을 추가해 **RAG가 페이지에도 보이게** 한다.
> (백엔드는 이미 `rag_context` 를 `GET /review` 로 돌려준다 — 프론트가 안 읽던 것뿐.)

> 범위: **프론트 한 곳** — `frontend/src/pages/review/ReviewPage.tsx`(`ReviewIssue` 인터페이스 + 이슈 테이블) + 테스트 `frontend/src/test/ReviewPage.test.tsx`. 백엔드 변경 없음.

> 선행: **7B**(값이 실제로 채워짐). 단, UI는 mock 데이터로 **독립 구현·테스트 가능**(값 없으면 칸은 `—`).

## 배경 (왜 UI만 고치면 되나 — 확인됨)
- `persist.save_review(... issues=combined ...)` 가 `combined`(=`rag_context` 포함)를 통째 JSON 으로 저장하고, `get_review` 가 그대로 반환한다(`persist.py`).
- 그런데 `ReviewPage.tsx` 의 `interface ReviewIssue` 에 `rag_context` 필드가 없어서, 받아도 표에 안 그린다. → **필드 추가 + 칸 추가**면 끝.

---

```
너는 우리 팀 프론트엔드 엔지니어다. 작업 디렉토리: C:\Users\user\Code-Shepherd\frontend
테스트(vitest): npm run test   (또는: npx vitest run src/test/ReviewPage.test.tsx)

[작업 방식]
- 테스트부터(기존 src/test/ReviewPage.test.tsx 패턴 따라). 네트워크/React Query 는 기존 방식대로 mock.
- 칸 위치·스타일은 기존 이슈 테이블(심각도/위치/규칙/설명·제안)의 톤(notion 스타일 토큰)에 맞춰 네가 깔끔하게.

[배경/문제]
ReviewPage 의 이슈 테이블은 심각도|위치|규칙|설명·제안 만 보여준다. 백엔드 GET /review 는 이슈마다
rag_context(검색된 사내 규칙 인용)를 같이 주는데, 프론트 interface ReviewIssue 에 그 필드가 없어 표시되지 않는다.

[목표]
1) interface ReviewIssue 에 rag_context?: string (그리고 출처가 있으면 source_url?: string) 추가.
   - 참고: 백엔드가 주는 issue dict 키 확인(rag_context 는 확정, 링크 키는 retriever 매핑에 따름 — 없으면 텍스트만).
2) 이슈 테이블에 '📖 사내 규칙' 칸 추가:
   - rag_context 있으면 인용 텍스트 표시(출처 링크 있으면 링크로, 없으면 텍스트만).
   - 비어 있으면 '—'.
3) 기존 칸/스타일/정직한 빈·로딩·에러 상태는 그대로 유지.

[반드시 지킬 것 — 합격 기준]
- 가짜 데이터/가짜 링크 금지 — rag_context 없으면 '—', source_url 없으면 링크 만들지 않음(텍스트만).
- 기존 data-testid·동작 회귀 0(review-issues, issue-row-* 등 유지). 새 칸엔 식별용 testid 부여.
- 값이 길 수 있으니 셀 줄바꿈/말줄임 등 레이아웃 안 깨지게.

[TDD]
- 기존 ReviewPage.test.tsx 의 mock review 이슈에 rag_context(+source_url) 넣어 → 칸에 인용/링크가 뜨는지.
- rag_context 없는 이슈 → '—' 표시.
- 회귀: 기존 테스트 green.

[끝나면]
- [변경 파일 / 테스트 결과 / 칸 렌더 모습(설명 또는 스크린샷)] 정리.
- (선택) '자동 리뷰 코멘트' 섹션은 지금 원문(raw)으로 렌더 → 7C 로 코멘트가 표 형태가 되면 파이프(|)가 보일 수 있음.
  마크다운으로 예쁘게 렌더하거나, 'GitHub 게시 원문'으로 라벨만 바꾸는 것도 고려(이번 필수는 아님).
- 막히면 멈추고 물어봐라.
```

---

## 참고 (사용자용 메모)
- 백엔드는 **이미 사내 규칙을 페이지로 보내고 있어요** — 페이지가 안 읽던 것뿐. **칸 하나** 추가가 전부.
- **7B 끝나면** 값이 채워져서 페이지에도 **자동으로 📖가 뜸**. (7E는 그걸 그릴 자리만 만드는 것)
- 프론트라 **FE 담당이 따로 있으면** 한 마디 하고 진행해요(겹침 방지). 이 페이지는 m3 리뷰 화면이라 보통 우리 쪽.
