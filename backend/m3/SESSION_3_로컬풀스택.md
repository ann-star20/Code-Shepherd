# SESSION 3 — 로컬 풀스택 "진짜" end-to-end (m1 값 채우기 포함) (VS Code 클로드코드 복붙용)

> 목적: 가짜 GitHub PR 웹훅 → **m1(값 채움)** → api-core(저장) → **m3(실 clone·분석)** → m4 까지 한 바퀴.
> SESSION_2B(빈 결과 아님 확인) 통과 후 실행. 여기서는 **m1이 m3로 진짜 값(clone_url/commit_sha/diff 텍스트)을 채워 보내서**
> 풀 파이프라인 끝까지 **실제 이슈가 흐르는지**를 본다. (예전 S3는 "라우팅만" 봤지만, 이번엔 실값까지)

> ⚠️ 선결 빵꾸 인지 — diff 텍스트:
> - m3 분석의 parse_diff 는 'diff --git/+++ b//@@/+줄' 같은 **diff 본문 텍스트**를 파싱한다.
> - 현재 m1 triggers.py 는 pr_diff 에 **diff_url(URL)**을 넣어 보낸다 → parse_diff 변경줄 0개 → 모든 이슈 drop → 조용히 빈 결과.
> - 현재 계약(M3VerifyRequest)엔 raw_diff 필드가 없다 → **diff 텍스트는 pr_diff 로만 전달**된다.
> - 따라서 이번 세션의 핵심 = **m1이 diff_url 을 fetch 해서 본문을 pr_diff 에 담아 보내게** 고치는 것.

---

```
너는 우리 팀 시니어 백엔드/DevOps 엔지니어다. 작업 디렉토리: C:\Users\user\Code-Shepherd
TDD/소그룹으로 진행하고, 외부의존 실패는 추측 우회 말고 정확히 보고하라.

[아키텍처]
- 입구 m1: backend/m1/app/routers/triggers.py 의 POST /triggers/pr (GitHub 웹훅, HMAC-SHA256 검증 settings.github_webhook_secret).
- m1 흐름: payload 파싱 → call_api_core_pr_ingest(레포→팀, sender→유저/멤버 매칭, 없으면 skip)
           → m2(static/security) → m3(verify/tests, analyze/performance) → m4(evaluate) 순서로 httpx 호출.
- 모듈 URL: backend/_shared/shared/config.py 의 settings(m2_url/m3_url/m4_url/api_core_url 등).
- m3 app(backend/m3/app/main.py)은 이미 실 분석에 연결됨(SESSION_2). clone_url 있으면 clone→run, 없으면 빈 issues.

[해야 할 핵심 수정 ① — m1 이 m3 로 진짜 값을 채워 보내기]  ← 이게 이번 세션의 메인
backend/m1/app/routers/triggers.py 에서 verify_req(M3VerifyRequest) 를 만드는 부분을 수정:
 - clone_url  = pull_request["head"]["repo"]["clone_url"]  (없으면 raw["repository"]["clone_url"])
 - commit_sha = pull_request["head"]["sha"]
 - pr_diff    = **diff_url 을 fetch 한 본문 텍스트** (아래). URL 그대로 넣지 말 것.
   예:
     import httpx
     diff_text = ""
     _durl = pull_request.get("diff_url", "")
     if _durl:
         try:
             _r = httpx.get(_durl, follow_redirects=True, timeout=15)
             if _r.status_code == 200 and _r.text.startswith("diff --git"):
                 diff_text = _r.text
         except Exception:
             diff_text = ""
     # m2·m3 둘 다 같은 diff_text 를 쓰게 한다(빈 문자열이면 분석은 빈 결과로 정직하게).
 - 주의: M3VerifyResponse / M4 로 가는 계약은 불변. m2 로 가는 analysis_req.pr_diff 도 diff_text 로 통일.
 - 인증: 위 데모 레포는 public 이라 토큰 불필요. (사내 private 레포는 Accept: application/vnd.github.v3.diff + 토큰 필요 — 이번 로컬엔 불필요)

[권장 수정 ② — m3 방어코드 (빵꾸 원천 차단, 작게)]
backend/m3/app/main.py 에서 pr_diff 가 'http' 로 시작하면(누가 URL을 보냈을 때) 한 번 fetch 해서 본문으로 바꾼 뒤 run 에 넘긴다.
→ m1이 어떤 이유로 URL을 보내도 m3가 조용히 빈 결과를 내지 않게. (실패 시 빈 문자열, 가짜 만들지 말 것)
 - 이 수정 후 backend/m3/tests 에 "pr_diff 가 URL이면 fetch 시도" 단위테스트 1개 추가(httpx mock).

[기동 — 최소 구성]
- 필수: api-core, m1, m3 / m2·m4(·m0)는 스텁 그대로 떠 있어야 함(m1이 m2를 먼저 호출하므로 m2가 죽어 있으면 m3 전에 502).
- 각 .env 정렬: m1(m2_url/m3_url/m4_url/api_core_url, github_webhook_secret), m3(POSTGRES_URL은 RAG용 — 이번엔 RAG off라 없어도 분석은 됨).
- DB: api-core용 Postgres + alembic 마이그레이션 필요한지 확인.

[사전 시드 — api-core DB (이게 안 맞으면 ingest 404 skip)]
- 팀 1개: github_repo_full_name = "kskt1234-netizen/-dev3-demo"
- 유저 1명: github_id = "<원하는 작성자 로그인>"(예: "junior_dev_01") + 그 유저를 위 팀의 멤버로
- (pr_service.ingest_pr_from_webhook 가 레포→팀, sender→유저→멤버 전부 매칭해야 통과)

[가짜 PR 웹훅 — 실제 데모 레포 값으로]  ← 실 clone·실 diff 가 되도록 진짜 값 사용
payload(JSON) 핵심 필드:
  action="opened", number=4,
  repository.full_name="kskt1234-netizen/-dev3-demo",
  repository.clone_url="https://github.com/kskt1234-netizen/-dev3-demo.git",
  pull_request.number=4,
  pull_request.user.login="<시드한 작성자와 동일>",
  pull_request.diff_url="https://github.com/kskt1234-netizen/-dev3-demo/pull/4.diff",
  pull_request.head.sha="27f5c96142260206ce714da1294aefbbddb0f4f6",
  pull_request.head.repo.clone_url="https://github.com/kskt1234-netizen/-dev3-demo.git",
  sender.login="<시드한 작성자와 동일>"
서명: body 를 github_webhook_secret 로 HMAC-SHA256 → 헤더 X-Hub-Signature-256: "sha256="+hexdigest
전송: POST http://localhost:<m1포트>/triggers/pr

[검증 — "진짜로 흐르는가" + "비어있지 않은가"]
1. m1 로그: pr_trigger_received → module_call(module=m3) status=200 → pr_trigger_dispatched(verdict 포함).
2. api-core: pull_requests 테이블에 행 생성.
3. ★ m3 응답 issues 가 **비어있지 않게**(데모 레포는 버그가 있으므로) 오는지 — 라우팅만이 아니라 실제 분석 결과까지.
   - Docker 미가용이면 커버리지(TEST-001)만 빠지고 N+1/복잡도는 나와야 한다(부분 동작 정상).
4. 응답 JSON status="dispatched", task_id/trace_id 존재.

[빵꾸 체크리스트 — 0건/실패 시 순서대로]
□ pr_diff 가 URL이 아니라 'diff --git' 텍스트인가 (수정① 적용?)
□ HMAC secret 가 m1 .env 와 서명 생성에 동일한가
□ 시드(레포명/작성자 github_id)가 payload 와 글자까지 같은가 (404 skip 원인 1위)
□ m2·m4 스텁이 떠 있는가 (m1이 m3 전에 m2 호출 → m2 죽으면 502)
□ commit_sha 체크아웃 성공했는가 (git fetch by sha)
□ m3_url 등 모듈 URL .env 가 실제 포트와 맞는가

[지킬 것]
- 서명 검증 우회 금지(실제 서명으로 통과). 가짜 diff/가짜 이슈 만들지 말 것.
- M3VerifyResponse/IssueItem/M4 계약 불변. test-performance-agent 분석 로직 수정 금지.
- 막히면 멈추고 물어봐라. 마지막에: [기동 서비스/포트 표] + [요청→응답 로그 발췌] + [m3 이슈 건수] + [빵꾸 체크리스트 결과].
```

---

## 참고 (사용자용 메모)
- **이번 S3의 달라진 점**: 예전엔 "라우팅만 보고 m3 빈 결과 OK"였는데, 이제 **m1이 실값을 채워(②) 보내서 m3가 진짜 이슈를 끝까지 흘려보내는지**까지 본다. 진짜 end-to-end.
- **제일 중요한 빵꾸 = diff 텍스트**: m1이 `diff_url`을 그대로 보내면(현재 코드) parse_diff가 빈손 → 이슈 0건. 그래서 수정①에서 m1이 .diff 본문을 fetch해 `pr_diff`에 담게 함. 수정②(m3 방어)까지 하면 누가 URL을 보내도 안 터짐.
- **m1 파일을 m3 브랜치에서 건드림**: 같은 레포라 가능하지만 m1은 그쪽 모듈이니 변경 최소화 + 머지 전 m1 담당자 리뷰 권장(이미 합의했으니 OK).
- **데모 레포 PR#4(payment)** 사용 — payment 커버리지 기준이 90%라 탐지가 잘 걸려 "비어있지 않음" 합격선이 명확.
- 0건 나오면 위 **빵꾸 체크리스트** 순서대로. 십중팔구 1번(diff URL) 또는 3번(시드 불일치).
