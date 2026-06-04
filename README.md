# code-shepherd

조직 지식 관리 + 개발자 온보딩 멀티 에이전트 플랫폼 모노레포 베이스라인.

## 구조

```
code-shepherd/
├── backend/
│   ├── _shared/       # 횡단 관심사 공유 패키지 (config, db, auth, logging, contracts, testing)
│   ├── api-core/      # GitHub OAuth 로그인, 사용자/팀 관리, JWT 인증 (포트 8000)
│   ├── m1/            # 오케스트레이터 — PR 웹훅 수신 → 모듈 호출 스케줄링 (포트 8001)
│   ├── m0/            # KMS 인제스트 스텁 (포트 8002)
│   ├── m2/            # 정적 분석·보안 스캔 스텁 (포트 8003)
│   ├── m3/            # 테스트 검증·성능 분석 스텁 (포트 8004)
│   ├── m4/            # 커리큘럼·평가 스텁 (포트 8005)
│   └── m5/            # GraphDB + YouTube 독립 모듈 스텁 (포트 8006)
├── frontend/          # React + Vite + TypeScript (포트 5173)
├── docker-compose.yml
├── .env.example
└── README.md
```

## 빠른 시작

### 사전 조건

- Docker + Docker Compose
- Cloud SQL Auth Proxy 서비스 계정 키 (`secrets/sa-key.json`)
- `.env` 파일 (`.env.example` 복사 후 값 채우기)

```bash
cp .env.example .env
# .env 파일에 실제 값 입력
mkdir -p secrets
# secrets/sa-key.json 배치
```

### 전체 스택 실행

```bash
docker compose up --build
```

### 헬스체크

```bash
curl http://localhost:8000/health   # api-core
curl http://localhost:8001/health   # m1
curl http://localhost:8002/health   # m0
curl http://localhost:8003/health   # m2
curl http://localhost:8004/health   # m3
curl http://localhost:8005/health   # m4
curl http://localhost:8006/health   # m5
curl http://localhost:7474          # neo4j browser (compose)
```

### 백엔드 테스트 (서비스별)

```bash
docker compose run --rm api-core uv run pytest --cov=app --cov-report=term-missing
docker compose run --rm m1 uv run pytest --cov=app --cov-report=term-missing
docker compose run --rm m0 uv run pytest
docker compose run --rm m2 uv run pytest
docker compose run --rm m3 uv run pytest
docker compose run --rm m4 uv run pytest
docker compose run --rm m5 uv run pytest
```

### 프론트엔드 테스트

```bash
docker compose run --rm frontend npm run test
```

### DB 마이그레이션

```bash
docker compose run --rm api-core uv run alembic upgrade head
```

## 담당 모듈

| 모듈 | 담당 | 설명 |
|------|------|------|
| `_shared` + `api-core` + `m1` + `frontend` 기반 | 베이스라인 | 이 레포의 골격 |
| `m0` | 팀원 | KMS 인제스트 파이프라인 |
| `m2` | 팀원 | 정적 분석·보안 스캔 |
| `m3` | 팀원 | 테스트 검증·성능 분석 |
| `m4` | 팀원 | 커리큘럼·판정·피드백 루프 |
| `m5` | 팀원 | 엔티티/관계 추출 → Neo4j, YouTube 학습 자료 추천 (Module 1과 독립) |

## 환경 변수

`.env.example` 참조. 시크릿은 절대 코드/깃에 하드코딩 금지.
