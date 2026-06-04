-- 마이그레이션 006: documents.category CHECK 제약 삭제
-- KB Evolution에서 신규 카테고리를 documents.category에 저장할 수 있도록
-- categories 테이블이 유효 카테고리의 단일 소스가 됐으므로 이 제약은 불필요

ALTER TABLE documents DROP CONSTRAINT IF EXISTS documents_category_check;
