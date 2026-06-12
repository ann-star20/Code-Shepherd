# 공유 DB 데이터 요구사항

공유 DB에 넣어야 할 데이터를 DB 종류별 + MVP 최소 필요 데이터 기준으로 정리한다.

---

## DB별로 넣어야 할 데이터

### Storage (S3/MinIO) — 원본 파일 보관

실제로 업로드할 원본 문서들:

| 문서 종류 | 예시 | 형식 |
|---|---|---|
| 코딩 컨벤션 | "Python 스타일 가이드", "API 네이밍 규칙" | PDF / DOCX / MD |
| 아키텍처 문서 | "서비스 전체 구조도", "DB 스키마 설명" | PDF / PPTX |
| 배포 프로세스 | "GitHub Actions 사용법", "배포 체크리스트" | MD / DOCX |
| 보안 가이드 | "SQL 인젝션 방지 패턴", "인증 처리 규칙" | MD / DOCX |
| 온보딩 문서 | "신입 1주차 가이드", "팀 문화 및 규칙" | PDF / DOCX |
| 기술 스택 문서 | "FastAPI 사용 컨벤션", "PostgreSQL 쿼리 최적화" | MD |

MVP 최소: 문서 10~20개면 데모 동작 가능. 실제 사내 문서 없으면 공개 문서(공식 docs, GitHub README 등)로 대체.

---

### PostgreSQL — 테이블별 필요 데이터

#### ① 문서 메타데이터 테이블

```
documents
  doc_id          UUID        -- 공통 키
  title           TEXT        -- "Python 코딩 컨벤션 v2"
  source          TEXT        -- "notion | confluence | upload | slack"
  source_url      TEXT        -- 원본 링크
  author          TEXT        -- 작성자
  team            TEXT        -- "백엔드팀 | 인프라팀"
  category        TEXT        -- "코딩컨벤션 | 아키텍처 | 온보딩"
  created_at      TIMESTAMP
  last_updated    TIMESTAMP   -- 노후화 감지용
  upload_status   TEXT        -- "processing | validated | stored"
```

#### ② 청크 메타데이터 테이블

```
chunks
  chunk_id        UUID
  doc_id          UUID        -- 공통 키로 문서와 연결
  parent_chunk_id UUID        -- null이면 Parent 청크
  chunk_type      TEXT        -- "parent | child"
  token_count     INT         -- 300~500 (child), 800~1500 (parent)
  page_number     INT
  section_header  TEXT        -- "3.2 API 설계 원칙"
  storage_path    TEXT        -- S3 경로
  vector_id       TEXT        -- pgVector에서의 ID
```

#### ③ 개발자 프로파일 테이블

```
developers
  dev_id          UUID
  name            TEXT
  role            TEXT        -- "backend | frontend | devops"
  tech_stack      JSONB       -- ["python", "fastapi", "postgresql"]
  skill_level     TEXT        -- "junior | mid | senior"
  join_date       DATE
  current_week    INT         -- 온보딩 몇 주차
```

#### ④ PR 리뷰 이력 테이블

```
pr_reviews
  review_id       UUID
  pr_id           TEXT        -- GitHub PR 번호
  dev_id          UUID
  verdict         TEXT        -- "lgtm | rework | escalate"
  critical_count  INT
  major_count     INT
  minor_count     INT
  issues          JSONB       -- 이슈 목록 전체
  reviewed_at     TIMESTAMP
  retry_count     INT         -- 재제출 횟수
```

#### ⑤ 반복 실수 패턴 테이블

```
mistake_patterns
  pattern_id      UUID
  dev_id          UUID
  pattern_type    TEXT        -- "n+1_query | sql_injection | missing_test"
  occurrence      INT         -- 이번 달 몇 번 발생
  first_seen      DATE
  last_seen       DATE
  resolved        BOOLEAN
```

#### ⑥ Trace 로그 테이블

```
agent_traces
  trace_id        TEXT        -- "trc_0001"
  task_id         UUID        -- PR 리뷰 파이프라인: PRReviewState.task_id / 문서 파이프라인: null
  agent_name      TEXT        -- "MarkdownConverterAgent"
  doc_id          UUID
  status          TEXT        -- "success | fail | review"
  started_at      TIMESTAMP
  ended_at        TIMESTAMP
  execution_ms    INT
  error_message   TEXT
```

---

### pgVector — 임베딩 데이터

문서 청킹 후 자동 생성. 직접 넣는 게 아니라 파이프라인이 넣어줌.

```
각 chunk → 임베딩 모델 (Claude / OpenAI text-embedding) → 벡터 저장

저장되는 것:
  vector_id    TEXT
  chunk_id     UUID        -- PostgreSQL chunks 테이블과 연결
  embedding    vector(1536) -- 임베딩 차원
  content      TEXT        -- 청크 본문 텍스트
  metadata     JSONB       -- 검색 필터용 (카테고리, 팀, 날짜)
```

---

### GraphDB (Neo4j) — 관계 데이터

```
노드 (Node) 종류:
  Document  { doc_id, title, category }
  Chunk     { chunk_id, section }
  Entity    { name, type }       -- "FastAPI", "JWT 인증", "배포 파이프라인"
  Developer { dev_id, role }

엣지 (Edge) 종류:
  (Document)-[HAS_CHUNK]->(Chunk)
  (Chunk)-[MENTIONS]->(Entity)        -- 이 청크가 이 개념을 언급
  (Document)-[REFERENCES]->(Document) -- A 문서가 B 문서를 참조
  (Entity)-[RELATED_TO]->(Entity)     -- "JWT 인증" ↔ "보안 가이드"
  (Developer)-[HAS_SKILL]->(Entity)   -- 개발자의 기술스택
```

---

## MVP 데모용 최소 필요 데이터 목록

### [반드시 있어야 하는 것 — P0]

**문서 (Storage + 파이프라인 처리):**
- ✅ 팀 코딩 컨벤션 (최소 1개)
- ✅ N+1 쿼리 방지 가이드 (데모 핵심 시나리오)
- ✅ SQL 인젝션 방지 패턴 (에스컬레이션 데모용)
- ✅ 신입 1주차 온보딩 가이드 (커리큘럼 에이전트용)

**개발자 프로파일 (PostgreSQL 직접 INSERT):**
- ✅ 신입 개발자 1명 (tech_stack, skill_level: junior)
- ✅ 시니어 개발자 1명 (에스컬레이션 수신용)

**테스트 PR 데이터:**
- ✅ N+1 쿼리 포함된 Python 코드 샘플 (PR 시뮬레이션용)
- ✅ SQL 인젝션 취약 코드 샘플 (Critical 에스컬레이션 데모용)

### [있으면 좋은 것 — P1]
- 📄 배포 프로세스 문서
- 📄 API 설계 가이드
- 📄 보안 체크리스트
- 👤 신입 개발자 2~3명 프로파일 (성장 그래프 시각화용)
- 🗃️ PR 리뷰 이력 5~10건 더미 데이터 (성장 지표 계산용)

---

## 데이터 수집 방법

| 데이터 종류 | 실제 있을 때 | 없을 때 (MVP 대체) |
|---|---|---|
| 사내 문서 | Notion/Confluence 연동 | 직접 MD 파일 작성 또는 공개 문서 사용 |
| 코딩 컨벤션 | 팀 기존 문서 업로드 | Google Python Style Guide 등 공개 자료 |
| PR 이력 | GitHub API 연동 | 더미 JSON 파일로 seed 데이터 |
| 개발자 프로파일 | 직접 입력 UI | SQL INSERT 스크립트로 직접 넣기 |

---

## 결론

파이프라인이 자동으로 채우는 데이터(pgVector 임베딩, trace 로그, 청크 메타데이터)는 신경 쓸 필요 없다. 팀이 직접 준비해야 하는 것은 딱 두 가지다.

1. **원본 문서 10~20개** (MD 파일이라도 OK)
2. **개발자 프로파일 seed 데이터** (INSERT 스크립트로 미리 넣기)

---

## 부록: SQL 스키마 및 시드 데이터

### PostgreSQL CREATE TABLE

```sql
-- 문서 메타데이터
CREATE TABLE documents (
    doc_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title         VARCHAR(500) NOT NULL,
    source        VARCHAR(50)  NOT NULL,
    source_url    TEXT,
    author        TEXT,
    team          TEXT,
    category      VARCHAR(100),
    file_type     VARCHAR(20),
    file_path     TEXT,
    last_updated  TIMESTAMPTZ,
    upload_status VARCHAR(20) DEFAULT 'processing',
    created_at    TIMESTAMPTZ DEFAULT NOW()
);

-- 청크 메타데이터
CREATE TABLE chunks (
    chunk_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    doc_id          UUID REFERENCES documents(doc_id),
    parent_chunk_id UUID REFERENCES chunks(chunk_id),
    chunk_type      VARCHAR(10) NOT NULL,  -- 'parent' | 'child'
    content         TEXT NOT NULL,
    token_count     INTEGER,
    page_number     INTEGER,
    section_header  VARCHAR(500),
    storage_path    TEXT,
    vector_id       TEXT,
    trace_id        VARCHAR(20),
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- 개발자 프로파일
CREATE TABLE developers (
    dev_id       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    github_id    VARCHAR(100) UNIQUE NOT NULL,
    name         VARCHAR(100) NOT NULL,
    role         VARCHAR(50),
    tech_stack   JSONB,
    skill_level  VARCHAR(20) NOT NULL,
    join_date    DATE,
    current_week INTEGER DEFAULT 1,
    created_at   TIMESTAMPTZ DEFAULT NOW()
);

-- PR 리뷰 이력
CREATE TABLE pr_reviews (
    review_id      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    pr_id          TEXT NOT NULL,
    dev_id         UUID REFERENCES developers(dev_id),
    verdict        VARCHAR(20),
    critical_count INTEGER DEFAULT 0,
    major_count    INTEGER DEFAULT 0,
    minor_count    INTEGER DEFAULT 0,
    issues         JSONB,
    reviewed_at    TIMESTAMPTZ DEFAULT NOW(),
    retry_count    INTEGER DEFAULT 0
);

-- 반복 실수 패턴
CREATE TABLE mistake_patterns (
    pattern_id   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    dev_id       UUID REFERENCES developers(dev_id),
    pattern_type TEXT NOT NULL,
    occurrence   INTEGER DEFAULT 1,
    first_seen   DATE DEFAULT CURRENT_DATE,
    last_seen    DATE DEFAULT CURRENT_DATE,
    resolved     BOOLEAN DEFAULT FALSE
);

-- Agent trace 로그
CREATE TABLE agent_traces (
    trace_id      TEXT PRIMARY KEY,
    task_id         UUID,
    agent_name    TEXT NOT NULL,
    doc_id        UUID REFERENCES documents(doc_id),
    status        TEXT,
    started_at    TIMESTAMPTZ,
    ended_at      TIMESTAMPTZ,
    execution_ms  INTEGER,
    error_message TEXT
);
```

### 개발자 프로파일 시드 INSERT (P0 필수)

```sql
INSERT INTO developers (github_id, name, role, tech_stack, skill_level, join_date, current_week) VALUES
('junior_dev_01', '신입 개발자', 'backend',
 '["python", "fastapi", "postgresql"]'::jsonb,
 'junior', CURRENT_DATE, 1),
('senior_dev_01', '시니어 개발자', 'backend',
 '["python", "fastapi", "postgresql", "redis", "aws"]'::jsonb,
 'senior', '2022-01-01', NULL);
-- github_id와 name은 실제 팀원 정보로 교체
```

### 테스트 PR 시드 INSERT (P0 필수)

```sql
-- N+1 쿼리 패턴 (rework 시나리오)
INSERT INTO pr_reviews (pr_id, dev_id, verdict, critical_count, major_count, issues)
SELECT
  'PR-001',
  dev_id,
  'rework',
  0, 1,
  '[{"severity": "Major", "type": "n+1_query", "file": "src/posts.py", "line": 14,
     "message": "for 루프 안에서 DB 쿼리 반복 호출",
     "suggestion": "joinedload() 또는 selectinload() 사용"}]'::jsonb
FROM developers WHERE github_id = 'junior_dev_01';

-- SQL 인젝션 (escalate 시나리오)
INSERT INTO pr_reviews (pr_id, dev_id, verdict, critical_count, issues)
SELECT
  'PR-002',
  dev_id,
  'escalate',
  1,
  '[{"severity": "Critical", "type": "sql_injection", "file": "src/auth.py", "line": 23,
     "message": "f-string으로 SQL 직접 조합",
     "suggestion": "파라미터 바인딩 사용: db.execute(query, {\"id\": user_id})"}]'::jsonb
FROM developers WHERE github_id = 'junior_dev_01';
```

### pgVector 확장 설정

> ⚠️ **차원 선택 필수** — 아래 DDL을 실행하기 전에 .env.example의
> PGVECTOR_DIMENSION 값과 일치하도록 `{차원}` 을 교체한다.
>
> | 임베딩 옵션 | 차원 | DDL 값 |
> |---|---|---|
> | Upstage solar-embedding-1-large (옵션 A) | 4096 | `vector(4096)` |
> | Ollama nomic-embed-text (옵션 B) | 768 | `vector(768)` |
>
> 팀 전체가 같은 옵션을 사용해야 한다. 한 번 테이블을 생성한 뒤 차원을 바꾸려면
> `DROP TABLE chunk_embeddings` 후 재생성이 필요하다 (데이터 전체 손실).

```sql
CREATE EXTENSION IF NOT EXISTS vector;

-- {차원} 자리에 4096 (Upstage) 또는 768 (Ollama) 을 입력한다
-- .env의 PGVECTOR_DIMENSION 값과 반드시 일치해야 한다
CREATE TABLE chunk_embeddings (
    chunk_id   UUID REFERENCES chunks(chunk_id) PRIMARY KEY,
    embedding  vector(4096),  -- ← 팀 결정값으로 교체 (4096 또는 768)
    model_name VARCHAR(100),  -- 사용한 임베딩 모델명 기록
    content    TEXT,
    metadata   JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX ON chunk_embeddings USING hnsw (embedding vector_cosine_ops);
```

### Neo4j Entity 시드 (수동 삽입)

```cypher
CREATE (:Entity {name: "FastAPI", type: "Technology", description: "Python 비동기 웹 프레임워크"})
CREATE (:Entity {name: "PostgreSQL", type: "Technology", description: "관계형 DB, 메타데이터 라우터"})
CREATE (:Entity {name: "pgVector", type: "Technology", description: "PostgreSQL 벡터 확장"})
CREATE (:Entity {name: "LangGraph", type: "Technology", description: "멀티에이전트 오케스트레이션 프레임워크"})
CREATE (:Entity {name: "LangSmith", type: "Technology", description: "LLM 관찰 및 트레이싱 도구"})
CREATE (:Entity {name: "Neo4j", type: "Technology", description: "그래프 DB, 관계 맵"})
CREATE (:Entity {name: "N+1 Query", type: "Pattern", description: "반복 DB 쿼리 안티패턴"})
CREATE (:Entity {name: "SQL Injection", type: "Pattern", description: "SQL 직접 조합 보안 취약점"})
CREATE (:Entity {name: "Missing Auth", type: "Pattern", description: "API 인증/인가 누락"})
CREATE (:Entity {name: "HITL", type: "Concept", description: "Human-in-the-Loop, 품질 임계값 미달 시 사람 개입"})
CREATE (:Entity {name: "RAG", type: "Concept", description: "Retrieval-Augmented Generation"})
CREATE (:Entity {name: "Parent-Child Chunking", type: "Concept", description: "Parent 800~1500 tokens, Child 300~500 tokens 계층 청킹"})
```

---

## 공통 키 구조 (전 DB 조인 기준점)

모든 데이터는 아래 공통 키를 가져야 에이전트 간 데이터 참조가 가능하다.

```json
{
  "doc_id": "uuid-v4",
  "chunk_id": "uuid-v4",
  "parent_chunk_id": "uuid-v4 | null",
  "trace_id": "trc_0001 ~ trc_0006",
  "source": "notion | confluence | slack | upload",
  "created_at": "ISO8601",
  "status": "processing | validated | stored | failed"
}
```

에이전트가 chunk를 검색하면 chunk_id 하나로 원본 문서(S3), 임베딩(pgVector), 관계(Neo4j) 모두 참조 가능.
