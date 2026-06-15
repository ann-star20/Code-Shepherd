# pr-comment-agent TASKS — 코드 리뷰 종합 + LLM 코멘트 작성

> 스코프: M2+M3 결과 합쳐서 verdict 판정 → 개인화 LLM 코멘트 생성 → GitHub PR 등록.
> Slack/KMS-RAG/DB저장은 스코프 밖 (필요시 추후 확장).

## Task B1. contracts.py
- **모델**: `CombinedIssue`, `Verdict` (Literal lgtm/rework/escalate), 
  `ReviewReport` (verdict, summary, comment_md, escalation_needed)
- **Red 테스트**:
  - ReviewReport 정상 생성
  - verdict 잘못된 값 → ValidationError
  - summary 카운트 자동 계산
- **완료기준**: 4+ PASS

## Task B2. config/settings.py
- 상수:
  - `CRITICAL_ESCALATE_THRESHOLD = 1`
  - `MAJOR_REWORK_THRESHOLD = 3`
  - `SKILL_LEVELS = {"junior", "mid", "senior"}`
  - `LLM_MODEL = "gpt-4o-mini"`
- env:
  - `OPENAI_API_KEY` (or ANTHROPIC/GOOGLE)
  - `GITHUB_TOKEN`
  - `GITHUB_REPO` (예: "team/proj")
- **Red 테스트**: 임계값·SKILL_LEVELS 존재 확인
- **완료기준**: 3+ PASS

## Task B3. aggregator.py ★ 코드 리뷰 핵심
- **입력**: `List[AgentOutput]` (M2 0~2개 + M3 2개)
- **출력**: `(combined_issues, verdict, summary)`
- **로직**:
  - scan_id 일관성 검증 (다르면 ValueError)
  - (rule_id, file, line) 키로 중복 제거
  - severity별 카운트
  - verdict: Critical ≥ 1 → "escalate" / Major ≥ 3 → "rework" / else → "lgtm"
- **Red 테스트 (긍정·부정)**:
  - 2 AgentOutput 합치기 → 이슈 합계 정확
  - 같은 (rule_id, file, line) 중복 → 1개로
  - Critical 1 → escalate
  - Major 3 → rework
  - Major 2 + Minor 5 → lgtm
  - 빈 입력 → lgtm + 0 이슈
  - scan_id 다름 → ValueError
- **완료기준**: 7+ PASS

## Task B4. llm_refiner.py ★ 코멘트 작성 핵심
- **입력**: `combined_issues`, `verdict`, `developer (skill_level)`
- **출력**: markdown 문자열 (PR 코멘트 본문)
- **방식**:
  - API 키 있음 → LLM 구조화 출력
  - 키 없음 → 휴리스틱 템플릿 (severity별 + suggestion 그대로 사용)
- **skill_level 톤**:
  - junior: 상세 + 예시 코드 + 왜 문제인가 + 다음 단계
  - mid: 핵심 + 개선안
  - senior: 한 줄 요약
- **마크다운 구조**:
  ```
  ## 🤖 자동 리뷰 ({verdict} · Major {n} · Minor {m})
  
  ### {sev_emoji} {severity}: {rule_id} ({file}:{line})
  {message}
  
  💡 {suggestion}
  ```
- **Red 테스트** (LLM 호출은 mock):
  - junior + N+1 → 코멘트에 예시 코드 + 친절한 설명
  - senior + 같은 → 짧은 한 줄
  - 빈 이슈 → "리뷰 통과 ✅" 메시지
  - 키 없음 → 휴리스틱 (예시 코드 없이 깔끔)
  - 모든 issue.suggestion 본문에 포함
- **완료기준**: 5+ PASS

## Task B5. github_poster.py
- **입력**: `pr_url` (또는 owner/repo/pr_num), `comment_body`
- **출력**: 등록된 코멘트 ID 또는 dry-run 결과
- **방식**:
  - GITHUB_TOKEN 있음 → PyGitHub 또는 requests로 PR comment 등록
  - 토큰 없음 → dry-run: `.dry_run_comments/PR-{n}.md`에 저장
- **Red 테스트** (전부 mock):
  - 토큰 있음 → PyGitHub create_issue_comment 호출 검증
  - 토큰 없음 → dry-run 파일 생성
  - 401 응답 → 명확한 에러 메시지
  - 빈 코멘트 → 등록 시도 안 함
- **완료기준**: 4+ PASS

## Task B6. main.py — 오케스트레이션
- **입력**: `List[AgentOutput]`, `Developer`, `pr_url`
- **출력**: `ReviewReport` (verdict, summary, comment_md, gh_response)
- **흐름**: aggregator → llm_refiner → github_poster
- **Red 테스트** (mock):
  - 정상 흐름: aggregator·llm·github 각 1회 호출
  - escalate verdict → ReviewReport.escalation_needed=True
  - llm 실패 → 휴리스틱 폴백, 흐름 안 끊김
  - github 실패 → 에러 전파 (또는 dry-run 폴백)
- **완료기준**: 4+ PASS

## Task B7. validation/eval.py + fixtures
- **fixtures**: `sample_outputs.json` (M2+M3 합쳐 4개 AgentOutput)
- **expected**: 예상 verdict + 이슈 카운트
- **Red 테스트**:
  - main(fixtures) → expected와 일치
  - dry-run 파일 생성 검증
- **완료기준**: 3+ PASS

## ✅ MVP 완성 기준
- B1~B7 전부 PASS
- `py main.py` → fixtures로 verdict 출력 + dry-run 코멘트 생성

## 🔜 추후 확장 (스코프 밖)
- C1. kms_rag.py (사내 문서 RAG)
- C2. slack_notifier.py (Critical → 시니어 알림)
- C3. issue_persister.py (PostgreSQL 적재)
- C4. harness.py (LangSmith 계측)