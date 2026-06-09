유저님이 제공해주신 구형 스키마 지침 구조와 최신 3-Factor 유사도 세부 지표 수집 조건(Jaro-Winkler, Name_Vector, Desc_Vector)을 완전히 정렬하여 리팩토링한 [최종 개정판 4레이어 온톨로지 스키마 지침서]입니다.

Link Resolver 엔진의 유사도 분석 투명성을 극대화하기 위해 PostgreSQL 마스터 및 스테이징 구조에 세부 지표 컬럼을 공식 반영하고, 제약조건 명세를 완벽히 보정했습니다.

---

# 📐 [최종 개정판] 4-레이어 지식 온톨로지 구조 및 DB 스키마 표준 명세서

### 4레이어 수렴형 아키텍처 토폴도지 도면

```
[ 레이어 1 : 도메인 거점 ]        (d:Domain)  { name: 'security' }
                                     │
                                     │ [:BELONGS_TO] (수정 시 재배선)
                                     ▼
[ 레이어 2 : 개념 통합 허브 ]      (c:Concept:Security:Performance)  ◀── [자석형 수렴 거점]
                                     │
         ┌───────────────────────────┼───────────────────────────┐
         │ [:CAUSED_BY]              │ [:MITIGATED_BY]           │ [:TUNED_BY]
         ▼                           ▼                           ▼
[ 레이어 3 : 추상 해결 허브 ]   (r:RootCause)               (m:Mechanism)               (p:Property)
                                                     { name: 'p_query' }        { unq_key: 'p_max' }
                                                             │
                                                             │ [:HAS_EXAMPLE]
                                                             ▼
[ 레이어 4 : 실물 플레이북 ]                             (code:CodeExample)  ◀── [버전별 독립 증분]
                                                   { unq_id: 'p_query_py_dj_5' }

```

---

## 1. 층별 역할 및 핵심 규칙 (Layer-by-Layer Specifications)

### 1.1. 레이어 1: 최상위 도메인 거점 (`:Domain`)

* **역할**: 전체 지식 토폴로지의 가장 거대한 뿌리이자 기준점이다.
* **특징**: `"security"`(보안), `"performance"`(성능)와 같이 대분류 도메인을 정의하며 정적으로 유지된다.

### 1.2. 레이어 2: 중앙 마스터 개념 허브 (`:Concept`) — ★ 아키텍처의 심장

* **역할**: 식별된 모든 기술적 문제점, 결함, 취약점(예: SQLi, MemoryLeak)이 모이는 단 하나의 자석형 허브 노드이다.
* **핵심 규칙 (물리 멀티 라벨)**: 도메인별로 노드를 쪼개지 않는다. `MemoryLeak`처럼 보안이면서 성능 결함인 교차 도메인 데이터가 인입되면, 단일 노드에 명찰을 겹쳐 붙여 `(:Concept:Security:Performance)`라는 3중 물리 라벨로 수렴시킨다.
* **핵심 규칙 (속성 통합)**: 구버전 아키텍처에 존재하던 무거운 유령 노드들(OWASPCategory, CWE 등)을 완전히 폐기하고, `:Concept` 노드 내부의 `owasp_id`, `cwe_id` 속성 필드로 흡수하여 그래프 탐색 깊이를 획기적으로 줄였다.

### 1.3. 레이어 3: 추상적 해결책 및 명세 레이어 (`:Mechanism`, `:Property`, `:RootCause`)

* **역할**: 개념 허브와 직결되어 문제를 일으키는 불씨(`:RootCause`), 논리적 해결 방향 (`:Mechanism`), 미세 조율 파라미터 (`:Property`)를 연결하는 중간 허브 층이다.
* **핵심 규칙 (네이밍 표준화)**: 이 레이어의 식별 키는 AI나 프론트엔드가 어떤 포맷으로 던지든 완전 소문자 스네이크 케이스(`lower_snake_case`)로 강제 변환하여 적재 정합성을 사전에 확보한다.
* **⚠️ 주의 (Mechanism 제약조건 충돌 방지)**: 다중 언어/프레임워크 환경 간 격리를 보장하기 위해, 백엔드 기동 시 `mechanism_name` 뒤에 프레임워크 식별 접미사를 결합(예: `output_encoding_django`)하여 글로벌 제약조건 충돌을 원천 차단한다.

### 1.4. 레이어 4: 버전별 실물 플레이북 레이어 (`:CodeExample`)

* **역할**: 프로그래밍 언어, 프레임워크, 그리고 세부 버전별로 파편화되는 구체적인 실물 소스코드 스니펫이 안착하는 최외곽 위성 노드 영역이다.
* **핵심 규칙 (독립 증분 체계)**: 개념적 완화책인 `:Mechanism` 하위에 `1:N` 관계로 기생한다. 신규 프레임워크 버전 문서가 수집되더라도 상위 골격은 유지된 채, 이 레이어의 `CodeExample` 노드만 독립적으로 덧붙여지는(`Append`) 형태를 취한다.
* **핵심 규칙 (복합 고유 키 자동화)**: 중복 생성을 물리 차단하기 위해 **`부모Mechanism명_언어_언어버전_프레임워크_프레임워크버전`** 조합의 고유 키(`unq_id`) 형식을 강제한다. 단, 오차 방지를 위해 키 조합 연산은 AI가 아닌 백엔드 Graph Writer가 수행한다.

---

## 2. PostgreSQL 운영 및 스테이징 스키마 DDL 명세

### 2.1. 운영 마스터 테이블 (`concepts`)

```sql
CREATE TABLE IF NOT EXISTS concepts (
  id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  concept_name   TEXT NOT NULL UNIQUE, -- 영문 표준 파스칼케이스 수렴 축
  doc_id         TEXT REFERENCES documents(doc_id) ON DELETE SET NULL,
  domains        TEXT[] NOT NULL,      -- 물리 멀티 라벨 동치 데이터
  concept_type   TEXT,                 -- 대칭 유형 식별자
  cwe_id         TEXT,
  owasp_id       TEXT,                 -- owasp_category 명칭 통일 반영
  severity       TEXT,                 -- critical | high | medium | low
  description_ko TEXT,                 -- 한국어 개념 명세 요약
  aliases        TEXT[] NOT NULL DEFAULT '{}',
  is_deprecated  BOOLEAN DEFAULT false, -- 소프트 딜리트 플래그
  
  -- ── ⚡ 3-Factor 하이브리드 수렴 벡터 저장소 (pgvector) ──
  name_vector    vector(768),          -- 개념명 및 동의어 풀 결합 컨텍스트 벡터
  desc_vector    vector(768),          -- 국문 요약본 의미론 벡터
  
  created_at     TIMESTAMPTZ DEFAULT now(),
  updated_at     TIMESTAMPTZ
);

```

### 2.2. [개정] 스테이징 임시 격리 테이블 (`staging_concepts v3`)

Link Resolver의 유사도 가중치 판정 근거를 투명하게 박제하여 대시보드 디버깅용 소스로 공급하기 위한 세부 3-Factor 컬럼이 공식 계정 추가되었습니다.

```sql
CREATE TABLE IF NOT EXISTS staging_concepts (
  id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  session_id       UUID NOT NULL,
  doc_id           TEXT REFERENCES documents(doc_id) ON DELETE CASCADE,
  concept_json     JSONB NOT NULL,     -- Gemini 가 배출한 규격 JSON 본문
  state            TEXT NOT NULL DEFAULT 'DRAFT', -- DRAFT | DOMAIN_PENDING | COMMITTED
  known_domains    TEXT[] DEFAULT '{}',
  unknown_domains  TEXT[] DEFAULT '{}',
  
  -- ── 🎯 3-Factor 하이브리드 중복 판정 역추적 전용 컬럼 ──
  infer_action     TEXT,               -- MERGE | RELATED_TO | NEW
  target_concept   TEXT,               -- 병합 대상 타겟 마스터 개념명
  infer_confidence FLOAT DEFAULT 0.0,  -- 최종 합산 가중치 하이브리드 스코어 (Confidence)
  score_jaro_winkler FLOAT DEFAULT 0.0, -- 1) 어휘 구조 일치도 점수 (40%)
  score_name_vector  FLOAT DEFAULT 0.0, -- 2) 키워드 융합 문맥 벡터 점수 (30%)
  score_desc_vector  FLOAT DEFAULT 0.0, -- 3) 요약 설명 코사인 유사도 점수 (30%)
  
  reviewed_at      TIMESTAMPTZ,
  committed_at     TIMESTAMPTZ,
  created_at       TIMESTAMPTZ DEFAULT now()
);

```

---

## 3. Neo4j 노드 및 관계 전체 명세 (Blueprint)

### 3.1. 노드 레이블 및 주요 속성 명세

| 레이블 (Label) | MERGE 식별 키 | 핵심 속성 (Properties) | 도메인 귀속 및 관리 규칙 |
| --- | --- | --- | --- |
| **`:Domain`** | `name` | `name` *(String, 소문자 고정)*<br>

<br>`description_ko` *(String)*<br>

<br>`created_at` *(Integer)* | **최상위 루트 레이어**<br>

<br>전체 지식 토폴로지의 거대한 줄기를 나누는 정적 기준점이다. |
| **`:Concept`** | `name` | `name` *(PascalCase)*<br>

<br>`concept_type` / `severity` *(String)*<br>

<br>`owasp_id` / `cwe_id` *(String | null)*<br>

<br>`description_ko` *(String)*<br>

<br>`aliases` / `domains` *(List<String>)*<br>

<br>`is_deprecated` *(Boolean)* | **중앙 마스터 허브 레이어**<br>

<br>데이터 유입에 따라 동적으로 **`:Security`** 및 **`:Performance`** 물리 멀티 라벨을 실시간 레이어링하여 자석처럼 통합 수렴한다. |
| **`:Mechanism`** | `name` | `name` *(String, 소문자 스네이크+환경 접미사)*<br>

<br>`created_at` *(Integer)* | **개념적 완화 기법 레이어**<br>

<br>취약점과 결함을 방어하는 기술적 수단이자 치료제 허브 노드이다. |
| **`:Property`** | `unq_key` | `unq_key` / `value` / `type` *(String)*<br>

<br>`created_at` *(Integer)* | **미들웨어 / 설정 속성 레이어**<br>

<br>`Concept` 노드와 `[:TUNED_BY]` 관계로 직결되어 인프라 수치를 미세 조율한다. |
| **`:CodeExample`** | `unq_id` | `unq_id` *(String, 복합 고유 키)*<br>

<br>`lang` / `lang_version` *(String)*<br>

<br>`framework` / `framework_version` *(String)*<br>

<br>`code` / `description` *(String)* | **[레이어 4] 말단 플레이북 레이어**<br>

<br>`:Mechanism` 하위에 `1:N` 구조로 매달리며, 신규 환경 인입 시 이 노드만 독립 증분(Append)된다. |
| **`:Document`** | `id` | `id` *(String, 해싱 마스터 키)*<br>

<br>`title` / `source` / `raw_url` *(String)* | **말단 가변 자산 레이어**<br>

<br>지식 출처를 보증하며, 인간 관리자 삭제 시 골격을 건드리지 않고 `DETACH DELETE` 연쇄 하드 딜리트되는 대상이다. |

### 3.2. 관계선 표준 명세

관계 정합성을 수호하기 위해 Neo4j 표준에 따라 **모두 대문자 스네이크 케이스**로 통일 조인한다.

* `(c:Concept)-[:BELONGS_TO]->(d:Domain)`
* `(c:Concept)-[:CAUSED_BY]->(r:RootCause)`
* `(c:Concept)-[:AFFECTS]->(x:Component)`
* `(c:Concept)-[:MITIGATED_BY]->(m:Mechanism)` (★ 기존 HAS_MECHANISM을 아키텍처 규칙 도면에 맞춰 수렴 대통합)
* `(m:Mechanism)-[:HAS_EXAMPLE]->(code:CodeExample)`
* `(c:Concept)-[:TUNED_BY]->(p:Property)`
* `(doc:Document)-[:REFERENCES]->(c:Concept)`

---

## 4. Neo4j 제약 조건 및 인덱스 선언 (`init_db.cypher`)

```cypher
// =========================================================================
// 🔒 1. 핵심 마스터 골격 노드 고유성 제약 조건 (Core Constraints)
// =========================================================================
CREATE CONSTRAINT domain_name_unique IF NOT EXISTS FOR (d:Domain) REQUIRE d.name IS UNIQUE;
CREATE CONSTRAINT concept_name_unique IF NOT EXISTS FOR (c:Concept) REQUIRE c.name IS UNIQUE;

-- ⚠️ 다중 언어/프레임워크 환경 격리를 위해 Mechanism 노드명은 소문자 스네이크 조합 고유 키 인입을 준수합니다.
CREATE CONSTRAINT mechanism_name_unique IF NOT EXISTS FOR (m:Mechanism) REQUIRE m.name IS UNIQUE;
CREATE CONSTRAINT root_cause_name_unique IF NOT EXISTS FOR (r:RootCause) REQUIRE r.name IS UNIQUE;
CREATE CONSTRAINT component_name_unique IF NOT EXISTS FOR (x:Component) REQUIRE x.name IS UNIQUE;

// =========================================================================
// 🔒 2. 말단 플레이북 및 가변 자산 영역 고유성 제약 조건 (Peripheral Constraints)
// =========================================================================
CREATE CONSTRAINT code_example_unq_id_unique IF NOT EXISTS FOR (code:CodeExample) REQUIRE code.unq_id IS UNIQUE;
CREATE CONSTRAINT property_unq_key_unique IF NOT EXISTS FOR (p:Property) REQUIRE p.unq_key IS UNIQUE;
CREATE CONSTRAINT document_id_unique IF NOT EXISTS FOR (doc:Document) REQUIRE doc.id IS UNIQUE;

// =========================================================================
// ⚡ 3. 멀티 라벨 고속 검색 및 하이브리드 필터링 인덱스 (Performance Indexes)
// =========================================================================
CREATE INDEX security_concept_idx IF NOT EXISTS FOR (c:Security) ON (c.name);
CREATE INDEX performance_concept_idx IF NOT EXISTS FOR (c:Performance) ON (c.name);
CREATE INDEX concept_active_status_idx IF NOT EXISTS FOR (c:Concept) ON (c.is_deprecated);
CREATE INDEX concept_owasp_idx IF NOT EXISTS FOR (c:Concept) ON (c.owasp_id);
CREATE INDEX concept_cwe_idx IF NOT EXISTS FOR (c:Concept) ON (c.cwe_id);

-- 🎯 [추가 패치] 대시보드 인스펙터 패널 다차원 횡단 필터링 고속 색인 인덱스
CREATE INDEX code_example_lookup_idx IF NOT EXISTS FOR (code:CodeExample) ON (code.lang, code.framework);

// =========================================================================
// ⚡ 4. 속성 통합형 분류 및 풀텍스트 검색 인덱스 (Deduplication Core)
// =========================================================================
-- Jaro-Winkler 계산 전, 동의어 및 한국어 번역명을 풀텍스트 스캔하여 입구 단 중복 병합을 실현하는 심장부입니다.
CREATE FULLTEXT INDEX concept_aliases_fulltext_idx IF NOT EXISTS FOR (c:Concept) ON EACH [c.name, c.aliases];

```