# SESSION 5 — PR 코드리뷰 페이지 (분석 결과를 화면에 표시) (VS Code 복붙용)

> 목적: 지금 빈 껍데기인 **`frontend/src/pages/review/Placeholder.tsx`** 를 진짜 페이지로 만들어서,
> SESSION_4에서 저장한 **m3 분석 결과(판정·이슈·코멘트)** 를 사용자가 웹사이트에서 눈으로 본다.
> → 사용자 입장 플로우의 ① "PR 코드리뷰 페이지에 눈에 보이는 결과" 완성.

> 선행: **SESSION_4 완료**(m3 /review 저장 + GET 조회 API 존재)해야 페이지가 읽을 게 있음.

---

```
너는 우리 팀 시니어 프론트엔드 엔지니어다. 작업 디렉토리: C:\Users\user\Code-Shepherd\frontend
기존 패턴(React + lib/api.ts + TeamContext + AppLayout + MSW 테스트)을 따른다.

[데이터 출처]
- PR 목록: api-core 기존 엔드포인트 GET /teams/{teamId}/prs (프론트 /api 프록시로 이미 접근됨)
  → 각 PR: github_pr_number, author_login, status, is_lgtm, github_pr_url, submitted_at
- PR 상세(리뷰 결과): m3 GET /review/{owner}/{repo}/{pr_number} (SESSION_4에서 추가)
  → { verdict, comment, issues: [{severity,file,line,message,rule_id,suggestion}] }
  ※ m3는 8004 포트. 로컬에선 vite proxy에 m3 경로 추가해서 접근(예: '/m3-api' → http://localhost:8004).
    vite.config.ts 에 프록시 항목 추가(기존 /api 프록시 보존). 프로덕션 경로는 TODO 주석만.

[만들 것 — pages/review/ 의 실제 페이지]
1. PR 리스트(좌측/상단): 현재 팀의 PR 목록을 GET /teams/{teamId}/prs 로 불러와 표시
   (PR번호·작성자·status·제출시각, lgtm 여부 뱃지). TeamContext에서 현재 teamId 사용.
2. PR 선택 시 상세(우측/하단): m3 GET /review/... 호출해서
   - **판정 뱃지**: lgtm(초록)/rework(노랑)/escalate(빨강)
   - **이슈 테이블**: severity · file:line · rule_id · message · suggestion (severity별 색)
   - **LLM 코멘트**: comment 본문 렌더(마크다운이면 마크다운으로). "GitHub에서 보기" 링크(github_pr_url)
3. 로딩/빈상태/에러 상태 처리(결과 아직 없으면 "분석 결과 없음/처리 중" 안내, 가짜 데이터 금지).
4. 라우팅: App.tsx 의 review 라우트를 이 페이지로 연결(현재 Placeholder 대체). 사이드바 메뉴에서 진입되는지 확인.
5. lib/api.ts 에 호출 함수 추가(기존 fetch 래퍼 패턴 재사용): getTeamPRs(teamId), getReview(owner, repo, prNumber).

[TDD]
- MSW(test/msw/handlers.ts)에 두 엔드포인트 mock 추가.
- 컴포넌트 테스트: PR 목록 렌더 → PR 클릭 → 판정 뱃지·이슈 테이블·코멘트 렌더 검증, 빈/에러 상태 검증.
- 기존 프론트 테스트 green 유지(App/AppLayout/AuthGuard).

[지킬 것]
- 디자인은 기존 페이지(DashboardHome/Team) 톤과 맞춤. 과한 라이브러리 추가 금지.
- 데이터 없을 때 가짜로 채우지 말 것(정직한 빈/처리중 상태).
- 막히면 멈추고 물어봐라. 마지막에 [변경파일 / 테스트결과 / 스크린샷 또는 화면 설명] 정리.
```

---

## 참고 (사용자용 메모)
- 이게 끝나면 **웹사이트에서 PR을 클릭하면 m3 분석 결과(판정·이슈·코멘트)가 화면에 뜸** = 네 사용자 플로우 ①.
- 데이터는 SESSION_4가 저장한 걸 읽어오는 거라, **SESSION_4 먼저** 돌려야 함.
- PR 목록은 api-core(웹사이트 공용), 상세는 m3(네 결과) — 출처가 둘이라 페이지에서 합쳐 보여주는 구조.
- 로컬에선 vite 프록시로 m3(8004)에 접근. (배포 땐 라우팅 따로 — 지금은 로컬 데모 우선)
