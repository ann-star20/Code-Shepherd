# 💡 온톨로지 Upsert/Append 멱등성 지침서

## 1. 노드 식별 기준 및 멱등성 보장 키 (Unique Keys)

그래프가 끊기지 않고 기존 노드에 연결(Append)되거나 갱신(Overwrite)되려면, 모든 엔티티마다 **비즈니스 유니크 키**가 정의되어야 합니다.

| 노드 레이블 (Label) | 고유 식별 기준 (Unique Key) | 설명 |
| --- | --- | --- |
| **Concept** | `concept_name` | 개념의 영문 식별자 (예: `ModulePreloading`) |
| **Mechanism** | `mechanism_name` | 구현 메커니즘명 (예: `react_dom_preload_module_api`) |
| **CodeExample** | `hash(code)` 또는<br>

<br>`[lang + framework + code_summary_hash]` | 코드 본문은 공백이나 스타일에 민감하므로, 코드 내용 자체의 해시값 또는 언어/프레임워크 정보와 결합한 고유 식별자가 필요합니다. |
| **ConfigProperty** | `[Concept.concept_name + key]` | 컨피그 속성은 독립적이기보다 특정 Concept 내에서 유일해야 합니다. |

---

## 2. 속성값 및 연관관계 병합 전략 (Overwrite vs Append)

기존에 노드나 관계가 존재할 때, 어떤 필드를 덮어쓰고 어떤 필드를 누적(Append)할지 결정하는 규칙입니다.

### ① 단일 값 속성 (Overwrite 전략)

개념의 설명이나 심각도 등, **최신 정보가 기존 정보를 대체해야 하는 필드**들입니다. 값이 `null`로 들어온 경우에는 기존 값을 보존할지, 비울지(`null` 처리) 정책을 세워야 합니다. 보통은 `null`이 아닐 때만 덮어쓰는 방식을 권장합니다.

* **대상 필드:** `concept_type`, `description_ko`, `cwe_id`, `owasp_id`, `severity`, `root_cause`
* **동작:** `ON MATCH SET node.description_ko = input.description_ko`

### ② 리스트/배열 속성 (Append & Deduplicate 전략)

별칭, 도메인, 영향받는 컴포넌트 등 **정보가 누적될수록 풍부해지는 필드**들입니다. 단순 추가 시 중복이 발생하므로 **Set(집합) 연산**을 통해 중으로 들어온 값은 제거하고 합집합을 만들어야 합니다.

* **대상 필드:** `aliases`, `domains`, `affected_components`
* **동작:** `ON MATCH SET node.aliases = apoc.coll.toSet(node.aliases + input.aliases)` (기존 배열에 새 배열을 더한 후 중복 제거)

### ③ 하위 엔티티 연관관계 (Conditional Append 전략)

질문하신 `Mechanism`과 `CodeExample`을 `lang`, `framework`,`lang_version`,`framework_version`에 따라 유기적으로 추가하는 핵심 규칙입니다.

* **Concept ➔ Mechanism 관계 (`:HAS_MECHANISM`)**
* `mechanism_name`이 이미 존재하면 **기존 Mechanism 노드를 재사용**하고 관계만 유지합니다. (끊기지 않는 핵심)


* **Mechanism ➔ CodeExample 관계 (`:HAS_EXAMPLE`)**
* 코드 예제는 언어, 프레임워크, 버전별로 다르게 관리되어야 합니다. 따라서 고유 식별자로 매칭하여 이미 있는 코드가 아니라면 **새로운 CodeExample 노드를 생성하여 Mechanism 노드에 연결(Append)** 합니다.



---

## 3. Cypher 쿼리로 보는 멱등성 구현 예시 (Neo4j 기준)

Cypher의 `MERGE` 구문과 `ON CREATE`, `ON MATCH`를 사용하면 완벽한 멱등성(몇 번을 실행해도 결과가 동일함)을 보장하는 그래프 인입 프로세스를 만들 수 있습니다.

```cypher
// 1. 기본 Concept 노드 생성 및 속성 Upsert (멱등성 확보)
MERGE (c:Concept {name: $input.concept_name})
ON CREATE SET 
    c.concept_type = $input.concept_type,
    c.description_ko = $input.description_ko,
    c.aliases = $input.aliases,
    c.domains = $input.domains,
    c.affected_components = $input.affected_components,
    c.created_at = timestamp()
ON MATCH SET 
    c.description_ko = COALESCE($input.description_ko, c.description_ko),
    c.concept_type = COALESCE($input.concept_type, c.concept_type),
    c.aliases = apoc.coll.toSet(c.aliases + $input.aliases),
    c.domains = apoc.coll.toSet(c.domains + $input.domains),
    c.affected_components = apoc.coll.toSet(c.affected_components + $input.affected_components),
    c.updated_at = timestamp()

// 🔥 [핵심 추가] domains 배열을 추출하여 노드에 레이블로 동적 추가 (Append)
// 입력된 도메인 단어들의 첫 글자를 대문자로 변환하여 레이블 형식을 맞춥니다.
WITH c, $input
UNWIND c.domains AS domainAttr
WITH c, $input, apoc.text.capitalize(domainAttr) AS labelName

// apoc.create.addLabels는 이미 존재하는 레이블이면 중복 추가하지 않고 안전하게 패스합니다.
CALL apoc.create.addLabels(c, [labelName]) YIELD node

// 2. 하위 Mechanism 처리 파이프라인 지속
WITH node AS c, $input
WITH c, $input.mechanism AS mechanisms
UNWIND mechanisms AS mech

MERGE (m:Mechanism {name: mech.mechanism_name})
ON CREATE SET m.created_at = timestamp()

// Concept과 Mechanism 연관관계 생성
MERGE (c)-[:HAS_MECHANISM]->(m)

// 3. CodeExample 처리 (하위 버전/환경별 Append)
WITH m, mech.code_examples AS examples
UNWIND examples AS ex

MERGE (e:CodeExample {
    example_id: m.name + "_" + COALESCE(ex.lang, "any") + "_" + COALESCE(ex.framework, "any") + "_" + apoc.util.md5([ex.code])
})
ON CREATE SET 
    e.code = ex.code,
    e.lang = ex.lang,
    e.lang_version = ex.lang_version,
    e.framework = ex.framework,
    e.framework_version = ex.framework_version,
    e.description = ex.description,
    e.created_at = timestamp()
ON MATCH SET
    e.lang_version = COALESCE(ex.lang_version, e.lang_version),
    e.framework_version = COALESCE(ex.framework_version, e.framework_version),
    e.description = COALESCE(ex.description, e.description),
    e.updated_at = timestamp()

MERGE (m)-[:HAS_EXAMPLE]->(e)

```

---

## 4. 요약 가이드라인 (개발용 체크리스트)

1. **그래프가 분리되는 원인 차단:** 데이터가 들어올 때 `CREATE` 대신 **`MERGE` (Upsert)** 를 사용하고, 매칭 기준을 반드시 `concept_name` 또는 `mechanism_name` 같은 **고유 식별 문자열**로 잡아야 합니다. 내부 생성 내부 ID(예: `elementId`)를 매칭 기준으로 쓰면 매번 새로운 노드가 생겨 그래프가 끊어집니다.
2. **외래 키 연동 지양, 노드 기반 연결:** JSON 계층 구조를 풀어서 그래프에 넣을 때, 부모 노드의 고유 키를 가지고 `MATCH`를 먼저 수행한 뒤 자식 노드를 붙여 나가는 파이프라인 구조를 잡으세요.
3. **새 정보 추가 규칙:** `lang`, `framework`, `lang_version`,`framework_version`이 다른 새로운 `code_example`이 들어오면 고유 식별 규칙(`lang` + `framework` + `hash`)에 의해 기존 코드와 매칭되지 않으므로, 자연스럽게 **새로운 노드로 생성되어 기존 Mechanism 노드에 Append** 됩니다.