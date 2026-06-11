-- dev2/migrations/004_aggregate_table.sql
-- 파이프라인 2 (PRD 노드 I): M2+M3 취합 결과 저장 테이블
-- aggregate_node가 취합한 전체 이슈 + 요약을 PR 단위로 1행 저장한다.

CREATE TABLE pr_aggregated_results (
    id           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    task_id      text        NOT NULL,
    pr_id        text        NOT NULL,
    developer_id text        NOT NULL,
    issues       jsonb       NOT NULL DEFAULT '[]',   -- severity 정렬된 전체 이슈
    summary      jsonb       NOT NULL DEFAULT '{}',   -- {"critical": n, "major": n, "minor": n}
    created_at   timestamptz NOT NULL DEFAULT now()
);

-- task_id 조회 (PR 재취합 이력)
CREATE INDEX idx_pr_agg_task       ON pr_aggregated_results (task_id);

-- 개발자별 시계열 인사이트 (equality 먼저, range 나중)
CREATE INDEX idx_pr_agg_developer  ON pr_aggregated_results (developer_id, created_at DESC);

-- GIN: issues JSONB 검색 (특정 rule_id/concept 필터링)
CREATE INDEX idx_pr_agg_issues     ON pr_aggregated_results USING gin (issues);
