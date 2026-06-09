# [마스터 지침] 4-레이어 지식 그래프 수렴 자동화 파이프라인 전사 빌드 세션

우리는 외부 비정형 기술 문서(HTML/Markdown/URL)를 지각하고 추론하여 정형 RDB 및 의미론적 지식 그래프(Neo4j)에 멱등적으로 적재하는 **"지능형 지식 플랫폼(AI Platform)"**을 구축 중입니다. 과거의 논의를 기반으로 아래 핵심 헌법을 엄수하여 백엔드 파이프라인 코드를 전개해 주세요.

## 1. 3번 Link Resolver Agent: 하이브리드 중복 병합 엔진 (SAME_AS 폐기)
* **목적**: 파편화된 동의어 노드가 생성되는 것을 방지합니다. 구형 `SAME_AS` 관계선은 완전 폐기합니다.
* **유사도 공식 (3-Factor 선형 결합)**: 
`Hybrid Score = (Jaro-Winkler * 0.4) + (Cosine(Name_Vector) * 0.3) + (Cosine(Desc_Vector) * 0.3)`
  1. **Jaro-Winkler (Lexical 40%)**: 대소문자/공백을 무시하고 타겟 이름과 시드 노드의 `aliases` 배열을 1:1로 비교해 최고점을 추출합니다.
  2. **Name_Vector (Semantic 1, 30%)**: 개념 이름과 `aliases` 배열을 쉼표로 이어 붙인 '키워드 풀(Keyword Pool)' 텍스트를 임베딩하여 코사인 유사도를 구합니다. (동의어 융합 문맥 파악)
  3. **Desc_Vector (Semantic 2, 30%)**: `description_ko` 요약 설명 벡터의 코사인 유사도를 구합니다.
* **액션 분기**:
  1. `Score >= 0.88`: 신규 노드를 만들지 않고 기존 노드로 병합(Deduplication)합니다. 이때 기존 `aliases` 배열에 새 이름이 없다면 추가하고, 확장된 키워드 풀(이름+동의어들)을 **다시 임베딩(Re-embedding)하여 PostgreSQL의 `name_vector`를 새로운 벡터로 UPDATE** 하는 '벡터 중심점 이동(Centroid Shifting)' 로직을 반드시 포함하세요.
  
  2. `0.72 <= Score < 0.88`: 두 노드 사이에 `[:RELATED_TO]` 엣지만 조인.
  3. `Score < 0.72`: 완전 신규 마스터 노드 생성.

## 2. 통합 데이터베이스 인프라 구조 계약
* **PostgreSQL (`schema.sql`)**: `concepts` 테이블에 `name_vector vector(768)` 및 `desc_vector vector(768)` 두 컬럼과 각각의 HNSW 인덱스가 구성되어 있으며, 소프트 딜리트용 `is_deprecated` 및 `root_cause TEXT` 컬럼이 완전 통합되어 있습니다. 
* **Neo4j (`init_db.cypher`)**: `RootCause`는 Concept 노드의 속성으로 넣지 않고, 별도의 `(:RootCause)` 노드를 MERGE하고 `[:CAUSED_BY]` 엣지 관계로 직결 조인합니다. 모든 병합 적재문에는 `apoc.coll.toSet` 집합 연산을 강제하여 라벨 및 속성 중복을 차단합니다.
* **`security_concepts.json` (Seed)**: DB의 Exact Match 가드레일이 작동하도록, `CSRF`나 `XSS` 같은 시드 노드의 `aliases` 배열에 `["CrossSiteRequestForgery", "CSRFAttack", "CrossSiteScripting"]` 등 파스칼케이스 풀네임이 선제 매핑되어 있습니다.

## 3. 동적 난수 모킹 엔진 (`MockEmbeddingService`) 및 전략적 Mock 데이터
* 개발/테스트 환경(`APP_MODE=development`)에서 API 비용과 지연 없이 하이브리드 엔진을 무한 테스트하기 위해, API 호출 없이 텍스트의 해시값을 시드로 삼아 항상 멱등적인 768차원 균등 분포 난수 벡터(-1.0 ~ 1.0)를 생성하고 L2 정규화(Normalization)를 수행하는 모킹 서비스를 구현하여 주입하세요.
* `MockClient` 가 배출하는 데이터 중 하나는 의도적으로 `concept_name: "CrossSiteRequestForgery"`, `cwe_id: "CWE-352"` 로 세팅하여 기존 시드 노드(`CSRF`)로 완벽히 병합 및 벡터 중심점 이동이 발생하는지 TDD 검증이 가능하도록 설계합니다.

## 4. Neo4j 멱등성 자석 적재 (`neo4j_repo.py`)
* 동일 노드에 다중 라벨이 중복 누적되거나(`["security", "security"]`), 동의어가 중복되는 런타임 버그를 차단하기 위해 모든 Cypher 병합 쿼리에 **APOC 라이브러리의 중복 제거 함수(`apoc.coll.toSet`)**를 반드시 강제 적용하세요.


## 5. 프론트엔드 비동기 UX 가드 및 렌더링 계약
* 무거운 로그 콘솔을 소거하고 파이프라인 단계(1~5)별 **스피너 ➔ 체크(✓) 비동기 전환** 및 실시간 `subText` 롤링을 적용합니다.
* `mechanism`의 `code_examples` 배열이 빈 배열(`length === 0`)일 경우 무한 '로딩 중' 스켈레톤을 탈출하고 "코드 예제 미등록" 안내 텍스트를 즉각 표출하는 예외 가드를 인스펙터 패널에 적용합니다.

## 6. 스키마 누락 필드 및 RootCause 전개 규칙 보완
* PostgreSQL `concepts` 테이블에 `is_deprecated BOOLEAN DEFAULT false`와 `root_cause TEXT` 컬럼이 반드시 포함되게 해주세요.
* Neo4j 적재 시 `root_cause`를 Concept 노드의 속성으로 넣지 마세요. PRD에 명시된 대로 별도의 `(:RootCause)` 노드를 MERGE하고 `[:CAUSED_BY]` 엣지로 조인해야 합니다
