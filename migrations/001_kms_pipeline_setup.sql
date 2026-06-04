-- ============================================================
-- KMS 파이프라인 마이그레이션 (2026-05-24)
-- Google Cloud SQL Studio에서 순서대로 실행
-- ============================================================

-- ============================================================
-- STEP 0: 벡터 차원 확인 (실행 후 결과 확인)
-- ============================================================
SELECT pg_catalog.format_type(atttypid, atttypmod) AS embedding_type
FROM pg_catalog.pg_attribute
WHERE attrelid = 'chunk_embeddings'::regclass
  AND attname = 'embedding'
  AND attnum > 0;
-- 결과가 vector(1024)이면 STEP 3 인덱스 생성 진행
-- 결과가 다른 차원이면 팀 내 합의 후 재결정 필요

-- ============================================================
-- STEP 1: documents 테이블 — KMS 파이프라인 필드 추가
-- ============================================================
ALTER TABLE documents
  ADD COLUMN IF NOT EXISTS page_count     INTEGER,
  ADD COLUMN IF NOT EXISTS parser         VARCHAR(50) DEFAULT 'llama_parse',
  ADD COLUMN IF NOT EXISTS markdown_path  TEXT,
  ADD COLUMN IF NOT EXISTS storage_synced BOOLEAN     DEFAULT FALSE,
  ADD COLUMN IF NOT EXISTS neo4j_synced   BOOLEAN     DEFAULT FALSE;

-- 코드에서 사용하는 문서 처리 상태와 DB CHECK 제약을 동기화한다.
DO $$
DECLARE
    constraint_name TEXT;
BEGIN
    FOR constraint_name IN
        SELECT con.conname
        FROM pg_constraint con
        JOIN pg_class rel ON rel.oid = con.conrelid
        JOIN pg_attribute attr
          ON attr.attrelid = rel.oid
         AND attr.attnum = ANY(con.conkey)
        WHERE rel.relname = 'documents'
          AND con.contype = 'c'
          AND attr.attname = 'upload_status'
    LOOP
        EXECUTE format('ALTER TABLE documents DROP CONSTRAINT %I', constraint_name);
    END LOOP;
END $$;

ALTER TABLE documents
  ADD CONSTRAINT documents_upload_status_check
  CHECK (
    upload_status IN (
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
    )
  );

-- ============================================================
-- STEP 2: HITL 큐 테이블 신규 생성
-- HITL 상태를 서버 재시작 후에도 보존하기 위해 DB에 영속화
-- ============================================================
CREATE TABLE IF NOT EXISTS hitl_queue (
    queue_id        UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    doc_id          UUID        REFERENCES documents(doc_id) ON DELETE CASCADE,
    stage           VARCHAR(20) NOT NULL,       -- 'stage2_validate | stage4_chunk_validate'
    reason          TEXT        NOT NULL,
    quality_score   FLOAT,
    issues          JSONB,
    status          VARCHAR(20) DEFAULT 'pending',  -- 'pending | approved | rejected | reprocessing'
    reviewer_id     VARCHAR(100),               -- users.github_id 참조
    reviewed_at     TIMESTAMPTZ,
    review_note     TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_hitl_queue_doc_id ON hitl_queue(doc_id);
CREATE INDEX IF NOT EXISTS idx_hitl_queue_status  ON hitl_queue(status);

-- ============================================================
-- STEP 3: agent_traces — 요약 필드 추가
-- LangSmith 미사용 환경에서도 입출력 추적 가능하도록
-- ============================================================
ALTER TABLE agent_traces
  ADD COLUMN IF NOT EXISTS input_summary  TEXT,
  ADD COLUMN IF NOT EXISTS output_summary TEXT;

-- ============================================================
-- STEP 4: chunk_embeddings — HNSW 인덱스
-- STEP 0 결과가 vector(1024)인 경우에만 실행
-- ============================================================
CREATE INDEX IF NOT EXISTS idx_chunk_embeddings_hnsw
    ON chunk_embeddings
    USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

-- ============================================================
-- STEP 5: 인덱스 확인
-- ============================================================
SELECT indexname, indexdef
FROM pg_indexes
WHERE tablename IN ('documents', 'chunks', 'chunk_embeddings', 'hitl_queue', 'agent_traces')
ORDER BY tablename, indexname;

-- ============================================================
-- STEP 6: 결과 확인
-- ============================================================
SELECT
    table_name,
    column_name,
    data_type
FROM information_schema.columns
WHERE table_schema = 'public'
  AND table_name IN ('documents', 'hitl_queue', 'agent_traces')
ORDER BY table_name, ordinal_position;
