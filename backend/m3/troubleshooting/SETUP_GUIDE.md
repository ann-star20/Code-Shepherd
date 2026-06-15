# 로컬 환경 완전 세팅 가이드

이 문서대로 하면 팀원 로컬에서 PR 코드리뷰가 무조건 동작한다.

---

## 사전 요구사항

| 도구 | 버전 | 확인 |
|------|------|------|
| Docker Desktop | 최신 | `docker --version` |
| Git | - | `git --version` |
| Python | 3.10+ | `python --version` |
| ngrok | - | `ngrok --version` |
| Ollama | 최신 | `ollama --version` |

---

## STEP 1 — 레포 클론 & 브랜치

```bash
git clone https://github.com/ann-star20/Code-Shepherd.git
cd Code-Shepherd

# dev 브랜치로 (최신 통합 코드)
git checkout dev
git pull origin dev
```

---

## STEP 2 — .env 파일 설정

프로젝트 루트에 `.env` 파일 생성:

```bash
# .env 파일 내용 (팀장한테 실제 값 받을 것)

# Anthropic
ANTHROPIC_API_KEY=sk-ant-...

# GitHub (본인 Personal Access Token — repo 권한 필요)
GITHUB_TOKEN=ghp_...
GITHUB_REPO=ann-star20/Code-Shepherd   # 팀 레포
GITHUB_WEBHOOK_SECRET=                  # 팀 공통 시크릿 (팀장한테 받기)

# DB
DB_HOST=localhost
DB_PORT=5432
DB_NAME=codeshepherd
DB_USER=postgres
DB_PASSWORD=postgres
POSTGRES_URL=postgresql://postgres:postgres@localhost:5432/codeshepherd

# LangSmith (본인 GitHub ID로 교체)
LANGCHAIN_TRACING_V2=true
LANGCHAIN_API_KEY=                      # LangSmith에서 발급
LANGCHAIN_PROJECT=dev3-본인GitHub아이디

# m3 설정
ENABLE_DB_WRITE=false                   # 개발 중엔 false
USE_MOCK_LLM=false

# Ollama
OLLAMA_BASE_URL=http://host.docker.internal:11434
OLLAMA_EMBEDDING_MODEL=bge-m3
```

> ⚠️ `.env` 파일은 절대 Git 커밋하지 않는다

---

## STEP 3 — Ollama + bge-m3 세팅

```bash
# Ollama 서버 실행 (백그라운드)
ollama serve &

# bge-m3 모델 다운로드 (1.2GB, 최초 1회만)
ollama pull bge-m3

# 설치 확인
ollama list
# bge-m3:latest 보이면 OK
```

---

## STEP 4 — Docker 전체 스택 실행

```bash
# 전체 서비스 빌드 & 실행
docker-compose up -d --build

# 상태 확인 (모두 Up이어야 함)
docker ps --format "table {{.Names}}\t{{.Status}}"
```

**정상 상태:**
```
code-shepherd-new-m0-1        Up
code-shepherd-new-m1-1        Up
code-shepherd-new-m2-1        Up
code-shepherd-new-m3-1        Up
code-shepherd-new-m4-1        Up
code-shepherd-new-m5-1        Up
code-shepherd-new-frontend-1  Up
code-shepherd-new-api-core-1  Up
code-shepherd-new-redis-1     Up
```

> ℹ️ `cloud-sql-proxy`가 Restarting 상태여도 로컬 개발에는 무관

---

## STEP 5 — 헬스체크

```bash
# m3 정상 동작 확인
curl http://localhost:8004/health
# {"status": "ok", "adapter": "dev3"} 나오면 OK

# Ollama + bge-m3 확인
python backend/m3/_check_ollama.py
# 모든 항목 [OK] 나오면 OK
```

---

## STEP 6 — ngrok 설정

```bash
# ngrok 실행 (m1 포트 8001로 포워딩)
ngrok http 8001
```

출력에서 Forwarding URL 복사:
```
Forwarding  https://xxxx-xxx.ngrok-free.app -> http://localhost:8001
```

---

## STEP 7 — GitHub 웹훅 등록

데모 레포 (PR 코드리뷰를 받을 레포) 기준:

1. GitHub 레포 → **Settings** → **Webhooks** → **Add webhook**
2. 설정값:
   ```
   Payload URL:   https://xxxx-xxx.ngrok-free.app   ← STEP 6에서 복사한 URL
   Content type:  application/json
   Secret:        .env의 GITHUB_WEBHOOK_SECRET 값과 동일하게
   SSL:           Enable SSL verification
   Events:        Let me select individual events → Pull requests ✓
   Active:        ✓
   ```
3. **Add webhook** 클릭

---

## STEP 8 — 동작 테스트

```bash
# 로그 모니터링 켜기 (별도 터미널)
docker logs code-shepherd-new-m1-1 -f &
docker logs code-shepherd-new-m3-1 -f &
```

데모 레포에서 테스트 PR 생성 후 확인:

**m1 로그에서 보여야 할 것:**
```json
{"event": "pr_trigger_received", "level": "info"}
{"module": "m3", "endpoint": "/review", "status": 200}
{"event": "pr_trigger_dispatched", "comment_posted": true}
```

**m3 로그에서 보여야 할 것:**
```
INFO [node=assemble_input   ] OK    12ms
INFO [node=extract_concepts ] OK   890ms
INFO [node=retrieve         ] OK  1203ms
INFO [node=check_sufficiency] OK   430ms
INFO [node=judge            ] OK  9200ms
INFO [node=compose_comment  ] OK   320ms
```

**GitHub PR 코멘트에 리뷰 결과 달리면 완료** ✅

---

## 자주 발생하는 문제

### PR 만들었는데 m1 로그에 아무것도 안 찍힘
→ `DEBUG_GUIDE.md` CASE 1, 2 확인

### m1 로그에 `pr_trigger_dispatch_error`
→ PR close 후 reopen (bge-m3 warm-up 필요)

### m3 로그에 `FAIL extract_concepts`
→ ANTHROPIC_API_KEY 확인

### `react-force-graph-2d` 프론트 에러
```bash
docker-compose build --no-cache frontend
docker-compose up -d -V frontend
```

### m0 재빌드 실패 (opencv-python timeout)
→ 기존 이미지 그대로 사용 (재빌드 불필요)
```bash
docker-compose up -d m0   # 빌드 없이 기존 이미지로 실행
```
