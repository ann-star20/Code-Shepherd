CREATE TABLE scan_executions (
    id            bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    task_id       text        NOT NULL,
    pr_id         text        NOT NULL,
    user_id       uuid        NOT NULL REFERENCES users(user_id),
    scanned_at    timestamptz NOT NULL DEFAULT now(),
    execution_ms  int
);

CREATE TABLE scan_issues (
    id                      bigint   GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    scan_id                 bigint   NOT NULL REFERENCES scan_executions(id) ON DELETE CASCADE,
    agent                   text     NOT NULL,
    severity                text     NOT NULL,
    rule_id                 text     NOT NULL,
    file                    text,
    line                    int,
    message                 text,
    suggestion              text,
    similar_issues          jsonb    NOT NULL DEFAULT '[]',
    keyword                 text     DEFAULT '',
    sub_keyword             text     DEFAULT '',
    metric_value            text     DEFAULT '',
    sub_category            text     DEFAULT '',
    code_context            text     DEFAULT '',
    issue_type              text,
    resolution_example      text,
    status                  text     DEFAULT 'Open',
    concept_id              text,
    mistake_type_concept_id text,
    confidence_score        double precision,
    code_snippet            text,
    learning_context        jsonb,
    taxonomy                jsonb,
    created_at              timestamp DEFAULT now(),
    CONSTRAINT scan_issues_agent_check    CHECK (agent    = ANY (ARRAY['static_analysis','security_scan','test_verification','performance'])),
    CONSTRAINT scan_issues_severity_check CHECK (severity = ANY (ARRAY['Critical','Major','Minor']))
);

CREATE TABLE scan_summaries (
    id        bigint  GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    scan_id   bigint  NOT NULL REFERENCES scan_executions(id) ON DELETE CASCADE,
    agent     text    NOT NULL,
    critical  int     NOT NULL DEFAULT 0,
    major     int     NOT NULL DEFAULT 0,
    minor     int     NOT NULL DEFAULT 0,
    metrics   jsonb,
    CONSTRAINT scan_summaries_agent_check CHECK (agent = ANY (ARRAY['static_analysis','security_scan','test_verification','performance']))
);

ALTER TABLE ONLY scan_summaries
    ADD CONSTRAINT uq_scan_summaries_scan_agent UNIQUE (scan_id, agent);
