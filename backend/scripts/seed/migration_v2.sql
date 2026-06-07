-- =============================================================================
-- migration_v2.sql — 기존 DB 스키마 보강 (멱등성 보장)
-- 실행: psql $DATABASE_URL -f scripts/seed/migration_v2.sql
-- =============================================================================

-- ── documents: infer_confidence 컬럼 추가
ALTER TABLE documents
    ADD COLUMN IF NOT EXISTS infer_confidence FLOAT;

-- ── pipeline_logs: 구형 컬럼 제거 + 신규 컬럼 추가
DO $$
BEGIN
    -- session_id 추가
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name='pipeline_logs' AND column_name='session_id'
    ) THEN
        ALTER TABLE pipeline_logs ADD COLUMN session_id UUID;
    END IF;

    -- agent 추가
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name='pipeline_logs' AND column_name='agent'
    ) THEN
        ALTER TABLE pipeline_logs ADD COLUMN agent TEXT;
    END IF;

    -- level 추가
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name='pipeline_logs' AND column_name='level'
    ) THEN
        ALTER TABLE pipeline_logs ADD COLUMN level TEXT NOT NULL DEFAULT 'INFO';
    END IF;

    -- message 추가
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name='pipeline_logs' AND column_name='message'
    ) THEN
        ALTER TABLE pipeline_logs ADD COLUMN message TEXT;
    END IF;

    -- created_at 추가
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name='pipeline_logs' AND column_name='created_at'
    ) THEN
        ALTER TABLE pipeline_logs ADD COLUMN created_at TIMESTAMPTZ DEFAULT now();
    END IF;

    -- 구형 컬럼 제거 (존재하는 경우에만)
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name='pipeline_logs' AND column_name='stage'
    ) THEN
        ALTER TABLE pipeline_logs DROP COLUMN stage;
    END IF;

    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name='pipeline_logs' AND column_name='status'
    ) THEN
        ALTER TABLE pipeline_logs DROP COLUMN status;
    END IF;

    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name='pipeline_logs' AND column_name='started_at'
    ) THEN
        ALTER TABLE pipeline_logs DROP COLUMN started_at;
    END IF;

    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name='pipeline_logs' AND column_name='ended_at'
    ) THEN
        ALTER TABLE pipeline_logs DROP COLUMN ended_at;
    END IF;

    -- agent NOT NULL 제약 적용 (기존 NULL 행 보호 후)
    UPDATE pipeline_logs SET agent = 'unknown' WHERE agent IS NULL;
    BEGIN
        ALTER TABLE pipeline_logs ALTER COLUMN agent SET NOT NULL;
    EXCEPTION WHEN OTHERS THEN NULL;
    END;

    -- session_id NOT NULL 제약 적용
    UPDATE pipeline_logs
    SET session_id = gen_random_uuid()
    WHERE session_id IS NULL;
    BEGIN
        ALTER TABLE pipeline_logs ALTER COLUMN session_id SET NOT NULL;
    EXCEPTION WHEN OTHERS THEN NULL;
    END;
END
$$;
