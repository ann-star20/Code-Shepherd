-- 마이그레이션 005: documents 테이블에 original_filename 컬럼 추가
-- HITL 큐 UI에서 원본 파일명을 표시하기 위해 필요

ALTER TABLE documents
    ADD COLUMN IF NOT EXISTS original_filename TEXT;
