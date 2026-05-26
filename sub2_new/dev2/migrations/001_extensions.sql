CREATE EXTENSION IF NOT EXISTS pg_stat_statements;

-- 보안 기본값
REVOKE ALL ON SCHEMA public FROM public;

-- 타임아웃 설정
ALTER SYSTEM SET idle_in_transaction_session_timeout = '30s';
ALTER SYSTEM SET statement_timeout = '30s';
SELECT pg_reload_conf();
