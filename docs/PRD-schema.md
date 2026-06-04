
### 15.2. PostgreSQL 스키마 DDL

```sql
-- ① documents: 수집 대상 URL 메타데이터
CREATE TABLE IF NOT EXISTS documents (
  doc_id           TEXT PRIMARY KEY,           -- PREFIX_url_hash8 마스터 키
  source_prefix    TEXT NOT NULL,              -- EXT / KMS / ...
  original_url     TEXT NOT NULL,              -- 원본 URL (정규화 전)
  content_hash     CHAR(8) NOT NULL,           -- SHA-256 앞 8자리
  etag             TEXT,                       -- HTTP ETag (우선 사용)
  lang             TEXT,                       -- EN / KO
  framework        TEXT,                       -- Pre-scan 추론값
  version          TEXT,                       -- Pre-scan 추론값
  infer_confidence REAL DEFAULT 0,             -- 추론 신뢰도 0.0~1.0
  state            TEXT NOT NULL DEFAULT 'PENDING',  -- 파이프라인 상태
  created_at       TIMESTAMPTZ DEFAULT now(),
  updated_at       TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_documents_prefix_state ON documents(source_prefix, state);
CREATE INDEX IF NOT EXISTS idx_documents_url_hash     ON documents(original_url, content_hash);

-- ② staging_concepts: Extractor 출력 임시 보관 (운영 DB 격리)
CREATE TABLE IF NOT EXISTS staging_concepts (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  session_id   UUID NOT NULL,                  -- 파이프라인 실행 세션
  doc_id       TEXT REFERENCES documents(doc_id) ON DELETE CASCADE,
  concept_json JSONB NOT NULL,                 -- Extractor 원본 출력
  state        TEXT NOT NULL DEFAULT 'DRAFT',  -- DRAFT→APPROVED→COMMITTED|REJECTED
  reviewed_at  TIMESTAMPTZ,
  committed_at TIMESTAMPTZ,
  created_at   TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_staging_session_state ON staging_concepts(session_id, state);

-- ③ concepts: 최종 승인 후 반영된 개념 정형 데이터
CREATE TABLE IF NOT EXISTS concepts (
  id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  concept_name   TEXT NOT NULL UNIQUE,         -- Neo4j Concept.name과 동일 (MERGE 키)
  doc_id         TEXT REFERENCES documents(doc_id) ON DELETE SET NULL,
  concept_domain TEXT NOT NULL,                -- security / performance / both
  concept_type   TEXT,                         -- 4종 컨셉 타입
  cwe_id         TEXT,
  owasp_id       TEXT,
  severity       TEXT,                         -- CRITICAL / HIGH / MEDIUM / LOW
  description_ko TEXT,
  aliases        TEXT[] DEFAULT '{}',
  created_at     TIMESTAMPTZ DEFAULT now(),
  updated_at     TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_concepts_domain   ON concepts(concept_domain);
CREATE INDEX IF NOT EXISTS idx_concepts_cwe_id   ON concepts(cwe_id);
CREATE UNIQUE INDEX IF NOT EXISTS uq_concepts_name ON concepts(concept_name);

-- ④ pipeline_logs: 에이전트 단계별 로그 (SSE 원본)
CREATE TABLE IF NOT EXISTS pipeline_logs (
  id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  doc_id     TEXT REFERENCES documents(doc_id) ON DELETE CASCADE,
  session_id UUID,
  agent      TEXT NOT NULL,   -- Input/Crawler/Extractor/Writer/Resolver
  level      TEXT NOT NULL,   -- INFO / WARNING / ERROR
  message    TEXT NOT NULL,
  created_at TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_logs_doc_session ON pipeline_logs(doc_id, session_id);

-- ⑤ concept_snapshots: Extractor 원본 JSON (감사 추적·LangSmith 피드백)
CREATE TABLE IF NOT EXISTS concept_snapshots (
  id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  doc_id           TEXT REFERENCES documents(doc_id) ON DELETE CASCADE,
  session_id       UUID NOT NULL,
  langsmith_run_id TEXT,          -- @traceable 자동 기록값
  raw_output_json  JSONB NOT NULL, -- Gemini 원본 출력 (수정 전)
  approved_json    JSONB,          -- 관리자 확정 JSON (HITL diff 소스)
  created_at       TIMESTAMPTZ DEFAULT now()
);
```

### 15.3. Neo4j 노드 및 관계 전체 명세

#### 노드 레이블 및 주요 속성

| 레이블 | MERGE 키 | 핵심 속성 | 도메인 |
|--------|----------|-----------|--------|
| `Domain` | `name` | `description_ko` | 공통 |
| `OWASPCategory` | `owasp_id` | `name`, `description_ko` | Security |
| `PerfAntipatternCategory` | `name` | `authority`, `description_ko` | Performance |
| `CWE` | `cwe_id` | `name`, `description_ko` | 공통 |
| `Concept` | `name` | `aliases[]`, `description_ko`, `severity`, `cwe_id` + 다중 라벨 | 공통 허브 |
| `SecurityMechanism` | `name` | `description_ko` | Security |
| `RootCause` | `name` | `description_ko` | 공통 |
| `Component` | `name` | `description_ko` | 공통 |
| `ConfigProperty` | `key` | `value`, `framework` | 공통 |
| `Framework` | `name` + `version` | `lang` | 공통 |
| `Document` | `doc_id` | `source_prefix`, `original_url`, `content_hash`, `framework`, `version` | 공통 |

#### 관계 타입 전체 목록

| 관계 타입 | 방향 | 의미 |
|-----------|------|------|
| `BELONGS_TO` | Domain → OWASPCategory / PerfAntipatternCategory | 도메인 분류 소속 |
| `MAPS_TO` | OWASPCategory → CWE | OWASP ↔ CWE 공식 매핑 (보안 도메인) |
| `REF_TO` | PerfAntipatternCategory → CWE | CWE 자원관리 선택적 참조 (성능 도메인) |
| `INSTANTIATED_BY` | CWE → Concept | CWE가 Concept으로 구체화됨 |
| `MITIGATED_BY` | Concept → SecurityMechanism | 대응 보안 메커니즘 |
| `CAUSED_BY` | Concept → RootCause | 취약점·결함 근본 원인 |
| `AFFECTS` | Concept → Component | 영향 받는 소프트웨어 컴포넌트 |
| `CONFIGURED_BY` | Concept → ConfigProperty | 관련 프레임워크 설정 속성 |
| `IMPLEMENTS` | Framework → Concept | 프레임워크가 해당 개념 구현·대응 |
| `RELATED_TO` | Concept ↔ Concept | 의미적 연관 개념 |
| `SAME_AS` | Concept ↔ Concept | 동의어·이명 관계 (Link Resolver 생성) |
| `SOURCED_FROM` | Document → Concept | 문서 출처 역추적 |

#### Concept 다중 라벨 규칙

| `concept_domain` 값 | 부여 라벨 | 예시 |
|---------------------|-----------|------|
| `"security"` | `:Concept:Security` | XSS, SQLi, CSRF |
| `"performance"` | `:Concept:Performance` | N+1Query, MissingIndex |
| `"both"` | `:Concept:Security:Performance` | MemoryLeak, ConnPoolExhaustion |

---