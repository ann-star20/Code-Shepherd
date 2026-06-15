# 📑 [최종 마스터 지침서] 4-Layer 온톨로지 파이프라인 및 APOC 기반 원자적 머지 정책

본 문서는 지식 그래프 데이터의 파편화(Fragmentation)와 오염을 방지하고, 특정 프레임워크나 언어에 종속되지 않는 청정한 기술 지식 네트워크를 Neo4j에 원자적(Atomic)으로 적재하기 위한 백엔드 개발 지침이다.

---

## 🏗️ 1. 4-Layer 온톨로지 계층 헌법 (Schema 위상)

시스템에 적재되는 모든 지식은 무조건 아래의 **4-Layer 구조**로만 분류되어야 하며, 상위 레이어의 아이덴티티를 훼손하지 않는 종속 트리를 유지한다.

* **Layer 1: Concept (최상위 개념 노드)**
* **정체성**: 시스템의 본질적인 **'문제 현상'**, **'보안 취약점 공격'**, 또는 **'성능 저하 패턴'** 자체.
* **라벨 및 타입**: `:Concept` 라벨을 공유하며, `concept_type` 속성을 통해 `'concept'`(보안) 또는 `'antipattern'`(성능)으로 2원화하여 정형화한다.
* **특이사항**: 거대 밀집 노드(Supernode) 버그를 방지하기 위해 `Domain(Security, Performance)`은 독자 노드로 파지 않고, **Concept 노드의 내부 속성(`c.domains = ['security']`) 및 동적 라벨(`:Security`)로만 처리**한다.


* **Layer 2: Sub-Features (종속 상세 명사 레이어)**
* **정체성**: Layer 1 개념을 설명하고 보좌하는 기술 표준 규격 명사들.
* **노드 종류**: `Mechanism`(방어 기법/해결책), `RootCause`(근본 원인), `Component`(영향을 받는 컴포넌트)


* **Layer 3: CodeExample (구현부 레이어)**
* **정체성**: Layer 2의 `Mechanism` 규격을 실제로 돌아가게 만든 **특정 언어/프레임워크 종속적인 소스 코드 조각**.


* **Layer 4: YouTubeVideo (시각 자료 레이어)**
* **정체성**: 유저의 다각도 학습을 돕기 위해 Neo4j 그래프 맥락 데이터를 기반으로 Retrieval-Reranking하여 유효기간(TTL 7일) 단위로 캐싱하는 최신 추천 영상 노드.



---

## ✍️ 2. LLM 데이터 추출(Extractor) 프롬프트 가이드라인

공식 가이드나 How-To 문서의 특성상 해결책 중심(`Protection`)으로 기술되어 있더라도, LLM이 쫄지 않고 **배후의 원천 취약점(Concept)을 역산**하여 4-Layer 트리를 만들도록 강제한다. 또한 텍스트 유실 방지를 위해 문서는 최소 **30,000자(30k Chunk)** 단위로 넉넉하게 스캔한다.

```python
prompt = (
    "다음 문서 텍스트를 4-Layer 온톨로지 구조\n"
    "(Layer1 Concept[문제/취약점 중심] -> Layer2 Mechanism/RootCause/Component[종속 명사] -> "
    "Layer3 CodeExample[구현 코드] -> Layer4 YouTubeVideo[추천 영상]) 명세에 맞춰 JSON 배열로 추출하라.\n"
    f"- framework: {metadata.get('framework') or ctx.get('framework')}\n"
    f"- language: {metadata.get('language') or ctx.get('lang')}\n"
    f"- allowed_domains (이 중에서만 분류): [{domain_hint}]\n"
    "각 항목 필드: concept_name, concept_type, domains(allowed_domains 중에서 선택), description_ko, "
    "aliases, root_cause, affected_components, "
    "mechanism(mechanism_name, code_examples[{lang, framework, code, description}]).\n\n"
    "## [절대 엄수 제약 조건]\n"
    "1. 노이즈 차단: 레이아웃 텍스트, 메뉴, 배너 등 기술 본문과 무관한 문장은 description_ko에서 철저히 무시하라.\n"
    "2. 명명 규칙 강제: concept_name은 접두사/해시접미사를 배제한 순수 파스칼케이스(PascalCase) 명사여야 한다. "
    "올바른 예: CsrfAttack, MemoryLeak. 잘못된 예: CsrfProtection (방어책 명칭 금지).\n"
    "3. 타입 제한: 최상위 객체의 concept_type은 'concept'(보안 취약점 등 일반 개념) 또는 'antipattern' 중 하나로만 분류하라.\n"
    "4. 문제 중심 역산 추출: 입력 문서가 'CsrfProtection'이나 'csrf-csrf 패키지 설정'처럼 오직 방어 기법만 설명하고 있더라도, "
    "해당 기술이 막고자 하는 '본질적인 취약점 이름'(예: CSRF)을 역산하여 최상위 concept_name(Layer1)으로 추출하고, "
    "방어 코드는 그 아래의 mechanism 배열 내부로 격하시켜 위치시켜라.\n"
    "5. Null 처리: 정보가 없는 필드는 키를 누락시키지 말고 null 또는 빈 배열([])로 명시하라.\n\n"
    # ... 후략 (Few-Shot 예시 연동) ...
)

```

---

## 🧭 3. 백엔드 파이프라인의 3대 머지(Merge) 비즈니스 정책

AI가 추출한 원시 데이터를 맹신하여 DB에 바로 꽂으면 지식망이 오염된다. 백엔드(`pipeline.py`의 `write_graph_task`)는 **Resolver의 판정 결과와 데이터 명사 성격에 따라 다음 3가지 정책 분기**를 강제한다.

```
[신규 데이터 진입]
       │
       ├─► [상황 A] Resolver 판정 == "MERGE" (중복 개념 발견)
       │            └─► [정책 1] 기존 노드에 속성/별칭 병합 (merge_core_concept)
       │
       ├─► [상황 B] Resolver 판정 == "RELATED_TO" 이나, 이름에 "Protection/Defense" 포함 (오기출)
       │            └─► [정책 2] 최상위 격하 후 부모 밑으로 메커니즘 강제 이식 (transplant_as_mechanism)
       │
       └─► [상황 C] Pure New 데이터
                    └─► [정책 3] 순수 신규 Concept 노드 생성 및 하위 서브 레이어 종속 적재

```

* **[정책 1] Strict Core Merge (진짜 중복 처리)**
* *대상 케이스*: `CsrfAttack` ➔ 기존 `CSRF` 노드와 머지 판정 시.
* *행동*: 노드를 새로 파지 않고 기존 `target` 노드의 설명문을 보정하며, 두 데이터의 별칭 배열을 **중복 없는 집합(`apoc.coll.toSet`)으로 원자적 병합**한다.


* **[정책 2] Sub-Layer Displacement (방어책 격하 이식)**
* *대상 케이스*: 프롬프트를 우회하여 `CsrfProtection`이 최상위 Concept으로 오인 추출되었으나, Resolver가 기존 `CSRF` 노드와 연관성이 있다고 판정한 경우.
* *행동*: `CsrfProtection`을 L1 독립 노드로 승격시키지 않는다. 해당 노드의 본문을 스네이크케이스(`csrf_protection`) 형태의 L2 Mechanism 노드로 강제 강등 변환하여 진짜 주인인 `CSRF` 노드 밑으로 이식(`transplant`)한다.


* **[정책 3] L2 Sub-Layer Context-Aware Integration (종속 적재)**
* *대상 케이스*: `Mechanism`, `RootCause`, `Component` 등 하위 레이어 적재 시.
* *행동*: 이들은 전역 공간에 단독으로 존재할 수 없다. 무조건 확정된 L1 부모 노드가 매칭된 상태에서 **부모의 컨텍스트 락(Context Lock)을 쥐고 그 하위에 `[:MITIGATED_BY|CAUSED_BY|AFFECTS]` 엣지로 묶어서 머지**한다.



---

## 💾 4. APOC 기반 멱등성 Upsert Cypher 쿼리 명세

리포지토리 레이어(`neo4j_repo.py`)에서 원자적 트랜잭션(`begin_transaction`) 내에서 실행할 핵심 멱등성 쿼리 표준 가이드이다.

### 1) [정책 1 구현] 최상위 코어 개념 속성/알리아스 원자적 병합

```cypher
MATCH (c:Concept {name: $target_name})
SET c.description_ko = COALESCE($description_ko, c.description_ko),
    c.aliases        = apoc.coll.toSet(c.aliases + $aliases),
    c.domains        = apoc.coll.toSet(c.domains + $domains),
    c.updated_at     = datetime()
RETURN c.name AS name

```

### 2) [정책 2 구현] 격상 오기된 방어책 노드의 메커니즘 하향 이식 (Transplant)

```cypher
MATCH (parent:Concept {name: $target_name})
MERGE (m:Mechanism {name: $mechanism_name})
ON CREATE SET 
    m.description = $description,
    m.created_at = datetime()
MERGE (parent)-[:MITIGATED_BY]->(m)

```

### 3) [L3-L4 구현] 소스 코드 본문 해시 기반의 CodeExample 멱등성 Upsert

문자열 조합 키는 소스 코드 수정 시 캐시 락을 유발하므로, **코드 본문의 MD5 해시값(`code_hash`)을 유니크 식별자 키로 강제**한다.

```cypher
MERGE (ce:CodeExample {unq_id: $unq_id})
ON CREATE SET
    ce.lang              = $lang,
    ce.lang_version      = $lang_version,
    ce.framework         = $framework,
    ce.framework_version = $framework_version,
    ce.code              = $code,
    ce.description       = $description,
    ce.created_at        = datetime()
ON MATCH SET
    ce.description = $description,
    ce.updated_at  = datetime()
WITH ce
MATCH (m:Mechanism {name: $mechanism_name})
MERGE (m)-[:HAS_EXAMPLE]->(ce)

```

---

## 🚨 5. 데이터 무결성 검증 예외 처리 (Edge Case)

* **동의어 오염(Alias Pollution) 필터링**: `CSRF` 개념 노드의 `aliases` 배열에 `"CSRFProtection"` 같은 해결책 명사가 섞여 들어오는 것을 상시 모니터링하고 차단한다. 알리아스가 오염되면 Resolver가 다음 적재 시 멀쩡한 방어 문서를 통째로 코어 노드에 MERGE 시켜버리는 대참사가 난다.
* **Idempotent Code Hash**: 동일한 메커니즘 내에서 공백이나 주석 한 줄만 바뀌어도 `CodeExample` 노드가 중복 생성되는 것을 방지하기 위해, 파이썬 단에서 텍스트 공백 정형화 후 MD5 해싱을 수행하여 `unq_id`를 빌드한다.
