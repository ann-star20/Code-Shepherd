유저님, 제공해주신 예전 DDL(`schema.sql`)을 꼼꼼하게 검토했습니다.

우리가 직전 논의에서 핵심 헌법으로 정의했던 **"Link Resolver Agent의 3-Factor 세부 유사도 분석 지표 영속화"** 정책에 맞게, 데이터 구조를 명확히 고정해야 합니다. 기존의 `infer_score`와 `target_concept_name` 필드를 개정된 명세 규격인 **`infer_confidence`와 세부 점수 컬럼(`score_jaro_winkler`, `score_name_vector`, `score_desc_vector`)으로 보정하고 완벽하게 싱크를 맞춘 수정본 DDL**을 제공해 드립니다.

---

### 🛠️ 보정 및 마이그레이션이 완료된 `schema.sql` 통합 DDL

```sql
-- =============================================================================
-- schema.sql — PostgreSQL 마스터 테이블 통합 DDL (v4. 3-Factor Metric Sync)
-- 멱등성: IF NOT EXISTS — 중복 실행 완전 안전 (마이그레이션 및 세부 지표 수집 보완)
-- =============================================================================
CREATE EXTENSION IF NOT EXISTS vector;

-- ── 1. 도메인 레지스트리 (파이프라인 DOMAIN_PENDING 인터락 기준)
CREATE TABLE IF NOT EXISTS domain_registry (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name         TEXT NOT NULL UNIQUE,
    label_ko     TEXT NOT NULL,
    description  TEXT,
    color_hex    TEXT NOT NULL DEFAULT '#6366f1',
    is_active    BOOLEAN NOT NULL DEFAULT true,
    created_at   TIMESTAMPTZ DEFAULT now(),
    created_by   TEXT NOT NULL DEFAULT 'system'
);

-- ── 2. 출처 문서 마스터 테이블
CREATE TABLE IF NOT EXISTS knowledge_documents (
    doc_id            TEXT PRIMARY KEY,
    source_prefix     TEXT NOT NULL,
    original_url      TEXT NOT NULL,
    content_hash      CHAR(8) NOT NULL,
    etag              TEXT,
    lang              TEXT,
    framework         TEXT,
    version           TEXT,
    infer_confidence  FLOAT,                              -- 메타 추론 신뢰도 지표
    is_deprecated     BOOLEAN NOT NULL DEFAULT false,     -- 문서 소프트 딜리트 플래그
    state             TEXT NOT NULL DEFAULT 'PENDING',
    created_at        TIMESTAMPTZ DEFAULT now(),
    updated_at        TIMESTAMPTZ,
    CONSTRAINT knowledge_document_state_check
        CHECK (state IN ('PENDING','CRAWLING','EXTRACTED','COMMITTED','FAILED'))
);

-- ── 3. 개념 마스터 테이블 (하이브리드 벡터 통합 스펙 보전)
CREATE TABLE IF NOT EXISTS concepts (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    concept_name   TEXT NOT NULL UNIQUE,
    doc_id         TEXT REFERENCES knowledge_documents(doc_id) ON DELETE SET NULL,
    domains        TEXT[] NOT NULL,
    concept_type   TEXT,
    cwe_id         TEXT,
    owasp_id       TEXT,                               -- owasp_category 수렴 통일 명세 반영
    severity       TEXT,
    description_ko TEXT,
    root_cause     TEXT,                               -- 취약점/결함 발생 근본 원인 문자열
    is_deprecated  BOOLEAN NOT NULL DEFAULT false,     -- 개념 소프트 딜리트 플래그
    aliases        TEXT[] NOT NULL DEFAULT '{}',
    name_vector    vector(768),                        -- 이름+동의어 융합형 3-Factor 매칭 벡터
    desc_vector    vector(768),                        -- 요약 설명문 문맥 인지용 시맨틱 벡터
    created_at     TIMESTAMPTZ DEFAULT now(),
    updated_at     TIMESTAMPTZ
);

-- ── 4. 스테이징 테이블 (DRAFT ➔ APPROVED ➔ COMMITTED)
-- 🎯 3-Factor 유사도 역추적 인프라를 위한 세부 점수 지표 컬럼 원자적 편입
CREATE TABLE IF NOT EXISTS staging_concepts (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id          UUID NOT NULL,
    doc_id              TEXT REFERENCES knowledge_documents(doc_id) ON DELETE CASCADE,
    concept_json        JSONB NOT NULL,
    state               TEXT NOT NULL DEFAULT 'DRAFT',
    known_domains       TEXT[] DEFAULT '{}',
    unknown_domains     TEXT[] DEFAULT '{}',
    infer_action        TEXT,                          -- 사전 계산된 액션 (MERGE/RELATED_TO/NEW)
    infer_confidence    FLOAT DEFAULT 0.0,             -- 3-Factor 최종 결합 하이브리드 스코어 (Confidence)
    target_concept_name TEXT,                          -- MERGE/RELATED_TO 대상 마스터 개념명
    score_jaro_winkler  FLOAT DEFAULT 0.0,             -- 1) 어휘 구조 일치도 점수 (40%)
    score_name_vector   FLOAT DEFAULT 0.0,             -- 2) 키워드 융합 문맥 벡터 점수 (30%)
    score_desc_vector   FLOAT DEFAULT 0.0,             -- 3) 요약 설명 코사인 유사도 점수 (30%)
    reviewed_at         TIMESTAMPTZ,
    committed_at        TIMESTAMPTZ,
    created_at          TIMESTAMPTZ DEFAULT now()
);

-- ── 5. 파이프라인 실행 로그 (단일 채널 SSE 스트림 롤링 연동 기둥)
CREATE TABLE IF NOT EXISTS pipeline_logs (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    doc_id     TEXT REFERENCES knowledge_documents(doc_id) ON DELETE SET NULL,
    session_id UUID NOT NULL,                          -- 태스크 세션 식별 고유키
    agent      TEXT NOT NULL,                          -- 이벤트를 유발한 에이전트명
    level      TEXT NOT NULL DEFAULT 'INFO',           -- 로그 레벨
    message    TEXT,                                   -- 실시간 상태 롤링 subText 메시지
    created_at TIMESTAMPTZ DEFAULT now()
);

-- =========================================================================
-- 🔒 [마이그레이션 가드] 기존 운영 인프라 하위 호환성 강제 업그레이드 (멱등성 보장)
-- =========================================================================

-- ① knowledge_documents 마이그레이션 패치
ALTER TABLE knowledge_documents ADD COLUMN IF NOT EXISTS infer_confidence FLOAT;
ALTER TABLE knowledge_documents ADD COLUMN IF NOT EXISTS is_deprecated    BOOLEAN NOT NULL DEFAULT false;

-- ② concepts 마이그레이션 패치
ALTER TABLE concepts ADD COLUMN IF NOT EXISTS root_cause     TEXT;
ALTER TABLE concepts ADD COLUMN IF NOT EXISTS is_deprecated  BOOLEAN NOT NULL DEFAULT false;
ALTER TABLE concepts ADD COLUMN IF NOT EXISTS aliases        TEXT[] NOT NULL DEFAULT '{}';
ALTER TABLE concepts ADD COLUMN IF NOT EXISTS name_vector    vector(768);
ALTER TABLE concepts ADD COLUMN IF NOT EXISTS desc_vector    vector(768);

-- ③ staging_concepts 세부 추론 지표 역추적 컬럼 멱등 마이그레이션
ALTER TABLE staging_concepts ADD COLUMN IF NOT EXISTS known_domains       TEXT[] DEFAULT '{}';
ALTER TABLE staging_concepts ADD COLUMN IF NOT EXISTS unknown_domains     TEXT[] DEFAULT '{}';
ALTER TABLE staging_concepts ADD COLUMN IF NOT EXISTS committed_at        TIMESTAMPTZ;
ALTER TABLE staging_concepts ADD COLUMN IF NOT EXISTS infer_action        TEXT;
ALTER TABLE staging_concepts ADD COLUMN IF NOT EXISTS infer_confidence    FLOAT DEFAULT 0.0;
ALTER TABLE staging_concepts ADD COLUMN IF NOT EXISTS target_concept_name TEXT;
ALTER TABLE staging_concepts ADD COLUMN IF NOT EXISTS score_jaro_winkler  FLOAT DEFAULT 0.0;
ALTER TABLE staging_concepts ADD COLUMN IF NOT EXISTS score_name_vector   FLOAT DEFAULT 0.0;
ALTER TABLE staging_concepts ADD COLUMN IF NOT EXISTS score_desc_vector   FLOAT DEFAULT 0.0;

-- ④ pipeline_logs 마이그레이션 패치
ALTER TABLE pipeline_logs ADD COLUMN IF NOT EXISTS session_id UUID NOT NULL DEFAULT gen_random_uuid();
ALTER TABLE pipeline_logs ADD COLUMN IF NOT EXISTS agent      TEXT NOT NULL DEFAULT 'system';
ALTER TABLE pipeline_logs ADD COLUMN IF NOT EXISTS level      TEXT NOT NULL DEFAULT 'INFO';
ALTER TABLE pipeline_logs ADD COLUMN IF NOT EXISTS message    TEXT;

-- =========================================================================
-- ⚡ [인덱스 레이어] HNSW 고속 유사도 검색 인덱스 빌드 (코사인 유사도 연산 전용)
-- =========================================================================
CREATE INDEX IF NOT EXISTS idx_concepts_name_vector_hnsw
ON concepts USING hnsw (name_vector vector_cosine_ops)
WITH (m = 16, ef_construction = 64);

CREATE INDEX IF NOT EXISTS idx_concepts_desc_vector_hnsw
ON concepts USING hnsw (desc_vector vector_cosine_ops)
WITH (m = 24, ef_construction = 100);

-- ── 초기 도메인 레지스트리 시드
INSERT INTO domain_registry (name, label_ko, description, color_hex) VALUES
    ('security',    '보안',    '보안 취약점 및 방어 메커니즘', '#ef4444'),
    ('performance', '성능',    '성능 안티패턴 및 최적화 기법', '#3b82f6')
ON CONFLICT (name) DO NOTHING;

```

---

### 🔍 주요 보정 및 변경 내역 (Fact Check)

1. **지침서 내 변수명 통일 (`infer_score` ➔ `infer_confidence`)**
* 유저님이 이전에 명명하셨던 구형 지침 명세서상의 `infer_score`는 마스터 테이블인 `documents.infer_confidence` 컬럼명과 단수형 정합성이 완전히 찢어져 있었습니다. 이를 개정된 표준 명세서인 `infer_confidence`로 정렬하고 `staging_concepts`에 완전 주입 마이그레이션 처리했습니다.


2. **3-Factor 세부 메트릭스 격리 수용**
* `staging_concepts` 테이블에 **`score_jaro_winkler`**, **`score_name_vector`**, **`score_desc_vector`** 3대 컬럼을 원자적으로 추가 확보함으로써, 대시보드의 하이브리드 추론 인스펙터 기능 구현 시 판정 로그 근거를 투명하게 영속 룩업할 수 있는 구조적 인프라를 100% 수립했습니다.
