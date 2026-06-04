-- Knowledge Graph Agent Pipeline — PostgreSQL DDL
-- Run: psql -h localhost -p 5433 -U postgres -d postgres -f schema.sql

CREATE TABLE IF NOT EXISTS documents (
    id          SERIAL PRIMARY KEY,
    doc_id      VARCHAR(255) UNIQUE NOT NULL,   -- build_doc_id: PREFIX_urlpart_sha8
    url         TEXT        NOT NULL,
    prefix      VARCHAR(10) NOT NULL DEFAULT 'EXT',
    status      VARCHAR(20) NOT NULL DEFAULT 'active' CHECK (status IN ('active','superseded')),
    etag        VARCHAR(255),
    content_hash VARCHAR(64),
    crawled_at  TIMESTAMPTZ,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS pipeline_jobs (
    id            SERIAL PRIMARY KEY,
    session_id    UUID        NOT NULL,
    doc_id        VARCHAR(255) REFERENCES documents(doc_id) ON DELETE SET NULL,
    status        VARCHAR(20) NOT NULL DEFAULT 'PENDING'
                  CHECK (status IN ('PENDING','RUNNING','SUCCESS','FAILED')),
    error_message TEXT,
    retry_count   INTEGER     NOT NULL DEFAULT 0,
    started_at    TIMESTAMPTZ,
    failed_at     TIMESTAMPTZ,
    completed_at  TIMESTAMPTZ,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS staging_concepts (
    id                   SERIAL PRIMARY KEY,
    session_id           UUID         NOT NULL,
    doc_id               VARCHAR(255) NOT NULL REFERENCES documents(doc_id),
    concept_name         VARCHAR(255) NOT NULL,
    concept_domain       VARCHAR(20)  NOT NULL CHECK (concept_domain IN ('security','performance','both')),
    severity             VARCHAR(20)  NOT NULL CHECK (severity IN ('critical','high','medium','low','info')),
    description_ko       TEXT         NOT NULL,
    concept_type         VARCHAR(100),
    cwe_id               VARCHAR(20),
    owasp_id             VARCHAR(30),
    aliases              JSONB        NOT NULL DEFAULT '[]',
    security_mechanisms  JSONB        NOT NULL DEFAULT '[]',
    affected_components  JSONB        NOT NULL DEFAULT '[]',
    config_properties    JSONB        NOT NULL DEFAULT '[]',
    root_cause           TEXT,
    status               VARCHAR(20)  NOT NULL DEFAULT 'DRAFT'
                         CHECK (status IN ('DRAFT','APPROVED','COMMITTED','REJECTED')),
    reviewed_at          TIMESTAMPTZ,
    created_at           TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at           TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS concepts (
    id                   SERIAL PRIMARY KEY,
    concept_name         VARCHAR(255) NOT NULL,
    concept_domain       VARCHAR(20)  NOT NULL CHECK (concept_domain IN ('security','performance','both')),
    severity             VARCHAR(20)  NOT NULL CHECK (severity IN ('critical','high','medium','low','info')),
    description_ko       TEXT         NOT NULL,
    concept_type         VARCHAR(100),
    cwe_id               VARCHAR(20),
    owasp_id             VARCHAR(30),
    aliases              JSONB        NOT NULL DEFAULT '[]',
    security_mechanisms  JSONB        NOT NULL DEFAULT '[]',
    affected_components  JSONB        NOT NULL DEFAULT '[]',
    config_properties    JSONB        NOT NULL DEFAULT '[]',
    root_cause           TEXT,
    neo4j_node_id        VARCHAR(255),
    first_seen_doc_id    VARCHAR(255),
    last_updated_doc_id  VARCHAR(255),
    created_at           TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at           TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    UNIQUE (concept_name, concept_domain)
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_pipeline_jobs_session   ON pipeline_jobs    (session_id);
CREATE INDEX IF NOT EXISTS idx_pipeline_jobs_status    ON pipeline_jobs    (status);
CREATE INDEX IF NOT EXISTS idx_staging_session         ON staging_concepts (session_id);
CREATE INDEX IF NOT EXISTS idx_staging_status          ON staging_concepts (status);
CREATE INDEX IF NOT EXISTS idx_staging_doc             ON staging_concepts (doc_id);
CREATE INDEX IF NOT EXISTS idx_concepts_owasp          ON concepts         (owasp_id);
CREATE INDEX IF NOT EXISTS idx_concepts_cwe            ON concepts         (cwe_id);
