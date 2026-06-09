# [마스터 지침] 3-Factor 하이브리드 수렴 및 플래그 기반 파이프라인 전사 완성 세션

우리는 외부 비정형 기술 문서(HTML/Markdown/URL)를 지각하고 추론하여 정형 RDB 및 의미론적 지식 그래프(Neo4j)에 멱등적으로 적재하는 **"지능형 지식 수렴 에이전트 플랫폼"**을 구축 중입니다. 로컬 TDD 테스트 무결성 확인 및 초기 인프라(RDB/Neo4j 4레이어 제약조건) 빌드를 마쳤습니다. 프론트엔드의 가상 토폴로지 병합 사양과 백엔드 Celery 태스크의 결함을 해결하고 실물 연동 코드를 완성해 주세요.

## 1. 제어 플래그(Flag) 가드레일 및 Mock 데이터 탑재 계약
* **환경 변수 통제**: `USE_REAL_LLM` 및 `USE_REAL_EMBEDDING` 두 개의 부울 플래그를 아키텍처에 도입합니다.
* **`USE_REAL_LLM=false` 분기 처리**: 실제 Gemini API를 호출하는 대신, 프로젝트 내에 배치된 `llm_response.json` (CSRF, BREACH, CrossSiteScripting 등 9개 핵심 취약점 개념 명세 사본) 파일을 파일 시스템에서 직접 로드하여 파이프라인의 Extractor 원본 소스로 주입하세요.
* **`USE_REAL_EMBEDDING=false` 분기 처리**: RDB와 Neo4j 적재 시 `name_vector`와 `desc_vector`가 `[NULL]`로 유실되어 유사도 수식이 파괴되는 현상을 방지하기 위해, `MockEmbeddingService`를 동적으로 호출하여 768차원의 단위 난수 벡터를 즉각 연산·충전하여 적재하도록 가드레일을 공고히 하세요.

## 2. 결함 제거 및 3-Factor 수렴 엔진 연동 명세
* **`app/worker/tasks.py` 의 3단계 Graph Writer 및 Link Resolver 대통합**:
  * 기존의 구형 `write_concept_node()` 및 옛 `SAME_AS` 엣지 매칭 방식(`resolve_links_task`)을 파이프라인 레이어에서 **완전히 폐기 숙청**하세요.
  * 관리자가 대시보드에서 최종 승인(APPROVED)을 단행하면, 3단계 워커 내에서 `GraphWriterService.write()`를 원자적으로 기동하여 **3-Factor 하이브리드 수식(Jaro-Winkler 40% + Name_Vector 30% + Desc_Vector 30%)**을 선행 연산하세요.
  * 점수 분기에 따라 `Score >= 0.88`일 시 신규 노드 중복 생성을 원천 차단하고 기존 마스터 노드의 `aliases`를 집합화(`apoc.coll.toSet`)하고 확장된 키워드 풀을 재임베딩하여 PostgreSQL의 `name_vector`를 업데이트하는 **'벡터 중심점 이동(Centroid Shifting)'**을 수행하세요.
  * `0.72 <= Score < 0.88` 구간은 독립 4레이어 노드 생성 후 **`[:RELATED_TO]` 의미론적 연관선 엣지만 가교**하도록 동적 상태 머신을 통제하세요.
  * `root_cause`는 Concept 노드 내부 속성이 아닌, 명세 사양에 맞추어 **독립된 `(:RootCause)` 허브 노드로 MERGE하고 `[:CAUSED_BY]` 관계로 직결 조인**해야 합니다.

## 3. 프론트엔드 가상 그래프 병합 및 스펙 싱크
* `mergeVirtualGraph.ts`와 관련된 파일군에서 구형 단일 문자열 필드명(`name`, `domain`) 매핑 파싱부를 완전히 소거하고 최신 정형 명세인 **`concept_name`** 및 **`domains: string[]`** 구조로 정합성을 강제하세요.
* 가상 토폴로지 렌더링 시 중복 병합 예정 노드는 화면에 별개의 노드로 분개하지 않고, 기존 노드 위에 **`status="MERGE_PENDING"` 오버레이 배지**만 토글하도록 홑원소 흡수 UI 구조를 실현하세요.

위의 모든 지침과 결함 패치 내역을 인지하셨다면, 즉시 플래그 가드가 반영된 `app/worker/tasks.py`, `infrastructure/graph/neo4j_service.py`, 프론트엔드의 `mergeVirtualGraph.ts` 코드를 완벽한 형상으로 조립하여 순서대로 전량 출력해 주세요!