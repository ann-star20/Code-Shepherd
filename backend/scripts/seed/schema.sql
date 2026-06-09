-- =============================================================================
-- schema.sql — PostgreSQL 마스터 테이블 통합 DDL (v4. 3-Factor Metric Sync)
-- 멱등성: IF NOT EXISTS — 중복 실행 완전 안전 (마이그레이션 및 세부 지표 수집 보완)
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

-- ── 2. 출처 문서 마스터 테이블
CREATE TABLE IF NOT EXISTS documents (
    doc_id            TEXT PRIMARY KEY,
    source_prefix     TEXT NOT NULL,
    original_url      TEXT NOT NULL,
    content_hash      CHAR(8) NOT NULL,
    etag              TEXT,
    lang              TEXT,
    framework         TEXT,
    version           TEXT,
    infer_confidence  FLOAT,                              -- 메타 추론 신뢰도 지표
    is_deprecated     BOOLEAN NOT NULL DEFAULT false,     -- 문서 소프트 딜리트 플래그
    state             TEXT NOT NULL DEFAULT 'PENDING',
    created_at        TIMESTAMPTZ DEFAULT now(),
    updated_at        TIMESTAMPTZ,
    CONSTRAINT documents_state_check
        CHECK (state IN ('PENDING','CRAWLING','EXTRACTED','COMMITTED','FAILED'))
);

-- ── 3. 개념 마스터 테이블 (하이브리드 벡터 통합 스펙 보전)
CREATE TABLE IF NOT EXISTS concepts (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    concept_name   TEXT NOT NULL UNIQUE,
    doc_id         TEXT REFERENCES documents(doc_id) ON DELETE SET NULL,
    domains        TEXT[] NOT NULL,
    concept_type   TEXT,
    cwe_id         TEXT,
    owasp_id       TEXT,                               -- owasp_category 수렴 통일 명세 반영
    severity       TEXT,
    description_ko TEXT,
    root_cause     TEXT,                               -- 취약점/결함 발생 근본 원인 문자열
    is_deprecated  BOOLEAN NOT NULL DEFAULT false,     -- 개념 소프트 딜리트 플래그
    aliases        TEXT[] NOT NULL DEFAULT '{}',
    name_vector    vector(1024),                        -- 이름+동의어 융합형 3-Factor 매칭 벡터
    desc_vector    vector(1024),                        -- 요약 설명문 문맥 인지용 시맨틱 벡터
    created_at     TIMESTAMPTZ DEFAULT now(),
    updated_at     TIMESTAMPTZ
);

-- ── 4. 스테이징 테이블 (DRAFT ➔ APPROVED ➔ COMMITTED)
-- 🎯 3-Factor 유사도 역추적 인프라를 위한 세부 점수 지표 컬럼 원자적 편입
CREATE TABLE IF NOT EXISTS staging_concepts (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id          UUID NOT NULL,
    doc_id              TEXT REFERENCES documents(doc_id) ON DELETE CASCADE,
    concept_json        JSONB NOT NULL,
    state               TEXT NOT NULL DEFAULT 'DRAFT',
    known_domains       TEXT[] DEFAULT '{}',
    unknown_domains     TEXT[] DEFAULT '{}',
    infer_action        TEXT,                          -- 사전 계산된 액션 (MERGE/RELATED_TO/NEW)
    infer_confidence    FLOAT DEFAULT 0.0,             -- 3-Factor 최종 결합 하이브리드 스코어 (Confidence)
    target_concept_name TEXT,                          -- MERGE/RELATED_TO 대상 마스터 개념명
    score_jaro_winkler  FLOAT DEFAULT 0.0,             -- 1) 어휘 구조 일치도 점수 (40%)
    score_name_vector   FLOAT DEFAULT 0.0,             -- 2) 키워드 융합 문맥 벡터 점수 (30%)
    score_desc_vector   FLOAT DEFAULT 0.0,             -- 3) 요약 설명 코사인 유사도 점수 (30%)
    reviewed_at         TIMESTAMPTZ,
    committed_at        TIMESTAMPTZ,
    created_at          TIMESTAMPTZ DEFAULT now()
);
SET maintenance_work_mem = '512MB';
-- ── 5. 파이프라인 실행 로그 (단일 채널 SSE 스트림 롤링 연동 기둥)
CREATE TABLE IF NOT EXISTS pipeline_logs (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    doc_id     TEXT REFERENCES documents(doc_id) ON DELETE SET NULL,
    session_id UUID NOT NULL,                          -- 태스크 세션 식별 고유키
    agent      TEXT NOT NULL,                          -- 이벤트를 유발한 에이전트명
    level      TEXT NOT NULL DEFAULT 'INFO',           -- 로그 레벨
    message    TEXT,                                   -- 실시간 상태 롤링 subText 메시지
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_concepts_name_vector_hnsw
ON concepts USING hnsw (name_vector vector_cosine_ops)
WITH (m = 16, ef_construction = 64);

CREATE INDEX IF NOT EXISTS idx_concepts_desc_vector_hnsw
ON concepts USING hnsw (desc_vector vector_cosine_ops)
WITH (m = 24, ef_construction = 100);

-- ── 초기 도메인 레지스트리 시드
INSERT INTO domain_registry (name, label_ko, description, color_hex) VALUES
    ('security',    '보안',    '보안 취약점 및 방어 메커니즘', '#ef4444'),
    ('performance', '성능',    '성능 안티패턴 및 최적화 기법', '#3b82f6')
ON CONFLICT (name) DO NOTHING;