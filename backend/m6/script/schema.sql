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

-- ── 2.0 영속 볼륨 마이그레이션: documents → knowledge_documents 리네이밍 (멱등)
ALTER TABLE IF EXISTS documents RENAME TO knowledge_documents;

-- ── 2. 출처 문서 마스터 테이블
CREATE TABLE IF NOT EXISTS knowledge_documents (
    doc_id            TEXT PRIMARY KEY,
    source_prefix     TEXT NOT NULL,
    original_url      TEXT NOT NULL,
    content_hash      CHAR(8) NOT NULL,
    etag              TEXT,
    doc_lang          TEXT, -- 문서 원문 언어
    lang              TEXT, -- 프로그램언어
    framework         TEXT, -- 프레임워크
    version           TEXT, -- 프레임워크 버전
    infer_confidence  FLOAT,                              -- 메타 추론 신뢰도 지표
    is_deprecated     BOOLEAN NOT NULL DEFAULT false,     -- 문서 소프트 딜리트 플래그
    state             TEXT NOT NULL DEFAULT 'PENDING',
    created_at        TIMESTAMPTZ DEFAULT now(),
    updated_at        TIMESTAMPTZ,
    CONSTRAINT documents_state_check
        CHECK (state IN ('PENDING','CRAWLING','EXTRACTING','EXTRACTED','COMMITTED','FAILED'))
);

-- ── 2.1 영속 볼륨 마이그레이션: 기존 knowledge_documents 테이블에 신규 컬럼 보강
ALTER TABLE knowledge_documents ADD COLUMN IF NOT EXISTS etag     TEXT;
ALTER TABLE knowledge_documents ADD COLUMN IF NOT EXISTS doc_lang TEXT;

-- ── 3. 개념 마스터 테이블 (하이브리드 벡터 통합 스펙 보전)
CREATE TABLE IF NOT EXISTS concepts (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    concept_name   TEXT NOT NULL UNIQUE,
    doc_id         TEXT REFERENCES knowledge_documents(doc_id) ON DELETE SET NULL,
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
    doc_id              TEXT REFERENCES knowledge_documents(doc_id) ON DELETE CASCADE,
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
    doc_id     TEXT REFERENCES knowledge_documents(doc_id) ON DELETE SET NULL,
    session_id UUID NOT NULL,                          -- 태스크 세션 식별 고유키
    agent      TEXT NOT NULL,                          -- 이벤트를 유발한 에이전트명
    level      TEXT NOT NULL DEFAULT 'INFO',           -- 로그 레벨
    message    TEXT,                                   -- 실시간 상태 롤링 subText 메시지
    etag              TEXT,
    description              TEXT,
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

CREATE TABLE IF NOT EXISTS framework_metadata (
    framework        TEXT PRIMARY KEY,              -- 'NestJS', 'Kubernetes', 'Docker' (Canonical Key)
    url_patterns     TEXT[] NOT NULL,               -- 🎯 [★추가] 정규식 매칭용 문자열 배열
    supported_langs  TEXT[] NOT NULL,               -- ['typescript', 'javascript'] 다중 언어 배열
    default_lang     TEXT NOT NULL,                 -- 우선순위 Fallback 기본 언어
    created_at       TIMESTAMPTZ DEFAULT now()
);

-- ── 🎯 웹 프레임워크 및 클라우드 인프라 정규식 대통합 시드 적재
INSERT INTO framework_metadata (framework, url_patterns, supported_langs, default_lang) VALUES
('NestJS',      ARRAY['nestjs\.com', 'docs\.nestjs\.com'],             ARRAY['typescript', 'javascript'], 'typescript'),
('Express',     ARRAY['expressjs\.com'],                               ARRAY['javascript', 'typescript'], 'javascript'),
('Spring',      ARRAY['spring\.io', 'docs\.spring\.io'],               ARRAY['java', 'kotlin'],           'java'),
('Django',      ARRAY['djangoproject\.com'],                           ARRAY['python'],                   'python'),
('FastAPI',     ARRAY['fastapi\.tiangolo\.com'],                       ARRAY['python'],                   'python'),
('ASP.NET Core',ARRAY['microsoft\.com/net', 'learn\.microsoft\.com'],  ARRAY['c#'],                       'c#'),
('Next.js',     ARRAY['nextjs\.org', 'nextjs\.com'],                   ARRAY['typescript', 'javascript'], 'typescript'),
('Gin',         ARRAY['gin-gonic\.com', 'github\.com/gin-gonic'],      ARRAY['go'],                       'go'),
('Docker',      ARRAY['docker\.com', 'docs\.docker\.com', 'dockerfile'],ARRAY['dockerfile'],               'dockerfile'),
('Kubernetes',  ARRAY['kubernetes\.io', 'k8s\.io', 'k8s'],             ARRAY['yaml', 'json'],             'yaml'),
('Terraform',   ARRAY['terraform\.io', 'hashicorp\.com/terraform'],    ARRAY['hcl'],                      'hcl')
ON CONFLICT (framework) DO UPDATE
SET url_patterns = EXCLUDED.url_patterns,
    supported_langs = EXCLUDED.supported_langs,
    default_lang = EXCLUDED.default_lang;

-- =============================================================================
-- ── 마이그레이션 보완 (멱등 — 기존 볼륨에 재실행해도 안전)
-- =============================================================================

-- knowledge_documents: session_id 추가 (prd §1.3 SSE /api/pipeline/stream/{session_id})
ALTER TABLE knowledge_documents ADD COLUMN IF NOT EXISTS session_id TEXT NOT NULL DEFAULT '';
CREATE INDEX IF NOT EXISTS idx_knowledge_document_session
    ON knowledge_documents (session_id);

-- staging_concepts: session_id 인덱스 (FAILED 클린업 멱등성 — prd ★ 버그 방지)
CREATE INDEX IF NOT EXISTS idx_staging_concepts_session
    ON staging_concepts (session_id);

-- staging_concepts: HITL 동시성 — APPROVED 행 직렬 처리용 partial index
-- (SELECT FOR UPDATE SKIP LOCKED 사용 시 이중 커밋 방지, prd ★)
CREATE INDEX IF NOT EXISTS idx_staging_concepts_approved
    ON staging_concepts (id)
    WHERE state = 'APPROVED';

-- staging_concepts: state / infer_action CHECK 제약 (idempotent DO-block)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints
        WHERE table_name = 'staging_concepts'
          AND constraint_name = 'staging_concepts_state_check'
    ) THEN
        ALTER TABLE staging_concepts
            ADD CONSTRAINT staging_concepts_state_check
            CHECK (state IN ('DRAFT','APPROVED','REJECTED','COMMITTED'));
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints
        WHERE table_name = 'staging_concepts'
          AND constraint_name = 'staging_concepts_infer_action_check'
    ) THEN
        ALTER TABLE staging_concepts
            ADD CONSTRAINT staging_concepts_infer_action_check
            CHECK (infer_action IN ('NEW','MERGE','RELATED_TO'));
    END IF;
END $$;

-- pipeline_logs: session_id 인덱스 (SSE 스트림 롤링 조회용)
CREATE INDEX IF NOT EXISTS idx_pipeline_logs_session
    ON pipeline_logs (session_id);

-- ★ 보정점 리마인더 (score_metrics 0.0 버그 — schema.md ★)
-- score_* 컬럼 기본값 0.0 = "아직 산출 안 됨".
-- hybrid_resolver._resolve()에서 반드시 {jaro, name_vec, desc_vec} dict를 채워 기록.
-- 3-Factor 점수가 모두 0.0인 채로 state=APPROVED 전이 금지.
-- (approver 서비스에서 SUM(score_*) > 0 검증 추가 필요)
