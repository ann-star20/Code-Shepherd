# SESSION 7C — 코멘트를 "리뷰 판정" 모양으로 렌더 (VS Code 복붙용)

> 목적: PR 코멘트 마크다운을 **확정한 리뷰-앵글**로 바꾼다.
> 판정+이유 / 이슈표(`심각도·규칙·file:line·고칠방향·📖사내규칙`) / 📊지표 한 줄(있으면) / 내 리뷰 페이지 링크.
> **개념설명·Before/After 코드·학습추천은 넣지 않는다** — 그건 dev4 커리큘럼 페이지 몫(겹치면 안 됨).

> 범위: **m3 한 곳** — `pr-comment-agent/llm_refiner.py`(`_build_prompt`·`_heuristic_refine`·`_issue_to_line`·`_build_header`) + 그 테스트(`pr-comment-agent/tests/`).

> 선행: **7B**(rag_context 가 채워져 들어옴). 후속: (선택) **7D**(지표 줄).

## 확정된 코멘트 모양 (이대로)
```
## 🤖 코드 리뷰 — `rework` ❌ (머지 보류)
왜 보류: Major 1건이 기준을 넘었어요.

| | 규칙 | 위치 | 고칠 방향 | 사내 규칙 |
|---|---|---|---|---|
| 🟡 | PERF-001 | src/posts.py:18 | 반복 쿼리 → 벌크 조회 | 📖 [DB접근 §3.2](링크) |
| 🔵 | TEST-001 | src/posts.py | 테스트 추가 | — |

📊 커버리지 62% · 최대 복잡도 14   ← (지표는 7D, 지금은 없으면 생략)
→ 전체 현황: [m3 리뷰 대시보드 열기](링크)
```

---

```
너는 우리 팀 시니어 백엔드 엔지니어다. 작업 디렉토리: C:\Users\user\Code-Shepherd\backend\m3
테스트는 m3 가상환경 python으로: .venv\Scripts\python.exe -m pytest pr-comment-agent/tests -q
(python.exe 는 Store 스텁이라 직접 호출 금지)

[작업 방식]
- tdd-workflow 스킬로 테스트부터(TDD는 항상). LLM 호출은 mock(_call_llm), 실제 Gemini 안 부른다.
- '어떻게'(프롬프트 문구·표 생성 헬퍼)는 코드를 읽고 네가 깔끔하게 설계해라. 아래는 '무엇/제약'이다.

[배경/문제]
llm_refiner.refine() 은 LLM 모드(_build_prompt→_call_llm)와 휴리스틱 모드(_heuristic_refine) 둘 다 코멘트 markdown 을
만든다. 지금은 이슈를 '### 제목 + 본문 + 💡제안' 나열식으로 낸다. 이걸 '리뷰 판정 + 이슈 표' 모양으로 바꾼다.

[목표]
LLM 모드와 휴리스틱 모드 '둘 다' 위 '확정된 코멘트 모양'으로 출력:
1) 헤더: 🤖 코드 리뷰 — verdict + 왜(한 줄) + severity 카운트
2) 이슈 표: | 심각도이모지 | rule_id | file:line | 고칠 방향(=suggestion) | 사내 규칙(rag_context 있으면 인용+링크, 없으면 —) |
3) 맨 아래: 리뷰 대시보드 링크 한 줄
개념 설명/코드 스니펫/학습 추천은 '넣지 않는다'(dev4 영역).

[반드시 지킬 것 — 합격 기준]
- LLM 실패·쿼터(429)로 휴리스틱 fallback 돼도 '같은 구조(표·📖 포함)' 가 나온다.
- rag_context 의 source_url 이 없으면 텍스트만(가짜 링크 금지).
- 이슈 0건 → 기존 '리뷰 통과 ✅' 메시지 유지.
- refine() 시그니처(issues, verdict, skill_level) 와 '항상 markdown string 반환' 계약 유지.
- 페이지 링크 URL은 환경값/플레이스홀더로(데모=localhost) — 하드코딩 가짜 도메인 금지.

[TDD]
- mock CombinedIssue 로: ① rag_context 있는 이슈 → 표 '사내 규칙' 칸에 인용 들어감 ② 없는 이슈 → '—' 
  ③ 휴리스틱 경로(키 없음)도 표/📖 구조 유지 ④ verdict 별 헤더.
- 기존 pr-comment-agent 코멘트 테스트가 옛 모양에 의존하면 새 모양으로 고치되 '무엇을 검증하는지'는 보존.

[끝나면]
- [변경 파일 / 테스트 결과 / 렌더된 코멘트 예시 1개] 정리.
- 막히면 멈추고 물어봐라.
```

---

## 참고 (사용자용 메모)
- 바뀌는 건 코멘트 **"모양"** 하나(파일 1개, llm_refiner).
- 핵심: **dev4 학습 페이지랑 안 겹치게** — 우린 판정/규칙/위치/고칠방향/📖/링크만.
- Gemini 무료라 됐다 안 됐다 해도 OK — **LLM 죽으면 휴리스틱이 같은 표를** 냄.
