--
-- PostgreSQL database dump
--

\restrict 2NACGsdnVHTsWGMDmukRkHeKEyFAsFLa37zVQrsFnCziUxMDrwFFNmLawikVQy6

-- Dumped from database version 18.3
-- Dumped by pg_dump version 18.3

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET transaction_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Name: google_vacuum_mgmt; Type: SCHEMA; Schema: -; Owner: -
--

CREATE SCHEMA google_vacuum_mgmt;


--
-- Name: google_vacuum_mgmt; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS google_vacuum_mgmt WITH SCHEMA google_vacuum_mgmt;


--
-- Name: EXTENSION google_vacuum_mgmt; Type: COMMENT; Schema: -; Owner: -
--

COMMENT ON EXTENSION google_vacuum_mgmt IS 'extension for assistive operational tooling';


--
-- Name: uuid-ossp; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS "uuid-ossp" WITH SCHEMA public;


--
-- Name: EXTENSION "uuid-ossp"; Type: COMMENT; Schema: -; Owner: -
--

COMMENT ON EXTENSION "uuid-ossp" IS 'generate universally unique identifiers (UUIDs)';


--
-- Name: vector; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA public;


--
-- Name: EXTENSION vector; Type: COMMENT; Schema: -; Owner: -
--

COMMENT ON EXTENSION vector IS 'vector data type and ivfflat and hnsw access methods';


--
-- Name: fn_set_updated_at(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.fn_set_updated_at() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$;


SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: agent_traces; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.agent_traces (
    trace_id character varying(100) NOT NULL,
    task_id uuid,
    agent_name character varying(100) NOT NULL,
    doc_id uuid,
    status character varying(20) DEFAULT 'success'::character varying NOT NULL,
    started_at timestamp with time zone DEFAULT now() NOT NULL,
    ended_at timestamp with time zone,
    execution_ms integer,
    error_message text,
    input_summary text,
    output_summary text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT agent_traces_execution_ms_check CHECK ((execution_ms >= 0)),
    CONSTRAINT agent_traces_status_check CHECK (((status)::text = ANY ((ARRAY['running'::character varying, 'success'::character varying, 'fail'::character varying, 'review'::character varying])::text[])))
);


--
-- Name: alembic_version; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.alembic_version (
    version_num character varying(32) NOT NULL
);


--
-- Name: alembic_version_m4; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.alembic_version_m4 (
    version_num character varying(32) NOT NULL
);


--
-- Name: auth_sessions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.auth_sessions (
    id bigint NOT NULL,
    user_id uuid NOT NULL,
    token_jti character varying(36) NOT NULL,
    is_revoked boolean DEFAULT false NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    expires_at timestamp with time zone NOT NULL
);


--
-- Name: auth_sessions_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.auth_sessions_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: auth_sessions_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.auth_sessions_id_seq OWNED BY public.auth_sessions.id;


--
-- Name: categories; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.categories (
    id integer NOT NULL,
    name character varying(100) NOT NULL,
    description text DEFAULT ''::text NOT NULL,
    active boolean DEFAULT true NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: categories_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.categories_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: categories_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.categories_id_seq OWNED BY public.categories.id;


--
-- Name: chunk_embeddings; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.chunk_embeddings (
    chunk_id uuid NOT NULL,
    embedding public.vector(1024) NOT NULL,
    model_name character varying(100) DEFAULT 'bge-m3'::character varying NOT NULL,
    content text NOT NULL,
    metadata jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: chunks; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.chunks (
    chunk_id uuid DEFAULT gen_random_uuid() NOT NULL,
    doc_id uuid NOT NULL,
    parent_chunk_id uuid,
    chunk_type character varying(10) NOT NULL,
    content text NOT NULL,
    token_count integer,
    page_number integer,
    section_header character varying(500),
    storage_path text,
    trace_id character varying(30),
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    chunk_index integer,
    CONSTRAINT chunks_chunk_type_check CHECK (((chunk_type)::text = ANY ((ARRAY['parent'::character varying, 'child'::character varying])::text[]))),
    CONSTRAINT chunks_page_number_check CHECK ((page_number > 0)),
    CONSTRAINT chunks_token_count_check CHECK ((token_count > 0))
);


--
-- Name: convention_embeddings; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.convention_embeddings (
    id bigint NOT NULL,
    doc_title text NOT NULL,
    source_url text DEFAULT ''::text NOT NULL,
    content text NOT NULL,
    embedding public.vector(1024) NOT NULL
);


--
-- Name: convention_embeddings_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.convention_embeddings ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME public.convention_embeddings_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: convention_policies; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.convention_policies (
    policy_key text NOT NULL,
    rule_id text,
    params jsonb NOT NULL,
    updated_at timestamp with time zone DEFAULT now()
);


--
-- Name: cs_sessions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.cs_sessions (
    id bigint NOT NULL,
    user_id bigint NOT NULL,
    token_jti character varying(36) NOT NULL,
    is_revoked boolean DEFAULT false NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    expires_at timestamp with time zone NOT NULL
);


--
-- Name: cs_sessions_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.cs_sessions_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: cs_sessions_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.cs_sessions_id_seq OWNED BY public.cs_sessions.id;


--
-- Name: cs_team_members; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.cs_team_members (
    id bigint NOT NULL,
    team_id bigint NOT NULL,
    user_id bigint NOT NULL,
    role character varying(20) DEFAULT 'member'::character varying NOT NULL,
    joined_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: cs_team_members_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.cs_team_members_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: cs_team_members_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.cs_team_members_id_seq OWNED BY public.cs_team_members.id;


--
-- Name: cs_teams; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.cs_teams (
    id bigint NOT NULL,
    name character varying(255) NOT NULL,
    is_deleted boolean DEFAULT false NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: cs_teams_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.cs_teams_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: cs_teams_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.cs_teams_id_seq OWNED BY public.cs_teams.id;


--
-- Name: cs_users; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.cs_users (
    id bigint NOT NULL,
    github_id bigint NOT NULL,
    login character varying(255) NOT NULL,
    name character varying(255),
    avatar_url character varying(512),
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: cs_users_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.cs_users_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: cs_users_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.cs_users_id_seq OWNED BY public.cs_users.id;


--
-- Name: curriculum_plan; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.curriculum_plan (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    issue_id uuid NOT NULL,
    status text DEFAULT 'pending'::text NOT NULL,
    llm_fallback boolean DEFAULT false NOT NULL,
    error_message text,
    card_content jsonb,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    completed_at timestamp with time zone,
    CONSTRAINT ck_curriculum_plan_status CHECK ((status = ANY (ARRAY['pending'::text, 'running'::text, 'completed'::text, 'failed'::text])))
);


--
-- Name: curriculum_weeks; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.curriculum_weeks (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    curriculum_id uuid NOT NULL,
    week_number integer NOT NULL,
    focus_area character varying(200),
    status character varying(20) DEFAULT 'pending'::character varying NOT NULL,
    coverage_avg double precision DEFAULT 0.0 NOT NULL,
    critical_issue_count integer DEFAULT 0 NOT NULL,
    rework_count integer DEFAULT 0 NOT NULL,
    repeat_issue_count integer DEFAULT 0 NOT NULL,
    retry_count integer DEFAULT 0 NOT NULL,
    topic_sequence jsonb DEFAULT '[]'::jsonb NOT NULL,
    skipped_topic_ids uuid[] DEFAULT '{}'::uuid[] NOT NULL,
    started_at timestamp with time zone,
    completed_at timestamp with time zone,
    CONSTRAINT curriculum_weeks_coverage_avg_check CHECK (((coverage_avg >= (0.0)::double precision) AND (coverage_avg <= (1.0)::double precision))),
    CONSTRAINT curriculum_weeks_retry_count_check CHECK ((retry_count <= 3)),
    CONSTRAINT curriculum_weeks_status_check CHECK (((status)::text = ANY ((ARRAY['pending'::character varying, 'in_progress'::character varying, 'completed'::character varying, 'retrying'::character varying])::text[]))),
    CONSTRAINT curriculum_weeks_week_number_check CHECK ((week_number > 0))
);


--
-- Name: curriculums; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.curriculums (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    user_id uuid NOT NULL,
    status character varying(20) DEFAULT 'active'::character varying NOT NULL,
    total_weeks integer NOT NULL,
    current_week integer DEFAULT 1 NOT NULL,
    generated_by character varying(20) DEFAULT 'agent'::character varying NOT NULL,
    started_at timestamp with time zone DEFAULT now() NOT NULL,
    completed_at timestamp with time zone,
    CONSTRAINT curriculums_generated_by_check CHECK (((generated_by)::text = ANY ((ARRAY['agent'::character varying, 'manual'::character varying, 'template'::character varying])::text[]))),
    CONSTRAINT curriculums_status_check CHECK (((status)::text = ANY ((ARRAY['active'::character varying, 'completed'::character varying, 'paused'::character varying])::text[]))),
    CONSTRAINT curriculums_total_weeks_check CHECK (((total_weeks >= 1) AND (total_weeks <= 8)))
);


--
-- Name: documents; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.documents (
    doc_id uuid DEFAULT gen_random_uuid() NOT NULL,
    title character varying(500) NOT NULL,
    source character varying(50) DEFAULT 'upload'::character varying NOT NULL,
    source_url text,
    author text,
    team text,
    category character varying(100),
    file_type character varying(20),
    file_path text,
    markdown_path text,
    storage_synced boolean DEFAULT false NOT NULL,
    neo4j_synced boolean DEFAULT false NOT NULL,
    last_updated timestamp with time zone,
    upload_status character varying(30) DEFAULT 'processing'::character varying NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    parser_used text,
    doc_complexity text,
    parsing_time_ms integer,
    original_filename text,
    CONSTRAINT documents_file_type_check CHECK (((file_type)::text = ANY ((ARRAY['pdf'::character varying, 'docx'::character varying, 'pptx'::character varying, 'md'::character varying, 'txt'::character varying])::text[]))),
    CONSTRAINT documents_source_check CHECK (((source)::text = ANY ((ARRAY['notion'::character varying, 'confluence'::character varying, 'upload'::character varying, 'slack'::character varying])::text[]))),
    CONSTRAINT documents_upload_status_check CHECK (((upload_status)::text = ANY ((ARRAY['processing'::character varying, 'validated'::character varying, 'stored'::character varying, 'stored_partial'::character varying, 'hitl_pending'::character varying, 'approved'::character varying, 'rejected'::character varying, 'reprocessing'::character varying, 'reprocess_failed'::character varying, 'failed'::character varying])::text[])))
);


--
-- Name: hitl_queue; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.hitl_queue (
    queue_id uuid DEFAULT gen_random_uuid() NOT NULL,
    doc_id uuid,
    stage character varying(30) NOT NULL,
    reason text NOT NULL,
    quality_score double precision,
    issues jsonb,
    status character varying(20) DEFAULT 'pending'::character varying NOT NULL,
    reviewer_id character varying(100),
    reviewed_at timestamp with time zone,
    review_note text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT hitl_queue_status_check CHECK (((status)::text = ANY ((ARRAY['pending'::character varying, 'approved'::character varying, 'rejected'::character varying, 'reprocessing'::character varying])::text[])))
);


--
-- Name: kms_documents; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.kms_documents (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    title character varying(300) NOT NULL,
    category character varying(100),
    content text NOT NULL,
    author_id uuid,
    status character varying(20) DEFAULT 'draft'::character varying NOT NULL,
    objection_rate double precision DEFAULT 0.0 NOT NULL,
    embedding public.vector(1024),
    last_updated_at timestamp with time zone DEFAULT now() NOT NULL,
    reviewed_at timestamp with time zone,
    reviewed_by uuid,
    CONSTRAINT kms_documents_objection_rate_check CHECK (((objection_rate >= (0.0)::double precision) AND (objection_rate <= (1.0)::double precision))),
    CONSTRAINT kms_documents_status_check CHECK (((status)::text = ANY ((ARRAY['draft'::character varying, 'approved'::character varying, 'deprecated'::character varying])::text[])))
);


--
-- Name: learning_materials; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.learning_materials (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    week_id uuid NOT NULL,
    topic_id uuid,
    title character varying(300) NOT NULL,
    source_type character varying(20) NOT NULL,
    url text,
    content text,
    is_verified boolean DEFAULT false NOT NULL,
    is_active boolean DEFAULT true NOT NULL,
    objection_count integer DEFAULT 0 NOT NULL,
    embedding public.vector(1024),
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT learning_materials_source_type_check CHECK (((source_type)::text = ANY ((ARRAY['kms'::character varying, 'external'::character varying, 'llm'::character varying])::text[])))
);


--
-- Name: mistake_patterns; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.mistake_patterns (
    pattern_id uuid DEFAULT gen_random_uuid() NOT NULL,
    user_id uuid NOT NULL,
    pattern_type text NOT NULL,
    occurrence integer DEFAULT 1 NOT NULL,
    first_seen date DEFAULT CURRENT_DATE NOT NULL,
    last_seen date DEFAULT CURRENT_DATE NOT NULL,
    resolved boolean DEFAULT false NOT NULL,
    resolved_at timestamp with time zone,
    CONSTRAINT mistake_patterns_occurrence_check CHECK ((occurrence >= 1))
);


--
-- Name: objections; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.objections (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    user_id uuid NOT NULL,
    material_id uuid NOT NULL,
    objection_type character varying(20) NOT NULL,
    description text,
    resolution_status character varying(20) DEFAULT 'pending'::character varying NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    resolved_at timestamp with time zone,
    CONSTRAINT objections_objection_type_check CHECK (((objection_type)::text = ANY ((ARRAY['wrong'::character varying, 'too_easy'::character varying, 'too_hard'::character varying])::text[]))),
    CONSTRAINT objections_resolution_status_check CHECK (((resolution_status)::text = ANY ((ARRAY['pending'::character varying, 'resolved'::character varying, 'dismissed'::character varying])::text[])))
);


--
-- Name: pr_reviews; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.pr_reviews (
    review_id uuid DEFAULT gen_random_uuid() NOT NULL,
    pr_id text NOT NULL,
    user_id uuid NOT NULL,
    task_id uuid,
    verdict character varying(20),
    critical_count integer DEFAULT 0 NOT NULL,
    major_count integer DEFAULT 0 NOT NULL,
    minor_count integer DEFAULT 0 NOT NULL,
    issues jsonb DEFAULT '[]'::jsonb NOT NULL,
    retry_count integer DEFAULT 0 NOT NULL,
    reviewed_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT pr_reviews_verdict_check CHECK (((verdict)::text = ANY ((ARRAY['lgtm'::character varying, 'rework'::character varying, 'escalate'::character varying])::text[])))
);


--
-- Name: pull_requests; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.pull_requests (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    user_id uuid NOT NULL,
    week_id uuid,
    github_pr_url text,
    github_pr_number integer NOT NULL,
    status character varying(20) DEFAULT 'open'::character varying NOT NULL,
    coverage double precision DEFAULT 0.0 NOT NULL,
    is_lgtm boolean DEFAULT false NOT NULL,
    submitted_at timestamp with time zone DEFAULT now() NOT NULL,
    repository_full_name character varying(255) NOT NULL,
    CONSTRAINT pull_requests_status_check CHECK (((status)::text = ANY ((ARRAY['open'::character varying, 'closed'::character varying, 'merged'::character varying])::text[])))
);


--
-- Name: review_issue; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.review_issue (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    pull_request_id uuid,
    user_id uuid,
    github_id text,
    agent text,
    severity text NOT NULL,
    keyword text NOT NULL,
    sub_category text,
    code_context text,
    code_snippet text,
    suggestion text,
    programming_language text,
    framework text,
    framework_version text,
    name_of_function text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_review_issue_severity CHECK ((severity = ANY (ARRAY['critical'::text, 'high'::text, 'medium'::text, 'low'::text])))
);


--
-- Name: scan_executions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.scan_executions (
    id bigint NOT NULL,
    task_id text NOT NULL,
    pr_id text NOT NULL,
    user_id uuid NOT NULL,
    scanned_at timestamp with time zone DEFAULT now() NOT NULL,
    execution_ms integer
);


--
-- Name: scan_executions_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.scan_executions ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME public.scan_executions_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: scan_issues; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.scan_issues (
    id bigint NOT NULL,
    scan_id bigint NOT NULL,
    agent text NOT NULL,
    severity text NOT NULL,
    rule_id text NOT NULL,
    file text,
    line integer,
    message text,
    suggestion text,
    similar_issues jsonb DEFAULT '[]'::jsonb NOT NULL,
    keyword text DEFAULT ''::text,
    sub_keyword text DEFAULT ''::text,
    metric_value text DEFAULT ''::text,
    sub_category text DEFAULT ''::text,
    code_context text DEFAULT ''::text,
    issue_type text,
    resolution_example text,
    status text DEFAULT 'Open'::text,
    concept_id text,
    mistake_type_concept_id text,
    confidence_score double precision,
    code_snippet text,
    learning_context jsonb,
    taxonomy jsonb,
    created_at timestamp without time zone DEFAULT now(),
    name_of_function text,
    CONSTRAINT scan_issues_agent_check CHECK ((agent = ANY (ARRAY['static_analysis'::text, 'security_scan'::text, 'test_verification'::text, 'performance'::text]))),
    CONSTRAINT scan_issues_severity_check CHECK ((severity = ANY (ARRAY['Critical'::text, 'Major'::text, 'Minor'::text])))
);


--
-- Name: scan_issues_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.scan_issues ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME public.scan_issues_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: scan_summaries; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.scan_summaries (
    id bigint NOT NULL,
    scan_id bigint NOT NULL,
    agent text NOT NULL,
    critical integer DEFAULT 0 NOT NULL,
    major integer DEFAULT 0 NOT NULL,
    minor integer DEFAULT 0 NOT NULL,
    metrics jsonb,
    CONSTRAINT scan_summaries_agent_check CHECK ((agent = ANY (ARRAY['static_analysis'::text, 'security_scan'::text, 'test_verification'::text, 'performance'::text])))
);


--
-- Name: scan_summaries_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.scan_summaries ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME public.scan_summaries_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: senior_approvals; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.senior_approvals (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    user_id uuid NOT NULL,
    curriculum_id uuid,
    approval_type character varying(50) NOT NULL,
    status character varying(20) DEFAULT 'pending'::character varying NOT NULL,
    approver_id uuid,
    note text,
    requested_at timestamp with time zone DEFAULT now() NOT NULL,
    resolved_at timestamp with time zone,
    CONSTRAINT senior_approvals_approval_type_check CHECK (((approval_type)::text = ANY ((ARRAY['early_promotion'::character varying, 'critical_repeat'::character varying, 'curriculum_redesign'::character varying])::text[]))),
    CONSTRAINT senior_approvals_status_check CHECK (((status)::text = ANY ((ARRAY['pending'::character varying, 'approved'::character varying, 'rejected'::character varying])::text[])))
);


--
-- Name: slack_notifications; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.slack_notifications (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    user_id uuid NOT NULL,
    event_type character varying(50) NOT NULL,
    message text NOT NULL,
    is_sent boolean DEFAULT false NOT NULL,
    retry_count integer DEFAULT 0 NOT NULL,
    sent_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: team_invitations; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.team_invitations (
    id uuid NOT NULL,
    team_id uuid NOT NULL,
    invitee_user_id uuid NOT NULL,
    invited_by_user_id uuid NOT NULL,
    status character varying(20) DEFAULT 'pending'::character varying NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    responded_at timestamp with time zone,
    CONSTRAINT ck_team_invitations_status CHECK (((status)::text = ANY ((ARRAY['pending'::character varying, 'accepted'::character varying, 'declined'::character varying, 'cancelled'::character varying])::text[])))
);


--
-- Name: team_members; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.team_members (
    id uuid NOT NULL,
    team_id uuid NOT NULL,
    user_id uuid NOT NULL,
    team_role character varying(20) DEFAULT 'member'::character varying NOT NULL,
    joined_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: teams; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.teams (
    team_id uuid NOT NULL,
    name character varying(100) NOT NULL,
    github_repo_full_name character varying(255) NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: topics; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.topics (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    name character varying(200) NOT NULL,
    category character varying(100) NOT NULL,
    difficulty character varying(20) NOT NULL,
    estimated_days integer DEFAULT 1 NOT NULL,
    prerequisite_ids uuid[] DEFAULT '{}'::uuid[] NOT NULL,
    target_levels character varying(20)[] DEFAULT '{}'::character varying[] NOT NULL,
    is_company_specific boolean DEFAULT false NOT NULL,
    neo4j_id character varying(100),
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT topics_difficulty_check CHECK (((difficulty)::text = ANY ((ARRAY['beginner'::character varying, 'junior'::character varying, 'mid'::character varying, 'senior'::character varying])::text[]))),
    CONSTRAINT topics_estimated_days_check CHECK ((estimated_days > 0))
);


--
-- Name: user_skills; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.user_skills (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    user_id uuid NOT NULL,
    skill_name character varying(100) NOT NULL,
    skill_type character varying(50) DEFAULT 'framework'::character varying NOT NULL,
    proficiency character varying(20) DEFAULT 'beginner'::character varying NOT NULL,
    extracted_from character varying(20) DEFAULT 'github'::character varying NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT user_skills_extracted_from_check CHECK (((extracted_from)::text = ANY ((ARRAY['github'::character varying, 'form'::character varying, 'llm'::character varying])::text[]))),
    CONSTRAINT user_skills_proficiency_check CHECK (((proficiency)::text = ANY ((ARRAY['beginner'::character varying, 'intermediate'::character varying, 'advanced'::character varying])::text[]))),
    CONSTRAINT user_skills_skill_type_check CHECK (((skill_type)::text = ANY ((ARRAY['language'::character varying, 'framework'::character varying, 'tool'::character varying, 'concept'::character varying])::text[])))
);


--
-- Name: users; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.users (
    user_id uuid DEFAULT gen_random_uuid() NOT NULL,
    github_id character varying(100),
    name character varying(100) NOT NULL,
    email character varying(255),
    github_url character varying(500),
    role character varying(100),
    team character varying(100),
    skill_level character varying(20) DEFAULT 'junior'::character varying NOT NULL,
    career_years integer DEFAULT 0 NOT NULL,
    tech_stack jsonb DEFAULT '[]'::jsonb NOT NULL,
    diagnosis_source character varying(20) DEFAULT 'form'::character varying NOT NULL,
    diagnosis_confidence double precision DEFAULT 0.0 NOT NULL,
    current_week integer DEFAULT 1,
    joined_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT users_current_week_check CHECK ((current_week >= 1)),
    CONSTRAINT users_diagnosis_confidence_check CHECK (((diagnosis_confidence >= (0.0)::double precision) AND (diagnosis_confidence <= (1.0)::double precision))),
    CONSTRAINT users_diagnosis_source_check CHECK (((diagnosis_source)::text = ANY ((ARRAY['github'::character varying, 'form'::character varying, 'github+form'::character varying])::text[]))),
    CONSTRAINT users_role_check CHECK (((role)::text = ANY ((ARRAY['backend'::character varying, 'frontend'::character varying, 'devops'::character varying, 'fullstack'::character varying])::text[]))),
    CONSTRAINT users_skill_level_check CHECK (((skill_level)::text = ANY ((ARRAY['beginner'::character varying, 'junior'::character varying, 'mid'::character varying, 'senior'::character varying])::text[])))
);


--
-- Name: auth_sessions id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.auth_sessions ALTER COLUMN id SET DEFAULT nextval('public.auth_sessions_id_seq'::regclass);


--
-- Name: categories id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.categories ALTER COLUMN id SET DEFAULT nextval('public.categories_id_seq'::regclass);


--
-- Name: cs_sessions id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.cs_sessions ALTER COLUMN id SET DEFAULT nextval('public.cs_sessions_id_seq'::regclass);


--
-- Name: cs_team_members id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.cs_team_members ALTER COLUMN id SET DEFAULT nextval('public.cs_team_members_id_seq'::regclass);


--
-- Name: cs_teams id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.cs_teams ALTER COLUMN id SET DEFAULT nextval('public.cs_teams_id_seq'::regclass);


--
-- Name: cs_users id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.cs_users ALTER COLUMN id SET DEFAULT nextval('public.cs_users_id_seq'::regclass);


--
-- Name: agent_traces agent_traces_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agent_traces
    ADD CONSTRAINT agent_traces_pkey PRIMARY KEY (trace_id);


--
-- Name: alembic_version_m4 alembic_version_m4_pkc; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.alembic_version_m4
    ADD CONSTRAINT alembic_version_m4_pkc PRIMARY KEY (version_num);


--
-- Name: alembic_version alembic_version_pkc; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.alembic_version
    ADD CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num);


--
-- Name: auth_sessions auth_sessions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.auth_sessions
    ADD CONSTRAINT auth_sessions_pkey PRIMARY KEY (id);


--
-- Name: auth_sessions auth_sessions_token_jti_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.auth_sessions
    ADD CONSTRAINT auth_sessions_token_jti_key UNIQUE (token_jti);


--
-- Name: categories categories_name_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.categories
    ADD CONSTRAINT categories_name_key UNIQUE (name);


--
-- Name: categories categories_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.categories
    ADD CONSTRAINT categories_pkey PRIMARY KEY (id);


--
-- Name: chunk_embeddings chunk_embeddings_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.chunk_embeddings
    ADD CONSTRAINT chunk_embeddings_pkey PRIMARY KEY (chunk_id);


--
-- Name: chunks chunks_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.chunks
    ADD CONSTRAINT chunks_pkey PRIMARY KEY (chunk_id);


--
-- Name: convention_embeddings convention_embeddings_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.convention_embeddings
    ADD CONSTRAINT convention_embeddings_pkey PRIMARY KEY (id);


--
-- Name: convention_policies convention_policies_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.convention_policies
    ADD CONSTRAINT convention_policies_pkey PRIMARY KEY (policy_key);


--
-- Name: cs_sessions cs_sessions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.cs_sessions
    ADD CONSTRAINT cs_sessions_pkey PRIMARY KEY (id);


--
-- Name: cs_sessions cs_sessions_token_jti_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.cs_sessions
    ADD CONSTRAINT cs_sessions_token_jti_key UNIQUE (token_jti);


--
-- Name: cs_team_members cs_team_members_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.cs_team_members
    ADD CONSTRAINT cs_team_members_pkey PRIMARY KEY (id);


--
-- Name: cs_teams cs_teams_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.cs_teams
    ADD CONSTRAINT cs_teams_pkey PRIMARY KEY (id);


--
-- Name: cs_users cs_users_github_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.cs_users
    ADD CONSTRAINT cs_users_github_id_key UNIQUE (github_id);


--
-- Name: cs_users cs_users_login_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.cs_users
    ADD CONSTRAINT cs_users_login_key UNIQUE (login);


--
-- Name: cs_users cs_users_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.cs_users
    ADD CONSTRAINT cs_users_pkey PRIMARY KEY (id);


--
-- Name: curriculum_plan curriculum_plan_issue_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.curriculum_plan
    ADD CONSTRAINT curriculum_plan_issue_id_key UNIQUE (issue_id);


--
-- Name: curriculum_plan curriculum_plan_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.curriculum_plan
    ADD CONSTRAINT curriculum_plan_pkey PRIMARY KEY (id);


--
-- Name: curriculum_weeks curriculum_weeks_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.curriculum_weeks
    ADD CONSTRAINT curriculum_weeks_pkey PRIMARY KEY (id);


--
-- Name: curriculums curriculums_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.curriculums
    ADD CONSTRAINT curriculums_pkey PRIMARY KEY (id);


--
-- Name: documents documents_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.documents
    ADD CONSTRAINT documents_pkey PRIMARY KEY (doc_id);


--
-- Name: hitl_queue hitl_queue_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.hitl_queue
    ADD CONSTRAINT hitl_queue_pkey PRIMARY KEY (queue_id);


--
-- Name: kms_documents kms_documents_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.kms_documents
    ADD CONSTRAINT kms_documents_pkey PRIMARY KEY (id);


--
-- Name: learning_materials learning_materials_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.learning_materials
    ADD CONSTRAINT learning_materials_pkey PRIMARY KEY (id);


--
-- Name: mistake_patterns mistake_patterns_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mistake_patterns
    ADD CONSTRAINT mistake_patterns_pkey PRIMARY KEY (pattern_id);


--
-- Name: objections objections_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.objections
    ADD CONSTRAINT objections_pkey PRIMARY KEY (id);


--
-- Name: pr_reviews pr_reviews_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pr_reviews
    ADD CONSTRAINT pr_reviews_pkey PRIMARY KEY (review_id);


--
-- Name: pull_requests pull_requests_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pull_requests
    ADD CONSTRAINT pull_requests_pkey PRIMARY KEY (id);


--
-- Name: review_issue review_issue_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.review_issue
    ADD CONSTRAINT review_issue_pkey PRIMARY KEY (id);


--
-- Name: scan_executions scan_executions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.scan_executions
    ADD CONSTRAINT scan_executions_pkey PRIMARY KEY (id);


--
-- Name: scan_issues scan_issues_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.scan_issues
    ADD CONSTRAINT scan_issues_pkey PRIMARY KEY (id);


--
-- Name: scan_summaries scan_summaries_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.scan_summaries
    ADD CONSTRAINT scan_summaries_pkey PRIMARY KEY (id);


--
-- Name: senior_approvals senior_approvals_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.senior_approvals
    ADD CONSTRAINT senior_approvals_pkey PRIMARY KEY (id);


--
-- Name: slack_notifications slack_notifications_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.slack_notifications
    ADD CONSTRAINT slack_notifications_pkey PRIMARY KEY (id);


--
-- Name: team_invitations team_invitations_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.team_invitations
    ADD CONSTRAINT team_invitations_pkey PRIMARY KEY (id);


--
-- Name: team_members team_members_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.team_members
    ADD CONSTRAINT team_members_pkey PRIMARY KEY (id);


--
-- Name: teams teams_github_repo_full_name_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.teams
    ADD CONSTRAINT teams_github_repo_full_name_key UNIQUE (github_repo_full_name);


--
-- Name: teams teams_name_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.teams
    ADD CONSTRAINT teams_name_key UNIQUE (name);


--
-- Name: teams teams_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.teams
    ADD CONSTRAINT teams_pkey PRIMARY KEY (team_id);


--
-- Name: topics topics_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.topics
    ADD CONSTRAINT topics_pkey PRIMARY KEY (id);


--
-- Name: curriculum_weeks uq_curriculum_weeks; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.curriculum_weeks
    ADD CONSTRAINT uq_curriculum_weeks UNIQUE (curriculum_id, week_number);


--
-- Name: curriculums uq_curriculums_active; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.curriculums
    ADD CONSTRAINT uq_curriculums_active UNIQUE (user_id, status);


--
-- Name: pull_requests uq_pull_requests_repo_number; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pull_requests
    ADD CONSTRAINT uq_pull_requests_repo_number UNIQUE (repository_full_name, github_pr_number);


--
-- Name: scan_summaries uq_scan_summaries_scan_agent; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.scan_summaries
    ADD CONSTRAINT uq_scan_summaries_scan_agent UNIQUE (scan_id, agent);


--
-- Name: team_members uq_team_members_team_user; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.team_members
    ADD CONSTRAINT uq_team_members_team_user UNIQUE (team_id, user_id);


--
-- Name: user_skills user_skills_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_skills
    ADD CONSTRAINT user_skills_pkey PRIMARY KEY (id);


--
-- Name: users users_email_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_email_key UNIQUE (email);


--
-- Name: users users_github_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_github_id_key UNIQUE (github_id);


--
-- Name: users users_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_pkey PRIMARY KEY (user_id);


--
-- Name: idx_agent_traces_doc_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_agent_traces_doc_id ON public.agent_traces USING btree (doc_id);


--
-- Name: idx_agent_traces_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_agent_traces_status ON public.agent_traces USING btree (status);


--
-- Name: idx_agent_traces_task_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_agent_traces_task_id ON public.agent_traces USING btree (task_id);


--
-- Name: idx_chunk_embeddings_hnsw; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_chunk_embeddings_hnsw ON public.chunk_embeddings USING hnsw (embedding public.vector_cosine_ops) WITH (m='16', ef_construction='64');


--
-- Name: idx_chunk_embeddings_metadata; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_chunk_embeddings_metadata ON public.chunk_embeddings USING gin (metadata);


--
-- Name: idx_chunks_chunk_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_chunks_chunk_type ON public.chunks USING btree (chunk_type);


--
-- Name: idx_chunks_doc_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_chunks_doc_id ON public.chunks USING btree (doc_id);


--
-- Name: idx_chunks_parent_chunk_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_chunks_parent_chunk_id ON public.chunks USING btree (parent_chunk_id);


--
-- Name: idx_curriculum_plan_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_curriculum_plan_status ON public.curriculum_plan USING btree (status);


--
-- Name: idx_documents_category; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_documents_category ON public.documents USING btree (category);


--
-- Name: idx_documents_created_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_documents_created_at ON public.documents USING btree (created_at DESC);


--
-- Name: idx_documents_source; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_documents_source ON public.documents USING btree (source);


--
-- Name: idx_documents_upload_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_documents_upload_status ON public.documents USING btree (upload_status);


--
-- Name: idx_hitl_queue_doc_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_hitl_queue_doc_id ON public.hitl_queue USING btree (doc_id);


--
-- Name: idx_hitl_queue_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_hitl_queue_status ON public.hitl_queue USING btree (status);


--
-- Name: idx_mistake_patterns_user_pattern; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX idx_mistake_patterns_user_pattern ON public.mistake_patterns USING btree (user_id, pattern_type);


--
-- Name: idx_pr_reviews_pr_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_pr_reviews_pr_id ON public.pr_reviews USING btree (pr_id);


--
-- Name: idx_pr_reviews_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_pr_reviews_user_id ON public.pr_reviews USING btree (user_id);


--
-- Name: idx_review_issue_pull_request_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_review_issue_pull_request_id ON public.review_issue USING btree (pull_request_id);


--
-- Name: idx_review_issue_user_keyword; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_review_issue_user_keyword ON public.review_issue USING btree (user_id, keyword);


--
-- Name: idx_scan_executions_scanned_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_scan_executions_scanned_at ON public.scan_executions USING brin (scanned_at);


--
-- Name: idx_scan_issues_scan_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_scan_issues_scan_id ON public.scan_issues USING btree (scan_id);


--
-- Name: idx_team_invitations_invitee_pending; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_team_invitations_invitee_pending ON public.team_invitations USING btree (invitee_user_id, status);


--
-- Name: idx_team_invitations_team_invitee; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_team_invitations_team_invitee ON public.team_invitations USING btree (team_id, invitee_user_id);


--
-- Name: idx_team_members_user; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_team_members_user ON public.team_members USING btree (user_id);


--
-- Name: idx_teams_repo; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_teams_repo ON public.teams USING btree (github_repo_full_name);


--
-- Name: idx_user_skills_user; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_user_skills_user ON public.user_skills USING btree (user_id);


--
-- Name: idx_users_skill_level; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_users_skill_level ON public.users USING btree (skill_level);


--
-- Name: idx_users_team; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_users_team ON public.users USING btree (team);


--
-- Name: documents trg_documents_updated_at; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_documents_updated_at BEFORE UPDATE ON public.documents FOR EACH ROW EXECUTE FUNCTION public.fn_set_updated_at();


--
-- Name: learning_materials trg_learning_materials_updated_at; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_learning_materials_updated_at BEFORE UPDATE ON public.learning_materials FOR EACH ROW EXECUTE FUNCTION public.fn_set_updated_at();


--
-- Name: users trg_users_updated_at; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_users_updated_at BEFORE UPDATE ON public.users FOR EACH ROW EXECUTE FUNCTION public.fn_set_updated_at();


--
-- Name: agent_traces agent_traces_doc_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agent_traces
    ADD CONSTRAINT agent_traces_doc_id_fkey FOREIGN KEY (doc_id) REFERENCES public.documents(doc_id) ON DELETE SET NULL;


--
-- Name: auth_sessions auth_sessions_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.auth_sessions
    ADD CONSTRAINT auth_sessions_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(user_id) ON DELETE CASCADE;


--
-- Name: chunk_embeddings chunk_embeddings_chunk_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.chunk_embeddings
    ADD CONSTRAINT chunk_embeddings_chunk_id_fkey FOREIGN KEY (chunk_id) REFERENCES public.chunks(chunk_id) ON DELETE CASCADE;


--
-- Name: chunks chunks_doc_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.chunks
    ADD CONSTRAINT chunks_doc_id_fkey FOREIGN KEY (doc_id) REFERENCES public.documents(doc_id) ON DELETE CASCADE;


--
-- Name: chunks chunks_parent_chunk_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.chunks
    ADD CONSTRAINT chunks_parent_chunk_id_fkey FOREIGN KEY (parent_chunk_id) REFERENCES public.chunks(chunk_id) ON DELETE SET NULL;


--
-- Name: cs_sessions cs_sessions_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.cs_sessions
    ADD CONSTRAINT cs_sessions_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.cs_users(id) ON DELETE CASCADE;


--
-- Name: cs_team_members cs_team_members_team_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.cs_team_members
    ADD CONSTRAINT cs_team_members_team_id_fkey FOREIGN KEY (team_id) REFERENCES public.cs_teams(id) ON DELETE CASCADE;


--
-- Name: cs_team_members cs_team_members_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.cs_team_members
    ADD CONSTRAINT cs_team_members_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.cs_users(id) ON DELETE CASCADE;


--
-- Name: curriculum_plan curriculum_plan_issue_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.curriculum_plan
    ADD CONSTRAINT curriculum_plan_issue_id_fkey FOREIGN KEY (issue_id) REFERENCES public.review_issue(id) ON DELETE CASCADE;


--
-- Name: curriculum_weeks curriculum_weeks_curriculum_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.curriculum_weeks
    ADD CONSTRAINT curriculum_weeks_curriculum_id_fkey FOREIGN KEY (curriculum_id) REFERENCES public.curriculums(id) ON DELETE CASCADE;


--
-- Name: curriculums curriculums_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.curriculums
    ADD CONSTRAINT curriculums_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(user_id) ON DELETE CASCADE;


--
-- Name: hitl_queue hitl_queue_doc_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.hitl_queue
    ADD CONSTRAINT hitl_queue_doc_id_fkey FOREIGN KEY (doc_id) REFERENCES public.documents(doc_id) ON DELETE CASCADE;


--
-- Name: kms_documents kms_documents_author_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.kms_documents
    ADD CONSTRAINT kms_documents_author_id_fkey FOREIGN KEY (author_id) REFERENCES public.users(user_id) ON DELETE SET NULL;


--
-- Name: kms_documents kms_documents_reviewed_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.kms_documents
    ADD CONSTRAINT kms_documents_reviewed_by_fkey FOREIGN KEY (reviewed_by) REFERENCES public.users(user_id) ON DELETE SET NULL;


--
-- Name: learning_materials learning_materials_topic_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.learning_materials
    ADD CONSTRAINT learning_materials_topic_id_fkey FOREIGN KEY (topic_id) REFERENCES public.topics(id) ON DELETE SET NULL;


--
-- Name: learning_materials learning_materials_week_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.learning_materials
    ADD CONSTRAINT learning_materials_week_id_fkey FOREIGN KEY (week_id) REFERENCES public.curriculum_weeks(id) ON DELETE CASCADE;


--
-- Name: mistake_patterns mistake_patterns_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mistake_patterns
    ADD CONSTRAINT mistake_patterns_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(user_id) ON DELETE CASCADE;


--
-- Name: objections objections_material_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.objections
    ADD CONSTRAINT objections_material_id_fkey FOREIGN KEY (material_id) REFERENCES public.learning_materials(id) ON DELETE CASCADE;


--
-- Name: objections objections_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.objections
    ADD CONSTRAINT objections_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(user_id) ON DELETE CASCADE;


--
-- Name: pr_reviews pr_reviews_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pr_reviews
    ADD CONSTRAINT pr_reviews_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(user_id) ON DELETE RESTRICT;


--
-- Name: pull_requests pull_requests_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pull_requests
    ADD CONSTRAINT pull_requests_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(user_id) ON DELETE CASCADE;


--
-- Name: pull_requests pull_requests_week_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pull_requests
    ADD CONSTRAINT pull_requests_week_id_fkey FOREIGN KEY (week_id) REFERENCES public.curriculum_weeks(id) ON DELETE SET NULL;


--
-- Name: review_issue review_issue_pull_request_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.review_issue
    ADD CONSTRAINT review_issue_pull_request_id_fkey FOREIGN KEY (pull_request_id) REFERENCES public.pull_requests(id) ON DELETE SET NULL;


--
-- Name: review_issue review_issue_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.review_issue
    ADD CONSTRAINT review_issue_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(user_id) ON DELETE SET NULL;


--
-- Name: scan_executions scan_executions_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.scan_executions
    ADD CONSTRAINT scan_executions_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(user_id);


--
-- Name: scan_issues scan_issues_scan_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.scan_issues
    ADD CONSTRAINT scan_issues_scan_id_fkey FOREIGN KEY (scan_id) REFERENCES public.scan_executions(id) ON DELETE CASCADE;


--
-- Name: scan_summaries scan_summaries_scan_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.scan_summaries
    ADD CONSTRAINT scan_summaries_scan_id_fkey FOREIGN KEY (scan_id) REFERENCES public.scan_executions(id) ON DELETE CASCADE;


--
-- Name: senior_approvals senior_approvals_approver_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.senior_approvals
    ADD CONSTRAINT senior_approvals_approver_id_fkey FOREIGN KEY (approver_id) REFERENCES public.users(user_id);


--
-- Name: senior_approvals senior_approvals_curriculum_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.senior_approvals
    ADD CONSTRAINT senior_approvals_curriculum_id_fkey FOREIGN KEY (curriculum_id) REFERENCES public.curriculums(id) ON DELETE SET NULL;


--
-- Name: senior_approvals senior_approvals_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.senior_approvals
    ADD CONSTRAINT senior_approvals_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(user_id) ON DELETE CASCADE;


--
-- Name: slack_notifications slack_notifications_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.slack_notifications
    ADD CONSTRAINT slack_notifications_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(user_id) ON DELETE CASCADE;


--
-- Name: team_invitations team_invitations_invited_by_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.team_invitations
    ADD CONSTRAINT team_invitations_invited_by_user_id_fkey FOREIGN KEY (invited_by_user_id) REFERENCES public.users(user_id) ON DELETE CASCADE;


--
-- Name: team_invitations team_invitations_invitee_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.team_invitations
    ADD CONSTRAINT team_invitations_invitee_user_id_fkey FOREIGN KEY (invitee_user_id) REFERENCES public.users(user_id) ON DELETE CASCADE;


--
-- Name: team_invitations team_invitations_team_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.team_invitations
    ADD CONSTRAINT team_invitations_team_id_fkey FOREIGN KEY (team_id) REFERENCES public.teams(team_id) ON DELETE CASCADE;


--
-- Name: team_members team_members_team_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.team_members
    ADD CONSTRAINT team_members_team_id_fkey FOREIGN KEY (team_id) REFERENCES public.teams(team_id) ON DELETE CASCADE;


--
-- Name: team_members team_members_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.team_members
    ADD CONSTRAINT team_members_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(user_id) ON DELETE CASCADE;


--
-- Name: user_skills user_skills_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_skills
    ADD CONSTRAINT user_skills_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(user_id) ON DELETE CASCADE;


--
-- PostgreSQL database dump complete
--

\unrestrict 2NACGsdnVHTsWGMDmukRkHeKEyFAsFLa37zVQrsFnCziUxMDrwFFNmLawikVQy6

