
## 5. 기술 스택 및 인프라 정책 (Technical Stacks & Infrastructure)

### 5.1. 기술 스택

| 영역 | 기술 |
|------|------|
| **Backend** | Python 3.11+, FastAPI, Celery, Redis |
| **Databases** | PostgreSQL (정형 메타데이터 및 상태 관리), Neo4j (지식 그래프 모델링) |
| **AI/LLM** | Google Gemini API (`gemini-2.5-flash`) |
| **LLM 평가/추적** | LangSmith (Pre-Eval 데이터셋, 프로덕션 트레이싱, HITL 피드백 루프) |
| **Frontend** | React, TypeScript, Vite, Tailwind CSS |
| **Graph 시각화** | `react-force-graph` 또는 `cytoscape.js` |
| **실시간 통신** | WebSocket / SSE (FastAPI 내장) |
| **컨테이너** | Docker, Docker Compose (애플리케이션 서비스 레이어 전용) |

### 5.2. 컨테이너 구성 원칙 — 애플리케이션 서비스 레이어만 컨테이너화

`docker-compose.yml`은 **순수 애플리케이션 서비스 3개만** 관리한다. PostgreSQL·Neo4j·Redis는 외부 독립 인프라로 격리하며, `docker-compose.yml`이 직접 기동하지 않는다.

```
┌─────────────────────────────────────────────────────┐
│              docker-compose.yml 관리 범위             │
│                                                     │
│  ┌──────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │ backend  │  │celery_worker │  │  frontend    │  │
│  │ FastAPI  │  │  Celery      │  │  React/Vite  │  │
│  │ :8000    │  │  Worker      │  │  :3000       │  │
│  └────┬─────┘  └──────┬───────┘  └──────────────┘  │
│       │               │                             │
│  (GCP profile only)   │                             │
│  ┌────┴───────────┐   │                             │
│  │cloud-sql-proxy │   │                             │
│  │127.0.0.1:5432  │   │                             │
│  └────────────────┘   │                             │
└───────────────────────┼─────────────────────────────┘
                        │  환경변수만 교체
        ┌───────────────┼─────────────────┐
        ▼               ▼                 ▼
  PostgreSQL        Neo4j             Redis
  (외부 인프라)    bolt://...        redis://...
  로컬 컨테이너     로컬 컨테이너     로컬 컨테이너
  → Cloud SQL Auth  → Neo4j Aura     → Memorystore
    Proxy (GCP)       (운영)           (GCP)
```

**서비스별 역할**:

| 서비스 | 이미지 | 역할 |
|--------|--------|------|
| `backend` | `./backend/Dockerfile` | FastAPI 앱 서버. REST API, SSE, 승인 게이트 |
| `celery_worker` | `./backend/Dockerfile` (공용) | 비동기 파이프라인 실행 (Crawler→Extractor→Graph Writer→Link Resolver) |
| `frontend` | `./frontend/Dockerfile` | React/Vite 정적 서빙 또는 개발 서버 |
| `cloud-sql-proxy` | `gcr.io/cloud-sql-connectors/cloud-sql-proxy` | GCP 운영 시 Cloud SQL IAM 중계. `--profile gcp` 전용 |

### 5.3. 완전 무상태(Stateless) 컨테이너 및 인프라 분리 정책

**컨테이너 무상태화**: 애플리케이션 서비스 레이어(`backend`, `frontend`, `celery_worker`)는 내부 데이터 영속성 결합을 100% 제거한 무상태(Stateless) 아키텍처로 구현한다. 컨테이너가 재시작·교체·스케일 아웃되어도 데이터 일관성에 영향을 주지 않는다.

**인프라 불가지론적 전환성**: RDB(PostgreSQL), GraphDB(Neo4j), 캐시/브로커(Redis) 등 모든 데이터 플랫폼은 외부 독립 인프라로 격리한다. 개발 환경의 로컬 외부 컨테이너망과 운영 환경의 Cloud SQL 및 관리형 인프라 간의 스위칭을 백엔드 코드 수정 없이 **인프라 런타임 환경변수(`DATABASE_URL`, `NEO4J_URI`, `REDIS_URL`) 교체만으로** 완벽하게 수용한다.

### 5.4. 환경별 전환 방법 (Environment Switching)

환경 전환은 `.env` 심볼릭 링크 교체 한 줄로 완료된다. 애플리케이션 코드를 건드리지 않는다.

**로컬 개발 환경** (외부 로컬 컨테이너 `bolt://`, `redis://`, `postgresql://` 직접 연결):

```bash
ln -sf .env.local .env
docker compose --profile local up -d
```

**GCP 운영 환경** (Cloud SQL Auth Proxy + Memorystore + Neo4j Aura):

```bash
ln -sf .env.prod .env
docker compose --profile gcp up -d   # cloud-sql-proxy 컨테이너 추가 기동
```

**핵심 환경변수 — 인프라 주소만 다르고 키 이름은 동일**:

| 환경변수 | 로컬 값 예시 | GCP 운영 값 예시 |
|----------|-------------|-----------------|
| `DATABASE_URL` | `postgresql+asyncpg://...@host.docker.internal:5432/kg_db` | `postgresql+asyncpg://...@127.0.0.1:5432/kg_db` (Proxy 경유) |
| `NEO4J_URI` | `bolt://host.docker.internal:7687` | `neo4j+s://xxxx.databases.neo4j.io` (Aura) |
| `REDIS_URL` | `redis://host.docker.internal:6379/0` | `redis://10.x.x.x:6379/0` (Memorystore) |
| `CELERY_BROKER_URL` | `redis://host.docker.internal:6379/0` | `redis://10.x.x.x:6379/0` |

### 5.5. GCP Cloud SQL Auth Proxy 보안 연결 구조

퍼블릭 IP를 열지 않고 IAM 서비스 계정 인증을 통해 Cloud SQL에 안전하게 접속한다.

```
backend 컨테이너
  │  DATABASE_URL=postgresql://...@127.0.0.1:5432/...
  ▼
cloud-sql-proxy 컨테이너 (--profile gcp 전용)
  │  127.0.0.1:5432 수신
  │  GOOGLE_APPLICATION_CREDENTIALS=/secrets/sa-key.json
  ▼
Cloud SQL (asia-northeast3)
  IAM 인증 + TLS — 퍼블릭 IP 불필요
```

**docker-compose.yml 프록시 서비스 핵심 설정**:

```yaml
cloud-sql-proxy:
  image: gcr.io/cloud-sql-connectors/cloud-sql-proxy:latest
  profiles: [gcp]                           # --profile gcp 없이는 기동 안 됨
  command: >
    --address 0.0.0.0 --port 5432
    ${CLOUD_SQL_INSTANCE}                   # my-project:region:instance-name
  volumes:
    - ${GCP_SERVICE_ACCOUNT_KEY_PATH}:/secrets/sa-key.json:ro
  environment:
    GOOGLE_APPLICATION_CREDENTIALS: /secrets/sa-key.json
  ports:
    - "127.0.0.1:5432:5432"                 # 호스트 외부 노출 없음
```

**각 서비스를 개별 컨테이너로 분리하는 이유**:

| 관점 | 이유 |
|------|------|
| 독립 스케일 아웃 | `celery_worker`만 인스턴스 수를 늘려도 `backend`에 영향 없음 |
| 독립 배포 | 프론트엔드 변경 시 백엔드 재시작 불필요 |
| 장애 격리 | Worker 크래시가 API 서버 가용성에 영향 없음 |
| CI/CD 분리 | 서비스별 독립 이미지 빌드·푸시 파이프라인 구성 가능 |
| 무상태 보장 | 컨테이너가 영속 데이터를 갖지 않아 언제든 교체 가능 |

---


## 9. 초기 마이그레이션 및 시드 스크립트 형상 관리 정책

### 9.1. 코드 및 정책 격리 원칙

시스템 초기화 및 데이터셋 구축을 위한 실행용 로우 스크립트(`schema.sql`, `seed_data.sql`, `seed_data.cypher`)는 본 PRD 문서에 직접 기술하여 관리하지 않는다. 대신 프로젝트 루트의 `scripts/seed/` 디렉토리 하위에 독립된 물리 파일로 격리하여 Git 형상 관리 시스템을 통해 버전 제어한다.

```
scripts/
  seed/
    security/
      schema.sql                   # PostgreSQL 테이블 DDL (IF NOT EXISTS)
      seed_data.sql                # OWASP Top 10 / CWE 정형 데이터 INSERT
      seed_data.cypher             # Neo4j 보안 도메인 노드/관계 MERGE
    performance/
      perf_antipattern_schema.sql  # 성능 도메인 PostgreSQL 확장 DDL
      perf_seed_data.sql           # PerfAntipatternCategory 정형 데이터
      perf_seed_data.cypher        # Neo4j 성능 도메인 노드/관계 MERGE
    verify_seed.py                 # 적재 후 정합성 검증 (노드 수, 고아 노드 탐지)
```

### 9.2. 멱등성(Idempotency) 보장

모든 데이터베이스 스크립트는 중복 실행되거나 어떤 환경에서 가동되더라도 기존 데이터를 파괴하지 않고 무결성을 유지하도록 아래 멱등성 규격을 필수 준수한다.

| DB | 멱등성 구문 | 적용 대상 |
|----|------------|-----------|
| PostgreSQL | `CREATE TABLE IF NOT EXISTS` | DDL 스크립트 전체 |
| PostgreSQL | `ON CONFLICT (doc_id) DO NOTHING` / `DO UPDATE` | INSERT 구문 전체 |
| Neo4j | `MERGE ... ON CREATE SET ... ON MATCH SET` | 노드/관계 생성 전체 |

### 9.3. 환경 불가지론적 재사용

격리된 스크립트 자산은 소스코드 변경 없이 아래 3개 환경에서 동일하게 재사용된다.

| 재사용 환경 | 실행 방법 |
|-------------|-----------|
| 로컬 개발 환경 초기화 | `psql $DATABASE_URL -f scripts/seed/security/schema.sql` |
| Phase 1 테스트 하네스 자동화 | `conftest.py` 픽스처에서 동일 파일 경로 참조 |
| Phase 4 GCP Cloud SQL 이관 | 환경변수 `DATABASE_URL`만 교체 후 동일 명령 실행 |

---


## 12. 형상 관리 및 Git 커밋 규칙 (Git Commit Convention)

모든 개발자 및 AI 협업 도구는 소스코드 변경 이력을 명확히 추적하고 코드 리뷰 효율을 높이기 위해 **Conventional Commits 1.0.0** 규격을 준수한다.

### 12.1. 커밋 메시지 구조

```
<type>(<scope>): <subject>          ← Header (필수)

[body]                              ← Body (선택, 변경 이유 및 상세 설명)

[footer]                            ← Footer (선택, 이슈 번호, Breaking Change)
```

- **Header**: 소문자, 50자 이내, 명령형 현재 시제
- **Body**: 72자 줄바꿈, "무엇을 왜" 설명
- **Footer**: `Closes #123`, `BREAKING CHANGE: ...`

### 12.2. 필수 커밋 타입 (Type)

| 타입 | 설명 | 예시 |
|------|------|------|
| `feat` | 새로운 기능 추가 | 에이전트 로직 구현, API 엔드포인트 신설 |
| `fix` | 버그 수정 | 파이프라인 락 에러 해결, JSON 파싱 예외 처리 |
| `docs` | 문서 수정 | PRD 업데이트, README.md 수정 |
| `style` | 코드 포맷팅, 세미콜론 누락 등 | 비즈니스 로직 변경 없음 |
| `refactor` | 코드 리팩토링 | 기능 추가나 버그 수정 없는 구조 개선 |
| `test` | 테스트 코드 추가 및 수정 | 테스트 하네스, PyTest 스크립트 추가 |
| `chore` | 빌드, 패키지 매니저, 도커파일 수정 | 프로덕션 코드 변경 없음 |

### 12.3. 프로젝트 전용 Scope 규정

제목의 `()` 안에 들어갈 Scope는 아래 항목으로 강제한다.

| Scope | 변경 모듈 |
|-------|-----------|
| `input` | Input Agent 및 URL Pre-scan 관련 |
| `crawler` | Crawler Agent 및 DOM 정제 관련 |
| `extractor` | Extractor Agent 및 Gemini 프롬프트/JSON 스키마 관련 |
| `writer` | Graph Writer Agent 및 PostgreSQL/Neo4j 적재 관련 |
| `resolver` | Link Resolver Agent 및 벡터 유사도 병합 관련 |
| `db` | 마이그레이션 스크립트, 시드 데이터(`schema.sql`, `seed_data.cypher` 등) 관련 |
| `infra` | Docker, Docker Compose, Cloud SQL Proxy 설정 관련 |
| `frontend` | UI 컴포넌트, 상태 관리, react-force-graph 관련 |

### 12.4. 커밋 예시

```bash
# 기능 추가
feat(extractor): add concept_domain field to gemini extraction schema

# 버그 수정
fix(writer): rollback postgresql on neo4j connection timeout

# 테스트
test(writer): add T04 neo4j multilabel dedup harness test

# 인프라
chore(infra): add cloud-sql-proxy service with gcp profile

# DB 스키마
feat(db): add staging_concepts table with state machine columns

# 리팩터
refactor(resolver): extract alias similarity into shared util

# BREAKING CHANGE 포함
feat(writer): enforce two-phase commit for cross-db atomicity

BREAKING CHANGE: graph_writer_task now raises CrossDbCommitError
on neo4j failure instead of silently continuing
```

---
