-- [CLAUDE.md §3] agent_traces 연동을 위해 trace_id 컬럼 포함
-- trace_id 형식: "pr_{12hex}" (PR 파이프라인), "{parent}_{agent}_{4hex}" (서브 에이전트)
CREATE TABLE scan_executions (
    id            bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    task_id       text        NOT NULL,
    trace_id      text        NOT NULL,  -- agent_traces.trace_id 연결 (CLAUDE.md §3)
    pr_id         text        NOT NULL,
    developer_id  text        NOT NULL,
    scanned_at    timestamptz NOT NULL DEFAULT now(),
    execution_ms  int
);

CREATE TABLE scan_issues (
    id                   bigint  GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    scan_id              bigint  NOT NULL REFERENCES scan_executions(id) ON DELETE CASCADE,
    agent                text    NOT NULL,   -- 'static_analysis' | 'security_scan'
    severity             text    NOT NULL,   -- 'Critical' | 'Major' | 'Minor'
    rule_id              text    NOT NULL,
    file                 text,
    line                 int,
    message              text,
    suggestion           text,
    similar_issues       jsonb    NOT NULL DEFAULT '[]',
    is_false_positive    boolean  NOT NULL DEFAULT false  -- 오탐 표시
);

CREATE TABLE scan_summaries (
    id        bigint  GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    scan_id   bigint  NOT NULL REFERENCES scan_executions(id) ON DELETE CASCADE,
    agent     text    NOT NULL,
    critical  int     NOT NULL DEFAULT 0,
    major     int     NOT NULL DEFAULT 0,
    minor     int     NOT NULL DEFAULT 0,
    CONSTRAINT uq_scan_summaries_scan_agent UNIQUE (scan_id, agent)
);
