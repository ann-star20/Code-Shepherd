# Code-Shepherd m3(DEV3) — 다음 세션 컨텍스트 전달

> 작성: 2026-06-08  
> 대상: 새 대화창을 열 때 이 문서를 통째로 붙여넣어 컨텍스트를 복원한다.

---

## 0. 프로젝트 한 줄 요약

**Code-Shepherd** — 멀티에이전트 GitHub PR 자동 코드리뷰 플랫폼.  
에이전트: m0(KMS) · m1(오케스트레이터) · m2(정적/보안) · **m3(테스트/성능, 내 담당)** · m4(커리큘럼/판정) · m5(그래프/유튜브)  
레포: `C:\Users\user\Code-Shepherd`  
m3 루트: `backend/m3/`

---

## 1. 지금까지 완성된 것 (SESSION 1~5 결과)

| 세션 | 완성 내용 | 상태 |
|------|-----------|------|
| SESSION 1 | RAG 로컬 검증 — conventions/ 6종 임베딩, top-k 검색 score≥0.5, 18테스트 green | ✅ |
| SESSION 2/2B | m3/app/main.py 실분석 연결 (clone→sandbox→run()→IssueItem), 358테스트 green | ✅ |
| SESSION 3 | 로컬 풀스택 e2e — m1 웹훅 → m3 분석 → 이슈 6건 실측, GitHub PR에 진짜 코멘트 달림 | ✅ |
| SESSION 4 | /review 엔드포인트 (집계→판정→Gemini코멘트→GitHub게시→DB저장), GET /review 조회 API | ✅ |
| SESSION 5 | 프론트 PR 코드리뷰 페이지 (2-pane: PR목록 + 판정뱃지·이슈테이블·LLM코멘트), 21 frontend tests green | ✅ |

### 실제로 돌아가는 풀 파이프라인 (검증 완료)
```
GitHub PR 오픈
  → ngrok → m1(8001) /triggers/pr
  → diff_url fetch → pr_diff=본문, clone_url, commit_sha 채움
  → m3(8004) /verify/tests + /analyze/performance
  → m3 /review: 집계 → 판정(verdict) → Gemini코멘트 → GitHub코멘트 게시 → SQLite저장
  → 프론트(5173) /review 페이지: PR선택 → 판정뱃지 + 이슈테이블 + 코멘트 표시
```

---

## 2. 현재 아키텍처 핵심 사항 (코드 수정 시 필수 숙지)

### 파일 위치
| 역할 | 파일 |
|------|------|
| m3 FastAPI 앱 | `backend/m3/app/main.py` |
| 계약(Contract) | `backend/_shared/shared/contracts.py` — M3VerifyRequest, M3ReviewRequest, M3ReviewResponse |
| 판정·집계 | `backend/m3/pr-comment-agent/aggregator.py` |
| LLM 코멘트 | `backend/m3/pr-comment-agent/llm_refiner.py` (GOOGLE_API_KEY 필요) |
| GitHub 게시 | `backend/m3/pr-comment-agent/github_poster.py` (GITHUB_TOKEN 필요) |
| DB 저장/조회 | `backend/m3/test-performance-agent/persist.py` — SQLite `dev3_demo.db` (로컬) / PostgreSQL (운영) |
| 웹훅 트리거 | `backend/m1/app/routers/triggers.py` — diff_url fetch + m3 /review 호출 |
| 프론트 리뷰 페이지 | `frontend/src/pages/review/ReviewPage.tsx` |
| API 함수 | `frontend/src/lib/api.ts` — reviewApi.getTeamPRs, reviewApi.getReview |
| vite 프록시 | `frontend/vite.config.ts` — /m3-api → localhost:8004 |

### 중요 설계 결정
- **m4 우회**: 판정·코멘트는 m3(DEV3)가 직접 소유. m1 → m3 /review 직접 호출.
- **pr_diff = diff 본문 텍스트** (URL 아님). m1이 diff_url fetch → 본문을 pr_diff에 담아 전송.
- **DB**: 로컬=SQLite(`dev3_demo.db`, .gitignore 처리됨), 운영=PostgreSQL(persist_pg 이미 구현됨).
- **RAG**: BGE-M3(1024차원), `convention_embeddings` 테이블 직접 pgvector 검색. 로컬은 SQLite에 별도 적재.
- **토큰 없으면 정직하게 skip**: GITHUB_TOKEN 없으면 comment_posted=false, GOOGLE_API_KEY 없으면 표준양식 fallback.

### 환경변수 (m3 프로세스에 필요한 것)
```
GITHUB_TOKEN=ghp_xxx        # PR 코멘트 게시 (webhook-gateway/.env 값 재사용)
GOOGLE_API_KEY=AIza_xxx     # Gemini LLM 코멘트 생성 (없으면 짧은 템플릿)
```
→ `backend/m3/.env` 에 넣고 m3 재시작하면 로딩됨.

---

## 3. 로컬 실행 방법 (매 세션 시작 시)

```powershell
# 각 서비스를 별도 터미널에서 실행
# api-core (8000)
cd backend/api-core && uvicorn app.main:app --reload --port 8000

# m1 오케스트레이터 (8001)
cd backend/m1 && uvicorn app.main:app --reload --port 8001

# m2 (8003, stub)
cd backend/m2 && uvicorn app.main:app --reload --port 8003

# m3 (8004) — .env에 GITHUB_TOKEN, GOOGLE_API_KEY 있어야 함
cd backend/m3 && uvicorn app.main:app --reload --port 8004

# 프론트 (5173)
cd frontend && npm run dev
```
헬스체크: `GET http://localhost:8004/review/x/y/999` → `{"found":false}` + 200 = 새 코드 살아있음.

---

## 4. 남은 작업 목록 (우선순위 순)

### 🔴 즉시 가능 (다음 세션에서 바로)

#### A. SESSION_5 프론트 커밋 (미완료)
마지막 세션에서 프론트 작업 완료됐지만 커밋이 안 됐을 수 있음.
확인: `git status` → `frontend/` 변경분 있으면 커밋.
```
커밋 메시지:
feat(frontend): PR 코드리뷰 페이지 — m3 /review 결과 화면 표시
- pages/review/ReviewPage: PR목록 + 판정뱃지·이슈테이블·LLM코멘트 + 상태처리(로딩/빈/에러)
- App.tsx: /review 라우트 Placeholder → ReviewPage
- lib/api.ts: m3Client + reviewApi.getTeamPRs/getReview
- vite.config: /m3-api → m3:8004 프록시(로컬 dev, prod TODO)
- test: ReviewPage 5개 + Node25 localStorage 폴리필(기존 테스트 회생) → 프론트 21 passed
```
(실제로는 git log 보면 이미 커밋됐을 수 있음 — 확인 먼저)

#### B. Gemini 코멘트 품질 검증
m3 루트에 `.env` 만들어서 `GOOGLE_API_KEY` 넣은 상태 + Docker 켜진 상태에서:
1. m3 재시작 (`Ctrl+C` → `uvicorn app.main:app --reload --port 8004`)
2. 데모 레포 PR#4 Close→Reopen (웹훅 발사)
3. 확인: GitHub PR에 Gemini 상세 코멘트 달렸는지 + 이슈 6건(Docker 켜면 TEST-001/004 포함)

---

### 🟡 SESSION B — async/202 (GitHub timeout 완전 해결)

**문제**: GitHub은 웹훅 응답을 10초 안에 기대하는데, m3 분석은 13~41초 걸림 → GitHub이 "timed out" 표시.  
**현재**: m1이 끝까지 완료하므로 코멘트는 달리지만, GitHub 웹훅 화면에 실패처럼 보임. 재시도 위험도 있음.

**해결 방향**: m1이 웹훅 수신 즉시 202 응답 + 분석은 백그라운드 태스크로.
```python
# backend/m1/app/routers/triggers.py 변경 방향
@router.post("/triggers/pr")
async def pr_webhook(request: Request, background_tasks: BackgroundTasks):
    # 1. 서명 검증 (빠름)
    # 2. 202 즉시 응답
    background_tasks.add_task(dispatch_to_agents, payload)
    return Response(status_code=202)
```

**작업 범위**: `backend/m1/app/routers/triggers.py` 수정 + 관련 테스트.
**세션 프롬프트**: `backend/m3/SESSION_B_async_202.md` 새로 작성 필요.

---

### 🟡 SESSION C — 자동화 (웹훅 + 토큰 한방에)

**문제**: 지금 수동으로 해야 하는 것 3개:
1. ngrok 켜서 주소 복사
2. GitHub 레포 Settings에서 웹훅 직접 등록
3. GITHUB_TOKEN 수동으로 .env에 넣기

**선택지 (팀 상의 필요)**:
- **A. GitHub App** (권장): 레포에 App 설치 시 웹훅 자동 등록 + 설치 토큰 자동 발급. 안전, 초기 셋업 있음.
- **B. OAuth 스코프 확장**: 기존 로그인에 `repo`+`admin:repo_hook` 스코프 추가 → access_token 저장. 빠름, 권한 넓음.

**담당 영역**: api-core(인증·웹훅생성·토큰저장) + frontend(등록 UI) + m3(게시 토큰 연결) + 인프라(배포/App).
→ m3 혼자 못 하는 일. **팀 협업 필요**.

**계획 문서**: `backend/m3/SESSION_C_자동화_웹훅_토큰_계획.md`

---

### 🟡 GCP PostgreSQL 실 DB 전환

**현재**: SQLite `dev3_demo.db` (로컬 파일, .gitignore됨, 재시작마다 초기화 가능).  
**목표**: GCP Cloud SQL(PostgreSQL) + pgvector → review_results, scan_issues도 운영 DB에 저장.

**이미 있는 것**:
- `persist.py`에 `persist_pg()` 함수 이미 구현 완료
- GCP scan_issues DDL: `HANDOFF_scan_issues_Dev2통일_컬럼.md`
- pgvector `convention_embeddings` 테이블: RAG 설계서에 스키마 있음

**남은 것**:
1. GCP PostgreSQL 인스턴스에 `review_results` 테이블 DDL 추가
   ```sql
   CREATE TABLE IF NOT EXISTS review_results (
       owner      TEXT NOT NULL,
       repo       TEXT NOT NULL,
       pr_number  INTEGER NOT NULL,
       verdict    TEXT NOT NULL,
       comment    TEXT,
       issues     JSONB,
       created_at TIMESTAMPTZ DEFAULT now(),
       PRIMARY KEY (owner, repo, pr_number)
   );
   ```
2. `persist.py`에 `save_review_pg()` 함수 추가 (현재 SQLite만)
3. m3 `.env`에 `POSTGRES_URL` 추가 → m3 재시작 → SQLite 대신 PG 사용
4. KMS 팀원이 conventions/ 6종 임베딩 후 `convention_embeddings` 테이블에 적재 → RAG 실검색 전환

**세션 프롬프트**: `backend/m3/SESSION_D_GCP_DB전환.md` 새로 작성 필요.

---

### 🟢 선택적 고도화

#### 마크다운 렌더링
현재 코멘트 본문은 `whitespace-pre-wrap`으로 표시. Gemini가 마크다운으로 작성하므로 렌더링하면 더 보기 좋음.
```bash
cd frontend && npm install react-markdown
```
`ReviewPage.tsx`에서 `<pre>` → `<ReactMarkdown>` 교체.

#### 리뷰 페이지 UX 개선
- 이슈 severity별 필터
- PR 상태 필터 (lgtm/rework/escalate)
- 실시간 분석 진행상황 표시 (WebSocket or SSE)

#### Docker 없이 커버리지 측정
현재 `run_sandbox()`가 Docker 필요. Docker 없는 환경에서는 TEST-001/004 미탐지.
→ `pytest --cov` 직접 실행 방식으로 fallback 추가.

---

## 5. 자주 쓰는 검증 명령어

```powershell
# m3 헬스 + 저장된 리뷰 결과 조회
Invoke-WebRequest http://localhost:8004/review/kskt1234-netizen/-dev3-demo/4 | ConvertFrom-Json

# m3 전체 테스트
cd backend/m3 && python -m pytest --tb=short -q

# 프론트 테스트
cd frontend && npm test -- --run

# git 상태 확인
git -C C:\Users\user\Code-Shepherd status
git -C C:\Users\user\Code-Shepherd log --oneline -5
```

---

## 6. ngrok 사용법 (매번 필요)

```powershell
# 터미널 1개 켜서 (m1이 떠있어야 함)
& "C:\ngrok\ngrok.exe" http 8001
```
→ 나오는 `https://xxxx.ngrok-free.dev` 주소를 GitHub 웹훅 Payload URL로 등록:
- Payload URL: `https://xxxx.ngrok-free.dev/triggers/pr`
- Content type: `application/json`
- Secret: 루트 `.env`의 `GITHUB_WEBHOOK_SECRET` 값
- Events: Pull requests

> ⚠️ ngrok 무료 = 재시작마다 주소 바뀜 → GitHub 웹훅도 다시 등록해야 함.
> 상세: `docs/ngrok_로컬_웹훅_테스트_가이드.md`

---

## 7. 트러블슈팅 빠른 표

| 증상 | 원인 | 해결 |
|------|------|------|
| 코멘트가 짧은 템플릿 | GOOGLE_API_KEY 없음 | `backend/m3/.env`에 KEY 추가 → m3 재시작 |
| 이슈 2건(perf만) | Docker 꺼져서 커버리지 측정 안 됨 | Docker Desktop 켜고 m3 재시작 |
| GitHub 웹훅 "timed out" | 분석 13~41초 > GitHub 10초 | 정상. m1은 끝까지 완료·코멘트는 달림. SESSION_B에서 async로 해결 예정 |
| 웹훅 401 | secret 불일치 | GitHub 웹훅 Secret = 루트 `.env`의 `GITHUB_WEBHOOK_SECRET` |
| 웹훅 404 | 레포/유저 미등록 | localhost:5173 로그인 → 팀 생성 + 레포 `kskt1234-netizen/-dev3-demo` 등록 |
| 페이지 비어있음 | m3 옛코드 또는 결과 없음 | `GET /review/.../4` → found:false면 PR 한 번 더 흐르게 |
| ngrok 실행 안 됨 | PATH 문제 | `& "C:\ngrok\ngrok.exe" http 8001` (전체경로 사용) |

---

## 8. 다음 세션 추천 시작 프롬프트

### SESSION B (async) 착수 시
```
너는 우리 팀 시니어 백엔드 엔지니어다.
작업 디렉토리: C:\Users\user\Code-Shepherd\backend\m1

[목표]
GitHub 웹훅이 10초 안에 응답을 받지 못해 "timed out"이 뜬다.
m1이 웹훅 수신 즉시 202 반환 + 분석을 FastAPI BackgroundTasks로 비동기 처리하도록 변경한다.

[현재 코드]
backend/m1/app/routers/triggers.py 에서 POST /triggers/pr 가
서명검증 → 동기로 m3 호출 → 결과 반환하는 구조.
m3 분석이 13~41초 걸려서 GitHub 10초 timeout 발생.

[변경 내용]
1. /triggers/pr 에서 서명 검증 후 즉시 202 응답
2. dispatch_to_agents(payload) 를 BackgroundTasks로 실행
3. 분석 결과/에러는 로그에만 (콜백 없음, 폴링은 /review GET으로)

[TDD]
- 웹훅 POST → 202 즉시 반환 확인
- 백그라운드에서 m3 호출됨 확인 (mock)
- 기존 서명검증 테스트 green 유지
```

### SESSION D (GCP DB) 착수 시
```
너는 우리 팀 시니어 백엔드 엔지니어다.
작업 디렉토리: C:\Users\user\Code-Shepherd\backend\m3

[목표]
m3가 현재 SQLite(dev3_demo.db)에 저장 중인 리뷰 결과(review_results)를
GCP PostgreSQL로 전환한다.

[현재 상태]
- persist.py에 persist_pg() 함수 있음 (scan_issues용)
- save_review(), get_review() 는 SQLite만 지원
- POSTGRES_URL 환경변수가 있으면 PG, 없으면 SQLite fallback 패턴으로 통일

[변경 내용]
1. persist.py에 save_review_pg(owner, repo, pr_number, verdict, comment, issues, conn=None) 추가
2. save_review() / get_review() 에 POSTGRES_URL 있으면 PG, 없으면 SQLite fallback
3. review_results PG DDL (TEXT/JSONB, PRIMARY KEY) 작성
4. GCP DB에 review_results 테이블 마이그레이션

[TDD]
- SQLite fallback: POSTGRES_URL 없을 때 기존 동작 유지
- PG 경로: psycopg2 mock으로 INSERT/SELECT 검증
```

---

## 9. 전체 세션 히스토리 (참고용)

```
SESSION 1  → RAG 로컬 검증 (pgvector, BGE-M3, conventions 6종)
SESSION 2  → m3/app/main.py 실분석 연결 (clone→sandbox→run()→IssueItem)
SESSION 2B → m1 실값 통합검증 (diff 본문 전달, 이슈 6건 실측)
SESSION 3  → 로컬 풀스택 e2e (ngrok, 웹훅, 진짜 PR 코멘트 달림)
SESSION 4  → /review 엔드포인트 (판정·코멘트·게시·저장)
SESSION 5  → 프론트 PR 리뷰 페이지 (2-pane, 21 tests)
SESSION B  → (예정) async/202 GitHub timeout 해결
SESSION C  → (예정, 팀 상의) 웹훅+토큰 자동화
SESSION D  → (예정) GCP PostgreSQL 전환
```

---

> 이 문서를 새 대화창 첫 메시지에 붙여넣으면 이전 세션의 모든 맥락이 복원된다.
> 작업하려는 SESSION 번호를 말하면 해당 세션 프롬프트를 기준으로 바로 시작한다.
