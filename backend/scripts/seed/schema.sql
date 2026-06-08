-- =============================================================================
-- schema.sql — PostgreSQL 마스터 테이블 통합 DDL (v3. Final Clean)
-- 멱등성: IF NOT EXISTS — 중복 실행 완전 안전 (migration_v2 통합 완료)
-- =============================================================================
CREATE EXTENSION IF NOT EXISTS vector;

-- ── 1. 도메인 레지스트리 (파이프라인 DOMAIN_PENDING 인터락 기준)
CREATE TABLE IF NOT EXISTS domain_registry (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name         TEXT NOT NULL UNIQUE,
    label_ko     TEXT NOT NULL,
    description  TEXT,
    color_hex    TEXT NOT NULL DEFAULT '#6366f1',
    is_active    BOOLEAN NOT NULL DEFAULT true,
    created_at   TIMESTAMPTZ DEFAULT now(),
    created_by   TEXT NOT NULL DEFAULT 'system'
);

-- ── 2. 출처 문서 마스터 테이블 (migration_v2 필드 흡수 완료)
CREATE TABLE IF NOT EXISTS documents (
    doc_id            TEXT PRIMARY KEY,
    source_prefix     TEXT NOT NULL,
    original_url      TEXT NOT NULL,
    content_hash      CHAR(8) NOT NULL,
    etag              TEXT,
    lang              TEXT,
    framework         TEXT,
    version           TEXT,
    infer_confidence  FLOAT,                              -- [통합] 메타 추론 신뢰도 지표
    is_deprecated     BOOLEAN NOT NULL DEFAULT false,     -- [통합] 문서 소프트 딜리트 플래그
    state             TEXT NOT NULL DEFAULT 'PENDING',
    created_at        TIMESTAMPTZ DEFAULT now(),
    updated_at        TIMESTAMPTZ,
    CONSTRAINT documents_state_check
        CHECK (state IN ('PENDING','CRAWLING','EXTRACTED','COMMITTED','FAILED'))
);

-- ── 3. 개념 마스터 테이블 (migration_v2 및 하이브리드 벡터 통합 완료)
CREATE TABLE IF NOT EXISTS concepts (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    concept_name   TEXT NOT NULL UNIQUE,
    doc_id         TEXT REFERENCES documents(doc_id) ON DELETE SET NULL,
    domains        TEXT[] NOT NULL,
    concept_type   TEXT,
    cwe_id         TEXT,
    owasp_id       TEXT,
    severity       TEXT,
    description_ko TEXT,
    root_cause     TEXT,                               -- [통합] 취약점/결함 발생 근본 원인 문자열
    is_deprecated  BOOLEAN NOT NULL DEFAULT false,     -- [통합] 개념 소프트 딜리트 플래그
    aliases        TEXT[] NOT NULL DEFAULT '{}',
    name_vector    vector(768),                        -- [통합] 이름+동의어 융합형 3-Factor 매칭 벡터
    desc_vector    vector(768),                        -- [통합] 요약 설명문 문맥 인지용 시맨틱 벡터
    created_at     TIMESTAMPTZ DEFAULT now(),
    updated_at     TIMESTAMPTZ
);

-- ── [마이그레이션] 기존 볼륨 스키마 → 현행 스키마 안전 업그레이드 (멱등성 보장)
-- documents: migration_v2 통합 컬럼
ALTER TABLE documents ADD COLUMN IF NOT EXISTS infer_confidence FLOAT;
ALTER TABLE documents ADD COLUMN IF NOT EXISTS is_deprecated    BOOLEAN NOT NULL DEFAULT false;

-- concepts: migration_v2 + 하이브리드 벡터 통합 컬럼
ALTER TABLE concepts ADD COLUMN IF NOT EXISTS root_cause     TEXT;
ALTER TABLE concepts ADD COLUMN IF NOT EXISTS is_deprecated  BOOLEAN NOT NULL DEFAULT false;
ALTER TABLE concepts ADD COLUMN IF NOT EXISTS aliases        TEXT[] NOT NULL DEFAULT '{}';
ALTER TABLE concepts ADD COLUMN IF NOT EXISTS name_vector    vector(768);
ALTER TABLE concepts ADD COLUMN IF NOT EXISTS desc_vector    vector(768);

-- HNSW 고속 유사도 검색 인덱스 빌드 (코사인 유사도 연산 전용)
CREATE INDEX IF NOT EXISTS idx_concepts_name_vector_hnsw
ON concepts USING hnsw (name_vector vector_cosine_ops)
WITH (m = 16, ef_construction = 64);

CREATE INDEX IF NOT EXISTS idx_concepts_desc_vector_hnsw
ON concepts USING hnsw (desc_vector vector_cosine_ops)
WITH (m = 24, ef_construction = 100);

-- ── 4. 스테이징 테이블 (DRAFT → APPROVED → COMMITTED)
CREATE TABLE IF NOT EXISTS staging_concepts (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id      UUID NOT NULL,
    doc_id          TEXT REFERENCES documents(doc_id) ON DELETE CASCADE,
    concept_json    JSONB NOT NULL,
    state           TEXT NOT NULL DEFAULT 'DRAFT',
    known_domains   TEXT[] DEFAULT '{}',
    unknown_domains TEXT[] DEFAULT '{}',
    reviewed_at     TIMESTAMPTZ,
    committed_at    TIMESTAMPTZ,
    created_at      TIMESTAMPTZ DEFAULT now()
);

-- staging_concepts: 마이그레이션 안전 컬럼 추가
ALTER TABLE staging_concepts ADD COLUMN IF NOT EXISTS known_domains   TEXT[] DEFAULT '{}';
ALTER TABLE staging_concepts ADD COLUMN IF NOT EXISTS unknown_domains  TEXT[] DEFAULT '{}';
ALTER TABLE staging_concepts ADD COLUMN IF NOT EXISTS committed_at     TIMESTAMPTZ;

-- ── 5. 파이프라인 실행 로그 (에이전트별 이벤트 스트림 리팩토링 반영 완료)
CREATE TABLE IF NOT EXISTS pipeline_logs (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    doc_id     TEXT REFERENCES documents(doc_id) ON DELETE SET NULL,
    session_id UUID NOT NULL,                          -- [통합] 태스크 세션 식별 고유키
    agent      TEXT NOT NULL,                          -- [통합] 이벤트를 유발한 에이전트명
    level      TEXT NOT NULL DEFAULT 'INFO',           -- [통합] 로그 레벨
    message    TEXT,                                   -- [통합] 실시간 상태 롤링 subText 메시지
    created_at TIMESTAMPTZ DEFAULT now()
);

-- pipeline_logs: 마이그레이션 안전 컬럼 추가
ALTER TABLE pipeline_logs ADD COLUMN IF NOT EXISTS session_id UUID NOT NULL DEFAULT gen_random_uuid();
ALTER TABLE pipeline_logs ADD COLUMN IF NOT EXISTS agent      TEXT NOT NULL DEFAULT 'system';
ALTER TABLE pipeline_logs ADD COLUMN IF NOT EXISTS level      TEXT NOT NULL DEFAULT 'INFO';
ALTER TABLE pipeline_logs ADD COLUMN IF NOT EXISTS message    TEXT;

-- ── 초기 도메인 레지스트리 시드
INSERT INTO domain_registry (name, label_ko, description, color_hex) VALUES
    ('security',    '보안',    '보안 취약점 및 방어 메커니즘', '#ef4444'),
    ('performance', '성능',    '성능 안티패턴 및 최적화 기법', '#3b82f6')
ON CONFLICT (name) DO NOTHING;