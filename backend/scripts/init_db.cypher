// =============================================================================
// init_db.cypher — Neo4j 4-레이어 지식 그래프 제약조건 및 인덱스 초기화 (최종 완공본)
// 멱등성: IF NOT EXISTS 보장 — 중복 실행 완전 안전 (Neo4j 5.x 표준 문법 반영)
// =============================================================================

// ── [🔒 레이어 1~3] 핵심 마스터 골격 노드 고유성 제약조건 (Core Constraints) ──

// ① 최상위 도메인 거점 노드의 name 필드 유일성 제약조건
CREATE CONSTRAINT domain_name_unique IF NOT EXISTS FOR (d:Domain) REQUIRE d.name IS UNIQUE;

// ② 중앙 마스터 개념 허브 노드의 name 필드 유일성 제약조건 (전체 지식 그래프의 심장)
CREATE CONSTRAINT concept_name_unique IF NOT EXISTS FOR (c:Concept) REQUIRE c.name IS UNIQUE;

// ③ 완화 메커니즘 허브 노드의 name 필드 유일성 제약조건
// ⚠️ 주의: 다중 언어/프레임워크 환경 격리를 위해, 백엔드 Graph Writer 레이어에서
// 소문자 스네이크 가공 및 환경 식별 접미사(Suffix)가 결합된 유일 명칭이 주입되어야 합니다.
CREATE CONSTRAINT mechanism_name_unique IF NOT EXISTS FOR (m:Mechanism) REQUIRE m.name IS UNIQUE;

// ⑦ 근본 원인 노드 고유성 제약조건
CREATE CONSTRAINT root_cause_name_unique IF NOT EXISTS FOR (r:RootCause) REQUIRE r.name IS UNIQUE;

// ⑧ 영향 컴포넌트 노드 고유성 제약조건
CREATE CONSTRAINT component_name_unique IF NOT EXISTS FOR (x:Component) REQUIRE x.name IS UNIQUE;


// ── [🔒 레이어 4 및 말단 가변 자산] 하부 영역 고유성 제약조건 (Peripheral Constraints) ──

// ④ 버전별 코드 플레이북 위성 노드 복합 고유성 제약조건
// (PRD 명세 규칙: 백엔드가 원자적으로 조합한 '부모명_언어_언어버전_프레임워크_버전' 규격을 강제합니다)
CREATE CONSTRAINT code_example_unq_id_unique IF NOT EXISTS FOR (ce:CodeExample) REQUIRE ce.unq_id IS UNIQUE;

// ⑤ 미들웨어 설정 속성 노드 고유성 제약조건
CREATE CONSTRAINT property_unq_key_unique IF NOT EXISTS FOR (p:Property) REQUIRE p.unq_key IS UNIQUE;

// ⑥ 출처 문서 마스터 노드 해싱 ID 고유성 제약조건
// ({PREFIX}_{정규화된_URL}_{SHA256_앞8자리} 무결성을 물리 강제합니다)
CREATE CONSTRAINT document_id_unique IF NOT EXISTS FOR (doc:Document) REQUIRE doc.id IS UNIQUE;


// ── [⚡ 인덱스 레이어] 멀티라벨 고속 스캔 및 상태 필터링 인덱스 (Performance Indexes) ──

// ① 보안 도메인 멀티라벨 고속 스캔 인덱스 (보안 화면 진입 시 풀스캔 방지)
CREATE INDEX security_concept_idx IF NOT EXISTS FOR (c:Security) ON (c.name);

// ② 성능 도메인 멀티라벨 고속 스캔 인덱스 (성능 화면 진입 시 풀스캔 방지)
CREATE INDEX performance_concept_idx IF NOT EXISTS FOR (c:Performance) ON (c.name);

// ③ 수명 주기(소프트 딜리트) 활성/비활성 상태 고속 검색용 인덱스
CREATE INDEX concept_active_status_idx IF NOT EXISTS FOR (c:Concept) ON (c.is_deprecated);

// ④ OWASP 카테고리 ID 속성 분류 록업 전용 인덱스
CREATE INDEX concept_owasp_idx IF NOT EXISTS FOR (c:Concept) ON (c.owasp_id);

// ⑤ 🎯 [★교정 완공] CWE 번호 속성 분류 록업 전용 인덱스 문법 완성
CREATE INDEX concept_cwe_idx IF NOT EXISTS FOR (c:Concept) ON (c.cwe_id);


// ── [⚡ 상용망 추가 패치] 플레이북 필터링 및 동의어 풀텍스트 인덱스 ──

// ⑥ 대시보드 인펙터 패널 횡단 조회 시 특정 프레임워크/언어별 코드 스니펫만 초고속 룩업하기 위한 인덱스
CREATE INDEX code_example_lookup_idx IF NOT EXISTS FOR (ce:CodeExample) ON (ce.lang, ce.framework);

// ⑦ 동의어 및 한국어 번역명 기반 입구 단 중복 방지 전용 '풀텍스트 검색 인덱스'
// AI나 인간 관리자가 공식 명칭이 아닌 오타나 한국어 별칭으로 검색해도 단 하나의 마스터 노드로 자석 수렴시킵니다.
CREATE FULLTEXT INDEX concept_aliases_fulltext_idx IF NOT EXISTS FOR (c:Concept) ON EACH [c.name, c.aliases];