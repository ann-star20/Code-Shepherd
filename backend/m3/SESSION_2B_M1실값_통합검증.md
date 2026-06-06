# SESSION 2B — M1 실제 값 수신 + 실 clone·분석 통합 검증 (VS Code 클로드코드 복붙용)

> 위치: **SESSION_2(스텁→실로직 구현) 다음, SESSION_3(풀스택) 전에 실행.**
> 목적: M1과 합의한 대로 `M3VerifyRequest`에 repo/diff 값이 **실제로 채워져 들어올 때**, m3가 그 값을 올바로 받아
> **진짜 clone → pytest/AST 분석 → 실제 이슈 반환**까지 도는지 끝까지 검증한다. (SESSION_2는 Mock 기반, 여기는 **실데이터**)

---

```
너는 우리 팀 시니어 백엔드 엔지니어다. 작업 디렉토리: C:\Users\user\Code-Shepherd\backend\m3

[합의 사항 — M1과 확정됨]
m1이 m3를 호출할 때 보내는 M3VerifyRequest(backend/_shared/shared/contracts.py)에 아래 필드가 채워져 온다:
  repository : "owner/repo"
  clone_url  : "https://github.com/owner/repo.git"
  commit_sha : PR head 커밋 SHA
  raw_diff   : (가능하면) diff 본문 텍스트. 없으면 None → m3가 pr_diff(diff_url)로 보완.

[먼저 — 계약 동기화 확인(제일 중요)]
1. backend/_shared/shared/contracts.py 의 M3VerifyRequest 에 위 4개 필드가 실제로 추가됐는지 확인.
   - 없거나 이름이 다르면(예: head_sha vs commit_sha) 멈추고 보고하라. m1이 보내는 키 == m3가 읽는 키가
     정확히 같아야 한다(이 불일치가 조용히 빈 결과를 만드는 1순위 원인).
   - 필드가 아직 안 들어왔으면, 추가 PR이 머지될 때까지 이 세션은 보류 — 사용자에게 알려라.

[m3 수신부 점검 — SESSION_2에서 만든 app/main.py]
2. backend/m3/app/main.py 의 /verify/tests · /analyze/performance 가:
   - M3VerifyRequest.clone_url / commit_sha 로 test-performance-agent 의 RepoInfo(clone_url, commit_sha) 구성
   - prepare/repo.py 의 prepare_repo(RepoInfo) 로 실제 clone → work_dir 확보
   - pr_diff(또는 raw_diff)를 Dev3Input.pr_diff 로 전달
   - main.run(dev3_input, work_dir) 실행 → AgentOutput → IssueItem 매핑
   순서로 동작하는지 코드로 확인. 빠진 연결이 있으면 SESSION_2 규칙대로 보완(분석 로직은 수정 금지, 어댑터만).

[통합 검증 — 2계층으로]
3. (A) 로컬 fixture로 "분석이 실제 이슈를 만든다" 확인 (clone 없이 빠르게):
   - test-performance-agent/tests/fixtures/sample_repo + sample_pr.diff 는 알려진 이슈가 있는 샘플이다.
   - 이 work_dir 와 diff 로 main.run()을 직접 호출 → test_verification·performance 이슈가 **비어있지 않게** 나오는지.
4. (B) "M1이 보내는 모양 그대로" 실 clone 통합 테스트:
   - 테스트 대상 = 실제 버그 코드가 든 공개 데모 레포(아래). PR이 4개 있어 그대로 쓴다.
       clone_url  : https://github.com/kskt1234-netizen/-dev3-demo.git   (public, 인증 불필요)
       PR 예시(head commit_sha):
         PR#4 feature/add-payment : 27f5c96142260206ce714da1294aefbbddb0f4f6   ← 권장(payment=커버리지 90% 기준이라 탐지 잘 걸림)
         PR#3 feature/add-cart    : 6401f8c46d5cd93588d949594d5272dbc576e23a
         PR#2 feature/add-orders  : 08c8b63499ce71c9840a10d0e0c048425b08cb19
         PR#1 feature/add-posts   : d66400e667094a25788217a236f0daade4390955

   ⚠️ 핵심 빵꾸 주의 — pr_diff 는 URL 이 아니라 "diff 본문 텍스트"여야 한다:
     - run() 내부 parse_diff 는 'diff --git / +++ b/ / @@ / +줄' 같은 **unified diff 텍스트**를 파싱한다.
     - pr_diff 에 URL(.../pull/4.diff)을 넣으면 parse_diff 가 변경줄 0개 → diff 필터가 **모든 이슈를 drop**
       → 에러 없이 조용히 빈 결과. (현재 계약엔 raw_diff 필드 없음 → diff 텍스트는 pr_diff 로만 들어간다.)
     - 그러니 먼저 .diff 본문을 받아서 pr_diff 에 넣어라:
         import httpx
         diff_text = httpx.get("https://github.com/kskt1234-netizen/-dev3-demo/pull/4.diff",
                               follow_redirects=True, timeout=15).text
       (diff_text 가 'diff --git' 으로 시작하는지 한 번 확인하고 진행)

   - 구성할 M3VerifyRequest(현재 계약 필드만): task_id, pr_id, pr_diff(=diff_text), clone_url, commit_sha.
   - app 엔드포인트(/verify/tests, /analyze/performance)에 POST(ASGITransport 또는 실서버) → 200 +
     issues 가 IssueItem 형식(severity/file/line/message/rule_id/suggestion)으로, **버그 레포니까 비어있지 않게** 오는지.
   - 참고 예시 요청(JSON, PR#4):
       {
         "task_id": "local-2b-pr4", "pr_id": "4",
         "clone_url": "https://github.com/kskt1234-netizen/-dev3-demo.git",
         "commit_sha": "27f5c96142260206ce714da1294aefbbddb0f4f6",
         "pr_diff": "<pull/4.diff 의 실제 본문 텍스트 — 'diff --git ...' 로 시작, URL 아님!>"
       }
   - clone→pytest 커버리지는 Docker 샌드박스가 필요할 수 있다(prepare/sandbox.py). Docker 미가용이면 그 사실과
     커버리지(TEST-001)만 skip되는지를 정확히 보고(가짜로 채우지 말 것). N+1·복잡도(AST)는 clone만으로도 검출돼야 한다.
   - 만약 이슈가 0건이면: ① pr_diff 가 URL인지(텍스트여야 함) ② commit_sha 체크아웃이 됐는지 ③ diff의 파일경로와
     clone된 레포의 경로가 맞는지 — 이 3개를 순서대로 확인(빈 결과의 단골 원인).
5. 계약 매핑 회귀 테스트(양측 동기화 고정):
   - backend/m3/tests/test_contract.py 를 확장: "repo 필드가 채워진 M3VerifyRequest" 케이스 추가.
     run()을 monkeypatch해 가짜 AgentOutput을 주더라도, app이 clone_url/commit_sha/raw_diff 를 읽어
     RepoInfo·Dev3Input 으로 올바로 넘기는지(인자 캡처로) 검증. → m1 키 변경 시 테스트가 깨져 바로 알 수 있게.
   - 기존 최소 payload 케이스(repo 필드 없음)도 그대로 통과(빈 issues, 200)해야 한다(하위호환).

[검증 명령]
- cd backend/m3 && pytest tests/test_contract.py
- cd backend/m3/test-performance-agent && pytest    (회귀: 분석 로직 안 깨졌는지)
- 실 clone 통합은 네트워크/Docker 필요 — 가능 여부 먼저 확인 후 실행.

[지킬 것]
- M3VerifyResponse / IssueItem 계약 불변. test-performance-agent 분석 로직 수정 금지(어댑터/테스트만).
- clone·diff·Docker가 안 되면 빈 결과로 정직하게(가짜 이슈/가짜 diff 만들지 말 것).
- 막히면 멈추고 물어봐라. 마지막에 표로: [점검항목 / 결과(OK·FAIL) / 실제 이슈 건수 / 비고].
```

---

## 참고 (사용자용 메모)
- **테스트 레포 = 내가 버그 코드 올려둔 데모**: `https://github.com/kskt1234-netizen/-dev3-demo` (public). PR #1~#4가 그대로 살아있어 실제 `commit_sha`+diff를 바로 씀. 일부러 넣은 버그가 있으니 "이슈가 나와야 정상"이라 합격 판정이 명확함. (예전에 독립 웹훅으로 돌려보던 그 레포)
- 이 세션의 **핵심 합격선**: "M1이 보내는 모양의 요청"으로 m3가 **비어있지 않은 진짜 이슈**를 IssueItem 형식으로 돌려주는 것. SESSION_3(풀스택)에서 라우팅이 빈 issues여도 OK였던 것과 달리, 여기서는 **m3 자체가 실제로 일하는지**를 본다.
- 가장 흔한 실패: **필드 이름 불일치**(m1이 `head_sha`로 보내는데 m3가 `commit_sha`로 읽는 식). 그래서 4번/5번에서 "키 동기화"를 테스트로 고정해 둠.
- Docker가 로컬에 없으면 커버리지(TEST-001)만 빠지고 N+1·복잡도(AST 기반)는 clone만으로도 검출됨 — 부분 동작은 정상.
