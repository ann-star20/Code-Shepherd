---
description: 오늘의 학습 계획을 세웁니다. ADHD 친화적 마이크로태스크로 분해하고, 에빙하우스 복습 주기를 반영합니다.
---

planner-agent를 호출해서 다음을 수행합니다:

1. 오늘 공부할 주제를 묻습니다
2. 가용 시간을 확인합니다
3. ADHD 친화적 마이크로태스크로 분해합니다
4. 오늘 복습이 필요한 항목을 체크합니다
5. 우선순위와 시간 배분을 포함한 하루 계획을 생성합니다

**사용법**:
- `/plan` — 오늘 계획 세우기
- `/plan [주제]` — 특정 주제 계획 세우기
- `/plan cert [자격증명]` — 자격증 공부 계획
- `/plan project` — 3rd-Project-sub2 프로젝트 작업 계획

---

## `/plan project` 실행 시 참조 문서

`/plan project` 호출 시 아래 순서로 문서를 읽고 오늘 작업할 Task를 결정합니다:

1. `docs/plans/making_implementation.md` 읽기
   - 전체 태스크 맵에서 미완료 Task 확인 (완료/대체 표시된 Task는 건너뜀)
   - 오늘 집중할 Task 1~2개 선정

2. `docs/plans/2026-04-30-3rd-project-sub2-design.md` 참조
   - 선정된 Task의 기능 목적·범위 확인

3. 3rd-Project 규칙 확인 (프론트엔드·백엔드 작업 시)
   - 백엔드: `backend/sub2/src/` — FastAPI, HS256 JWT, 클린 아키텍처
   - 프론트엔드: `frontend/src/` — React 18, TypeScript, Vite (3rd-Project 공용)
   - Task 10 계열은 3rd-Project `frontend/`에 작업

4. 오늘 계획 출력 형식:

```
오늘의 3rd-Project-sub2 작업 계획

집중 Task: [Task 번호 + 이름]
예상 소요: [시간]

마이크로태스크 (25분 단위):
  [ ] 1. ...
  [ ] 2. ...
  [ ] 3. ...

완료 기준: [이 Task가 끝났다고 볼 수 있는 조건]
참고 문서: implementation.md [Task 번호] 섹션
```

> 새 기능·컴포넌트·API가 추가됐다면 작업 후 `/update-docs [내용]` 실행
