# [마스터 지침] 3-Factor 하이브리드 수렴 엔진 완성 및 LangSmith LLMOps / 실시간 SSE 스트림 통합 세션

우리는 비정형 기술 문서를 파싱하여 3-Factor 하이브리드 수렴 헌법에 따라 PostgreSQL과 Neo4j에 멱등 적재하는 비동기 Celery 파이프라인 엔진 완성 및 로컬 유닛 테스트 하네스 검증(94+ passed GREEN)을 완료했습니다. 이제 3-Factor 추론 근거를 RDB 스테이징에 박제하고, 실제 상용 Gemini API 전환을 위한 LangSmith 관제 레이어 및 웹소켓을 대체하는 FastAPI 실시간 SSE 로그 스트림 관제판을 전사적으로 구축해 주세요.

---

## 1. 전담 백엔드 아키텍처 연동 명세

### 1.1. 추론 점수 영속화 및 2단계 Extractor 가동 (`backend/app/worker/tasks.py`)

* **데이터 규격 확장**: 2단계 Extractor 에이전트가 개념을 도출하는 시점에 계산된 하이브리드 추론 근거를 영구 저장하도록 `staging_concepts` 테이블 구조와 매핑하세요.
* `infer_action` (TEXT): 3-Factor 엔진이 판정한 추천 액션 플래그 (`'MERGE'` | `'RELATED_TO'` | `'NEW'`)
* `infer_score` (FLOAT): 최종 하이브리드 가중치 합산 점수
* `target_concept_name` (TEXT): `MERGE` 혹은 `RELATED_TO` 분기 발생 시 조인 타겟이 되는 기존 PostgreSQL 마스터 테이블의 `concept_name`


* **선행 추론 바인딩**: `_do_extract` 함수 흐름 내에서 개념 추출이 완료되는 즉시, 후행 게이트로 `hybrid_resolver.compute_resolve_score()`를 선행 기동시켜 메모리 단에서 3대 가중치 점수를 계산하세요. 계산된 `ResolveResult`를 `write_staging_draft`를 통해 `staging_concepts` 테이블에 원자적으로 함께 적재(UPSERT) 하도록 흐름을 완비하세요.
* **LangSmith 트레이싱 주입**: `_do_extract` 및 수렴 커널 함수들을 LangSmith SDK의 `@traceable`로 래핑하여 프롬프트 토큰 소모량과 추론 지연 시간을 실시간 트레이싱하세요.

### 1.2. 3단계 Graph Writer 서비스 경량화 최적화 (`backend/app/infrastructure/graph/neo4j_service.py`)

* 3단계 `write_graph_task` 워커 가동 시, 매번 무거운 RDB 전체 스캔과 코사인 유사도 연산을 처음부터 무식하게 재계산하지 마세요.
* **경량화 최적화**: 관리자가 승인한 `staging_concepts` 레코드에서 이미 2단계 단에서 보관 완료한 `infer_action`과 점수, 타겟 마스터 이름을 즉각 static하게 다이렉트로 로드하여 분기를 태우는 **`write_with_precomputed()`** 메서드를 구현하세요.
* 점수가 로드되면 `_do_merge`를 통한 PostgreSQL `name_vector` 공간 좌표 업데이트(**Centroid Shifting**) 및 Neo4j `aliases` 배열 집합 동기화만 영속화 처리하세요.

### 1.3. FastAPI SSE(Server-Sent Events) 실시간 스트림 라우터 구축 (`backend/app/api/pipeline.py`)

* 기존의 2초 간격의 무거운 프론트엔드 RDB 폴링 방식을 완전히 소거합니다.
* FastAPI 단에 **`GET /api/pipeline/stream/{session_id}`** 엔드포인트를 신설하여, Celery 워커가 `pipeline_logs`에 로그를 쌓거나 `documents.state` 변이를 유발할 때마다 `StreamingResponse` 비동기 제너레이터를 통해 실시간으로 이벤트를 푸시(Push)하는 SSE 스트림 엔진을 구현하세요. 헌법에 따라 `data: {...}` 표준 데이터 프로토콜 포맷을 강제해야 합니다.

### 1.4. 관리자 HITL 피드백 환류 게이트 구축

* 관리자가 HITL 대시보드에서 에이전트의 판단을 뒤집거나 내용을 수정하여 거부(`diff`)가 발생할 때, 해당 수동 수정 이력을 `client.create_feedback()` 인스턴스를 통해 LangSmith 피드백 저장소에 영속화하는 피드백 환류 코드를 백엔드 승인 게이트 API 엔드포인트에 주입하세요.

---

## 2. 전담 프론트엔드 UI/UX 연동 명세

### 2.1. 실시간 스트림 구독 훅 (`frontend/src/hooks/usePipelineSSE.ts`) 구현

* 백엔드가 신설한 실시간 스트리밍 엔드포인트 URL을 `EventSource` 인터페이스로 정확히 리스닝하는 커스텀 훅을 구현하세요.
* `CRAWLING` ➔ `EXTRACTED` ➔ `COMMITTED` 상태 변이 패킷 수신 즉시, 메인 대시보드에 연동된 5단계 상태 인디케이터 스피너를 체크(✓) 아이콘으로 실시간 리플로우(Reflow) 시키고, 터미널 로그 서랍에 실시간 이벤트 패킷을 끊김 없이 스트리밍(Streaming)해 내는 UX 가드를 완성하세요.

### 2.2. 가상 그래프 병합 엔진 및 API 데이터 구조 매핑 (`frontend/src/utils/mergeVirtualGraph.ts`)

* 구형 메타 필드명(`name`, `domain`) 매핑 파싱부를 완전히 소거하고 최신 백엔드 표준 명세인 **`concept_name`** 및 **`domains: string[]`** 문자열 배열 필드를 기준으로 싱크를 강제하세요.
* 가상 토폴로지 렌더링 시 중복 병합 예정 노드는 화면에 별개의 독립 노드로 분개하지 마세요. 기존 노드 위에 **`status="MERGE_PENDING"` 오버레이 배지**만 토글하도록 홑원소 흡수 UI 구조를 실현하고, 회색 지대 데이터에 한해서만 독립 점선 노드 파생 및 `type: "RELATED_TO_CANDIDATE"` 가교 엣지를 생성하도록 렌더링을 일치시키세요.

---

## 3. 인프라 환경 제어 플래그 및 물리 규칙 (참고용)

* **환경 변수 통제**: `USE_REAL_LLM` 및 `USE_REAL_EMBEDDING` 두 개의 부울 플래그 가드를 올린 모킹 상태에서 외부 구글 API 비용 지연 없이 분당 수천 건의 동시성 및 DB 데드락 검증 부하 테스트가 가능한 상태를 완벽하게 고수하세요.
* `USE_REAL_LLM=false`: `llm_response.json` (CSRF, BREACH, XSS 등 9개 핵심 취약점 사본 파일) 가동.
* `USE_REAL_EMBEDDING=false`: `MockEmbeddingService` 난수 벡터 엔진 가동 (PostgreSQL 벡터 NULL 유실 차단).


* **3-Factor 결합 유사도 공식**: `Score = (JaroWinkler * 0.4) + (CosineName * 0.3) + (CosineDesc * 0.3)`
* **독립 원인 노드 격리**: 명세 도면에 따라 `root_cause` 필드는 Concept 노드 내부 속성이 아닌, 독립된 **`(:RootCause)` 허브 노드로 MERGE하고 `[:CAUSED_BY]` 관계로 직결 조인**해야 합니다. 모든 그래프 트랜잭션 문맥에는 `apoc.coll.toSet` 중복 제거 가드레일을 누적 적용하세요.
