# code-shepherd 베이스라인 개발 프롬프트 (AI-native · TDD)

---

## 0. 너(에이전트)의 역할과 기본 자세

너는 나와 페어로 일하는 시니어 풀스택 엔지니어다. 이 작업의 산출물은 **다른 팀원들이 각자의 모듈(M0·M2·M3·M4)을 채워 넣을 모노레포 골격(baseline)**이다. 나는 골격만 만들고, 모듈의 실제 비즈니스 로직은 만들지 않는다.

기본 자세:
- **테스트 우선(TDD).** 구현 코드를 쓰기 전에 그 동작을 기술하는 **실패하는 테스트를 먼저 작성**한다. 테스트가 곧 명세다. (상세는 3장)
- **실제로 동작하는 최소 코드**를 쓴다. 의사코드·TODO 더미로 떼우지 말 것. 단, 모듈 비즈니스 로직은 스텁으로 둔다.
- 변경은 **서비스 단위로 스코프**를 좁혀서 한다. 한 번에 여러 서비스를 휘젓지 않는다.
- 큰 변경 전에는 **계획을 먼저 요약**하고, 막힐 때만 질문한다. 스펙에 없는 의존성을 추가하려면 먼저 묻는다.
- 각 서비스 디렉토리에 짧은 `README.md`를 남긴다(실행법·담당 범위·확장 지점).

---

## 1. 목표

`code-shepherd` 멀티 에이전트 플랫폼의 베이스라인을 구축한다. 백엔드를 서비스별로 분리한 이유는 **팀원들이 모듈을 나눠 개발할 때 머지 충돌을 최소화**하기 위함이다. 이 원칙을 모든 설계 결정의 기준으로 삼는다.

---

## 2. 절대 규칙 (하드 제약 — 위반 금지)

**DO — 직접 구현한다**
1. `backend/api-core`: GitHub OAuth 로그인, `users`/`teams`, 팀 기반 조회·권한, JWT 인증/세션, 헬스체크 등 **M0·M2·M3·M4를 제외한 서비스 공통 기능 전부**.
2. `backend/m1` (오케스트레이터): PR 웹훅 + 문서 업로드 완료 신호 인입 → 트리거 분류 → 하위 모듈(M0·M2~M4) **호출 골격 + 트레이스 로깅**.
3. `frontend`: 로그인, 앱 레이아웃(노션 스타일 사이드바), 대시보드 홈, 사용자/팀 화면, 설정 등 **기본 화면**.

**DON'T — 절대 구현하지 않는다**
1. M0·M2·M3·M4의 **실제 비즈니스 로직**(LangGraph 파이프라인, 임베딩, 청킹, pytest 샌드박스, 커리큘럼 생성 알고리즘 등). → 각 모듈은 `/health` + 오케스트레이터가 호출할 **빈 엔드포인트 스텁**만 둔다(요청을 받아 200과 고정 더미 응답 반환).
2. M1 오케스트레이터에서 **하위 모듈 내부 로직**. → 호출(httpx)만 하고 결과는 받아서 트레이스 로깅까지만.
3. 비밀값(클라이언트 시크릿, DB 비밀번호, HMAC 시크릿 등)을 코드/깃에 하드코딩. → 전부 `.env` + `.env.example`로 분리하고 `.gitignore` 처리.
4. **새 Cloud SQL 인스턴스 생성**. → 팀이 이미 만든 인스턴스에 **Cloud SQL Auth Proxy로 연결만** 한다(테스트 DB도 같은 인스턴스 안에 만든다).

---

## 3. TDD 개발 방법론 (필수 — 모든 Phase에 적용)

### 3.1 핵심 원칙
- **Red → Green → Refactor.** 항상 실패하는 테스트부터.
- **테스트가 명세다.** 요구사항(6장)을 코드가 아니라 테스트로 먼저 표현한다.
- **테스트와 구현을 함께 커밋**한다. 구현만 따로 들어오지 않는다.
- **스텁은 계약만 테스트**한다. m0/m2/m3/m4는 로직이 없으므로 비즈니스 로직 테스트를 만들지 않는다(만들면 DON'T 위반). 대신 "엔드포인트가 계약 DTO를 받아 계약 형태로 200을 반환"하는 **계약 테스트**만 둔다 — 이것이 모듈 팀의 인터페이스 가드레일이 된다.

### 3.2 에이전트가 각 작업에서 지킬 루프
1. 요구사항 하나를 **실패하는 테스트**로 작성한다.
2. 테스트를 실행해 **RED**임을 확인하고 보고한다(어떤 테스트가 왜 실패하는지).
3. 테스트를 통과할 **최소 구현**을 한다.
4. 테스트를 실행해 **GREEN**을 확인한다.
5. 테스트가 green인 상태로 **리팩터**한다(중복 제거·정리).
6. **커버리지 게이트**를 확인한다. 미달이면 테스트를 보강한다.
- 한 루프는 작게 유지한다. 막히면 구현을 강행하지 말고 질문한다.

### 3.3 TDD 적용 범위
- **풀 TDD**: `api-core`(인증·팀·권한 가드), `m1`(HMAC 검증·트리거 분류 라우팅·호출 디스패치·트레이스 로깅), `frontend`(기본 화면·라우팅 가드).
- **계약/헬스 테스트만**: `m0`·`m2`·`m3`·`m4` 스텁.

### 3.4 테스트 종류와 도구
- **백엔드 단위 테스트**: pytest, pytest-asyncio, pytest-cov. 외부 의존(DB·GitHub·하위 모듈)은 모킹.
  - FastAPI 호출: `httpx.AsyncClient` + `ASGITransport`.
  - 아웃바운드 httpx(오케스트레이터→모듈, OAuth→GitHub): `respx`로 모킹.
- **백엔드 통합 테스트**: 실제 DB 스키마가 필요한 경우 **기존 Cloud SQL 인스턴스 내 테스트 DB**에 Auth Proxy로 접속, **테스트마다 트랜잭션 롤백**(nested transaction/savepoint)으로 격리. 새 인스턴스 금지 규칙 준수.
- **프론트엔드**: Vitest + React Testing Library(컴포넌트), MSW(API 모킹). 로그인→대시보드 흐름은 Playwright e2e(선택).
- **CI(선택, 권장)**: GitHub Actions에서 PR마다 `pytest`(서비스별) + `vitest` 실행, 커버리지 게이트 강제.

### 3.5 커버리지 게이트
- `api-core`, `m1`: 라인 커버리지 **≥ 80%**(PRD의 80% 기조와 일치).
- 스텁(m0/m2/m3/m4): 로직 커버리지 제외, **계약·헬스 테스트 존재**만 확인.
- 프론트엔드: 핵심 컴포넌트/가드/페이지에 대한 테스트 존재.

---

## 4. 기술 스택 (버전 고정, 임의 변경 금지)

**백엔드 (각 서비스 공통)**
- Python 3.12, 패키지 매니저 `uv`, 서비스별 `pyproject.toml`
- FastAPI, Uvicorn
- SQLAlchemy 2.0 (async) + asyncpg, Alembic
- Pydantic v2 / pydantic-settings
- 인증: Authlib(OAuth) + PyJWT
- 서비스 간 호출: httpx (async)
- 로깅: structlog (JSON 로그 + correlation/trace id)
- **테스트: pytest, pytest-asyncio, pytest-cov, respx, httpx(AsyncClient)**

**프론트엔드 (단일 서비스)**
- React 18 + Vite + TypeScript
- Tailwind CSS + shadcn/ui (노션 스타일 사이드바 레이아웃)
- 라우팅: React Router
- 서버 상태/캐싱: TanStack Query
- HTTP: fetch 래퍼 또는 axios (JWT 자동 첨부)
- **테스트: Vitest, React Testing Library, MSW, (선택) Playwright**

**인프라**
- Docker: 백엔드는 **서비스별 Dockerfile**, 프론트엔드는 **단일 Dockerfile**
- 루트 `docker-compose.yml`로 통합, **개발 단계부터 compose 사용**
- `cloud-sql-proxy` 컨테이너로 Cloud SQL 접속(로컬 Postgres 컨테이너 두지 않음)

**DB (이미 프로비저닝됨 — 연결만)**
- Google Cloud SQL: PostgreSQL 18 + `pgvector` 확장 설치 가정
- 운영/개발용 DB와 별개로 **같은 인스턴스 내 테스트 DB**(예: `codeshepherd_test`) 사용

---

## 5. 디렉토리 구조 (정확히 이대로 생성)

```
code-shepherd/
├── backend/
│   ├── _shared/                 # 횡단 관심사 전용 얇은 공유 패키지
│   │   ├── pyproject.toml
│   │   ├── config.py            # pydantic-settings 기반 설정 로더
│   │   ├── db.py                # async SQLAlchemy 엔진/세션 헬퍼
│   │   ├── auth.py              # JWT 발급/검증 (모든 서비스 일관)
│   │   ├── logging.py           # structlog 설정 + trace id 미들웨어
│   │   ├── contracts.py         # 서비스 간 요청/응답 Pydantic DTO (계약)
│   │   └── testing.py           # 공용 테스트 픽스처(앱 클라이언트·DB 롤백 세션)
│   ├── api-core/
│   │   ├── Dockerfile
│   │   ├── pyproject.toml
│   │   ├── alembic/             # 공통 스키마 마이그레이션 (실제 채움)
│   │   ├── app/
│   │   │   ├── main.py
│   │   │   ├── routers/         # auth, users, teams, health
│   │   │   ├── models/          # users, teams, team_members, sessions
│   │   │   └── services/
│   │   ├── tests/               # 인증·팀·권한 가드 테스트 (풀 TDD)
│   │   └── README.md
│   ├── m1/                      # 오케스트레이터 (스켈레톤 실제 구현)
│   │   ├── Dockerfile
│   │   ├── pyproject.toml
│   │   ├── app/
│   │   │   ├── main.py
│   │   │   ├── routers/         # triggers, health
│   │   │   └── clients/         # m0/m2/m3/m4 httpx 클라이언트
│   │   ├── tests/               # HMAC·분류·디스패치·트레이스 테스트
│   │   └── README.md
│   ├── m0/                      # 스텁 (KMS — 담당자 채움)
│   │   ├── Dockerfile
│   │   ├── pyproject.toml
│   │   ├── alembic/             # 빈 마이그레이션 골격
│   │   ├── app/main.py          # /health + 빈 엔드포인트 스텁
│   │   ├── tests/               # 계약·헬스 테스트만
│   │   └── README.md
│   ├── m2/                      # 스텁 (정적분석·보안)  ── m0과 동일 구조
│   ├── m3/                      # 스텁 (테스트·성능)    ── m0과 동일 구조
│   └── m4/                      # 스텁 (커리큘럼·판정)  ── m0과 동일 구조
├── frontend/
│   ├── Dockerfile
│   ├── package.json
│   ├── vite.config.ts           # vitest 설정 포함
│   ├── tailwind.config.ts
│   └── src/
│       ├── main.tsx
│       ├── App.tsx              # 라우터 + 인증 가드
│       ├── layouts/AppLayout.tsx  # 노션 스타일 사이드바
│       ├── lib/                 # api client, auth context
│       ├── components/
│       ├── pages/               # 페이지별 파일 (팀원이 본인 파일만 수정)
│       │   ├── Login.tsx
│       │   ├── DashboardHome.tsx
│       │   ├── Team.tsx
│       │   ├── Settings.tsx
│       │   ├── kms/Placeholder.tsx
│       │   ├── review/Placeholder.tsx
│       │   ├── learning/Placeholder.tsx
│       │   └── graph/Placeholder.tsx
│       └── test/                # MSW 핸들러·테스트 셋업
├── docker-compose.yml
├── .env.example
├── .gitignore
└── README.md
```

---

## 6. 컴포넌트별 상세 요구사항 (각 항목은 테스트 먼저 작성)

### 6.1 `backend/_shared`
- **횡단 관심사만** 담는다(설정, DB 세션, JWT, 로깅, 계약, 테스트 픽스처). 비즈니스 로직·도메인 모델은 넣지 않는다.
- `auth.py`: JWT 발급/검증 함수, FastAPI 의존성(`get_current_user`).
- `db.py`: async 엔진/세션팩토리, `get_session` 의존성. DSN은 설정에서 주입.
- `logging.py`: structlog JSON 설정 + 요청별 `trace_id` 주입 미들웨어.
- `contracts.py`: 오케스트레이터↔모듈 간 요청/응답 DTO(6.3 계약). 계약의 단일 출처(SSoT).
- `testing.py`: 앱별 `AsyncClient` 픽스처, **트랜잭션 롤백 세션 픽스처**, 테스트 DB 설정.
- **테스트 초점**: JWT 발급→검증 라운드트립, 만료/위조 토큰 거부.

### 6.2 `backend/api-core` (전부 구현)
- **GitHub OAuth 로그인**: authorize 리다이렉트 → callback → 프로필 조회 → `users` upsert → JWT 발급. 로그인용 OAuth만(웹훅/PR 코멘트용 GitHub App은 범위 밖).
- **users**: `id`, `github_id`, `login`, `name`, `avatar_url`, `created_at`.
- **teams / team_members**: 사용자끼리 팀 구성. `role`(`lead` | `member`). **팀장(lead)은 팀원의 PR과 현황을 조회** 가능.
- **인증/세션 엔드포인트**:
  - `GET /me` — 내 정보.
  - `POST /auth/logout` — 현재 세션 무효화(`sessions` 레코드 삭제/만료 처리). 이후 같은 토큰으로 보호 라우트 접근 시 401.
  - (이미 명시) authorize/callback, JWT 발급·**갱신(refresh)**·검증.
- **사용자 엔드포인트**:
  - `GET /users?search=` — login/name 부분일치 검색. **팀원 추가 UI의 사용자 선택을 위해 필수.** 인증 필요. 결과는 `id`,`login`,`name`,`avatar_url`만 노출(이메일 등 민감정보 제외).
- **팀 엔드포인트**:
  - `GET /teams` — **내가 속한 팀만** 반환.
  - `POST /teams` — 팀 생성. **생성자는 자동으로 `lead`로 `team_members`에 등록.**
  - `PATCH /teams/{id}` — 팀 이름 등 수정. **lead만.**
  - `DELETE /teams/{id}` — 팀 삭제(soft delete 권장). **lead만.**
- **팀 멤버 엔드포인트** (별도 명시 없으면 **추가/제거/역할변경은 lead만**):
  - `GET /teams/{id}/members` — 멤버 목록(팀 소속이면 조회 가능).
  - `POST /teams/{id}/members` — 멤버 추가(`user_id` 지정). 중복 추가 방지.
  - `DELETE /teams/{id}/members/{user_id}` — 멤버 제거. 마지막 lead 제거는 거부(팀에 lead 0명 방지).
  - `PATCH /teams/{id}/members/{user_id}` — 역할 변경(`lead`↔`member`).
- **PR 엔드포인트** (UI·권한만 실제, 데이터/다운스트림은 스텁):
  - `GET /teams/{id}/prs` — 팀 PR 현황. **lead는 팀 전체, member는 본인 것만.** 데이터는 빈 목록(실제 적재는 m4 몫).
  - `POST /prs/{id}/approve` — 승인 액션. **권한 가드 실제**, GitHub 반영 등 다운스트림은 스텁.
- **헬스체크**: `GET /health`(DB 연결 확인 포함).
- **Alembic 베이스라인**: `users`, `teams`, `team_members`, `sessions`. 이 4개 테이블 마이그레이션은 api-core 소유.
- **권한 정책 요약**(테스트로 강제): 비인증 → 401. 팀 비소속자의 팀 리소스 접근 → 403. 멤버의 팀 관리(생성 외 수정/삭제/멤버변경) → 403. member의 타 팀원 PR 조회 → 403.
- **테스트 초점**: OAuth 콜백 시 user upsert + JWT 발급(respx로 GitHub 모킹), 만료/무효 토큰 거부, **logout 후 토큰 무효화(401)**, `GET /users` 검색 결과·민감정보 미노출, 팀 생성 시 생성자 lead 자동등록, **lead만 수정/삭제/멤버 추가·제거·역할변경 가능(member는 403)**, 마지막 lead 제거 거부, `GET /teams`가 내 팀만 반환, **lead는 `/teams/{id}/prs`·approve 가능 / member는 타인 데이터에 403·본인 것만 조회**, `/health` 200.

### 6.3 `backend/m1` 오케스트레이터 (스켈레톤)
- `POST /triggers/pr`: GitHub 웹훅 수신. **HMAC-SHA256 서명 검증**(시크릿 env). 불일치 → 401.
- `POST /triggers/document`: 문서 업로드 완료 신호 수신.
- **트리거 분류**: 이벤트 타입 기준의 **결정적 라우팅**(LLM 의도 분류는 모듈 로직이므로 제외).
  - PR → m2·m3 호출 → m4 호출
  - 문서 → m0 호출
- **하위 모듈 호출**: `clients/`의 httpx async 클라이언트. 응답을 받아 **trace 로깅**(trace_id, 트리거 타입, 호출 모듈, 소요시간, 상태)까지만. 결과 가공/판정 금지.
- 호출 요청/응답은 `_shared/contracts.py` DTO 사용. `GET /health`.
- **테스트 초점**: 유효 서명 200/무효·누락 서명 401, PR 트리거 시 m2·m3·m4 호출(respx 어서션)·문서 트리거 시 m0 호출, 트레이스 로그에 필수 필드 포함, **결과 가공 없이 전달/로깅만** 함.

### 6.4 `backend/m0`·`m2`·`m3`·`m4` (스텁만)
- `GET /health`
- 오케스트레이터가 호출할 **계약 엔드포인트 스텁**(요청 받아 고정 더미 200):
  - `m0`: `POST /ingest`
  - `m2`: `POST /analyze/static`, `POST /analyze/security`
  - `m3`: `POST /verify/tests`, `POST /analyze/performance`
  - `m4`: `POST /evaluate`, `POST /curriculum`
- 자체 `pyproject.toml`·`Dockerfile`·**빈 `alembic/` 골격**. 모듈 테이블 스키마 생성 금지.
- **테스트 초점(계약만)**: 각 엔드포인트가 계약 DTO를 받아 계약 형태로 200을 반환, `/health` 200. **비즈니스 로직 테스트 금지.**
- `README.md`에 담당 범위·확장 지점 명시.

### 6.5 `frontend`
- **로그인**: GitHub OAuth 시작 → api-core 콜백 → 토큰 저장.
- **인증 컨텍스트 + 보호 라우트**: 미인증 시 로그인으로.
- **AppLayout(노션 사이드바)**: 좌측 사이드바(접이식 섹션), 상단바(검색바 자리·사용자 메뉴), 콘텐츠. 역할(lead/member)별 메뉴 분기.
- **대시보드 홈**: 역할 인지형(팀장=팀원 PR 현황/승인 대기 스텁, 멤버=본인 현황 스텁).
- **사용자/팀 화면**: 내 팀 목록, 팀 생성, 팀 수정/삭제(lead), **사용자 검색(`GET /users?search=`)으로 팀원 추가**, 멤버 제거·역할변경(lead), 멤버 목록·역할 표시. **설정 화면**과 로그아웃(`POST /auth/logout`) 동작 포함.
- **API 클라이언트**: JWT 자동 첨부, 401 처리.
- **모듈 전용 화면**: `pages/{kms,review,learning,graph}/Placeholder.tsx`로 **라우팅만 + "준비 중"**.
- **테스트 초점**: 미인증 시 보호 라우트가 로그인으로 리다이렉트, 로그인 화면이 OAuth 시작을 트리거, 사이드바가 역할별 메뉴를 렌더, 대시보드가 모킹 API(MSW)로 역할별 렌더, **사용자 검색→팀원 추가 흐름, lead만 멤버 관리 UI 노출, 로그아웃 후 로그인으로 복귀**, placeholder가 "준비 중" 표시.

---

## 7. 환경 변수 / 시크릿

`.env.example`에 **키 이름만** 둔다(값 비움). 실제 `.env`는 `.gitignore`. 최소 키:
```
# DB (Cloud SQL via Auth Proxy)
DB_HOST=cloud-sql-proxy
DB_PORT=5432
DB_NAME=
DB_USER=
DB_PASSWORD=
TEST_DB_NAME=codeshepherd_test     # 같은 인스턴스 내 테스트 DB
# Cloud SQL Auth Proxy
CLOUDSQL_INSTANCE_CONNECTION_NAME=
GOOGLE_APPLICATION_CREDENTIALS=/secrets/sa-key.json
# Auth
JWT_SECRET=
GITHUB_OAUTH_CLIENT_ID=
GITHUB_OAUTH_CLIENT_SECRET=
# Orchestrator
GITHUB_WEBHOOK_SECRET=
# Service URLs (compose 내부 호스트)
M0_URL=http://m0:8002
M2_URL=http://m2:8003
M3_URL=http://m3:8004
M4_URL=http://m4:8005
```
- 서비스계정 키 파일(`sa-key.json`)은 깃에 올리지 않는다(`.gitignore`). compose에서 볼륨 마운트.
- 코드 어디에도 시크릿 하드코딩 금지. 전부 `_shared/config.py`를 통해 로드.

---

## 8. Docker / docker-compose

- **백엔드 Dockerfile(서비스별)**: python:3.12-slim, uv 설치, `_shared` + 서비스 코드 복사, `uv sync`, uvicorn 실행. 멀티스테이지.
- **프론트엔드 Dockerfile**: node 빌드 → 개발은 vite dev, 운영은 nginx 정적 서빙.
- **docker-compose.yml** 서비스: `cloud-sql-proxy`, `api-core`(8000), `m1`(8001), `m0`(8002), `m2`(8003), `m3`(8004), `m4`(8005), `frontend`(5173). 단일 네트워크, 소스 볼륨 마운트 + 핫리로드.
- **테스트 실행**: 각 백엔드 컨테이너에서 `uv run pytest`, 프론트는 `npm run test`. CI(선택)는 GitHub Actions에서 동일 명령.

---

## 9. DB 연결 & 마이그레이션

- 모든 백엔드는 `cloud-sql-proxy` 호스트로 접속(로컬 Postgres 컨테이너 없음). **새 인스턴스 생성 금지**, 연결만.
- **테스트 DB**: 같은 인스턴스 안에 `codeshepherd_test` DB를 사용(인스턴스가 아니라 데이터베이스를 추가하는 것이므로 규칙에 부합). 통합 테스트는 트랜잭션 롤백으로 격리.
- **마이그레이션 소유권**: `api-core`가 공통 스키마(`users`·`teams`·`team_members`·`sessions`) 소유·작성. `m0`~`m4`는 **빈 alembic 골격만**. cross-service FK는 `users`/`teams` 참조 정도만 README 문서화.
- `pgvector`는 인스턴스에 설치돼 있다고 가정.

---

## 10. 빌드 순서 (Phase 단위 · 각 Phase는 Red→Green→Refactor)

각 Phase에서: **(1) 테스트 작성 → (2) RED 확인·보고 → (3) 최소 구현 → (4) GREEN → (5) 리팩터 → (6) 커버리지 확인.**

- **Phase 1 — 레포 골격**: 디렉토리 트리, `.gitignore`, `.env.example`, 루트 `README.md`, `docker-compose.yml` 뼈대. (스모크 테스트: 구조/설정 로드)
- **Phase 2 — `_shared` + 인프라**: config/db/auth/logging/contracts/testing, `cloud-sql-proxy` compose, api-core가 proxy로 DB 연결. (테스트: JWT 라운드트립, DB 세션 롤백 픽스처 동작)
- **Phase 3 — api-core 인증**: OAuth·JWT·`/me`·**`/auth/logout`**·`/health`, Alembic 베이스라인(`users`,`sessions`). (테스트: OAuth 콜백 upsert+발급, 토큰 거부, logout 무효화, health)
- **Phase 4 — api-core 팀 기능**: `teams`/`team_members`, **`GET /users` 검색**, 팀 생성(생성자 lead)·수정·삭제, 멤버 추가·제거·역할변경, 권한 가드, `/teams/{id}/prs`(스텁), approve(가드). (테스트: lead만 관리 / member 403, 마지막 lead 제거 거부, 내 팀만 조회, 본인 PR만)
- **Phase 5 — m1 + m0/m2/m3/m4 스텁**: 트리거 인입·HMAC·결정적 분류·httpx 호출·트레이스 로깅, 스텁 계약 엔드포인트. (테스트: 서명 검증, 라우팅 디스패치, 트레이스 필드, 스텁 계약·health)
- **Phase 6 — frontend**: 로그인·AppLayout·대시보드·팀·설정·placeholder·API 클라이언트. (테스트: 라우트 가드, 역할별 렌더, placeholder)

---

## 11. 완료 기준 (Definition of Done)

- `docker compose up`으로 **모든 서비스 기동** + 각 `/health` 200.
- 백엔드가 **Cloud SQL Auth Proxy 경유로 실제 연결**되고 `alembic upgrade head` 성공.
- **모든 테스트 통과**(`pytest` 서비스별, `vitest`), `api-core`·`m1` 커버리지 **≥ 80%**.
- 프론트에서 **GitHub OAuth 로그인** 동작 → 대시보드 진입.
- **팀장 계정**은 팀 생성·수정·삭제, 팀원 검색·추가·제거·역할변경, PR 현황·승인에 접근 가능, **멤버 계정**은 관리 동작에서 권한 가드로 차단됨(테스트로 증명). 로그아웃 시 토큰이 무효화됨.
- m1이 트리거를 받아 모듈 스텁을 호출하고 **trace 로그**가 남음(모듈 로직 없음).
- **모듈 전용 화면은 "준비 중" placeholder**로 라우팅.
- 깃 트래킹 대상에 **시크릿/키 파일 없음**(`.env.example`만 존재).

---

## 12. 산출물 점검 체크리스트 (마지막에 스스로 확인)

- [ ] 구현마다 **테스트가 먼저 작성**되고 함께 커밋되었는가
- [ ] 스텁(m0~m4)에 **계약/헬스 테스트만** 있고 비즈니스 로직 테스트는 없는가
- [ ] `api-core`·`m1` 커버리지 ≥ 80% 인가
- [ ] 백엔드 서비스마다 독립 `pyproject.toml` + `Dockerfile` + `tests/` 존재
- [ ] `_shared`에 비즈니스 로직이 새어들어가지 않았는가
- [ ] m0~m4에 실제 모듈 로직이 들어가지 않고 스텁만 있는가
- [ ] 오케스트레이터가 모듈을 "호출만" 하고 결과 가공을 하지 않는가
- [ ] 시크릿 하드코딩 없음, `.gitignore` 정상
- [ ] 새 Cloud SQL 인스턴스를 만들지 않았는가(연결만, 테스트 DB도 같은 인스턴스 내)
- [ ] 각 서비스 README에 담당 범위·확장 지점이 적혀 있는가