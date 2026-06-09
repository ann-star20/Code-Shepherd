# [마스터 지침] 4-레이어 지식 그래프 수렴 자동화 파이프라인 서비스 레이어 구축 세션

우리는 외부 비정형 기술 문서(HTML/Markdown/URL)를 지각하고 추론하여 정형 RDB 및 의미론적 지식 그래프(Neo4j)에 멱등적으로 적재하는 **"지능형 지식 수렴 에이전트 플랫폼"**을 구축 중입니다. 파편화되어 있던 `schema.sql`과 마이그레이션 스크립트는 완전히 단일 대통합 청소가 완료되었습니다. 다음 요건을 만족하는 서비스 코드를 전사적으로 완성해 주세요.

## 1. 전담 구현 과제 명세
1. **`infrastructure/graph/neo4j_service.py` 신규 생성**:
   * `GraphWriterService` 아키텍처 레이어를 구축합니다.
   * `hybrid_resolver.py`를 통해 연산된 3-Factor 결합 유사도 점수를 바탕으로 3대 분기 처리를 드라이브합니다.
   * **[MERGE 분기 시 Centroid Shifting 강제]**: `Score >= 0.88`인 경우, 신규 노드 생성을 차단하고 기존 마스터 노드로 수렴합니다. 이때 인입된 새로운 개념명을 기존 `aliases` 배열에 결합하고, 확장된 '이름+동의어' 키워드 풀을 `MockEmbeddingService`로 재임베딩하여 PostgreSQL의 `name_vector` 컬럼을 갱신 업데이트하는 '벡터 중심점 이동'을 원자적으로 수행하세요. Neo4j 역시 `apoc.coll.toSet`으로 aliases를 집합 동기화합니다.
   * **[RELATED_TO 및 NEW 분기]**: `0.72 <= Score < 0.88`일 시 독립 노드로 4레이어를 빌드한 후 `[:RELATED_TO]` 관계선을 가교하며, 미달 시 완전한 독자 노드로 영속화합니다. PRD 사양에 따라 `root_cause`는 속성이 아닌 독립된 `(:RootCause)` 노드로 MERGE하고 `[:CAUSED_BY]`로 연결합니다.

2. **`usecases/run_pipeline.py` 제어 루프 통합**:
   * 추출(Extractor) 완료된 후행 단계에 `run_link_resolve()` 파이프라인 게이트를 바인딩하여, 위에서 구현한 `GraphWriterService.write()`가 격리된 스테이징 데이터를 순회하며 지능적으로 중복을 정화하고 커밋하도록 제어 흐름을 리팩토링하세요.

3. **산출물 형상 관리 자동 갱신**:
   * 본 작업 완료와 동시에 `project_hybrid_resolver.md`(완료 명세 기록), `feedback_seed_alias_strategy.md`(PascalCase 동의어 보강 전략 수립), `MEMORY.md` 자산을 최신 상태로 동기화 갱신해 주세요.

## 2. 통합 데이터베이스 인프라 구조 계약 (참고용)
* **PostgreSQL (`schema.sql`)**: `concepts` 테이블에 `name_vector vector(768)` 및 `desc_vector vector(768)` 두 컬럼과 각각의 HNSW 인덱스가 구성되어 있으며, 소프트 딜리트용 `is_deprecated` 및 `root_cause TEXT` 컬럼이 완전 통합되어 있습니다.
* **Neo4j (`init_db.cypher`)**: `RootCause`는 독립된 `(:RootCause)` 노드로 MERGE하고 `[:CAUSED_BY]` 엣지 관계로 직결 조인합니다. 모든 병합 적재문에는 `apoc.coll.toSet` 집합 연산을 강제하여 라벨 및 속성 중복을 차단합니다.
* **`security_concepts.json` (Seed)**: DB의 Exact Match 가드레일이 작동하도록, `CSRF`나 `XSS` 같은 시드 노드의 `aliases` 배열에 `["CrossSiteRequestForgery", "CSRFAttack", "CrossSiteScripting"]` 등 파스칼케이스 풀네임이 선제 매핑되어 있습니다.

## 3. 동적 난수 모킹 엔진 (`MockEmbeddingService`)
* 개발/테스트 환경(`APP_MODE=development`)에서 API 비용과 지연 없이 하이브리드 엔진을 무한 테스트하기 위해, API 호출 없이 텍스트의 해시값을 시드로 삼아 항상 멱등적인 768차원 균등 분포 난수 벡터(-1.0 ~ 1.0)를 생성하고 L2 정규화(Normalization)를 수행하는 모킹 서비스를 적극 활용하세요.

위의 지침을 100% 인지하셨다면, 즉시 `neo4j_service.py`와 `run_pipeline.py` 수정본 및 관련 마크다운 형상 관리 문서의 업데이트 내용을 거침없이 출력해 주세요!