// =============================================================================
// init_db.cypher — Neo4j 4-레이어 지식 그래프 제약조건 및 인덱스 초기화
// 멱등성: IF NOT EXISTS 보장 — 중복 실행 완전 안전
// =============================================================================

// ── 제약조건 ① : 최상위 도메인 거점 노드 고유성
CREATE CONSTRAINT domain_name_unique IF NOT EXISTS FOR (d:Domain) REQUIRE d.name IS UNIQUE;

// ── 제약조건 ② : 중앙 마스터 개념 허브 노드 고유성 (지식 그래프의 심장)
CREATE CONSTRAINT concept_name_unique IF NOT EXISTS FOR (c:Concept) REQUIRE c.name IS UNIQUE;

// ── 제약조건 ③ : 완화 메커니즘 허브 노드 고유성
CREATE CONSTRAINT mechanism_name_unique IF NOT EXISTS FOR (m:Mechanism) REQUIRE m.name IS UNIQUE;

// ── 제약조건 ④ : 버전별 코드 플레이북 위성 노드 복합 고유성 (mech_lang_langver_fw_fwver)
CREATE CONSTRAINT code_example_unq_id_unique IF NOT EXISTS FOR (ce:CodeExample) REQUIRE ce.unq_id IS UNIQUE;

// ── 제약조건 ⑤ : 미들웨어 설정 속성 노드 고유성
CREATE CONSTRAINT property_unq_key_unique IF NOT EXISTS FOR (p:Property) REQUIRE p.unq_key IS UNIQUE;

// ── 제약조건 ⑥ : 출처 문서 마스터 노드 해싱 ID 고유성
CREATE CONSTRAINT document_id_unique IF NOT EXISTS FOR (doc:Document) REQUIRE doc.id IS UNIQUE;

// ── 제약조건 ⑦ : 근본 원인 노드 고유성
CREATE CONSTRAINT root_cause_name_unique IF NOT EXISTS FOR (r:RootCause) REQUIRE r.name IS UNIQUE;

// ── 제약조건 ⑧ : 영향 컴포넌트 노드 고유성
CREATE CONSTRAINT component_name_unique IF NOT EXISTS FOR (x:Component) REQUIRE x.name IS UNIQUE;

// ── 인덱스 ① : 보안 도메인 멀티라벨 고속 스캔 (보안 화면 풀스캔 방지)
CREATE INDEX security_concept_idx IF NOT EXISTS FOR (c:Security) ON (c.name);

// ── 인덱스 ② : 성능 도메인 멀티라벨 고속 스캔 (성능 화면 풀스캔 방지)
CREATE INDEX performance_concept_idx IF NOT EXISTS FOR (c:Performance) ON (c.name);

// ── 인덱스 ③ : 소프트 딜리트 상태 필터링
CREATE INDEX concept_active_status_idx IF NOT EXISTS FOR (c:Concept) ON (c.is_deprecated);

// ── 인덱스 ④ : OWASP 카테고리 ID 분류 룩업
CREATE INDEX concept_owasp_idx IF NOT EXISTS FOR (c:Concept) ON (c.owasp_id);

// ── 인덱스 ⑤ : CWE 번호 분류 룩업
CREATE INDEX concept_cwe_idx IF NOT EXISTS FOR (c:Concept) ON (c.cwe_id);

// ── 풀텍스트 인덱스 : 동의어·한국어명 기반 alias 중복 방지 검색
// AI·관리자가 별칭이나 한국어명으로 검색해도 단 하나의 마스터 노드로 수렴
CREATE FULLTEXT INDEX concept_aliases_fulltext_idx IF NOT EXISTS FOR (n:Concept) ON EACH [n.name, n.aliases];
