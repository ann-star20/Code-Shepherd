# 통합 가이드 — 팀 compose에서 m3를 dev3로 교체

> D5 (2026-06-12). 원칙: **팀 파일 무수정** — docker-compose.yml·api-core·m0·frontend를 건드리지 않고
> override 파일 1개 추가로 교체한다. 계약은 `backend/_shared/shared/contracts.py` 정본과 필드 단위 일치
> (검증: docs/INTEGRATION_READINESS.md G1).

## 1. 이미지 빌드

```bash
cd <dev3-repo-root>
docker build -t dev3-m3:latest .
```

- 이미지에는 코드(src/·contracts/·corpus/)만 들어간다. **.env·키·인덱스는 미포함** (.dockerignore).

## 2. 팀 compose에 끼우기 — override 파일 (팀 파일 무수정)

`Code-Shepherd/docker-compose.override.yml` 을 **새로 추가**:

```yaml
services:
  m3:
    image: dev3-m3:latest
    build: !reset null          # 팀 m3 빌드 설정 무효화
    volumes:                    # 팀 volumes 대체 — 인덱스·캐시만 마운트
      - <dev3-repo-root>/.chroma:/app/.chroma
      - <dev3-repo-root>/.cache:/app/.cache
    environment:
      OLLAMA_BASE_URL: http://host.docker.internal:11434
      ENABLE_DB_WRITE: "false"
    command: uvicorn src.adapters.http_adapter:app --host 0.0.0.0 --port 8004
```

- `docker compose up -d m3` → m1(`M3_URL=http://m3:8004`)·프론트(`/m3-api`)는 **변경 없이 그대로 동작**.
- 원복: override 파일 삭제 후 `docker compose up -d m3`.
- Linux 호스트(WSL 아님)에서는 `extra_hosts: ["host.docker.internal:host-gateway"]` 추가 필요
  (Docker Desktop은 자동 지원).

## 3. 인덱스 준비

볼륨 마운트(권장): 호스트에서 `make reindex` 해 둔 `.chroma`/`.cache`를 그대로 공유.
인덱스가 없으면 컨테이너에서 1회:

```bash
docker exec <m3-container> python -m src.ingestion
```

핫스왑 시연 시: 호스트에서 corpus 수정 → `make reindex` → **컨테이너 재시작** (Chroma 핸들 캐시 갱신).

## 4. 직접실행 ↔ 도커 .env 차이 (전환은 .env만으로)

| 변수 | 직접실행 (uvicorn 로컬) | 도커 컨테이너 |
|---|---|---|
| `OLLAMA_BASE_URL` | `http://localhost:11434` (기본값) | `http://host.docker.internal:11434` (Dockerfile ENV 기본) |
| `EMBEDDING_PROVIDER` | `ollama` (기본) / 폴백 `openai` | 동일 |
| `ENABLE_DB_WRITE` | `false` (기본) — eval·개발 중 INSERT 금지 | `false` — E2E 검증 시에만 `true` |
| `ANTHROPIC_API_KEY` 등 키 4종 | repo 루트 `.env` | `env_file: .env` 로 주입 (이미지 미포함) |
| `POSTGRES_URL` | 실 Cloud SQL URL (G3) | 동일 — 컨테이너에서 Cloud SQL 직접 접속 |

주의: `.env`에 `OLLAMA_BASE_URL=http://localhost:11434`를 **명시하면 컨테이너에서 깨진다**
(env_file이 Dockerfile ENV를 덮음). 직접실행은 기본값으로 충분하므로 .env에는 넣지 않는 것을 권장.

## 5. 직접 실행 (도커 없이)

```bash
.venv/Scripts/uvicorn src.adapters.http_adapter:app --port 8004
```

m1을 로컬에서 직접 띄우는 경우 `M3_URL=http://localhost:8004` 로 지정.

## 6. 동작 확인

```bash
curl http://localhost:8004/health
# {"status":"ok","adapter":"dev3"}
curl -X POST http://localhost:8004/review -H "Content-Type: application/json" \
  -d '{"task_id":"t1","pr_id":"4","repository":"kskt1234-netizen/-dev3-demo","pr_number":4}'
```

응답 스키마: M3ReviewResponse (task_id, pr_id, verdict, comment_posted, comment_url, persisted
[+ 옵셔널 trace — m1은 무시]).

## 7. 알려진 제약

- m1 호출 타임아웃 60초: LLM 캐시 미스 시 파이프라인 ~25-40초 — 통과하지만 여유 적음.
  리허설로 캐시를 워밍하면 <5초.
- diff 소스: M3ReviewRequest에 diff가 없으므로 GITHUB_TOKEN으로 GitHub API에서 직접 fetch.
  private repo는 토큰 권한 필요.
- DB(review_issue) 적재: ENABLE_DB_WRITE=true + 실 POSTGRES_URL + psycopg2-binary 설치 시 활성.
  현재 mock 검증 완료, 실 DB는 접속정보 확보 대기 (G3).
