-- BRIN: scanned_at 시계열 (순차 증가 → B-tree보다 크기 90% 작음)
CREATE INDEX idx_scan_executions_scanned_at
    ON scan_executions USING brin (scanned_at);

-- 복합: developer 인사이트 쿼리 (equality 먼저, range 나중)
CREATE INDEX idx_scan_executions_developer_time
    ON scan_executions (developer_id, scanned_at DESC);

-- 커버링: /insights/developer 쿼리 (테이블 스캔 제거)
CREATE INDEX idx_executions_developer_covering
    ON scan_executions (developer_id)
    INCLUDE (id, scanned_at);

-- FK 인덱스: JOIN 성능
CREATE INDEX idx_scan_issues_scan_id    ON scan_issues (scan_id);
CREATE INDEX idx_scan_summaries_scan_id ON scan_summaries (scan_id);

-- 복합: 팀별 인사이트 GROUP BY rule_id, severity
CREATE INDEX idx_scan_issues_rule_severity
    ON scan_issues (rule_id, severity);

-- 부분 인덱스: Critical만 (에스컬레이션 조회 전용, 전체의 5~10%)
CREATE INDEX idx_scan_issues_critical
    ON scan_issues (scan_id, rule_id)
    WHERE severity = 'Critical';

-- GIN: similar_issues JSONB 검색
CREATE INDEX idx_scan_issues_similar
    ON scan_issues USING gin (similar_issues);
