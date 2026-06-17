# SESSION 4 — m3 review 엔드포인트 (집계→판정→코멘트→GitHub 게시→DB 저장) (VS Code 복붙용)

> 목적: m1이 **m4 대신 m3의 새 `/review` 엔드포인트**를 호출하게 해서, **DEV3가 직접**
> ① 이슈 집계+판정 ② LLM 코멘트 생성 ③ GitHub PR에 코멘트 게시 ④ DB 저장 ⑤ 결과 조회 API 제공.
> → 플랫폼(m1·api-core·웹사이트 PR목록)은 그대로 유지. **새로 짜는 건 적고 기존 DEV3 코드 조립이 대부분.**

> 확정된 설계: **m1 → (m4 X) → m3 `/review` 호출.** 토큰은 **기존 `GITHUB_TOKEN` 재사용**(webhook-gateway/.env 에 있음).

---

```
너는 우리 팀 시니어 백엔드 엔지니어다. TDD로(테스트 먼저), 한 번에 하나씩.
작업 디렉토리: C:\Users\user\Code-Shepherd\backend\m3

[배경 — 이미 있는 DEV3 코드 (재사용 필수, 새로 짜지 말 것)]
- pr-comment-agent/aggregator.py : 이슈 모아 판정(Critical 1개→escalate / Major 3개↑→rework / 그외 lgtm)
- pr-comment-agent/llm_refiner.py : Gemini로 신입 맞춤 코멘트 생성(rag_context 인용)
- pr-comment-agent/github_poster.py : GITHUB_TOKEN으로 GitHub Issues Comments API에 게시
- pr-comment-agent/main.py : 위를 묶는 오케스트레이션(있으면 그대로 활용)
- test-performance-agent/persist.py : 이슈를 scan_issues 테이블에 저장
- webhook-gateway/gateway.py : clone→분석→집계→코멘트→게시 전체 흐름(참고용 청사진)
- m3/app/main.py : 이미 /verify/tests·/analyze/performance 로 실분석 연결됨(SESSION 2/2B)

[목표 — m3에 review 단계 추가]
1. 계약: shared/contracts.py 에 M3ReviewRequest / M3ReviewResponse 추가(또는 m3 자체 계약).
   - M3ReviewRequest: task_id, pr_id, repository("owner/repo"), pr_number,
     static_analysis, security_scan, test_verification, performance  (= 네 모듈 4결과; M4EvaluateRequest와 동형 + repository/pr_number)
   - M3ReviewResponse: task_id, pr_id, verdict("lgtm"|"rework"|"escalate"), comment_posted(bool),
     comment_url(str|None), persisted(bool)
2. m3/app/main.py 에 POST /review 추가. 동작:
   a) 4개 결과의 이슈를 합쳐 aggregator로 **판정(verdict)** 산출 (pr-comment-agent 재사용)
   b) llm_refiner로 **코멘트 본문 생성** (LLM 키 없으면 표준 fallback 코멘트, 가짜 금지)
   c) github_poster로 **repository#pr_number 에 코멘트 게시** (GITHUB_TOKEN 사용; 토큰 없거나 실패 시 게시 skip + 사유 로그, 가짜 금지)
   d) persist로 **이슈+verdict+코멘트를 DB에 저장** (조회용)
   e) M3ReviewResponse 반환
   - 모듈 isolation(sys.path/sys.modules)은 기존 dev3_adapter/app 패턴 그대로.
3. 조회 API: m3/app 에 GET /review/{owner}/{repo}/{pr_number} 추가 → 저장된 {verdict, comment, issues[]} 반환.
   (SESSION 5 프론트 페이지가 이걸 읽어 표시한다. 없으면 404/빈 결과.)
4. m1 연결: m1/app/routers/triggers.py 에서 call_m4_evaluate 대신(또는 그 자리에) **m3 /review 호출**로 교체.
   - module_clients.py 에 call_m3_review 추가. eval 데이터(4결과) + repository + pr_number 채워 전달.
   - m4 호출은 제거하거나 주석(이번 결정: 코멘트·판정은 m3 소유). M4EvaluateResponse 의존 코드가 있으면 verdict만 M3ReviewResponse에서 받게 정리.

[토큰]
- 기존 GITHUB_TOKEN 재사용. webhook-gateway/.env 에 있을 것 → m3/app 실행 환경(루트 .env 또는 m3 .env)에 GITHUB_TOKEN 으로 세팅해 github_poster가 읽게 한다. (값은 문서/코드/깃에 적지 말 것)

[TDD — 외부의존 전부 Mock]
- aggregator 판정: Critical/Major/그외 케이스별 verdict 단위테스트
- /review: github_poster·llm_refiner·persist 를 monkeypatch → "게시 호출됨/저장 호출됨/verdict 반환" 검증
- 토큰 없음/게시 실패 → comment_posted=false + 사유, 예외 안 터짐(정직)
- GET /review: 저장된 결과 반환 / 없으면 빈 결과
- m1: call_m3_review 가 4결과+repository+pr_number로 호출되는지(인자 캡처). m4 미호출 확인.
- 회귀: 기존 pr-comment-agent/test-performance-agent/m3 tests green 유지

[지킬 것]
- 분석 로직(run·탐지기)·기존 pr-comment-agent 로직 수정 최소화 — "조립 + 엔드포인트"만.
- 가짜 코멘트/가짜 게시 금지: 토큰·LLM 없으면 정직하게 skip/fallback.
- 막히면 멈추고 물어봐라. 마지막에 [변경파일 / 테스트결과 / 실제 게시된 코멘트 URL(있으면)] 표로.
```

---

## 참고 (사용자용 메모)
- 이 세션이 끝나면: PR 올리면 **GitHub PR에 코멘트가 자동으로 달리고**, 결과가 **DB에 저장**되며, **조회 API**까지 생겨. (페이지는 SESSION_5)
- m4는 이번 흐름에서 빠지고 **판정·코멘트는 m3(DEV3) 소유**가 됨 — 네 pr-comment-agent가 그 일을 함.
- 토큰은 새로 안 만들고 **기존 GITHUB_TOKEN 재사용**. 게시 실패해도 분석/저장은 정상 동작(코멘트만 skip).
- ⚠️ live 테스트 시 GitHub 10초 timeout은 여전함(코멘트 게시까지 더 길어질 수 있음) → 그건 B(async)에서 해결. 지금은 m1이 끝까지 완료하면 코멘트는 달림.
