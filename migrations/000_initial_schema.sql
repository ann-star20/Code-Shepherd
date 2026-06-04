-- ============================================================
-- KMS + 온보딩 플랫폼 — 전체 초기 스키마
-- Google Cloud SQL Studio에서 실행
--
-- 001_kms_pipeline_setup.sql 컬럼도 여기에 포함되어 있어
-- 이 파일 하나만 실행하면 됩니다.
-- ============================================================

-- pgVector 확장 활성화 (Cloud SQL에서 이미 활성화돼 있으면 무시됨)
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ============================================================
-- users (개발자 프로파일)
-- ============================================================
CREATE TABLE IF NOT EXISTS users (
    user_id       UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    github_id     VARCHAR(100) UNIQUE NOT NULL,
    name          VARCHAR(200),
    email         VARCHAR(200),
    skill_level   VARCHAR(20)  NOT NULL DEFAULT 'junior'
                  CHECK (skill_level IN ('junior', 'mid', 'senior')),
    tech_stack    JSONB        NOT NULL DEFAULT '[]',
    created_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

-- ============================================================
-- documents (원본 문서 메타데이터)
-- ============================================================
CREATE TABLE IF NOT EXISTS documents (
    doc_id         UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    title          TEXT         NOT NULL,
    source         VARCHAR(50)  NOT NULL DEFAULT 'upload',
    category       VARCHAR(100),
    file_type      VARCHAR(20),
    file_path      TEXT,
    markdown_path  TEXT,
    storage_synced BOOLEAN      NOT NULL DEFAULT FALSE,
    neo4j_synced   BOOLEAN      NOT NULL DEFAULT FALSE,
    page_count     INTEGER,
    parser         VARCHAR(50)  DEFAULT 'llama_parse',
    upload_status  VARCHAR(30)  NOT NULL DEFAULT 'processing'
                   CHECK (upload_status IN (
                       'processing',
                       'validated',
                       'stored',
                       'stored_partial',
                       'hitl_pending',
                       'approved',
                       'rejected',
                       'reprocessing',
                       'reprocess_failed',
                       'failed'
                   )),
    created_at     TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at     TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_documents_upload_status ON documents(upload_status);
CREATE INDEX IF NOT EXISTS idx_documents_source        ON documents(source);
CREATE INDEX IF NOT EXISTS idx_documents_created_at    ON documents(created_at DESC);

-- ============================================================
-- chunks (청킹 결과)
-- ============================================================
CREATE TABLE IF NOT EXISTS chunks (
    chunk_id        UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    doc_id          UUID        NOT NULL REFERENCES documents(doc_id) ON DELETE CASCADE,
    parent_chunk_id UUID        REFERENCES chunks(chunk_id) ON DELETE SET NULL,
    chunk_type      VARCHAR(20) NOT NULL CHECK (chunk_type IN ('parent', 'child')),
    content         TEXT        NOT NULL,
    token_count     INTEGER,
    page_number     INTEGER,
    section_header  TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_chunks_doc_id          ON chunks(doc_id);
CREATE INDEX IF NOT EXISTS idx_chunks_parent_chunk_id ON chunks(parent_chunk_id);
CREATE INDEX IF NOT EXISTS idx_chunks_chunk_type      ON chunks(chunk_type);

-- ============================================================
-- chunk_embeddings (pgVector — 1024차원, Ollama bge-m3)
-- ============================================================
CREATE TABLE IF NOT EXISTS chunk_embeddings (
    chunk_id   UUID         PRIMARY KEY REFERENCES chunks(chunk_id) ON DELETE CASCADE,
    embedding  vector(1024) NOT NULL,
    model_name VARCHAR(100) NOT NULL DEFAULT 'bge-m3',
    content    TEXT         NOT NULL,
    metadata   JSONB        NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

-- HNSW 인덱스 (코사인 유사도 검색용)
CREATE INDEX IF NOT EXISTS idx_chunk_embeddings_hnsw
    ON chunk_embeddings
    USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

-- ============================================================
-- agent_traces (파이프라인 실행 추적)
-- ============================================================
CREATE TABLE IF NOT EXISTS agent_traces (
    trace_id       VARCHAR(100) PRIMARY KEY,
    task_id        UUID,
    agent_name     VARCHAR(100) NOT NULL,
    doc_id         UUID         REFERENCES documents(doc_id) ON DELETE SET NULL,
    status         VARCHAR(20)  NOT NULL DEFAULT 'success'
                   CHECK (status IN ('success', 'fail', 'review')),
    started_at     TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    ended_at       TIMESTAMPTZ,
    execution_ms   INTEGER,
    error_message  TEXT,
    input_summary  TEXT,
    output_summary TEXT
);

CREATE INDEX IF NOT EXISTS idx_agent_traces_doc_id    ON agent_traces(doc_id);
CREATE INDEX IF NOT EXISTS idx_agent_traces_status    ON agent_traces(status);
CREATE INDEX IF NOT EXISTS idx_agent_traces_task_id   ON agent_traces(task_id);

-- ============================================================
-- hitl_queue (Human-in-the-Loop 검토 큐)
-- ============================================================
CREATE TABLE IF NOT EXISTS hitl_queue (
    queue_id      UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    doc_id        UUID        REFERENCES documents(doc_id) ON DELETE CASCADE,
    stage         VARCHAR(20) NOT NULL,
    reason        TEXT        NOT NULL,
    quality_score FLOAT,
    issues        JSONB,
    status        VARCHAR(20) NOT NULL DEFAULT 'pending'
                  CHECK (status IN ('pending', 'approved', 'rejected', 'reprocessing')),
    reviewer_id   VARCHAR(100),
    reviewed_at   TIMESTAMPTZ,
    review_note   TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_hitl_queue_doc_id ON hitl_queue(doc_id);
CREATE INDEX IF NOT EXISTS idx_hitl_queue_status  ON hitl_queue(status);

-- ============================================================
-- pr_reviews (PR 리뷰 이력 — Dev4/5 연동용)
-- ============================================================
CREATE TABLE IF NOT EXISTS pr_reviews (
    review_id     UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    pr_id         VARCHAR(100) NOT NULL,
    user_id       UUID        REFERENCES users(user_id) ON DELETE SET NULL,
    verdict       VARCHAR(20) CHECK (verdict IN ('lgtm', 'rework', 'escalate')),
    comment_body  TEXT,
    issues        JSONB       NOT NULL DEFAULT '[]',
    summary       JSONB       NOT NULL DEFAULT '{}',
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_pr_reviews_pr_id    ON pr_reviews(pr_id);
CREATE INDEX IF NOT EXISTS idx_pr_reviews_user_id  ON pr_reviews(user_id);
CREATE INDEX IF NOT EXISTS idx_pr_reviews_verdict  ON pr_reviews(verdict);

-- ============================================================
-- mistake_patterns (반복 실수 패턴 — Dev5 연동용)
-- ============================================================
CREATE TABLE IF NOT EXISTS mistake_patterns (
    pattern_id       UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id          UUID        REFERENCES users(user_id) ON DELETE CASCADE,
    pattern_type     VARCHAR(100) NOT NULL,
    occurrence_count INTEGER     NOT NULL DEFAULT 1,
    last_seen_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    example_pr_ids   JSONB       NOT NULL DEFAULT '[]',
    resolved         BOOLEAN     NOT NULL DEFAULT FALSE,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_mistake_patterns_user_id ON mistake_patterns(user_id);

-- ============================================================
-- 시드 데이터 — MVP 데모용 최소 레코드
-- ============================================================
INSERT INTO users (user_id, github_id, name, skill_level, tech_stack)
VALUES
    ('00000000-0000-0000-0000-000000000001', 'junior_dev_01', '주니어 개발자',
     'junior', '["python","fastapi","postgresql"]'),
    ('00000000-0000-0000-0000-000000000002', 'senior_dev_01', '시니어 개발자',
     'senior', '["python","fastapi","postgresql","langchain"]')
ON CONFLICT (github_id) DO NOTHING;

-- ============================================================
-- 확인 쿼리
-- ============================================================
SELECT table_name, pg_size_pretty(pg_total_relation_size(quote_ident(table_name)))
FROM information_schema.tables
WHERE table_schema = 'public'
ORDER BY table_name;
