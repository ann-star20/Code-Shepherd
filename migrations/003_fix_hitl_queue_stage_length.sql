-- Migration 003: hitl_queue.stage 컬럼 VARCHAR(20) → VARCHAR(30)
-- 문제: stage4_chunk_validate(21자), stage5b_metadata_validate(24자)가 VARCHAR(20) 초과
-- 영향: HITL 재처리 시 stage5b/stage4 HITL INSERT 실패 → reprocess_failed

ALTER TABLE hitl_queue
    ALTER COLUMN stage TYPE VARCHAR(30);
