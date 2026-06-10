
## **4. 기술 스택 및 인프라 정책 (Technical Stacks & Infrastructure)**

### **4.1. 기술 스택**

| 영역 | 기술 스펙 |
| :---- | :---- |
| **Backend** | Python 3.11+, FastAPI, Celery, Redis |
| **Databases** | PostgreSQL (정형 메타데이터 및 상태 관리), Neo4j (지식 그래프 모델링) |
| **AI/LLM** | Google Gemini API (gemini-2.5-flash-preview-09-2025) |
| **LLM 평가/추적** | LangSmith (Pre-Eval 데이터셋, 프로덕션 트레이싱, HITL 피드백 루프) |
| **Frontend** | React, TypeScript, Vite, Tailwind CSS |
| **Graph 시각화** | react-force-graph 또는 cytoscape.js |
| **실시간 통신** | WebSocket / SSE (FastAPI 내장) |
| **컨테이너** | Docker, Docker Compose (애플리케이션 서비스 레이어 전용) |

### **4.2. 컨테이너 구성 원칙 — 애플리케이션 서비스 레이어만 컨테이너화**

docker-compose.yml은 **순수 애플리케이션 서비스 3개만** 관리한다. PostgreSQL·Neo4j·Redis는 외부 독립 인프라로 격리하며, docker-compose.yml이 직접 기동하지 않는다.

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
  → Cloud SQL Auth  → Neo4j Aura      → Memorystore  
    Proxy (GCP)       (운영)           (GCP)

**서비스별 역할**:

| 서비스 | 이미지 | 역할 |
| :---- | :---- | :---- |
| backend | ./backend/Dockerfile | FastAPI 앱 서버. REST API, SSE, 승인 게이트 |
| celery_worker | ./backend/Dockerfile (공용) | 비동기 파이프라인 실행 (Crawler→Extractor→Graph Writer→Link Resolver) |
| frontend | ./frontend/Dockerfile | React/Vite 정적 서빙 또는 개발 서버 |
| cloud-sql-proxy | gcr.io/cloud-sql-connectors/cloud-sql-proxy | GCP 운영 시 Cloud SQL IAM 중계. --profile gcp 전용 |

### **4.3. 완전 무상태(Stateless) 컨테이너 및 인프라 분리 정책**

* **컨테이너 무상태화**: 애플리케이션 서비스 레이어(backend, frontend, celery_worker)는 내부 데이터 영속성 결합을 100% 제거한 무상태(Stateless) 아키텍처로 구현한다. 컨테이너가 재시작·교체·스케일 아웃되어도 데이터 일관성에 영향을 주지 않는다.  
* **인프라 불가지론적 전환성**: RDB(PostgreSQL), GraphDB(Neo4j), 캐시/브로커(Redis) 등 모든 데이터 플랫폼은 외부 독립 인프라로 격리한다. 개발 환경의 로컬 외부 컨테이너망과 운영 환경의 Cloud SQL 및 관리형 인프라 간의 스위칭을 백엔드 코드 수정 없이 **인프라 런타임 환경변수(DATABASE_URL, NEO4J_URI, REDIS_URL) 교체만으로** 완벽하게 수용한다.

### **4.4. 환경별 전환 방법 (Environment Switching)**

환경 전환은 .env 심볼릭 링크 교체 한 줄로 완료된다. 애플리케이션 코드를 건드리지 않는다.

* **로컬 개발 환경** (외부 로컬 컨테이너 bolt://, redis://, postgresql:// 직접 연결):

ln -sf .env.local .env  
docker compose --profile local up -d

* **GCP 운영 환경** (Cloud SQL Auth Proxy + Memorystore + Neo4j Aura):

ln -sf .env.prod .env  
docker compose --profile gcp up -d   # cloud-sql-proxy 컨테이너 추가 기동

**핵심 환경변수 — 인프라 주소만 다르고 키 이름은 동일**:

| 환경변수 | 로컬 값 예시 | GCP 운영 값 예시 |
| :---- | :---- | :---- |
| DATABASE_URL | postgresql+asyncpg://...@host.docker.internal:5432/kg_db | postgresql+asyncpg://...@127.0.0.1:5432/kg_db (Proxy 경유) |
| NEO4J_URI | bolt://host.docker.internal:7688 | neo4j+s://xxxx.databases.neo4j.io (Aura) |
| REDIS_URL | redis://host.docker.internal:6379/0 | redis://10.x.x.x:6379/0 (Memorystore) |
| CELERY_BROKER_URL | redis://host.docker.internal:6379/0 | redis://10.x.x.x:6379/0 |

### **4.5. GCP Cloud SQL Auth Proxy 보안 연결 구조**

퍼블릭 IP를 열지 않고 IAM 서비스 계정 인증을 통해 Cloud SQL에 안전하게 접속한다.

backend 컨테이너  
  │  DATABASE_URL=postgresql://...@127.0.0.1:5432/...  
  ▼  
cloud-sql-proxy 컨테이너 (--profile gcp 전용)  
  │  127.0.0.1:5432 수신  
  │  GOOGLE_APPLICATION_CREDENTIALS=/secrets/sa-key.json  
  ▼  
Cloud SQL (asia-northeast3)  
  IAM 인증 + TLS — 퍼블릭 IP 불필요

**docker-compose.yml 프록시 서비스 핵심 설정**:

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
    - "127.0.0.1:5433:5432"                 # 호스트 외부 노출 없음

**각 서비스를 개별 컨테이너로 분리하는 이유**:

| 관점 | 이유 |
| :---- | :---- |
| **독립 스케일 아웃** | celery_worker만 인스턴스 수를 늘려도 backend에 영향 없음 |
| **독립 배포** | 프론트엔드 변경 시 백엔드 재시작 불필요 |
| **장애 격리** | Worker 크래시가 API 서버 가용성에 영향 없음 |
| **CI/CD 분리** | 서비스별 독립 이미지 빌드·푸시 파이프라인 구성 가능 |
| **무상태 보장** | 컨테이너가 영속 데이터를 갖지 않아 언제든 교체 가능 |