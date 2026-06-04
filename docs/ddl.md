-- =============================================================================
-- [조직 지식 관리 + 개발자 온보딩 멀티 에이전트 플랫폼] 통합 DDL
-- 대상: PostgreSQL 15+ / pgvector 0.5+
-- =============================================================================

-- -----------------------------------------------------------------------------
-- 0. Extensions
-- -----------------------------------------------------------------------------
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";  -- gen_random_uuid() 생성용
CREATE EXTENSION IF NOT EXISTS vector;        -- pgVector 임베딩 검색용


-- =============================================================================
-- 1. users — 통합 사용자(신입/시니어) 프로파일 (기존 developers 병합)
-- =============================================================================
CREATE TABLE users (
    user_id              UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    github_id            VARCHAR(100) UNIQUE,
    name                 VARCHAR(100) NOT NULL,
    email                VARCHAR(255) UNIQUE,
    github_url           VARCHAR(500),
    role                 VARCHAR(100) CHECK (role IN ('backend', 'frontend', 'devops', 'fullstack')),
    team                 VARCHAR(100),
    skill_level          VARCHAR(20)  NOT NULL DEFAULT 'junior'
                         CHECK (skill_level IN ('beginner', 'junior', 'mid', 'senior')),
    career_years         INT          NOT NULL DEFAULT 0,
    tech_stack           JSONB        NOT NULL DEFAULT '[]',
    diagnosis_source     VARCHAR(20)  NOT NULL DEFAULT 'form'
                         CHECK (diagnosis_source IN ('github', 'form', 'github+form')),
    diagnosis_confidence FLOAT        NOT NULL DEFAULT 0.0
                         CHECK (diagnosis_confidence BETWEEN 0.0 AND 1.0),
    current_week         INTEGER      DEFAULT 1 CHECK (current_week >= 1),
    joined_at            TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at           TIMESTAMPTZ  NOT NULL DEFAULT now()
);

COMMENT ON TABLE users IS '시스템에 등록된 전체 사용자(신입사원, 시니어) 통합 프로파일 및 진단 결과.';
COMMENT ON COLUMN users.user_id              IS '사용자 고유 식별자 (PK)';
COMMENT ON COLUMN users.github_id            IS 'GitHub 사용자명. Webhook 수신 시 식별자';
COMMENT ON COLUMN users.name                 IS '표시 이름';
COMMENT ON COLUMN users.email                IS '이메일 — 로그인 및 Slack 알림 발송 기준';
COMMENT ON COLUMN users.github_url           IS 'GitHub 레포 URL — 에이전트 진단 대상';
COMMENT ON COLUMN users.role                 IS '직무 (backend, frontend 등)';
COMMENT ON COLUMN users.team                 IS '소속 팀명 (팀 이동 감지용)';
COMMENT ON COLUMN users.skill_level          IS '진단/지정된 숙련도 (beginner~senior)';
COMMENT ON COLUMN users.career_years         IS '총 경력 연수';
COMMENT ON COLUMN users.tech_stack           IS '보유 기술스택 (JSON 배열)';
COMMENT ON COLUMN users.diagnosis_source     IS '진단 근거 (github, form 등)';
COMMENT ON COLUMN users.diagnosis_confidence IS '진단 신뢰도 (0.0~1.0)';
COMMENT ON COLUMN users.current_week         IS '현재 진행 중인 온보딩 주차';
COMMENT ON COLUMN users.joined_at            IS '입사 및 시스템 등록 일시';

CREATE INDEX idx_users_skill_level ON users (skill_level);
CREATE INDEX idx_users_team        ON users (team);


-- =============================================================================
-- 2. user_skills — 추출된 보유 스킬
-- =============================================================================
CREATE TABLE user_skills (
    id             UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id        UUID         NOT NULL REFERENCES users (user_id) ON DELETE CASCADE,
    skill_name     VARCHAR(100) NOT NULL,
    skill_type     VARCHAR(50)  NOT NULL DEFAULT 'framework'
                   CHECK (skill_type IN ('language', 'framework', 'tool', 'concept')),
    proficiency    VARCHAR(20)  NOT NULL DEFAULT 'beginner'
                   CHECK (proficiency IN ('beginner', 'intermediate', 'advanced')),
    extracted_from VARCHAR(20)  NOT NULL DEFAULT 'github'
                   CHECK (extracted_from IN ('github', 'form', 'llm')),
    created_at     TIMESTAMPTZ  NOT NULL DEFAULT now()
);

COMMENT ON TABLE user_skills IS '코드 분석 또는 입사 폼으로 추출한 사용자 보유 스킬 목록.';
COMMENT ON COLUMN user_skills.user_id IS 'users 테이블 참조 FK';
CREATE INDEX idx_user_skills_user ON user_skills (user_id);


-- =============================================================================
-- 3. documents — 원본 문서 메타데이터
-- =============================================================================
CREATE TABLE documents (
    doc_id        UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    title         VARCHAR(500) NOT NULL,
    source        VARCHAR(50)  NOT NULL
                  CHECK (source IN ('notion', 'confluence', 'upload', 'slack')),
    source_url    TEXT,
    author        TEXT,
    team          TEXT,
    category      VARCHAR(100)
                  CHECK (category IN ('코딩컨벤션', '아키텍처', '온보딩', '보안', '배포', '기타')),
    file_type     VARCHAR(20)
                  CHECK (file_type IN ('pdf', 'docx', 'pptx', 'md', 'txt')),
    file_path     TEXT,
    last_updated  TIMESTAMPTZ,
    upload_status VARCHAR(20)  NOT NULL DEFAULT 'processing'
                  CHECK (upload_status IN ('processing', 'validated', 'stored', 'failed')),
    created_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE documents IS '업로드/수집된 사내 원본 문서 메타데이터.';
COMMENT ON COLUMN documents.doc_id IS '문서 공통 식별키 (chunks 등에서 참조)';

CREATE INDEX idx_documents_category ON documents (category);


-- =============================================================================
-- 4. chunks — 청크 메타데이터
-- =============================================================================
CREATE TABLE chunks (
    chunk_id        UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    doc_id          UUID         NOT NULL REFERENCES documents (doc_id) ON DELETE CASCADE,
    parent_chunk_id UUID         REFERENCES chunks (chunk_id) ON DELETE SET NULL,
    chunk_type      VARCHAR(10)  NOT NULL CHECK (chunk_type IN ('parent', 'child')),
    content         TEXT         NOT NULL,
    token_count     INTEGER      CHECK (token_count > 0),
    page_number     INTEGER      CHECK (page_number > 0),
    section_header  VARCHAR(500),
    storage_path    TEXT,
    vector_id       TEXT,
    trace_id        VARCHAR(30),
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE chunks IS '문서를 검색용(parent)과 정밀매칭용(child)으로 분할한 청크 데이터.';
CREATE INDEX idx_chunks_doc_id ON chunks (doc_id);


-- =============================================================================
-- 5. chunk_embeddings — 임베딩 벡터 저장소
-- =============================================================================
CREATE TABLE chunk_embeddings (
    chunk_id   UUID         PRIMARY KEY REFERENCES chunks (chunk_id) ON DELETE CASCADE,
    embedding  vector(2000),  -- 🌟 팀 결정: GCP 제약으로 2000 차원 통일
    model_name VARCHAR(100) NOT NULL,
    content    TEXT         NOT NULL,
    metadata   JSONB        NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE chunk_embeddings IS 'pgVector를 활용한 임베딩 저장소 (차원: 2000).';
CREATE INDEX idx_chunk_embeddings_hnsw ON chunk_embeddings USING hnsw (embedding vector_cosine_ops);
CREATE INDEX idx_chunk_embeddings_metadata ON chunk_embeddings USING gin (metadata);


-- =============================================================================
-- 6. kms_documents — 정제/승인된 사내 지식 (KMS)
-- =============================================================================
CREATE TABLE kms_documents (
    id              UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    title           VARCHAR(300) NOT NULL,
    category        VARCHAR(100),
    content         TEXT         NOT NULL,
    author_id       UUID         REFERENCES users (user_id) ON DELETE SET NULL,
    status          VARCHAR(20)  NOT NULL DEFAULT 'draft'
                    CHECK (status IN ('draft', 'approved', 'deprecated')),
    objection_rate  FLOAT        NOT NULL DEFAULT 0.0
                    CHECK (objection_rate BETWEEN 0.0 AND 1.0),
    embedding       VECTOR(2000), -- 🌟 팀 결정 차원 통일
    last_updated_at TIMESTAMPTZ  NOT NULL DEFAULT now(),
    reviewed_at     TIMESTAMPTZ,
    reviewed_by     UUID         REFERENCES users (user_id) ON DELETE SET NULL
);

COMMENT ON TABLE kms_documents IS '시니어가 검토/승인한 사내 공식 지식 저장소 문서.';


-- =============================================================================
-- 7. topics — 커리큘럼 토픽 마스터
-- =============================================================================
CREATE TABLE topics (
    id                  UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
    name                VARCHAR(200)  NOT NULL,
    category            VARCHAR(100)  NOT NULL,
    difficulty          VARCHAR(20)   NOT NULL
                        CHECK (difficulty IN ('beginner', 'junior', 'mid', 'senior')),
    estimated_days      INT           NOT NULL DEFAULT 1 CHECK (estimated_days > 0),
    prerequisite_ids    UUID[]        NOT NULL DEFAULT '{}',
    target_levels       VARCHAR(20)[] NOT NULL DEFAULT '{}',
    is_company_specific BOOLEAN       NOT NULL DEFAULT false,
    neo4j_id            VARCHAR(100),
    created_at          TIMESTAMPTZ   NOT NULL DEFAULT now()
);

COMMENT ON TABLE topics IS '커리큘럼을 구성하는 학습 토픽 마스터 데이터.';


-- =============================================================================
-- 8. curriculums — 개인별 커리큘럼 헤더
-- =============================================================================
CREATE TABLE curriculums (
    id           UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id      UUID         NOT NULL REFERENCES users (user_id) ON DELETE CASCADE,
    status       VARCHAR(20)  NOT NULL DEFAULT 'active'
                 CHECK (status IN ('active', 'completed', 'paused')),
    total_weeks  INT          NOT NULL CHECK (total_weeks BETWEEN 1 AND 8),
    current_week INT          NOT NULL DEFAULT 1,
    generated_by VARCHAR(20)  NOT NULL DEFAULT 'agent'
                 CHECK (generated_by IN ('agent', 'manual', 'template')),
    started_at   TIMESTAMPTZ  NOT NULL DEFAULT now(),
    completed_at TIMESTAMPTZ,
    CONSTRAINT uq_curriculums_active UNIQUE (user_id, status)
);

COMMENT ON TABLE curriculums IS '개발자별 활성화된 온보딩 커리큘럼 헤더 (유저당 활성 1개 제한).';


-- =============================================================================
-- 9. curriculum_weeks — 주차별 학습 이력
-- =============================================================================
CREATE TABLE curriculum_weeks (
    id                   UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    curriculum_id        UUID         NOT NULL REFERENCES curriculums (id) ON DELETE CASCADE,
    week_number          INT          NOT NULL CHECK (week_number > 0),
    focus_area           VARCHAR(200),
    status               VARCHAR(20)  NOT NULL DEFAULT 'pending'
                         CHECK (status IN ('pending', 'in_progress', 'completed', 'retrying')),
    coverage_avg         FLOAT        NOT NULL DEFAULT 0.0 CHECK (coverage_avg BETWEEN 0.0 AND 1.0),
    critical_issue_count INT          NOT NULL DEFAULT 0,
    rework_count         INT          NOT NULL DEFAULT 0,
    repeat_issue_count   INT          NOT NULL DEFAULT 0,
    retry_count          INT          NOT NULL DEFAULT 0 CHECK (retry_count <= 3),
    topic_sequence       JSONB        NOT NULL DEFAULT '[]',
    skipped_topic_ids    UUID[]       NOT NULL DEFAULT '{}',
    started_at           TIMESTAMPTZ,
    completed_at         TIMESTAMPTZ,
    CONSTRAINT uq_curriculum_weeks UNIQUE (curriculum_id, week_number)
);

COMMENT ON TABLE curriculum_weeks IS '주차별 학습 구성과 진급 판정(커버리지, 이슈 카운트) 지표.';


-- =============================================================================
-- 10. learning_materials — 학습 자료
-- =============================================================================
CREATE TABLE learning_materials (
    id                UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    week_id           UUID         NOT NULL REFERENCES curriculum_weeks (id) ON DELETE CASCADE,
    topic_id          UUID         REFERENCES topics (id) ON DELETE SET NULL,
    title             VARCHAR(300) NOT NULL,
    source_type       VARCHAR(20)  NOT NULL
                      CHECK (source_type IN ('kms', 'external', 'llm')),
    url               TEXT,
    content           TEXT,
    is_verified       BOOLEAN      NOT NULL DEFAULT false,
    is_active         BOOLEAN      NOT NULL DEFAULT true,
    objection_count   INT          NOT NULL DEFAULT 0,
    embedding         VECTOR(2000), -- 🌟 팀 결정 차원 통일
    created_at        TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ  NOT NULL DEFAULT now()
);

COMMENT ON TABLE learning_materials IS '커리큘럼 주차에 배정된 학습 자료 매핑 및 본문.';


-- =============================================================================
-- 11. pull_requests — PR 메타정보
-- =============================================================================
CREATE TABLE pull_requests (
    id               UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id          UUID         NOT NULL REFERENCES users (user_id) ON DELETE CASCADE,
    week_id          UUID         REFERENCES curriculum_weeks (id) ON DELETE SET NULL,
    github_pr_url    TEXT,
    github_pr_number INT          NOT NULL,
    status           VARCHAR(20)  NOT NULL DEFAULT 'open'
                     CHECK (status IN ('open', 'closed', 'merged')),
    coverage         FLOAT        NOT NULL DEFAULT 0.0,
    is_lgtm          BOOLEAN      NOT NULL DEFAULT false,
    submitted_at     TIMESTAMPTZ  NOT NULL DEFAULT now()
);

COMMENT ON TABLE pull_requests IS 'GitHub Webhook 기반으로 수집되는 PR 요청 메타 정보.';

-- api-core Alembic 0005: webhook upsert 키 (GCP에 테이블만 있고 컬럼이 없을 때 ADD COLUMN)
-- ALTER TABLE pull_requests ADD COLUMN repository_full_name VARCHAR(255) NOT NULL;
-- CREATE UNIQUE INDEX uq_pull_requests_repo_number ON pull_requests (repository_full_name, github_pr_number);


-- =============================================================================
-- 12. scan_executions — PR 통합 분석 스캔 실행 기록
-- =============================================================================
CREATE TABLE scan_executions (
    id           BIGINT       GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    task_id      TEXT         NOT NULL,
    pr_id        TEXT         NOT NULL,
    user_id      UUID         NOT NULL REFERENCES users (user_id),
    scanned_at   TIMESTAMPTZ  NOT NULL DEFAULT now(),
    execution_ms INT
);

COMMENT ON TABLE scan_executions IS 'PR 코드를 4대 검증(정적분석, 보안, 테스트, 성능) 엔진이 스캔한 1회 실행 기록.';
CREATE INDEX idx_scan_executions_scanned_at ON scan_executions USING brin (scanned_at);


-- =============================================================================
-- 13. scan_issues — 개별 검증 이슈 내역
-- =============================================================================
CREATE TABLE scan_issues (
    id             BIGINT       GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    scan_id        BIGINT       NOT NULL REFERENCES scan_executions(id) ON DELETE CASCADE,
    agent          TEXT         NOT NULL
                   CHECK (agent IN ('static_analysis','security_scan','test_verification','performance')),
    severity       TEXT         NOT NULL
                   CHECK (severity IN ('Critical','Major','Minor')),
    rule_id        TEXT         NOT NULL,
    file           TEXT,
    line           INT,
    message        TEXT,
    suggestion     TEXT,
    similar_issues JSONB        NOT NULL DEFAULT '[]'
);

COMMENT ON TABLE scan_issues IS '스캔 실행 1건에서 발견된 개별 에러 및 경고 항목 기록.';
CREATE INDEX idx_scan_issues_scan_id ON scan_issues (scan_id);


-- =============================================================================
-- 14. pr_reviews — 에이전트 종합 판정 기록
-- =============================================================================
CREATE TABLE pr_reviews (
    review_id      UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    pr_id          TEXT         NOT NULL,
    user_id        UUID         NOT NULL REFERENCES users (user_id) ON DELETE RESTRICT,
    task_id        UUID,
    verdict        VARCHAR(20)  CHECK (verdict IN ('lgtm', 'rework', 'escalate')),
    critical_count INTEGER      NOT NULL DEFAULT 0,
    major_count    INTEGER      NOT NULL DEFAULT 0,
    minor_count    INTEGER      NOT NULL DEFAULT 0,
    issues         JSONB        NOT NULL DEFAULT '[]',
    retry_count    INTEGER      NOT NULL DEFAULT 0,
    reviewed_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE pr_reviews IS '에이전트가 여러 스캔 결과를 종합하여 최종 LGTM/Rework 등을 판정한 이력.';


-- =============================================================================
-- 15. mistake_patterns — 반복 실수 감지 레지스트리
-- =============================================================================
CREATE TABLE mistake_patterns (
    pattern_id   UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id      UUID         NOT NULL REFERENCES users (user_id) ON DELETE CASCADE,
    pattern_type TEXT         NOT NULL,
    occurrence   INTEGER      NOT NULL DEFAULT 1 CHECK (occurrence >= 1),
    first_seen   DATE         NOT NULL DEFAULT CURRENT_DATE,
    last_seen    DATE         NOT NULL DEFAULT CURRENT_DATE,
    resolved     BOOLEAN      NOT NULL DEFAULT FALSE,
    resolved_at  TIMESTAMPTZ
);

COMMENT ON TABLE mistake_patterns IS '특정 유저가 지속적으로 틀리는 문제 패턴을 누적 추적하는 테이블.';
CREATE UNIQUE INDEX idx_mistake_patterns_user_pattern ON mistake_patterns (user_id, pattern_type);


-- =============================================================================
-- 16. agent_traces — 에이전트 실행 로그(LangSmith 보조)
-- =============================================================================
CREATE TABLE agent_traces (
    trace_id      TEXT         NOT NULL,
    task_id       UUID,
    agent_name    TEXT         NOT NULL,
    doc_id        UUID         REFERENCES documents (doc_id) ON DELETE SET NULL,
    status        TEXT         NOT NULL CHECK (status IN ('success', 'fail', 'review')),
    started_at    TIMESTAMPTZ,
    ended_at      TIMESTAMPTZ,
    execution_ms  INTEGER      CHECK (execution_ms >= 0),
    error_message TEXT,
    created_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    CONSTRAINT pk_agent_traces PRIMARY KEY (trace_id, task_id) DEFERRABLE INITIALLY DEFERRED
);

COMMENT ON TABLE agent_traces IS 'LangGraph 에이전트들의 개별 노드/워크플로우 실행 시작-종료 트레이스 로그.';


-- =============================================================================
-- 17. objections — 학습 자료 이의 제기
-- =============================================================================
CREATE TABLE objections (
    id                UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id           UUID         NOT NULL REFERENCES users (user_id) ON DELETE CASCADE,
    material_id       UUID         NOT NULL REFERENCES learning_materials (id) ON DELETE CASCADE,
    objection_type    VARCHAR(20)  NOT NULL CHECK (objection_type IN ('wrong', 'too_easy', 'too_hard')),
    description       TEXT,
    resolution_status VARCHAR(20)  NOT NULL DEFAULT 'pending'
                      CHECK (resolution_status IN ('pending', 'resolved', 'dismissed')),
    created_at        TIMESTAMPTZ  NOT NULL DEFAULT now(),
    resolved_at       TIMESTAMPTZ
);

COMMENT ON TABLE objections IS '개발자가 학습 자료나 난이도에 대해 제기한 이의 기록.';


-- =============================================================================
-- 18. senior_approvals — Human-in-the-Loop 개입 결재
-- =============================================================================
CREATE TABLE senior_approvals (
    id            UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id       UUID         NOT NULL REFERENCES users (user_id) ON DELETE CASCADE,
    curriculum_id UUID         REFERENCES curriculums (id) ON DELETE SET NULL,
    approval_type VARCHAR(50)  NOT NULL
                  CHECK (approval_type IN ('early_promotion', 'critical_repeat', 'curriculum_redesign')),
    status        VARCHAR(20)  NOT NULL DEFAULT 'pending'
                  CHECK (status IN ('pending', 'approved', 'rejected')),
    approver_id   UUID         REFERENCES users (user_id),
    note          TEXT,
    requested_at  TIMESTAMPTZ  NOT NULL DEFAULT now(),
    resolved_at   TIMESTAMPTZ
);

COMMENT ON TABLE senior_approvals IS '에이전트가 독자적으로 판정할 수 없는 중대 상황에 대해 시니어의 승인을 기록.';


-- =============================================================================
-- 19. slack_notifications — 알림 발송 큐
-- =============================================================================
CREATE TABLE slack_notifications (
    id           UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id      UUID         NOT NULL REFERENCES users (user_id) ON DELETE CASCADE,
    event_type   VARCHAR(50)  NOT NULL,
    message      TEXT         NOT NULL,
    is_sent      BOOLEAN      NOT NULL DEFAULT false,
    retry_count  INT          NOT NULL DEFAULT 0,
    sent_at      TIMESTAMPTZ,
    created_at   TIMESTAMPTZ  NOT NULL DEFAULT now()
);

COMMENT ON TABLE slack_notifications IS '비동기 큐잉을 위한 Slack 발송 대기 메시지 보관 테이블.';


-- =============================================================================
-- 20. 기본 트리거 및 View (예시로 updated_at 트리거 유지)
-- =============================================================================
CREATE OR REPLACE FUNCTION fn_set_updated_at()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$;

COMMENT ON FUNCTION fn_set_updated_at IS 'UPDATE 발생 시 updated_at 컬럼을 현재 시간으로 동기화하는 트리거 함수';

-- 트리거 적용 (대표 테이블)
CREATE TRIGGER trg_users_updated_at
    BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION fn_set_updated_at();

CREATE TRIGGER trg_learning_materials_updated_at
    BEFORE UPDATE ON learning_materials
    FOR EACH ROW EXECUTE FUNCTION fn_set_updated_at();


-- =============================================================================
-- 부록 A. teams / team_members (운영 DB additive — api-core Alembic 0004)
-- =============================================================================
-- 기존 users.team(팀명 문자열)과 동기화. 팀 역할은 team_role (users.role 직무와 분리).

CREATE TABLE IF NOT EXISTS teams (
    team_id               UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    name                  VARCHAR(100) NOT NULL UNIQUE,
    github_repo_full_name VARCHAR(255) NOT NULL UNIQUE,
    created_at            TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at            TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS team_members (
    id         UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    team_id    UUID         NOT NULL REFERENCES teams (team_id) ON DELETE CASCADE,
    user_id    UUID         NOT NULL REFERENCES users (user_id) ON DELETE CASCADE,
    team_role  VARCHAR(20)  NOT NULL DEFAULT 'member'
               CHECK (team_role IN ('lead', 'member')),
    joined_at  TIMESTAMPTZ  NOT NULL DEFAULT now(),
    CONSTRAINT uq_team_members_team_user UNIQUE (team_id, user_id)
);

CREATE INDEX IF NOT EXISTS idx_teams_repo ON teams (github_repo_full_name);
CREATE INDEX IF NOT EXISTS idx_team_members_user ON team_members (user_id);