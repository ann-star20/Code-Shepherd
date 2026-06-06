-- Knowledge Graph Agent Pipeline — PostgreSQL DDL v2 (Corrected)
-- Spec: PRD-schema.md §15.2
-- Run: psql -h localhost -p 5433 -U postgres -d postgres -f schema.sql

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
  state            TEXT NOT NULL DEFAULT 'PENDING',  -- PENDING|CRAWLING|EXTRACTED|COMMITTED|FAILED
  created_at       TIMESTAMPTZ DEFAULT now(),
  updated_at       TIMESTAMPTZ,
  CONSTRAINT documents_state_check CHECK (
    state IN ('PENDING','CRAWLING','EXTRACTED','COMMITTED','FAILED')
  )
);
CREATE INDEX IF NOT EXISTS idx_documents_prefix_state ON documents(source_prefix, state);
CREATE INDEX IF NOT EXISTS idx_documents_url_hash     ON documents(original_url, content_hash);

-- ② staging_concepts: Extractor 출력 임시 보관 (운영 DB 격리)
CREATE TABLE IF NOT EXISTS staging_concepts (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  session_id      UUID NOT NULL,                  -- 파이프라인 실행 세션
  doc_id          TEXT REFERENCES documents(doc_id) ON DELETE CASCADE,
  concept_json    JSONB NOT NULL,                 -- Extractor 원본 출력
  state           TEXT NOT NULL DEFAULT 'DRAFT',  -- DRAFT|APPROVED|COMMITTED|REJECTED|DOMAIN_PENDING
  known_domains   TEXT[] DEFAULT '{}',            -- 매핑 완료되었거나 등록된 도메인 목록
  unknown_domains TEXT[] DEFAULT '{}',            -- 미등록 도메인 → HITL 검토 대상
  reviewed_at     TIMESTAMPTZ,
  committed_at    TIMESTAMPTZ,
  created_at      TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_staging_session_state ON staging_concepts(session_id, state);
-- HITL 대시보드 미등록 도메인 유효성 스캔 가속화를 위한 부분 인덱스(Partial Index)
CREATE INDEX IF NOT EXISTS idx_staging_domain_pending ON staging_concepts(state) WHERE state = 'DOMAIN_PENDING';

-- ③ concepts: 최종 승인 후 반영된 개념 정형 데이터
CREATE TABLE IF NOT EXISTS concepts (
  id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  concept_name   TEXT NOT NULL,                -- Neo4j Concept.name 동일 (MERGE 키)
  doc_id         TEXT REFERENCES documents(doc_id) ON DELETE SET NULL,
  domains        TEXT[] NOT NULL DEFAULT '{}', -- 교차 도메인을 유연하게 담는 배열 구조 (both 폐기 반영)
  concept_type   TEXT,                         -- 4종 컨셉 타입
  cwe_id         TEXT,
  owasp_id       TEXT,
  severity       TEXT,                         -- critical / high / medium / low
  description_ko TEXT,
  aliases        TEXT[] DEFAULT '{}',
  created_at     TIMESTAMPTZ DEFAULT now(),
  updated_at     TIMESTAMPTZ,
  CONSTRAINT concepts_severity_check CHECK (
    severity IS NULL OR severity IN ('critical','high','medium','low')
  )
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_concepts_name   ON concepts(concept_name);
CREATE INDEX IF NOT EXISTS idx_concepts_cwe_id        ON concepts(cwe_id);
-- 배열 데이터 검색 원자성 및 결합 조회를 위한 GIN 최적화 인덱스
CREATE INDEX IF NOT EXISTS idx_concepts_domains_gin   ON concepts USING gin(domains);

-- severity 소문자 정책 멱등 적용 (기존 데이터 정규화 → 제약 교체)
ALTER TABLE concepts DROP CONSTRAINT IF EXISTS concepts_severity_check;
UPDATE concepts SET severity = lower(severity) WHERE severity IS NOT NULL;
ALTER TABLE concepts ADD CONSTRAINT concepts_severity_check
  CHECK (severity IS NULL OR severity IN ('critical','high','medium','low'));

-- ④ pipeline_logs: 에이전트 단계별 로그 (SSE 원본)
CREATE TABLE IF NOT EXISTS pipeline_logs (
  id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  doc_id     TEXT REFERENCES documents(doc_id) ON DELETE CASCADE,
  session_id UUID,
  agent      TEXT NOT NULL,   -- Input/Crawler/Extractor/Writer/Resolver
  level      TEXT NOT NULL,   -- INFO / WARNING / ERROR
  message    TEXT NOT NULL,
  created_at TIMESTAMPTZ DEFAULT now(),
  CONSTRAINT logs_level_check CHECK (level IN ('INFO','WARNING','ERROR'))
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

-- ⑥ domain_registry: 등록된 도메인 목록 (동적 확장)
CREATE TABLE IF NOT EXISTS domain_registry (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name        TEXT NOT NULL UNIQUE,        -- "security", "performance", "compliance"
  label_ko    TEXT NOT NULL,               -- "보안", "성능", "규정 준수"
  description TEXT,
  color_hex   TEXT DEFAULT '#888780',
  is_active   BOOLEAN DEFAULT true,
  created_at  TIMESTAMPTZ DEFAULT now(),
  created_by  TEXT DEFAULT 'system'
);
CREATE INDEX IF NOT EXISTS idx_domain_registry_active ON domain_registry(is_active);

-- 초기 도메인 시드 (멱등)
INSERT INTO domain_registry (name, label_ko, description, color_hex) VALUES
  ('security',    '보안',  '웹 애플리케이션 보안 취약점 도메인', '#1D9E75'),
  ('performance', '성능',  '백엔드 성능 안티패턴 도메인',       '#BA7517')
ON CONFLICT (name) DO NOTHING;