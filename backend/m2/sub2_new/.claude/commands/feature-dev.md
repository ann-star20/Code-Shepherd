---
description: 새 기능 개발 워크플로우. 현재 상태 파악 → 최소 변경 구현 → 테스트 → 요약 순서로 진행합니다.
---

새 기능을 개발할 때 아래 순서로 진행합니다:

1. **현재 상태 파악** — 관련 파일 읽기, 기존 패턴 확인
2. **계획** — planner 에이전트로 구현 단계 정리
3. **테스트 먼저** — tdd-guide 기준으로 테스트 파일 작성
4. **최소 구현** — 테스트를 통과하는 가장 작은 코드
5. **리뷰** — code-reviewer, typescript-reviewer, security-reviewer 순으로 체크
6. **커밋** — commit-rules 형식으로 커밋

**사용법**:
- `/feature-dev [기능명]` — 기능 개발 시작
- 예: `/feature-dev 위클리 플래너 체크리스트`
- 예: `/feature-dev planner-agent LangChain 연동`
