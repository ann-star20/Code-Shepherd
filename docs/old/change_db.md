PostgreSQL의 DDL처럼 **Neo4j 그래프 데이터베이스의 구체적인 노드(Node), 속성(Properties), 관계선(Edge/Relationship)의 스키마 구조와 타입, 카디널리티(연결 관계)를 한눈에 볼 수 있도록 정형화된 명세서** 형태로 정리해 드릴게요.

Neo4j는 널스펙(Schemaless) 기반이지만, 프로덕션 환경에서 정합성을 지키려면 이 문서처럼 물리적인 속성 타입과 관계 규칙을 명확히 정의해 두고 백엔드(Pydantic/Cypher)와 싱크를 맞춰야 합니다.

---

##  1. 노드(Node) 및 속성(Properties) 상세 명세

각 노드 라벨별로 들어가는 물리적인 속성 키, 데이터 타입, 그리고 제약 조건 명세입니다.

### ① `:Domain` (최상위 도메인 거점 노드)

* **설명**: 전체 지식 그래프의 거대한 줄기(보안, 성능 등)를 나누는 루트 노드
* **속성 명세**:
| 속성 키 (Property Key) | 데이터 타입 (Type) | 제약 조건 / 설명 | 예시 데이터 |
| --- | --- | --- | --- |
| `name` | `String` | **주 키 (Unique / Required)**, 소문자 고정 | `"security"`, `"performance"` |
| `description_ko` | `String` | 도메인 국문 상세 설명 | `"웹 취약점 통제 도메인"` |
| `created_at` | `Integer (Epoch)` | 노드 생성 타임스탬프 | `1772345678` |



### ② `:Concept` (중앙 마스터 개념 노드)

* **설명**: 식별된 모든 기술적 문제점, 결함, 취약점의 핵심 마스터 데이터
* **속성 명세**:
| 속성 키 (Property Key) | 데이터 타입 (Type) | 제약 조건 / 설명 | 예시 데이터 |
| --- | --- | --- | --- |
| `name` | `String` | **주 키 (Unique / Required)**, 파스칼케이스 약어 | `"SQLi"`, `"ConnPoolExhaustion"` |
| `concept_type` | `String` | 문제 분류 범주 | `"vulnerability_root_cause"`, ... |
| `domains` | `List<String>` | 소속 도메인 검색용 소문자 배열 | `["security", "performance"]` |
| `severity` | `String` | 위험 심각도 등급 (소문자 고정) | `"critical"`, `"high"`, `"medium"` |
| `description_ko` | `String` | 국문 개념 상세 설명 문서 | `"커넥션 풀이 완전히 고갈되어..."` |
| `aliases` | `List<String>` | 동의어 및 한국어 번역명 배열 (Full-text 대상) | `["SQL 인젝션", "SQL Injection"]` |
| `is_deprecated` | `Boolean` | **소프트 딜리트 플래그** (Human-in-the-Loop용) | `false` 또는 `true` |
| `created_at` | `Integer (Epoch)` | 생성일 타임스탬프 | `1772345678` |
| `updated_at` | `Integer (Epoch)` | **증분 업데이트 시 이 필드만 최신화** | `1772399999` |
| `deprecated_at` | `Integer / Null` | 폐기 처리된 시점의 타임스탬프 | `1772388888` |



### ③ `:Mechanism` (통합 완화 메커니즘 노드)

* **설명**: 문제를 해결하거나 완화하는 전천후 기술적 대책 핵심 노드
* **속성 명세**:
| 속성 키 (Property Key) | 데이터 타입 (Type) | 제약 조건 / 설명 | 예시 데이터 |
| --- | --- | --- | --- |
| `name` | `String` | **주 키 (Unique / Required)**, 소문자 스네이크 | `"parameterized_query"`, `"conn_pooling"` |



### ④ `:CodeExample` (버전별 소스코드 위성 노드)

* **설명**: 레이어 4에 위치하며, 매커니즘 하위에 1:N으로 결합하는 구체적인 실무 플레이북 코드 조각
* **속성 명세**:
| 속성 키 (Property Key) | 데이터 타입 (Type) | 제약 조건 / 설명 | 예시 데이터 |
| --- | --- | --- | --- |
| `unq_id` | `String` | **주 키 (Unique)**, 부모이름+언어+버전 복합 키 | `"conn_pooling_python_>=3.10_django_>=5.0"` |
| `lang` | `String` | 프로그래밍 언어 (소문자 고정) | `"python"`, `"java"` |
| `lang_version` | `String` | 언어 권장/호환 버전 명세 | `">=3.10"`, `"17"` |
| `framework` | `String` | 프레임워크 명칭 (소문자 고정) | `"django"`, `"spring_boot"` |
| `framework_version` | `String` | 프레임워크 권장/호환 버전 명세 | `">=5.0"`, `"6.0.x"` |
| `code` | `String` | 순수 소스코드 본문 문자열 (이스케이프 필수) | `"results = MyModel.objects.filter(...)"` |
| `description` | `String` | 해당 버전 환경에서의 코드 효율성/안전성 설명 | `"Django 5.0+에서 호환되는 ORM..."` |



### ⑤ `:Property` (미들웨어 / 환경 변수 설정 노드)

* **설명**: 코드 외적으로 시스템을 미세 조율(`TUNED_BY`)할 수 있는 정적 환경 설정 파라미터
* **속성 명세**:
| 속성 키 (Property Key) | 데이터 타입 (Type) | 제약 조건 / 설명 | 예시 데이터 |
| --- | --- | --- | --- |
| `unq_key` | `String` | **주 키 (Unique / Required)**, 소문자 스네이크 | `"pool_max_size"`, `"csrf_cookie_secure"` |
| `value` | `String` | 권장 설정 제어값 문자열 | `"10"`, `"true"`, `"60"` |
| `type` | `String` | 성격 분류 분류 지표 | `"security"` 또는 `"tuning"` |



### ⑥ 기타 말단 공용 및 가변 노드 (`:RootCause`, `:Component`, `:Document`)

* **`:RootCause`** 속성: `name (String, Unique)` -> 예: `"untrusted_string_concatenation"`
* **`:Component`** 속성: `name (String, Unique)` -> 예: `"database_access_layer"`
* **`:Document`** 속성: `id (String, Unique)` -> 예: `"{PREFIX}_{정규화된_URL}_{SHA256_앞8자리}"`, `title (String)`, `source (String)` -> 예: `"confluence"`

---

##  2. 관계선(Edge/Relationship) 스키마 및 카디널리티 명세

노드와 노드를 연결하는 화살표선의 명칭, 방향, 그리고 연결 구조 규칙(관계 정합성) 명세입니다. Neo4j 표준에 따라 **모두 대문자 스네이크 케이스**로 통일합니다.

| 관계선 타입 (Edge Type) | 출발 노드 (From) | 도착 노드 (To) | 카디널리티 (소속 구조) | 아키텍처적 의미 및 관리 규칙 |
| --- | --- | --- | --- | --- |
| **`BELONGS_TO`** | `:Concept` | `:Domain` | `N : M` | 특정 결함 개념이 어느 루트 도메인 울타리에 속하는지 정의합니다. (수정 시 끊고 재조인) |
| **`CAUSED_BY`** | `:Concept` | `:RootCause` | `N : M` | 취약점이나 병목이 터지게 된 기술적 불씨(원인)를 추적 체인으로 연결합니다. |
| **`AFFECTS`** | `:Concept` | `:Component` | `N : M` | 이 결함이 유발되었을 때 내부 인프라에서 타격을 입거나 파괴되는 소프트웨어/물리 부품 레이어를 지정합니다. |
| **`MITIGATED_BY`** | `:Concept` | `:Mechanism` | `N : M` | 문제를 무력화하는 전천후 해결 기법 허브 노드로 화살표를 직결합니다. |
| **`HAS_EXAMPLE`** | `:Mechanism` | `:CodeExample` | `1 : N` | 개념적 완화책 하위에 기생하는 **버전별 구체적 실무 소스코드 위성 노드**들을 주렁주렁 매달아 줍니다. |
| **`TUNED_BY`** | `:Concept` | `:Property` | `N : M` | 결함 차단을 위해 미세 조율해야 하는 인프라/프레임워크 제어 파라미터를 연결합니다. |
| **`REFERENCES`** | `:Document` | `:Concept`<br>

<br>또는 `:RootCause` | `N : M` | **말단 가변 데이터선**. 사내 문서가 지식 마스터의 어떤 문제점과 조인되어 있는지 링크합니다. (하드 딜리트 대상) |

---

###  3. 이 명세도가 백엔드 개발자에게 주는 무기

이 뼈대 명세도가 100% 확정되어 있으면, 나중에 팀원들과 협업하거나 다음 단계로 코드를 확장할 때 엄청난 정합성 방어선이 생깁니다.

1. **화살표 방향 오류 원천 차단**:
Cypher 쿼리를 짤 때 `(c:Concept)-[:BELONGS_TO]->(d:Domain)` 방향인지 반대 방향인지 헷갈릴 일이 없습니다. 명세서에 화살표 출발지와 도착지가 엄격하게 고정되어 있으니까요.
2. **타입 불일치 런타임 에러 예방**:
FastAPI가 Neo4j에 데이터를 밀어 넣을 때, `created_at`은 무조건 정수형 타임스탬프(`Integer`)로, 프로퍼티의 값은 숫자가 섞여도 무조건 문자열(`String`)로 폰트를 맞추어 데이터 오염을 예방합니다.
3. **휴먼 인 루프 삭제 범위 명확화**:
`is_deprecated` 플래그는 오직 뼈대인 `:Concept` 노드에만 존재하며, 사용자가 강제 딜리트 시 끊어내야 할 말단 자산(`:CodeExample`, `:Document`)의 타깃 범위가 아키텍처적으로 완벽히 정돈됩니다.

```
(d1:Domain {name: 'security'}) 
         │
         │ [:BELONGS_TO]
         ▼
   ┌────────────────────────┐ 
   │ (c:Concept)            │ ◀─── [:REFERENCES] ─── (doc1:Document {id: ~})
   │ :Security :Performance │ 
   │ name: 'ConnPoolExhaust'│ ◀─── [:REFERENCES] ─── (doc2:Document {id: ~})
   └────────────────────────┘ 
         ▲
         │ [:BELONGS_TO]
         │
  (d2:Domain {name: 'performance'})
```
```
   ┌───────────────────────┐
   │ (doc1:Document)       │
   │ id: "~~"       │
   │ source: "confluence"  │
   └───────────────────────┘
               │
               │ [:REFERENCES]
               ▼
   ┌───────────────────────┐                 ┌───────────────────────┐
   │ (c:Concept)           │  [:BELONGS_TO]  │ (d1:Domain)           │
   │ :Security :Performance│ ◀────────────── │ name: 'security'      │
   │ name: 'ConnPoolExhaust'                 └───────────────────────┘
   └───────────────────────┘                     
               │                                 
               ├───────────────┬───────────────────────────────┐
               │               │                               │
               │ [:CAUSED_BY]  │ [:MITIGATED_BY]               │ [:TUNED_BY]
               ▼               ▼                               ▼
   ┌──────────────────┐  ┌──────────────────┐            ┌──────────────────┐
   │ (r:RootCause)    │  │ (m:Mechanism)    │            │ (p:Property)     │
   │ name: 'conn_leak'│  │ name: 'conn_pool'│            │ unq_key: 'p_max' │
   └──────────────────┘  └──────────────────┘            └──────────────────┘
               ▲                           │
               │                           │ [:HAS_EXAMPLE]
               │ [:REFERENCES]             ▼
   ┌───────────────────────┐     ┌──────────────────┐
   │ (doc2:Document)       │     │ (code:CodeExample)
   │ id: "GITHUB-PR-45"    │     │ unq_id: '...'    │ ◀── (말단 가변 영역: 하드 딜리트 대상)
   │ source: "github"      │     └──────────────────┘
   └───────────────────────┘```
---


// =========================================================================
// 🔒 1. 고유성 및 필수값 제어 제약 조건 (Constraints) 선언
// =========================================================================

-- ① 최상위 도메인 노드의 name 필드 유일성 및 필수 제약 조건
CREATE CONSTRAINT domain_name_unique IF NOT EXISTS
FOR (d:Domain) REQUIRE d.name IS UNIQUE;

-- ② 중앙 마스터 개념 노드의 name 필드 유일성 제약 조건 (가장 강력한 마스터 외래키 축)
CREATE CONSTRAINT concept_name_unique IF NOT EXISTS
FOR (c:Concept) REQUIRE c.name IS UNIQUE;

-- ③ 하위 완화 기법 노드의 name 필드 유일성 제약 조건
CREATE CONSTRAINT mechanism_name_unique IF NOT EXISTS
FOR (m:Mechanism) REQUIRE m.name IS UNIQUE;

-- ④ 타격 부품 노드의 name 필드 유일성 제약 조건
CREATE CONSTRAINT component_name_unique IF NOT EXISTS
FOR (x:Component) REQUIRE x.name IS UNIQUE;

-- ⑤ 근본 원인 노드의 name 필드 유일성 제약 조건
CREATE CONSTRAINT root_cause_name_unique IF NOT EXISTS
FOR (r:RootCause) REQUIRE r.name IS UNIQUE;

-- ⑥ [레이어 4] 버전별 코드 플레이북 위성 노드의 복합 복제 방지 유일성 제약 조건
CREATE CONSTRAINT code_example_unq_id_unique IF NOT EXISTS
FOR (code:CodeExample) REQUIRE code.unq_id IS UNIQUE;

-- ⑦ 미들웨어 / 환경 변수 설정 프로퍼티 노드의 유일성 제약 조건
CREATE CONSTRAINT property_unq_key_unique IF NOT EXISTS
FOR (p:Property) REQUIRE p.unq_key IS UNIQUE;

-- ⑧ 말단 가변 자산 사내 문서 노드의 유일성 제약 조건
CREATE CONSTRAINT document_id_unique IF NOT EXISTS
FOR (doc:Document) REQUIRE doc.id IS UNIQUE;


// =========================================================================
// ⚡ 2. 고속 융합 조회를 위한 고성능 물리 검색 인덱스 (Indexes) 선언
// =========================================================================

-- ① 도메인별 멀티 라벨 인덱스 강제 적용 (대시보드 필터용)
CREATE INDEX security_concept_idx IF NOT EXISTS FOR (c:Security) ON (c.name);
CREATE INDEX performance_concept_idx IF NOT EXISTS FOR (c:Performance) ON (c.name);

-- ② 소프트 딜리트 상태 고속 스캔용 인덱스
CREATE INDEX concept_active_status_idx IF NOT EXISTS FOR (c:Concept) ON (c.is_deprecated);

-- ③ [인간 통제용 완벽 방어벽] 동의어 및 한국어 번역명 전용 '풀텍스트 검색 인덱스'
-- AI나 인간이 정식 명칭이 아닌 오타나 동의어로 검색해도 마스터 노드를 정확히 유추해 냅니다.
CREATE FULLTEXT INDEX concept_aliases_fulltext_idx IF NOT EXISTS
FOR (c:Concept) ON EACH [c.name, c.aliases];


