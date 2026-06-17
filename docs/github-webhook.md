# GitHub PR Webhook 설정

팀 생성 시 등록한 `owner/repo`와 **동일한 저장소**에 웹훅을 연결해야 PR이 `pull_requests` 테이블에 적재됩니다.

## 엔드포인트

- **URL**: `http(s)://<m1-host>:8001/triggers/pr`
- **Content type**: `application/json`
- **Secret**: `.env`의 `GITHUB_WEBHOOK_SECRET` (HMAC SHA-256)
- **Events**: Pull requests

## 흐름

1. GitHub → m1 `POST /triggers/pr` (서명 검증)
2. m1 → api-core `POST /internal/pr-ingest` (`X-Internal-Token: INTERNAL_SERVICE_TOKEN`)
3. api-core: `teams.github_repo_full_name` 매칭 → 작성자 `users.github_id` → `pull_requests` upsert
4. m1: m2/m3/m4 스텁 파이프라인 (기존과 동일)
5. UI: `GET /teams/{team_id}/prs` — 팀장은 팀 전체, 팀원은 본인 PR만

## ingest가 스킵되는 경우 (HTTP 200, `status: "skipped"`)

- 등록되지 않은 repository
- GitHub login이 플랫폼에 없음
- PR 작성자가 해당 팀 멤버가 아님

## 로컬 compose

`docker-compose.yml`의 m1·api-core는 동일 `.env`를 사용합니다. 최소값:

```env
GITHUB_WEBHOOK_SECRET=<github-webhook-secret>
INTERNAL_SERVICE_TOKEN=dev-internal-token
API_CORE_URL=http://api-core:8000
```
