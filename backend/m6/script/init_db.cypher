// =============================================================================
// init_db.cypher — Neo4j 스키마 초기화 (4-Layer 온톨로지 제약 + 인덱스)
// 멱등성: IF NOT EXISTS — 중복 실행 완전 안전
// schema.md §2.3 기준 UNIQUE 7종 + fulltext 1종
// =============================================================================

// ── L1 Domain
CREATE CONSTRAINT domain_name_unique IF NOT EXISTS
    FOR (d:Domain) REQUIRE d.name IS UNIQUE;

// ── L2 Concept
CREATE CONSTRAINT concept_name_unique IF NOT EXISTS
    FOR (c:Concept) REQUIRE c.name IS UNIQUE;

// ── L3 Mechanism
CREATE CONSTRAINT mechanism_name_unique IF NOT EXISTS
    FOR (m:Mechanism) REQUIRE m.name IS UNIQUE;

// ── L3 RootCause
CREATE CONSTRAINT rootcause_name_unique IF NOT EXISTS
    FOR (r:RootCause) REQUIRE r.name IS UNIQUE;

// ── L3 Component
CREATE CONSTRAINT component_name_unique IF NOT EXISTS
    FOR (comp:Component) REQUIRE comp.name IS UNIQUE;

// ── L3 Property  (unq_key = snake_case 식별자)
CREATE CONSTRAINT property_unq_key_unique IF NOT EXISTS
    FOR (p:Property) REQUIRE p.unq_key IS UNIQUE;

// ── L4 CodeExample  (unq_id = mechanism_name + "_ex_" + 순번)
CREATE CONSTRAINT codeexample_unq_id_unique IF NOT EXISTS
    FOR (ce:CodeExample) REQUIRE ce.unq_id IS UNIQUE;

// ── Fulltext index — alias 사전 dedup 조회용 (schema.md §2.3)
// Concept.name + Concept.aliases 배열 동시 인덱싱
CREATE FULLTEXT INDEX concept_aliases_fulltext_idx IF NOT EXISTS
    FOR (c:Concept) ON EACH [c.name, c.aliases];
