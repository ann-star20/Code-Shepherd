-- =============================================================================
-- schema.sql — PostgreSQL 마스터 테이블 DDL
-- 멱등성: IF NOT EXISTS — 중복 실행 완전 안전
-- =============================================================================
CREATE EXTENSION IF NOT EXISTS vector;
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
    doc_id            TEXT PRIMARY KEY,
    source_prefix     TEXT NOT NULL,
    original_url      TEXT NOT NULL,
    content_hash      CHAR(8) NOT NULL,
    etag              TEXT,
    lang              TEXT,
    framework         TEXT,
    version           TEXT,
    infer_confidence  FLOAT,
    state             TEXT NOT NULL DEFAULT 'PENDING',
    created_at        TIMESTAMPTZ DEFAULT now(),
    updated_at        TIMESTAMPTZ,
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
-- PostgreSQL pgvector 플러그인 활용 (하이브리드 메타 검색)/
-- ② concepts 테이블에 임베딩 벡터 컬럼 추가 (Gemini embedding-001 기준 768차원)
ALTER TABLE concepts ADD COLUMN IF NOT EXISTS desc_vector vector(768);
-- ③ 고속 유사도 검색을 위한 HNSW 인덱스 빌드 (코사인 유사도 전용)
-- ③ 설명 임베딩 인덱스 빌드 (Semantic RELATED_TO 추천용) ★ 훨씬 더 중요함 ★
-- m = 24 (더 촘촘한 연결선 구축), ef_construction = 100 (더 정교한 그래프 레이어 빌드)
-- 설명문은 데이터 밀도(Density)와 엔트로피가 높으므로 HNSW 그래프 구조를 더 촘촘히 짜서 재현율(Recall)을 극대화합니다.
CREATE INDEX IF NOT EXISTS idx_concepts_desc_vector_hnsw 
ON concepts USING hnsw (desc_vector vector_cosine_ops)
WITH (m = 24, ef_construction = 100);

-- ── 런타임 고속 검색 질의문 예시 (Query-time ef_search 튜닝)
-- ef_search 값을 조정하여 쿼리 속도(Speed)와 재현율(Recall) 사이의 트레이드오프를 동적으로 제어합니다.
-- SET hnsw.ef_search = 40; 
-- SELECT concept_name, description_ko, 1 - (desc_vector <=> $1) AS similarity 
-- FROM concepts 
-- ORDER BY desc_vector <=> $1 LIMIT 5;

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

-- ── 파이프라인 실행 로그 (에이전트별 이벤트 스트림)
CREATE TABLE IF NOT EXISTS pipeline_logs (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    doc_id     TEXT REFERENCES documents(doc_id) ON DELETE SET NULL,
    session_id UUID NOT NULL,
    agent      TEXT NOT NULL,
    level      TEXT NOT NULL DEFAULT 'INFO',
    message    TEXT,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- ── 초기 도메인 레지스트리 시드
INSERT INTO domain_registry (name, label_ko, description, color_hex) VALUES
    ('security',    '보안',    '보안 취약점 및 방어 메커니즘', '#ef4444'),
    ('performance', '성능',    '성능 안티패턴 및 최적화 기법', '#3b82f6')
ON CONFLICT (name) DO NOTHING;
