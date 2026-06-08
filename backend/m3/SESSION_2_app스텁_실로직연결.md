# SESSION 2 — m3/app 스텁 → 진짜 분석 파이프라인 연결 (VS Code 클로드코드 복붙용)

> 목적: m1 오케스트레이터가 호출하는 `m3/app/main.py`의 `/verify/tests`·`/analyze/performance`가
> 지금은 **빈 스텁**(issues=[])이다. 이걸 실제 `test-performance-agent` 분석에 연결한다.
> ⚠️ 선행: `M3VerifyRequest`에 repo/diff 선택 필드 추가(REQUEST_to_M1_계약필드.md)가 m1 쪽에 반영되면 가장 깔끔.
>   아직 안 됐으면, m3/app에서 그 필드를 "선택"으로 읽도록 짜고 로컬 테스트는 완전한 요청으로 진행한다.

---

```
너는 우리 팀 시니어 백엔드 엔지니어다. TDD로 진행한다(테스트 먼저 → 통과 → 다음).
작업 디렉토리: C:\Users\user\Code-Shepherd\backend\m3

[현 상태]
- backend/m3/app/main.py 는 스텁: /verify/tests, /analyze/performance 가 항상 빈 issues 반환.
- 진짜 분석 로직은 backend/m3/test-performance-agent/ 에 있다:
    main.py:run(dev3_input: Dev3Input, repo_path: str) -> list[AgentOutput]   ← 골든4 탐지기 실행
    contracts.py: Dev3Input / AgentOutput / Issue (이 폴더 자체 계약, shared와 다름)
    prepare/repo.py, prepare/sandbox.py: clone·Docker 샌드박스
- 이미 똑같은 변환을 하는 참고 코드가 있다:
    webhook-gateway/agents/dev3_adapter.py
      → clone된 work_dir 받아 Dev3Input 구성 → dev3_main.run() → Issue를 표준 dict로 변환.
      → 중요: 'contracts','main','config' 모듈명이 다른 폴더와 충돌하므로 sys.path/sys.modules 격리 패턴을 쓴다. 이걸 그대로 본떠라.
- 플랫폼 계약은 backend/_shared/shared/contracts.py 의 M3VerifyRequest / M3VerifyResponse / IssueItem.

[목표]
m3/app/main.py 의 두 엔드포인트를 실제 분석에 연결:
  /verify/tests      → run() 결과 중 agent=="test_verification" 의 issues
  /analyze/performance → run() 결과 중 agent=="performance" 의 issues
응답은 M3VerifyResponse(task_id, agent, issues=list[IssueItem], summary, execution_ms).

[데이터 매핑]
- 입력 M3VerifyRequest → test-performance-agent 의 Dev3Input 으로 변환:
    task_id, pr_id, pr_diff(또는 raw_diff), developer.id, 그리고 repo(clone_url/commit_sha).
    repo 정보가 요청에 없으면(선택 필드 미반영) → 명확한 에러 대신, 분석 불가 사유를 남기고 빈 issues 반환(가짜 만들지 말 것).
- clone: prepare/repo.py 로 clone_url@commit_sha 를 받아 work_dir 확보. diff 본문이 없으면 diff_url에서 받거나 clone 후 확보.
- 출력 Issue(test-performance-agent) → IssueItem(shared) 필드 매핑:
    severity, line, file, message, rule_id, suggestion  (IssueItem에 없는 keyword/code_context/rag_context 등은 버림 — 계약 준수)
    summary는 severity 카운트로 채움.

[TDD 순서]
1. 먼저 테스트부터: backend/m3/tests/test_contract.py 를 확장(또는 새 test 파일).
   - 외부의존(clone·docker·embed·run)을 Mock해서, "완전한 M3VerifyRequest → /verify/tests 가 test_verification 이슈를 IssueItem 형식으로 반환" 검증.
   - /analyze/performance 가 performance 이슈만 반환하는지 분리 검증.
   - repo 정보 없는 요청 → 빈 issues + 200(혹은 명시적 사유) 검증.
   - dev3_main.run 을 monkeypatch 해 가짜 AgentOutput 2개를 돌려주게 하면 clone/docker 없이 테스트 가능.
2. app/main.py 구현 → 테스트 통과.
3. 모듈 격리 주의: app(shared.contracts)와 test-performance-agent(자체 contracts)의 동명 모듈 충돌을
   dev3_adapter.py 처럼 sys.path.insert + sys.modules 정리로 격리. import를 함수 안에서(지연) 하라.
4. 회귀 확인: 기존 test-performance-agent/tests 전체와 m3/tests 가 여전히 green인지.
   pytest backend/m3/tests
   (cd backend/m3/test-performance-agent && pytest) — 둘 다.

[지킬 것]
- M3VerifyResponse / IssueItem 계약(필드·타입)을 절대 바꾸지 마라(m1·m4가 의존).
- test-performance-agent 의 분석 로직(run, 탐지기)은 수정 금지 — app은 "변환 어댑터"만 추가.
- 한 번에 하나씩. 막히면 멈추고 물어봐라. 마지막에 변경 파일 목록 + 테스트 결과 표로 요약.
```

---

## 참고 (사용자용 메모)
- 이 세션의 결과물은 사실상 "`dev3_adapter.py`를 HTTP 엔드포인트 버전으로 옮긴 것". 독립 게이트웨이(webhook-gateway)는 안 쓰고, m1이 호출하는 app/main.py가 진짜 입구가 됨.
- `M3VerifyRequest` 선택 필드(repository/clone_url/commit_sha/raw_diff)가 m1에 반영되기 전이라도, app은 그 필드를 optional로 읽게 짜두면 m1 반영 즉시 동작.
