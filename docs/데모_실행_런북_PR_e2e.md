# 풀스택 데모 실행 런북 — PR 한 번 → 페이지·DB·코멘트 (수동 e2e) · 팀 공유용

> **목적**: PR을 올리면 → 분석 → ① **리뷰 페이지 표시** ② **DB 저장** ③ **GitHub 코멘트** 까지
> 전부 도는 걸 로컬에서 끝까지 확인. 팀원도 이 문서 하나로 재현 가능.
>
> **전제**: 코드는 SESSION 1~5로 이미 구현 완료. 이 런북은 **"실행 + 검증"만**.
> **자동화(웹훅·토큰 한방에)** 는 아직 수동 — 자동화 계획은 `backend/m3/SESSION_C_자동화_웹훅_토큰_계획.md` (팀 상의 후 착수).

## 역할 분담
- 🖥️ **세션(VS Code)**: 서비스 기동(새 코드), 토큰 주입, 백엔드 검증
- 🙋 **나(사용자)**: ngrok, GitHub 웹훅 등록, 웹사이트 로그인/등록, PR, 화면 확인

---

## Phase 0 — 서비스 기동 (★ 새 코드로) [세션]
지금 돌던 m1·m3는 옛 코드일 수 있음 → **새 코드로 다시** 띄워야 함.
- [ ] api-core (8000)
- [ ] m1 (8001) — **새 코드**: m4 대신 m3 `/review` 호출
- [ ] m2 (8003) — stub 그대로
- [ ] m3 (8004) — **새 코드** + **환경에 `GITHUB_TOKEN` 주입**(webhook-gateway/.env 값 재사용 = 코멘트 게시용)
- [ ] frontend (5173)
- **확인**: 각 `/health` 200 · `GET http://localhost:8004/review/x/y/999` → `found:false` + 200 (새 코드 살아있다는 신호)

## Phase 1 — ngrok + GitHub 웹훅 [사용자]
- [ ] 터널: `& "C:\ngrok\ngrok.exe" http 8001` → `https://xxxx.ngrok-free.dev` 복사 (상세: `docs/ngrok_로컬_웹훅_테스트_가이드.md`)
- [ ] GitHub repo → Settings → Webhooks → Add/Edit:
  - Payload URL = `https://xxxx.ngrok-free.dev/triggers/pr`  (끝에 `/triggers/pr` 필수)
  - Content type = `application/json`
  - Secret = 루트 `.env` 의 `GITHUB_WEBHOOK_SECRET` 와 동일
  - Events = **Pull requests**
- [ ] ngrok 터미널 **켜둔 채로**

## Phase 2 — 웹사이트 로그인 + 레포 등록 [사용자]
- [ ] `http://localhost:5173` → **GitHub 로그인**
- [ ] 팀 생성 + 레포 등록: `kskt1234-netizen/-dev3-demo` (글자 정확히)
  - → 팀·유저·멤버십이 api-core DB에 생성됨 (PR ingest 404 방지)

## Phase 3 — PR 실행 [사용자]
- [ ] repo에서 **PR #4 Close → Reopen** (또는 새 PR) → 웹훅 발사
- [ ] GitHub 웹훅 "Recent Deliveries" 에 **200** 뜨는지 (🔴401=secret, 🔴404=시드)
  - timeout 떠도 m1은 끝까지 완료 → 코멘트는 달림. 빠르게 보려면 로컬 서명 웹훅(`_send_test_webhook.py`) 사용 가능.

## Phase 4 — 검증 (3개 다 도는지) [사용자/세션]
- [ ] ① **GitHub 코멘트**: PR#4 에 자동 리뷰 코멘트 달렸는지 (Gemini 본문 + 판정)
- [ ] ② **DB 저장**: `GET http://localhost:8004/review/kskt1234-netizen/-dev3-demo/4` → `found:true` + 이슈 목록
- [ ] ③ **페이지**: `localhost:5173` 리뷰 페이지 → PR 선택 → **판정 뱃지 + 이슈 테이블 + 코멘트** 표시

→ 셋 다 ✅ 이면 **DEV3 풀 e2e 완성.**

---

## 토큰·시크릿 정리 (어디에 뭘 넣나)
| 이름 | 용도 | 위치 |
|---|---|---|
| `GITHUB_TOKEN` | 서버가 PR에 **코멘트 게시** (repo 권한) | m3 실행 env (webhook-gateway/.env 값 재사용) |
| `GITHUB_WEBHOOK_SECRET` | m1이 웹훅 **서명 검증** | 루트 `.env` (= GitHub 웹훅 설정 Secret) |
| `GOOGLE_API_KEY` | 코멘트 **LLM 생성**(Gemini) | pr-comment-agent/.env (있으면 진짜 리뷰, 없으면 표준양식) |
> ⚠️ 토큰·시크릿은 `.env`에만. **git에 올리지 말 것** (`.gitignore`에 `.env` 포함됨).

## 트러블슈팅 (빠른표)
| 증상 | 원인 | 조치 |
|---|---|---|
| 웹훅 timeout | GitHub 10초 < 분석시간 | 정상(m1 완료·코멘트 달림). 빠른검증=로컬 서명 웹훅 |
| 웹훅 401 | secret 불일치 | Phase 1 Secret = 루트 .env |
| 웹훅 404 skip | 레포/작성자/멤버 미등록 | Phase 2 등록 + payload 작성자=로그인 계정 |
| 코멘트 안 달림 | GITHUB_TOKEN 없음/만료 | Phase 0 토큰 주입 / 만료면 PAT 재발급 |
| 페이지 비어있음 | m3 옛 코드 / found:false | Phase 0 새 코드+토큰 / 그 PR로 한 번 흐르게 |

---

## 다음(오늘 이후) — 자동화
이 런북의 **수동 3개(ngrok·웹훅·토큰)** 를 "레포 등록 한방에"로 바꾸는 게 자동화. 접근 A(GitHub App)/B(OAuth 확장) + 배포 필요.
→ `backend/m3/SESSION_C_자동화_웹훅_토큰_계획.md` 에 정리됨. **팀 상의 후** 접근 정해서 착수.
