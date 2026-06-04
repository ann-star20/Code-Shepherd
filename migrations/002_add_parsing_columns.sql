-- 마이그레이션 002: documents 테이블에 파싱 상세 컬럼 추가
-- Document Parser Agent (Stage 1) 결과를 저장하기 위한 컬럼

ALTER TABLE documents
    ADD COLUMN IF NOT EXISTS parser_used      TEXT,
    ADD COLUMN IF NOT EXISTS doc_complexity   TEXT,
    ADD COLUMN IF NOT EXISTS parsing_time_ms  INTEGER;

-- quality_score는 000_initial_schema.sql에 이미 존재 (FLOAT 타입 확인됨)
-- parser_used: "pymupdf", "python_docx", "upstage", "unstructured", "direct_read", "hitl_required" 등
-- doc_complexity: "LOW", "MEDIUM", "HIGH"
-- parsing_time_ms: 변환 소요 시간 (밀리초)
