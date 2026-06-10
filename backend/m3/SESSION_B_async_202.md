# SESSION B — async/202: GitHub 웹훅 timeout 해결 (VS Code 복붙용)

> 목적: m1이 PR 웹훅을 받으면 **HMAC 서명 검증 후 즉시 202로 응답**하고,
> 무거운 분석(ingest→diff→m2/m3→m3 /review)은 **백그라운드**로 돌린다.
> → GitHub 10초 timeout 빨간불 + 재전송으로 인한 중복 분석 위험 제거.
> 코멘트 게시·DB 저장·페이지 표시 등 **눈에 보이는 결과는 지금과 동일**.

> 범위: **m1 한 곳** — `backend/m1/app/routers/triggers.py` 의 `POST /triggers/pr` + 그 테스트(`tests/test_triggers.py`). m2/m3/프론트 변경 없음.

---

```
너는 우리 팀 시니어 백엔드 엔지니어다. 작업 디렉토리: C:\Users\user\Code-Shepherd\backend\m1
이 레포 테스트는 py 런처로 돈다: py -m pytest tests/test_triggers.py -q  (python.exe 는 Store 스텁이라 안 잡힘)

[작업 방식 — 중요]
- tdd-workflow 스킬을 써서 테스트부터 짜고 진행한다(TDD는 항상).
- 구현 방법(어디서 끊을지·함수 분리·BackgroundTasks vs 다른 방식)은 정해주지 않는다.
  현재 코드를 직접 읽고 가장 깔끔한 설계를 네가 정해라. 대안이 있으면 비교해보고 고른다.
- 막히거나 애매하면 systematic-debugging / verification-before-completion 스킬을 활용해도 된다.

[문제]
GitHub 은 웹훅 응답을 10초 안에 기대하는데, 지금 /triggers/pr 는 m3 분석(clone+분석, 13~41초)이
끝날 때까지 동기로 기다렸다가 응답한다. → GitHub "timed out" 빨간불 + 같은 웹훅 재전송 → 중복 분석.

[목표]
1. /triggers/pr 가 서명 검증 직후 즉시 202 를 반환한다(접수 확인).
2. 무거운 분석 체인(ingest → diff fetch → m2/m3 호출 → m3 /review)은 백그라운드로 돌린다.
3. 결과 확인은 기존 GET /review 폴링으로. 별도 콜백 없음.

[반드시 지킬 것 — 합격 기준]
- 서명 검증은 응답 전에 그대로(잘못된/없는 서명 → 401 유지).
- 백그라운드에서는 예외를 raise 하지 말고 로그만 남긴다(응답이 이미 나갔으니 받을 곳이 없다).
  skip(미등록 레포 ingest 404 등)·모듈 실패도 정직하게 로그로 처리.
- 코멘트 게시·DB 저장 등 기존 동작과 최종 결과는 그대로 유지(사용자가 보는 결과가 달라지면 안 됨).
- 가짜 데이터/가짜 성공 금지.

[TDD]
- 최소 검증: ① 유효 서명 → 202 즉시 ② 백그라운드에서 m2·m3·review 가 실제 호출됨(respx) ③ 잘못된 서명 → 401.
- 기존 test_triggers.py 가 200·응답본문(verdict 등)에 의존하면, 202·새 응답 형태에 맞게 고치되
  "무엇을 검증하는지"의 의미는 보존해라.
- 위는 최소선이다. 경계 케이스(payload 파싱 실패, diff 없음, ingest 404 등)는 네가 더 생각해서 다양하게 테스트해라.
- (테스트 함정 참고) httpx ASGITransport 는 응답 후 백그라운드까지 끝낸 뒤 반환한다
  → 테스트에선 respx .called 단언이 그대로 유효(실서버는 비동기지만 테스트는 동기적으로 끝남).

[끝나면]
- [변경 파일 / 테스트 결과 / 수동 e2e(PR 한 번 → GitHub 즉시 202 + 잠시 후 코멘트 달림)] 정리.
- 단일 워커에서 백그라운드가 도는 동안의 한계(동시 다(多)PR)·운영용 큐 전환은 이번 범위 밖 — 주석/메모로만.
- 막히면 멈추고 물어봐라.
```

---

## 참고 (사용자용 메모)
- 바뀌는 건 딱 하나 — GitHub 를 **문 앞에 세워두지 않고 "접수증(202)"부터 끊어주기**. 코멘트·페이지·저장 결과는 지금과 똑같이 나온다.
- 건드리는 파일은 **m1 1개 + 그 테스트**뿐 → m3 혼자 반나절.
- 성공 신호: 작업 후 GitHub 웹훅 "Recent Deliveries" 에 빨간 "timed out" 대신 **초록 202** 가 뜨고, 잠시 뒤 PR 에 코멘트가 달린다.
- 후속: 자동화 `SESSION_C_자동화_웹훅_토큰_계획.md`(팀 협업), GCP DB 전환(SESSION D).
