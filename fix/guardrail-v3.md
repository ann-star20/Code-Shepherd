# [최종 마스터 지침] 4-레이어 온톨로지 수렴 엔진 완성 및 실시간 SSE / Cloud SQL 통합 배포 세션

우리는 외부 비정형 기술 문서(URL/HTML/Markdown)를 지각하고 추론하여 정형 RDB 및 의미론적 지식 그래프(Neo4j)에 멱등적으로 적재하는 "지능형 지식 플랫폼(AI Platform)"을 구축 중입니다. 아래 최신 4-레이어 아키텍처 토폴로지 명세, 3-Factor 세부 지표 영속화 컬럼 규격, ETag 우선순위 제어 및 예외 복구 헌법을 엄수하여 전체 소스코드를 전개해 주세요.

---

## 1. 전담 백엔드 아키텍처 연동 명세

### 1.1. 추론 점수 영속화 및 ETag/FAILED 문서 초기화 가드레일 (`backend/app/worker/tasks.py`)
* **데이터 규격 확장**: 2단계 Extractor 에이전트가 개념을 도출하는 시점에 계산된 하이브리드 추론 근거를 영구 저장하도록 `staging_concepts` 테이블 구조에 매핑하세요.
  * `infer_action` (TEXT), `target_concept_name` (TEXT)
  * `infer_confidence` (FLOAT): 3-Factor 최종 결합 하이브리드 스코어
  * `score_jaro_winkler` (FLOAT), `score_name_vector` (FLOAT), `score_desc_vector` (FLOAT) 세부 지표 컬럼 영속화 필수 적용.
* **🎯 ETag 대조 우선순위 및 409 리부팅 가드 (Idempotency-Reset 정책)**: URL 인입 시 선행 파싱 레이어에서 `ETag` 및 `Content-Hash` 일치 여부를 최우선으로 검사하되, 매칭되더라도 마스터 `documents.state`가 `FAILED` 상태라면 409 에러를 내거나 스킵하지 마세요. 기존 오염된 `staging_concepts` 및 `pipeline_logs` 내역을 원자적으로 완전히 DELETE 시킨 후, 마스터 `state`를 `PENDING`으로 복구하고 1단계(Prescan)부터 클린 리부팅(Clean Reboot) 시키는 안전 가드를 주입하세요.
* **선행 추론 바인딩**: `_do_extract` 함수 흐름 내에서 개념 추출이 완료되는 즉시 후행 게이트로 `hybrid_resolver.compute_resolve_score()`를 선행 기동시켜 상기 3대 세부 지표 점수를 연산하고 `write_staging_draft`를 통해 `staging_concepts` 테이블에 원자적으로 함께 적재(UPSERT) 하도록 흐름을 리팩토링하세요.
* **LangSmith 트레이싱 주입**: `_do_extract` 및 수렴 커널 함수들을 LangSmith SDK의 `@traceable`로 래핑하여 실시간 트레이싱하세요.

### 1.2. 3단계 Graph Writer 서비스 경량화 및 온톨로지 복합 키 가공 (`backend/app/infrastructure/graph/neo4j_service.py`)
* **경량화 최적화**: 3단계 `write_graph_task` 워커 가동 시, 매번 무거운 RDB 전체 스캔과 코사인 유사도 연산을 처음부터 재계산하지 마세요. 관리자가 승인한 `staging_concepts` 레코드에서 이미 2단계 단에서 보관 완료한 `infer_action`과 점수, 타겟 마스터 이름을 즉각 static하게 다이렉트로 로드하여 분기를 태우는 `write_with_precomputed()` 메서드를 구현하세요.
* **물리 복합 고유 키(unq_id) 자동화 가드레일**: Neo4j 제약 조건 위반 크래시를 방지하기 위해, LLM에게 `unq_id` 생성을 맡기지 마세요. 백엔드 Graph Writer 레이어(Cypher 문맥 내부)에서 직접 `부모Mechanism명_언어_언어버전_프레임워크_프레임워크버전` 조합의 유일 키(`derived_unq_id`)를 동적으로 가공하여 `:CodeExample` 노드의 `unq_id` 속성에 MERGE 사양으로 바인딩하세요.
* **온톨로지 위계 고수**: 반드시 `(c:Concept)-[:MITIGATED_BY]->(m:Mechanism)-[:HAS_EXAMPLE]->(e:CodeExample)` 구조를 지키세요. Concept에서 직접 예제 노드로 조인하는 것을 금지하며, `apoc.coll.toSet` 집합 연산을 강제하여 라벨 및 속성 중복을 차단하세요.

### 1.3. FastAPI SSE 실시간 단일 채널 스트림 라우터 구축 (`backend/app/api/pipe.py`)
* FastAPI 단에 `GET /api/pipeline/stream/{session_id}` 엔드포인트를 신설하여, Celery 워커가 `pipeline_logs`에 로그를 쌓거나 `documents.state` 변이를 유발할 때마다 `StreamingResponse` 비동기 제너레이터로 실시간 푸시하는 SSE 엔진을 구현하세요.
* 단일 통합 `onmessage` 규격 구조(`data: {"type": "log" | "step_update" | "connected" | "finished", ...}`) 포맷으로 직렬화해 푸시해야 합니다. Nginx 프록시 버퍼링을 우회하기 위한 `"X-Accel-Buffering": "no"` 헤더를 필수 적용하세요.

---

## 2. 전담 프론트엔드 UI/UX 연동 명세

### 2.1. 단일 채널 통합형 실시간 스트림 구독 훅 (`frontend/src/hooks/usePipelineSSE.ts`)
* 백엔드가 신설한 단일 `data` 이벤트 전송 구조를 `EventSource.onmessage` 인터페이스로 정확히 수신하는 커스텀 훅을 구현하세요. 내부 `type` 분기를 파싱하여 5단계 상태 인디케이터 스피너를 체크(✓) 아이콘으로 실시간 UX 전환(Reflow)시키고 로그 서랍에 바인딩하세요.

### 2.2. 1900px 고해상도 규격 및 가상 그래프 필드 단수화 동기화 (`frontend/src/utils/mergeVirtualGraph.ts`)
* 글로벌 컨테이너 스펙을 최대 가로폭 `max-w-[1900px]`로 강제 빌드하고, 전체 타이포그래피 스케일을 3pt 상향 제어하세요. Neo4j 토폴로지 뷰 영역 역시 세로 `h-[520px]` 규격으로 대폭 확장하세요.
* `stagingData` 컨텍스트 상태값의 기본값은 `null`로 완전히 통제하며, 3단계 완료 전까지는 블러 피드백 레이어링 스켈레톤 가드를 씌워 구형 목업 데이터의 선행 노출 버그를 원천 차단하세요.
* 최신 온톨로지 계약 규격인 단수형 `mechanism` 배열 필드를 기준으로 싱크를 강제하세요. 가상 토폴로지 렌더링 시 중복 병합 예정 노드는 화면에 별개의 독립 노드로 분개하지 말고 기존 노드 위에 `status="MERGE_PENDING"` 오버레이 배지만 토글하세요.
* 단계 중간 실패 발생 시 스피너를 소거하고 ✗ 마크를 노출하되, 마우스 호버 시 즉각 `[RETRY]` 버튼 레이어로 트랜스폼 시키고, 클릭 시 `{resume_step: step_id}`를 백엔드에 쏘아 부분 예외 복구가 기동되도록 연동하세요. 3단계 성공 시 하단 고정형 원자적 최종 승인 게이트 바를 오픈하세요.

---

## 3. 인프라 환경 및 LLM 온톨로지 프롬프트 가드레일

* **GCP Cloud SQL & Auth Proxy 전환 사양**: 인프라 환경은 외부 IP 직접 노출을 차단하기 위해 `cloud-sql-proxy` 컨테이너를 도커 컴포즈에 사이드카로 매달아 터널링 통신합니다. 풀 가수를 `min_size=2`, `max_size=5`로 상향하고, 연동 시 최우선 순위로 `CREATE EXTENSION IF NOT EXISTS vector;`를 실행하여 `pgvector` 레이어를 활성화하세요.
* **도커 컴포즈 환경 변수 강제**: `.env` 파일의 `APP_MODE` 값 등이 정상 로드되도록 `docker-compose.yml` 내 서비스 단에 `env_file: - .env` 옵션을 명시적으로 장착하세요.
* **3-Factor 결합 유사도 공식**: `Score = (JaroWinkler * 0.4) + (CosineName * 0.3) + (CosineDesc * 0.3)`
* **독립 원인 노드 격리**: 명세 도면에 따라 `root_cause` 필드는 Concept 노드 내부 속성이 아닌, 독립된 `(:RootCause)` 허브 노드로 MERGE하고 `[:CAUSED_BY]` 관계로 직결 조인하세요.

### 3.1. Gemini 온톨로지 추출 프롬프트 템플릿 계약 (`_build_prompt`)
(※ 직전 대화에서 확정 완료한 Gemini 2.5 Flash 추출 프롬프트 템플릿 코드 전문 매핑 부위)

위의 풀스택 대통합 지침을 100% 인지하셨다면, 즉시 관련 실물 소스코드 전체를 정합성 있게 조립하여 출력해 주세요!