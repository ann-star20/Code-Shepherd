# Phase 0 중간보고서 — PR 웹훅 진입점

**일자**: 2026-06-12 | **브랜치**: `feature/module2-static-security`
**상태**: ✅ 완료 (pytest 전체 통과)

## 목표
설계가 "모듈별 end-to-end"로 전환됨에 따라 m1을 거치지 않고 **m2가 GitHub PR 웹훅을 직접 수신**한다.
Phase 1의 오케스트레이터를 호출하는 **입구**.

## 신규 파일
| 파일 | 역할 |
|------|------|
| `app/webhook.py` | `POST /webhook/github` — 서명검증 → 이벤트/action 필터 → payload 파싱 → diff fetch → `run_m2_orchestration` |
| `app/clients/github_client.py` | `diff_url` → unified diff fetch (GITHUB_TOKEN 있으면 인증, 실패 시 graceful `None`) |
| `tests/test_webhook.py` | 서명검증 4종 + 이벤트/action 필터 + 전체 흐름 |

## 수정 파일
- `app/main.py` — `app.include_router(webhook_router)`

## 처리 단계
1. **서명검증** — `X-Hub-Signature-256` HMAC-SHA256(`GITHUB_WEBHOOK_SECRET`). 불일치 시 401.
   secret 미설정(dev)이면 검증 생략.
2. **이벤트 필터** — `X-GitHub-Event != pull_request` 면 skip(ping 등 무시).
3. **action 필터** — `opened/reopened/synchronize/ready_for_review`만 처리, 그 외 skip.
4. **payload 파싱** — `pull_request`(id/number/user.login/diff_url), `repository.full_name`.
5. **diff fetch** — `diff_url`에서 본문 fetch(원본 웹훅엔 diff 본문 없음). 실패 시 skip.
6. **오케스트레이션** — `M2OrchestrateRequest` 구성 → `run_m2_orchestration()` 동기 실행 후 결과 반환.

## 결정한 잠정값 (plan 미결 → 구현 채택)
| 항목 | 결정 |
|------|------|
| 처리 모델 | **동기**(분석이 가벼움). 무거워지면 202 + 백그라운드로 전환 가능 |
| 서명 | secret 설정 시 강제, 미설정 시 생략(dev) |
| diff 소스 | `pull_request.diff_url` fetch |
| github_id | `pull_request.user.login` → `DeveloperProfile.id` |

## 배포 시 필요 (코드 아님)
- m2 컨테이너 **재빌드**(httpx 런타임 의존성).
- GitHub repo 웹훅을 **m2(8003) `/webhook/github`** 로 등록 + `GITHUB_WEBHOOK_SECRET` 공유.
