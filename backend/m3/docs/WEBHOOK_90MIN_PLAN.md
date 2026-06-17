# 웹훅 90분 타임박스 점검 계획 (D1 — go/no-go는 정현 결정)

목표: 브리프 §2.5 통과 기준 3종을 90분 안에 검증. **하나라도 실패 → 자동 no-go → Streamlit 단독.**

- [ ] ① payload에 diff(또는 diff 조회 가능한 정보) 포함
- [ ] ② PAT로 PR 코멘트 POST 성공
- [ ] ③ ngrok 터널 30분 유지

## 사전 분석 결과 (코드 리딩 기반, 실행 전 확인됨)

- 재사용 원본: `Desktop\Code-Shepherd\backend\m3\webhook-gateway\` (server.py / gateway.py / registry.py)
- GitHub PR 웹훅 payload에는 diff **본문이 없고**, `repository.full_name` + `number` 가 온다 →
  기존 `gateway.fetch_pr_diff()` 가 `Accept: application/vnd.github.v3.diff` 로 조회 (기준 ① 충족 경로 이미 구현됨).
- server.py 는 자기 폴더의 `.env` 를 읽음 → 점검 시 repo 루트 `.env` 를 환경변수로 주입하거나 경로 수정 필요.
- ngrok: winget 설치 확인됨 (`ngrok.exe` PATH 존재). 무료 플랜이면 authtoken 등록 + URL이 실행마다 바뀜 → 시연 직전 webhook URL 재등록 절차 필요.
- 기존 코드 중 Postgres 적재·pr-comment-agent 경로는 사용하지 않음 (v2 컷) — 점검도 그 경로를 우회.

## 타임라인 (총 90분)

| 시각 | 작업 | 통과 신호 | 실패 시 |
|---|---|---|---|
| 0–10' | venv에 flask 확인, `GITHUB_TOKEN` 유효성: `GET /user`, `GET /repos/kskt1234-netizen/code_review_agent` (응답의 login·permissions만 확인, 토큰 미출력) | 200 + push 권한 | PAT 재발급(scope: repo) 후 1회 재시도 |
| 10–25' | 데모 repo에 테스트 브랜치+PR 1개 생성 → `GET /pulls/{n}` (Accept: v3.diff)로 diff 수신 | diff 텍스트 수신 = **기준①** | API 응답 헤더·권한 확인, 15분 내 미해결 시 기준① 실패 기록 |
| 25–40' | 같은 PR에 코멘트 POST (`POST /issues/{n}/comments`, 테스트 후 삭제) | 201 = **기준②** | 403이면 scope 문제 — PAT 재발급 1회만 |
| 40–55' | `ngrok http 5000` 기동(authtoken 필요 시 등록) + server.py 로컬 기동(루트 .env 주입) → GitHub Webhooks에 URL+secret 등록 → ping/redelivery 200 | delivery 성공 | 서명검증 실패면 secret 일치 확인 1회, 그래도 실패면 secret 빈값(데모모드)로 격리 테스트 후 원인 기록 |
| 55–85' | 테스트 PR에 빈 커밋 push(synchronize) → 수신→diff조회→코멘트 E2E 1회. 이 30분간 터널 유지 관찰(40' 기동 기준 모니터링, 5분 간격 /health 체크) | E2E 코멘트 등록 + 끊김 없음 = **기준③** | 끊기면 1회 재기동 후 재관찰, 재발 시 기준③ 실패 |
| 85–90' | 체크리스트 집계 → go/no-go 권고 작성 → 정현에게 제출 | — | — |

## go 시 D4 연결 범위 (미리 합의)

server.py 골조 + fetch_pr_diff 재사용, 코멘트 POST는 urllib 직접 구현(≈20줄), 분석 호출부는
`src.graph.run_review()` 1줄로 교체. registry/DB/pr-comment-agent 코드는 가져오지 않는다.

## no-go 시

Streamlit 단독 시연 (장면1을 Streamlit에서 수행). 웹훅 재도전 없음 — D4 시간 보호.
