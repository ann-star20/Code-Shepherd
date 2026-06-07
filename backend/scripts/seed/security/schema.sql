-- =============================================================================
-- schema.sql — PostgreSQL 마스터 테이블 DDL
-- 멱등성: IF NOT EXISTS — 중복 실행 완전 안전
-- =============================================================================

-- ── 도메인 레지스트리 (파이프라인 DOMAIN_PENDING 인터락 기준)
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

-- ── 출처 문서 마스터 테이블
CREATE TABLE IF NOT EXISTS documents (
    doc_id        TEXT PRIMARY KEY,
    source_prefix TEXT NOT NULL,
    original_url  TEXT NOT NULL,
    content_hash  CHAR(8) NOT NULL,
    etag          TEXT,
    lang          TEXT,
    framework     TEXT,
    version       TEXT,
    state         TEXT NOT NULL DEFAULT 'PENDING',
    created_at    TIMESTAMPTZ DEFAULT now(),
    updated_at    TIMESTAMPTZ,
    CONSTRAINT documents_state_check
        CHECK (state IN ('PENDING','CRAWLING','EXTRACTED','COMMITTED','FAILED'))
);

-- ── 개념 마스터 테이블 (PostgreSQL 정규화 사본)
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
    aliases        TEXT[] NOT NULL DEFAULT '{}',
    created_at     TIMESTAMPTZ DEFAULT now(),
    updated_at     TIMESTAMPTZ
);

-- ── 스테이징 테이블 (DRAFT → APPROVED → COMMITTED)
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

-- ── 파이프라인 실행 로그
CREATE TABLE IF NOT EXISTS pipeline_logs (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    doc_id     TEXT REFERENCES documents(doc_id) ON DELETE SET NULL,
    stage      TEXT NOT NULL,
    status     TEXT NOT NULL DEFAULT 'RUNNING',
    message    TEXT,
    started_at TIMESTAMPTZ DEFAULT now(),
    ended_at   TIMESTAMPTZ
);

-- ── 초기 도메인 레지스트리 시드
INSERT INTO domain_registry (name, label_ko, description, color_hex) VALUES
    ('security',    '보안',    '보안 취약점 및 방어 메커니즘', '#ef4444'),
    ('performance', '성능',    '성능 안티패턴 및 최적화 기법', '#3b82f6')
ON CONFLICT (name) DO NOTHING;
