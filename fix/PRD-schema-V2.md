### 4레이어 수렴형 아키텍처 토폴로지 도면
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
층별 역할 및 핵심 규칙 (Layer-by-Layer Specifications)
1. 레이어 1: 최상위 도메인 거점 (:Domain)
역할: 전체 지식 토폴로지의 가장 거대한 뿌리이자 기준점이다.

특징: "security"(보안), "performance"(성능)와 같이 대분류 도메인을 정의하며 정적으로 유지된다.

2. 레이어 2: 중앙 마스터 개념 허브 (:Concept) — ★ 아키텍처의 심장
역할: 식별된 모든 기술적 문제점, 결함, 취약점(예: SQLi, MemoryLeak)이 모이는 단 하나의 자석형 허브 노드이다.

핵심 규칙 (물리 멀티 라벨): 도메인별로 노드를 쪼개지 않습니다. MemoryLeak처럼 보안이면서 성능 결함인 교차 도메인 데이터가 인입되면, 단일 노드에 명찰을 겹쳐 붙여 (:Concept:Security:Performance)라는 3중 물리 라벨로 수렴시킵니다.

핵심 규칙 (속성 통합): 구버전 아키텍처에 존재하던 무거운 유령 노드들(OWASPCategory, CWE 등)을 완전히 폐기하고, :Concept 노드 내부의 owasp_id, cwe_id 속성(Property) 필드로 흡수하여 그래프 탐색 깊이를 획기적으로 줄였습니다.

3. 레이어 3: 추상적 해결책 및 명세 레이어 (:Mechanism, :Property, :RootCause)
역할: 개념 허브와 직결되어 문제를 일으키는 불씨(:RootCause), 논리적 해결 방향(:Mechanism), 미세 조율 파라미터(:Property)를 연결하는 중간 허브 층이다.

핵심 규칙 (네이밍 표준화): 이 레이어의 식별 키(name, unq_key)는 AI나 프론트엔드가 어떤 포맷으로 던지든 백엔드 입구 단에서 완전 소문자 스네이크 케이스(lower_snake_case)로 강제 변환하여 적재 정합성을 사전에 확보한다 (예: "ParameterizedQuery" ──> "parameterized_query").

4. 레이어 4: 버전별 실물 플레이북 레이어 (:CodeExample)
역할: 프로그래밍 언어, 프레임워크, 그리고 세부 버전별로 파편화되는 구체적인 실물 소스코드 스니펫이 안착하는 최외곽 위성 노드 영역이다.

핵심 규칙 (독립 증분 체계): 개념적 완화책인 :Mechanism 하위에 1:N 관계로 기생한다 새로운 프레임워크 버전(예: Django 5.1)의 문서가 추가로 수집되더라도 상위의 Concept이나 Mechanism은 그대로 유지된 채, 이 레이어의 CodeExample 노드만 자석처럼 찰떡같이 새로 덧붙여지는(Append) 형태를 취한다

핵심 규칙 (복합 고유 키): 중복 생성을 원천 차단하기 위해 부모명_언어_언어버전_프레임워크_프레임워크버전을 조합한 물리적 복합 유일 키(unq_id)를 강제한다.
### 15.2. PostgreSQL 스키마 DDL
- 스키마 명세 : [../backend/scripts/seed/security/schema.sql)](../backend/scripts/seed/security/schema.sql)

### 15.3. Neo4j 노드 및 관계 전체 명세

#### 노드 레이블 및 주요 속성 명세 (Final Schema Blueprint)

| 레이블 (Label) | MERGE 식별 키 | 핵심 속성 (Properties) | 도메인 귀속 및 관리 규칙 |
| :--- | :--- | :--- | :--- |
| **`:Domain`** | `name` | `name` *(String, 소문자 고정: `"security"`, `"performance"`)*<br>`description_ko` *(String, 도메인 국문 설명)*<br>`created_at` *(Integer Epoch)* | **최상위 루트 레이어**<br>전체 지식 토폴로지의 거대한 줄기를 나누는 정적 기준점이다. |
| **`:Concept`** | `name` | `name` *(String, 영문 약어 파스칼케이스: `"SQLi"`, `"MemoryLeak"`)*<br>`concept_type` *(String: `"vulnerability_root_cause"`, `"performance_antipattern"`)*<br>`severity` *(String: `"critical"`, `"high"`, `"medium"`, `"low"`)*<br>`owasp_id` *(String, 속성 흡수: `"A03:2021"` 또는 `null`)*<br>`cwe_id` *(String, 속성 흡수: `"CWE-89"`, `"CWE-401"`)*<br>`description_ko` *(String, 한국어 통합 개념 명세)*<br>`aliases` *(List\<String\>, 동의어 문자열 배열: `["SQL 인젝션", ...]`, Full-text 색인)*<br>`domains` *(List\<String\>, 소속 도메인 검색용 소문자 배열: `["security"]`)*<br>`is_deprecated` *(Boolean, 인간 검수용 소프트 딜리트 플래그)*<br>`created_at` / `updated_at` *(Integer Epoch)* | **중앙 마스터 허브 레이어**<br>도메인 분기 시 노드를 분리하지 않고, 데이터 흐름에 따라 동적으로 **`:Security`** 및 **`:Performance`** 물리 멀티 라벨을 실시간 레이어링하여 자석처럼 통합 수렴한다 |
| **`:Mechanism`** | `name` | `name` *(String, 완전 소문자 스네이크케이스 강제 가공)*<br>`created_at` *(Integer Epoch)* | **개념적 완화 기법 레이어**<br>취약점과 결함을 방어하는 기술적 수단이자 치료제 허브 노드이다. |
| **`:Property`** | `unq_key` | `unq_key` *(String, 소문자 스네이크 변수명: `"pool_max_size"`)*<br>`value` *(String, 권장 설정값 문자열: `"10"`, `"true"`)*<br>`type` *(String, 성격 분류 지표: `"security"` 또는 `"tuning"`)*<br>`created_at` *(Integer Epoch)* | **미들웨어 / 설정 속성 레이어**<br>`Concept` 노드와 `[:TUNED_BY]` 관계로 직결되어 시스템 인프라 수치를 미세 조율한다 |
| **`:CodeExample`** | `unq_id` | `unq_id` *(String, 복합 유일 키: `부모명_언어_언어버전_프레임워크_버전`)*<br>`lang` / `lang_version` *(String: `"python"`, `">=3.10"`)*<br>`framework` / `framework_version` *(String: `"django"`, `">=5.0"`)*<br>`code` *(String, 순수 소스코드 스니펫 본문 문자열)*<br>`description` *(String, 해당 환경 전용 구동 가이드)*<br>`created_at` *(Integer Epoch)* | **[레이어 4] 말단 플레이북 레이어**<br>`:Mechanism` 하위에 `1:N` 구조로 매달리며, 신규 언어/프레임워크 버전이 인입될 때 컨셉을 건드리지 않고 이 노드만 독립 증분(Append)된다. |
| **`:Document`** | `id` | `id` *(String, 해싱 ID: `{PREFIX}_{정규화된_URL}_{SHA256_앞8자리}`)*<br>`title` *(String, 문서 혹은 PR 제목)*<br>`source` *(String, 출처 플랫폼 분류: `"confluence"`, `"github"`)*<br>`raw_url` *(String, 원본 브라우저 접근 링크)*<br>`created_at` *(Integer Epoch)* | **말단 가변 자산 레이어**<br>지식 그래프 마스터에 화살표를 꽂아 출처를 보증하며, 인간 관리자 삭제(Purge) 시 다른 마스터 골격을 다치지 않게 `DETACH DELETE`로 연쇄 하드 딜리트되는 대상이다. |

#### 관계 타입 전체 목록

노드와 노드를 연결하는 화살표선의 명칭, 방향, 그리고 연결 구조 규칙(관계 정합성) 명세이다. Neo4j 표준에 따라 **모두 대문자 스네이크 케이스**로 통일한다

| 관계선 타입 (Edge Type) | 출발 노드 (From) | 도착 노드 (To) | 카디널리티 (소속 구조) | 아키텍처적 의미 및 관리 규칙 |
| --- | --- | --- | --- | --- |
| **`BELONGS_TO`** | `:Concept` | `:Domain` | `N : M` | 특정 결함 개념이 어느 루트 도메인 울타리에 속하는지 정의한다 (수정 시 끊고 재조인) |
| **`CAUSED_BY`** | `:Concept` | `:RootCause` | `N : M` | 취약점이나 병목이 터지게 된 기술적 불씨(원인)를 추적 체인으로 연결한다 |
| **`AFFECTS`** | `:Concept` | `:Component` | `N : M` | 이 결함이 유발되었을 때 내부 인프라에서 타격을 입거나 파괴되는 소프트웨어/물리 부품 레이어를 지정한다 |
| **`MITIGATED_BY`** | `:Concept` | `:Mechanism` | `N : M` | 문제를 무력화하는 전천후 해결 기법 허브 노드로 화살표를 직결한다 |
| **`HAS_EXAMPLE`** | `:Mechanism` | `:CodeExample` | `1 : N` | 개념적 완화책 하위에 기생하는 **버전별 구체적 실무 소스코드 위성 노드**들을 주렁주렁 매달아 줍니다. |
| **`TUNED_BY`** | `:Concept` | `:Property` | `N : M` | 결함 차단을 위해 미세 조율해야 하는 인프라/프레임워크 제어 파라미터를 연결한다 |
| **`REFERENCES`** | `:Document` | `:Concept`<br>

<br>또는 `:RootCause` | `N : M` | **말단 가변 데이터선**. 사내 문서가 지식 마스터의 어떤 문제점과 조인되어 있는지 링크한다 (하드 딜리트 대상) |


#### Concept 다중 라벨 규칙
| 유입되는 `domains` 배열 스펙 | Neo4j 물리 노드 생성 형태 (라벨 결합) | 실제 매핑되는 개념 예시 |
| --- | --- | --- |
| `["security"]` | `(:Concept:Security)` | `XSS`, `SQLi`, `CSRF` 등 순수 보안 취약점 |
| `["performance"]` | `(:Concept:Performance)` | `N+1Query`, `MissingIndex` 등 순수 성능 안티패턴 |
| `["security", "performance"]` | `(:Concept:Security:Performance)` | `MemoryLeak`, `ConnPoolExhaustion` 등 **교차 결함** |

> ⚠️ **주의 (네이밍 컨벤션)**: 주 골격 라벨인 `Concept`과 동적 서브 도메인 라벨인 `Security`, `Performance`는 Neo4j 표준에 따라 **반드시 첫 글자가 대문자인 파스칼 케이스(PascalCase)**를 준수한다

#### ⚡ 2. 백엔드(Pydantic) ↔ DB(Cypher) 동적 적재 가공 규칙

AI 추출 에이전트(Extractor)가 자유롭게 확장 가능한 소문자 문자열 배열(`["security", "performance"]`)을 던지면, 백엔드의 `graph_writer` 레이어는 이를 받아 하드코딩된 분기문(`if/else`) 없이 **APOC 프로시저를 통해 동적으로 물리 라벨을 누적 주입**한다 



### 15.4. Neo4j 제약 조건 및 인덱스 선언

```cypher
// =========================================================================
// 🔒 1. 핵심 마스터 골격 노드 고유성 제약 조건 (Core Constraints)
// =========================================================================

-- ① 최상위 도메인 거점 노드의 name 필드 유일성 제약 조건
CREATE CONSTRAINT domain_name_unique IF NOT EXISTS FOR (d:Domain) REQUIRE d.name IS UNIQUE;

-- ② 중앙 마스터 개념 허브 노드의 name 필드 유일성 제약 조건
-- (전체 지식 그래프의 심장부이며, AI 증분 적재 및 인간 검수의 기준 축이 됩니다)
CREATE CONSTRAINT concept_name_unique IF NOT EXISTS FOR (c:Concept) REQUIRE c.name IS UNIQUE;

-- ③ 완화 메커니즘 허브 노드의 name 필드 유일성 제약 조건
CREATE CONSTRAINT mechanism_name_unique IF NOT EXISTS FOR (m:Mechanism) REQUIRE m.name IS UNIQUE;


// =========================================================================
// 🔒 2. 말단 가변 자산 및 하부 영역 고유성 제약 조건 (Peripheral Constraints)
// =========================================================================

-- ④ [레이어 4] 버전별 코드 플레이북 위성 노드의 복합 복제 방지 유일성 제약 조건
-- (부모명_언어_언어버전_프레임워크_버전 규격을 강제하여 중복 생성을 물리 차단합니다)
CREATE CONSTRAINT code_example_unq_id_unique IF NOT EXISTS FOR (code:CodeExample) REQUIRE code.unq_id IS UNIQUE;

-- ⑤ 미들웨어 / 환경 변수 설정 프로퍼티 노드의 유일성 제약 조건
CREATE CONSTRAINT property_unq_key_unique IF NOT EXISTS FOR (p:Property) REQUIRE p.unq_key IS UNIQUE;

-- ⑥ 말단 출처 문서 노드의 유일성 제약 조건
-- ({PREFIX}_{정규화된_URL}_{SHA256_앞8자리} 해싱 ID 무결성을 강제합니다)
CREATE CONSTRAINT document_id_unique IF NOT EXISTS FOR (doc:Document) REQUIRE doc.id IS UNIQUE;

-- ⑦ 근본 원인 및 물리/논리 타격 부품 노드의 유일성 제약 조건 (확장 대비)
CREATE CONSTRAINT root_cause_name_unique IF NOT EXISTS FOR (r:RootCause) REQUIRE r.name IS UNIQUE;

CREATE CONSTRAINT component_name_unique IF NOT EXISTS FOR (x:Component) REQUIRE x.name IS UNIQUE;

// =========================================================================
// ⚡ 3. 멀티 라벨 고속 스캔 및 상태 필터링 인덱스 (Label & Status Indexes)
// =========================================================================

-- ① 보안 도메인 전용 고속 물리 라벨 색인 인덱스 (보안 화면 진입 시 풀스캔 방지)
CREATE INDEX security_concept_idx IF NOT EXISTS FOR (c:Security) ON (c.name);

-- ② 성능 도메인 전용 고속 물리 라벨 색인 인덱스 (성능 화면 진입 시 풀스캔 방지)
CREATE INDEX performance_concept_idx IF NOT EXISTS FOR (c:Performance) ON (c.name);

-- ③ 수명 주기(소프트 딜리트) 활성/비활성 상태 고속 검색용 인덱스
CREATE INDEX concept_active_status_idx IF NOT EXISTS FOR (c:Concept) ON (c.is_deprecated);


// =========================================================================
// ⚡ 4. 속성 통합형 분류 및 풀텍스트 검색 인덱스 (Property & Full-text Indexes)
// =========================================================================

-- ④ [속성 전환 대응] OWASP 카테고리 ID 및 CWE 번호 기반 분류 록업 전용 인덱스
CREATE INDEX concept_owasp_idx IF NOT EXISTS FOR (c:Concept) ON (c.owasp_id);

CREATE INDEX concept_cwe_idx IF NOT EXISTS FOR (c:Concept) ON (c.cwe_id);

-- ⑤ [인간 통제용 완벽 방어벽] 동의어 및 한국어 번역명 전용 '풀텍스트 검색 인덱스'
-- AI나 인간 관리자가 정식 명칭(name)이 아닌 임의의 별칭이나 오타로 검색해도 
-- 단 하나의 마스터 개념 노드를 정확하게 유추해 적재 수렴(Deduplication)시킵니다.
CREATE FULLTEXT INDEX concept_aliases_fulltext_idx IF NOT EXISTS FOR (c:Concept) ON EACH [c.name, c.aliases];
```
