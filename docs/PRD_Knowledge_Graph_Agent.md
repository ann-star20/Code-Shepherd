
## 4. 비기능 요구사항 (Non-Functional Requirements)

- **확장성(Scalability)**: 보안 도메인에 국한하지 않고 Tech Issue & Solution KG로 확장 가능하도록 `Domain` 노드 기반 다도메인 구조 설계.
- **성능(Performance)**: Neo4j Indexing (`name`, `cwe_id`, `aliases`) 및 PostgreSQL 관계 최적화.
- **멱등성(Idempotency)**: 동일 URL 반복 요청 시 LLM 토큰 중복 소모 방지를 위한 캐싱 레이어 확보.
- **감사 추적(Auditability)**: 파이프라인 각 단계의 입/출력 스냅샷을 PostgreSQL에 기록하여 추출 결과 검증 가능.
- **DB 안전성(DB Safety)**: 스테이징 테이블 분리로 운영 DB 커넥션 풀 고갈 및 테이블 락 위험 원천 차단. 최종 승인 게이트(Commit Gate) 이전에는 운영 DB 쓰기 트랜잭션 미발생을 시스템 설계 원칙으로 강제.
- **LLM 품질 보증(LLM Quality Gate)**: 프롬프트는 LangSmith Pre-Eval을 통해 스키마 이탈률 0% 기준을 통과한 버전만 프로덕션에 반영. 프로덕션 HITL 수정률 ≥ 20% 발생 시 프롬프트 재평가 사이클 자동 트리거 (→ 3.10절 참조).

---


## 6. 에이전트 파이프라인 상세 아키텍처 흐름

```
[사용자 입력]
    │  URL 1~5개
    ▼
[선행 파싱 레이어 — Pre-scan]
    │  URL 경로 패턴 + HTML 메타 스캔 → 메타데이터 자동 추론
    ▼
[Human-in-the-Loop 검증]
    │  추론 성공 → Pre-fill + Confirm
    │  추론 실패 → PENDING + 관리자 수동 입력 (Interlock)
    ▼
[1단계] Input Agent
    │  유효성 검사, ETag 중복 체크, 대기열 추가
    ▼
[2단계] Crawler Agent
    │  DOM 파싱 → 불필요 태그 제거 → 텍스트 블록 분류
    ▼
[3단계] Extractor Agent
    │  gemini-2.5-flash 호출
    │  힌트: 배경→기전→영향도→대응코드 패턴
    │  타겟: 보안메커니즘 / 취약점원인 / 설정속성 / 영향컴포넌트
    │  출력: 구조화 JSON + 한국어 번역
    ▼
[4단계] Graph Writer Agent
    │  aliases 동의어 중복 체크 → PostgreSQL 적재
    │  Neo4j MERGE 증분 업데이트 (온톨로지 매핑 기준)
    ▼
[5단계] Link Resolver Agent
    │  SAME_AS 관계 탐색 → 벡터 유사도 병합 → 노드 최종 확정
    ▼
[결과]
    대시보드: 토폴로지 뷰 + 컨셉 인스펙터 + 실시간 로그
```

### 단계별 상세

| 단계 | 에이전트 | 주요 처리 내용 |
|------|----------|---------------|
| Pre-scan | — | URL 메타데이터 자동 추론, Human-in-the-Loop 인터락 |
| 1 | Input Agent | URL 유효성 검증, 중복 방지, 메타데이터 확정 |
| 2 | Crawler Agent | DOM 파싱, 텍스트 정제, 청크 분류 |
| 3 | Extractor Agent | LLM 추출, 4종 컨셉 타겟팅, 한국어 번역, JSON 스키마화 |
| 4 | Graph Writer Agent | aliases 중복 체크, PostgreSQL 적재, Neo4j MERGE |
| 5 | Link Resolver Agent | SAME_AS 탐색, 유사도 병합, 관계 최종 확정 |

---

## 7. 데이터 모델 개요 (Data Model Overview)

### PostgreSQL 주요 테이블

| 테이블명 | PK / 주요 컬럼 | 설명 |
|----------|---------------|------|
| `documents` | `doc_id TEXT PK` (`PREFIX_url_hash8`) | 수집 대상 URL 메타데이터. 마스터 키로 Neo4j `Document` 노드와 1:1 매핑. `source_prefix`, `original_url`, `content_hash`, `etag`, `framework`, `version`, `state` |
| `pipeline_logs` | `id UUID PK` | 단계별 처리 로그. `doc_id FK`, agent, level, message, timestamp |
| `staging_concepts` | `id UUID PK` | Extractor 출력 임시 보관. `doc_id FK`, `concept_json`, state(DRAFT→APPROVED→COMMITTED\|REJECTED) |
| `concepts` | `id UUID PK` | 관리자 최종 승인 후 반영된 개념 정형 데이터. `doc_id FK`, `concept_name`, `cwe_id`, severity, aliases, `description_ko` |
| `concept_snapshots` | `id UUID PK` | Extractor 출력 원본 JSON 스냅샷 (감사 추적). `doc_id FK` |

**`doc_id` 매핑 원칙**: `documents.doc_id` = Neo4j `Document.doc_id`. 별도 매핑 테이블 없이 동일 값으로 양방향 직접 참조. `pipeline_logs`, `staging_concepts`, `concepts` 모두 `doc_id`를 FK로 보유하여 특정 문서의 전체 처리 이력을 단일 키로 추적 가능.

**상태 전이 원칙**: `staging_concepts`의 레코드가 `COMMITTED` 되기 전까지 운영 `concepts` 테이블과 Neo4j에는 어떠한 쓰기도 발생하지 않는다. DB 커넥션 풀과 테이블 락을 Staging 단계에서 완전히 격리한다.

### Neo4j 노드/관계 모델 — 통합 Concept 허브

| 구분 | 내용 |
|------|------|
| **노드 레이블** | `Domain`, `OWASPCategory`, `PerfAntipatternCategory`, `CWE`, `Concept`(통합 허브), `SecurityMechanism`, `RootCause`, `Component`, `ConfigProperty`, `Framework` |
| **Concept 다중 라벨** | `:Concept:Security` / `:Concept:Performance` / `:Concept:Security:Performance` (교차 도메인) |
| **관계 타입** | `BELONGS_TO`, `MAPS_TO`, `REF_TO`, `INSTANTIATED_BY`, `MITIGATED_BY`, `CAUSED_BY`, `AFFECTS`, `CONFIGURED_BY`, `RELATED_TO`, `SAME_AS`, `IMPLEMENTS` |
| **MERGE 식별 키** | `Concept.name` (영문 약어, 도메인 무관 단일 키), `CWE.cwe_id`, `OWASPCategory.owasp_id` |
| **Neo4j Index** | `CREATE INDEX concept_name FOR (c:Concept) ON (c.name)` · `CREATE INDEX concept_aliases FOR (c:Concept) ON (c.aliases)` |

**교차 도메인 Concept 예시**:

| name | 라벨 | 비고 |
|------|------|------|
| `XSS` | `:Concept:Security` | 보안 전용 |
| `N+1Query` | `:Concept:Performance` | 성능 전용 |
| `MemoryLeak` | `:Concept:Security:Performance` | CWE-401 — 보안 + 성능 교차 |
| `ConnPoolExhaustion` | `:Concept:Security:Performance` | 자원 고갈 — 보안 + 성능 교차 |

---

## 8. 개발 순서 (Development Phases)

### Phase 1 — Backend Core
1. PostgreSQL + Neo4j 스키마 설계 및 마이그레이션 (`staging_concepts` 포함)
2. OWASP Top 10 / CWE SW Dev View / CWE Top 25 시드 데이터 적재 스크립트
3. FastAPI 라우터 구성 (URL 입력 API, Pre-scan API, 파이프라인 트리거 API)
4. Celery + Redis 비동기 태스크 구성 및 상태 관리
5. **[LangSmith]** 테스트 하네스 환경 구성 (`docker-compose.test.yml`, DB 픽스처)

### Phase 2 — Agent Pipeline
6. Pre-scan Layer: URL 패턴 파싱 + HTML 메타 추론 + Human-in-the-Loop API
7. Crawler Agent: 웹 크롤링 및 텍스트 정제
8. **[LangSmith]** Pre-Eval 실행: `extractor_schema_eval` 데이터셋 구성 → `gemini-2.5-flash` 프롬프트 후보 평가 → 스키마 이탈률 0% 달성 프롬프트 확정
9. Extractor Agent: 확정 프롬프트 적용, 4종 컨셉 타겟, `concept_domain` 필드 포함 JSON 추출 → `staging_concepts` DRAFT 적재. LangSmith `@traceable` 래핑
10. 최종 승인 게이트 API (`/approve`, `/reject`, `/diff`) 구현
11. Graph Writer Agent: APPROVED 항목 → `concept_domain` 기반 다중 라벨 결정 → `MERGE` 단일 노드 → `apoc.create.addLabels` 라벨 누적 → state = COMMITTED
12. Link Resolver Agent: SAME_AS 탐색, 유사도 기반 노드 병합. LangSmith 트레이싱 적용
13. **[LangSmith]** 하네스 통합 테스트 실행: 레이스 컨디션, DB 락, MERGE 멱등성, 다중 라벨 누적 검증

### Phase 3 — Frontend
14. React + TypeScript + Vite 프로젝트 셋업
15. Human-in-the-Loop 메타데이터 검증 UI (추론 신뢰도 배지, 인터락 폼)
16. 파이프라인 5단계 상태 인디케이터 컴포넌트
17. WebSocket/SSE 기반 실시간 로그 콘솔
18. 가상 노드 미리보기: `GET /api/graph/topology` + `GET /api/staging/{session_id}` 클라이언트 병합 렌더링
19. 승인 UI: DRAFT 노드 점선/반투명 스타일, 개별 승인/거부 토글, diff 요약, 최종 승인 버튼
20. react-force-graph 토폴로지 뷰 (온톨로지 계층 필터, 색상 범례, COMMITTED 후 가상→실제 노드 전환)
21. 컨셉 인스펙터 패널 (4종 컨셉 타입 필터 + 상세 대응 방안)

### Phase 4 — 프로덕션 모니터링 (LangSmith)
22. **[LangSmith]** HITL 수정 피드백 기록: 관리자 수정 diff → `client.create_feedback()` 연동
23. **[LangSmith]** 피드백 환류: 수정 빈도 높은 패턴 → `extractor_schema_eval` 데이터셋 추가 → Pre-Eval 재실행
24. **[LangSmith]** 모니터링 알림 설정: 스키마 이탈 1건/시간 → Slack, HITL 수정률 ≥ 20% → 프롬프트 재평가 트리거

---


## 16. LLM 인프라 추상화 및 Mock 메커니즘 (의존성 역전 기반)

### 16.1. 설계 목표

비즈니스 유즈케이스(`usecases/`)는 외부 인프라(Gemini API, LangSmith)의 실체에 의존하지 않는다. `infrastructure/llm/interface.py`에 추상 인터페이스를 두고 `.env`의 `APP_MODE` 플래그에 따라 `MockClient` 또는 `GeminiClient`를 주입한다. **애플리케이션 코드 변경 없이** DEV ↔ PROD 전환이 완료된다.

```
┌──────────────────────────────────────────────────────┐
│  usecases/run_pipeline.py                            │
│  → self.llm: ILLMClient  ← 인터페이스만 참조 (DIP)   │
└──────────────┬───────────────────────────────────────┘
               │ APP_MODE 플래그 분기 (factory.py)
        ┌──────┴──────┐
        ▼             ▼
  MockClient    GeminiClient
  (DEV)         (PROD)
  즉시 반환      실제 API 호출
  LangSmith ✗   LangSmith ✓
```

### 16.2. 파일 구조 및 역할

```
backend/app/infrastructure/llm/
├── interface.py        # 추상 인터페이스 ILLMClient — usecases가 참조하는 유일한 계약
├── gemini_client.py    # PROD: 실제 Gemini API + LangSmith @traceable 활성화
├── mock_client.py      # DEV:  PRD §3.3.3 스키마 고정 Mock JSON 즉시 반환
└── factory.py          # APP_MODE 기반 클라이언트 선택 팩토리
```

### 16.3. 추상 인터페이스 명세 (`interface.py`)

유즈케이스가 참조하는 **유일한 계약**. 구현체(Gemini/Mock)는 이 인터페이스를 반드시 구현한다.

```python
# backend/app/infrastructure/llm/interface.py
from abc import ABC, abstractmethod
from app.domain.models import ConceptExtractionSchema

class ILLMClient(ABC):
    """LLM 추출 클라이언트 추상 인터페이스 (DIP 계약).
    usecases 레이어는 이 인터페이스만 참조한다.
    구현체(GeminiClient / MockClient)는 factory.py가 주입한다.
    """

    @abstractmethod
    async def extract_concepts(
        self,
        text_chunk: str,
        doc_id: str,
        metadata: dict,
    ) -> list[ConceptExtractionSchema]:
        """공식 문서 청크에서 구조화 컨셉 스키마 목록을 추출한다.

        Args:
            text_chunk: Crawler Agent가 정제한 텍스트 청크
            doc_id:     마스터 키 (LangSmith Run 태그용)
            metadata:   {framework, version, lang} Pre-scan 추론값

        Returns:
            PRD §3.3.3 ConceptExtractionSchema 목록
            (concept_name, concept_domain, cwe_id, severity,
             description_ko, aliases, security_mechanisms,
             affected_components, config_properties, root_cause)
        """

    @abstractmethod
    def is_tracing_enabled(self) -> bool:
        """LangSmith 트레이싱 활성화 여부 반환.
        MockClient: False / GeminiClient: True (PROD)
        """
```

### 16.4. 상용 모드 구현체 (`gemini_client.py`)

```python
# backend/app/infrastructure/llm/gemini_client.py
from langsmith import traceable
from app.infrastructure.llm.interface import ILLMClient
from app.domain.models import ConceptExtractionSchema

class GeminiClient(ILLMClient):
    """PROD 모드: 실제 Gemini 2.5 Flash API + LangSmith 트레이싱 100% 활성화."""

    def __init__(self, api_key: str, langsmith_project: str):
        import google.generativeai as genai
        genai.configure(api_key=api_key)
        self._model = genai.GenerativeModel("gemini-2.5-flash")
        self._project = langsmith_project

    @traceable(name="extractor_agent", tags=["extractor"])
    async def extract_concepts(
        self, text_chunk: str, doc_id: str, metadata: dict
    ) -> list[ConceptExtractionSchema]:
        prompt = _build_extraction_prompt(text_chunk, metadata)
        response = await self._model.generate_content_async(prompt)
        raw_json = _parse_json_safely(response.text)
        return [ConceptExtractionSchema(**item) for item in raw_json]

    def is_tracing_enabled(self) -> bool:
        return True
```

### 16.5. 개발 모드 구현체 (`mock_client.py`)

PRD §3.3.3에 정의된 4종 컨셉 타겟을 커버하는 **고정 스펙 Mock 데이터**를 반환한다. 네트워크 I/O 없이 즉시 반환하며 LangSmith를 비활성화한다.

```python
# backend/app/infrastructure/llm/mock_client.py
from app.infrastructure.llm.interface import ILLMClient
from app.domain.models import ConceptExtractionSchema

# PRD §3.3.3 4종 컨셉 타겟을 커버하는 고정 Mock 스펙
_MOCK_CONCEPTS: list[dict] = [
    {
        "concept_name":          "XSS",
        "concept_domain":        "security",
        "concept_type":          "vulnerability_root_cause",
        "cwe_id":                "CWE-79",
        "owasp_id":              "A03:2021",
        "severity":              "HIGH",
        "description_ko":        "크로스 사이트 스크립팅 — 사용자 입력이 HTML 컨텍스트에서 이스케이프 없이 출력됨",
        "aliases":               ["Cross-Site Scripting", "크로스 사이트 스크립팅"],
        "security_mechanisms":   ["OutputEncoding", "ContentSecurityPolicy"],
        "affected_components":   ["템플릿 렌더링 레이어", "API 응답 직렬화"],
        "config_properties":     [{"key": "SECURE_BROWSER_XSS_FILTER", "value": "True"}],
        "root_cause":            "사용자 입력값 HTML 이스케이프 미처리",
    },
    {
        "concept_name":          "N+1Query",
        "concept_domain":        "performance",
        "concept_type":          "vulnerability_root_cause",
        "cwe_id":                "CWE-1072",
        "severity":              "HIGH",
        "description_ko":        "ORM 관계 조회 시 N번 추가 쿼리 발생으로 DB 과부하",
        "aliases":               ["N+1 Query", "N+1 쿼리"],
        "security_mechanisms":   ["select_related", "prefetch_related"],
        "affected_components":   ["ORM 레이어", "DB 커넥션 풀"],
        "config_properties":     [],
        "root_cause":            "ORM Lazy Loading 기본값 미조정",
    },
    {
        "concept_name":          "MemoryLeak",
        "concept_domain":        "both",          # 교차 도메인 — :Security:Performance
        "concept_type":          "vulnerability_root_cause",
        "cwe_id":                "CWE-401",
        "severity":              "HIGH",
        "description_ko":        "객체 참조 미해제로 인한 GC 부하 및 힙 메모리 소진. 보안(자원 고갈) 및 성능 교차 영역",
        "aliases":               ["Memory Leak", "메모리 누수"],
        "security_mechanisms":   ["명시적 리소스 해제", "컨텍스트 매니저 사용"],
        "affected_components":   ["힙 메모리", "GC"],
        "config_properties":     [],
        "root_cause":            "객체 참조 순환 또는 명시적 해제 누락",
    },
    {
        "concept_name":          "CSRFProtection",
        "concept_domain":        "security",
        "concept_type":          "security_mechanism",  # 보안 메커니즘 타겟
        "cwe_id":                "CWE-352",
        "owasp_id":              "A01:2021",
        "severity":              "HIGH",
        "description_ko":        "크로스 사이트 요청 위조 방어 — CSRF 토큰 기반 상태 변경 요청 검증",
        "aliases":               ["CSRF Token", "CSRF 방어"],
        "security_mechanisms":   ["SameSiteCookie", "CSRFToken"],
        "affected_components":   ["세션 관리", "인증 모듈"],
        "config_properties":     [{"key": "CSRF_COOKIE_SECURE", "value": "True"}],
        "root_cause":            "요청 출처 검증 미적용",
    },
]

class MockClient(ILLMClient):
    """DEV 모드: 외부 API 호출 없이 고정 Mock 스펙 즉시 반환.
    - LangSmith 트레이싱 비활성화 (네트워크 I/O 차단)
    - 테스트 하네스 레이어 D (test_llm_eval.py) 의 Pydantic 검증 대상
    """

    async def extract_concepts(
        self, text_chunk: str, doc_id: str, metadata: dict
    ) -> list[ConceptExtractionSchema]:
        # 네트워크 I/O 없음 — 즉시 반환
        return [ConceptExtractionSchema(**item) for item in _MOCK_CONCEPTS]

    def is_tracing_enabled(self) -> bool:
        return False
```

### 16.6. 팩토리 — `APP_MODE` 기반 런타임 주입 (`factory.py`)

```python
# backend/app/infrastructure/llm/factory.py
from app.infrastructure.llm.interface import ILLMClient

def create_llm_client(settings) -> ILLMClient:
    """APP_MODE 환경변수에 따라 LLM 클라이언트를 선택 주입한다.
    애플리케이션 코드(usecases)는 이 팩토리를 직접 호출하지 않는다.
    FastAPI 의존성 주입(Depends) 또는 Celery 태스크 초기화 시 1회 호출된다.
    """
    if settings.APP_MODE == "production":
        from app.infrastructure.llm.gemini_client import GeminiClient
        return GeminiClient(
            api_key=settings.GEMINI_API_KEY,
            langsmith_project=settings.LANGCHAIN_PROJECT,
        )
    else:  # development (기본값)
        from app.infrastructure.llm.mock_client import MockClient
        return MockClient()
```

### 16.7. 인프라 불가지론적 런타임 구동 모드 (`APP_MODE`)

| 항목 | `APP_MODE=development` | `APP_MODE=production` |
|------|------------------------|----------------------|
| LLM 호출 | `MockClient` — 즉시 고정값 반환 | `GeminiClient` — 실제 Gemini 2.5 Flash |
| LangSmith 트레이싱 | `LANGCHAIN_TRACING_V2=false` 강제 | 100% 활성화 (Pre-Eval · 트레이싱 · 피드백 루프) |
| 네트워크 I/O | 없음 (비용·지연 없음) | Gemini API + LangSmith 엔드포인트 |
| 테스트 하네스 연동 | `CELERY_TASK_ALWAYS_EAGER=True`와 조합 | 하네스 환경에서는 사용 안 함 |
| `.env` 설정 | `APP_MODE=development` | `APP_MODE=production` |

**`.env.local` 추가 항목**:
```bash
APP_MODE=development
# LangSmith 강제 비활성화 (MockClient가 자동 처리하지만 명시적 선언 권장)
LANGCHAIN_TRACING_V2=false
```

**`.env.prod` 추가 항목**:
```bash
APP_MODE=production
LANGCHAIN_TRACING_V2=true
```

### 16.8. 유즈케이스에서의 사용 패턴

유즈케이스는 `ILLMClient` 인터페이스만 참조한다. `GeminiClient`인지 `MockClient`인지 알지 못하며 알 필요도 없다.

```python
# backend/app/usecases/run_pipeline.py
from app.infrastructure.llm.interface import ILLMClient

class RunPipelineUsecase:
    def __init__(
        self,
        llm_client: ILLMClient,        # 인터페이스만 참조 — 구현체 무관
        pg_repo,                        # IRepository 구현체
        graph_service,                  # IGraphService 구현체
    ):
        self.llm = llm_client

    async def execute(self, doc_id: str, text_chunks: list[str], metadata: dict):
        all_concepts = []
        for chunk in text_chunks:
            concepts = await self.llm.extract_concepts(
                text_chunk=chunk,
                doc_id=doc_id,
                metadata=metadata,
            )
            all_concepts.extend(concepts)
        # 이하 staging INSERT 로직 — DB 구현체와도 인터페이스로만 통신
        await self.pg_repo.insert_staging_draft(doc_id, all_concepts)
```

### 16.9. SDD & TDD (AAA 패턴) — Mock 레이어 검증 명세

#### T09. MockClient 즉시 반환 및 스키마 검증 (레이어 D 확장)

| 항목 | 내용 |
|------|------|
| Spec (SDD) | `APP_MODE=development`일 때 LLM 호출 없이 4종 컨셉 Mock 데이터 반환 |
| Assert 목표 | 반환값이 `ILLMClient` 계약을 만족하고 Pydantic 검증 통과 |

```python
# tests/harness/test_llm_eval.py — T09 추가

def test_mock_client_returns_spec_schema():
    # Arrange
    mock_client = MockClient()

    # Act
    concepts = asyncio.run(
        mock_client.extract_concepts(
            text_chunk="dummy text",
            doc_id="EXT_test_00000000",
            metadata={"framework": "Django", "version": "5.0", "lang": "EN"},
        )
    )

    # Assert 1: 4종 컨셉 타겟 모두 포함
    domains   = {c.concept_domain for c in concepts}
    types_set = {c.concept_type   for c in concepts}
    assert "security"    in domains
    assert "performance" in domains
    assert "both"        in domains          # 교차 도메인 존재
    assert "vulnerability_root_cause" in types_set
    assert "security_mechanism"       in types_set  # §3.3.3 4종 중 보안 메커니즘

    # Assert 2: Pydantic 스키마 완전성
    for c in concepts:
        assert c.concept_domain in {"security", "performance", "both"}
        assert isinstance(c.aliases, list)
        assert len(c.description_ko) > 0

    # Assert 3: LangSmith 트레이싱 비활성화
    assert mock_client.is_tracing_enabled() is False
```

#### T10. 팩토리 주입 분기 검증

| 항목 | 내용 |
|------|------|
| Spec (SDD) | `APP_MODE` 값에 따라 올바른 클라이언트 타입이 주입됨 |
| Assert | `development` → `MockClient`, `production` → `GeminiClient` 인스턴스 |

```python
def test_factory_injects_correct_client():
    # Arrange / Act / Assert — development
    from unittest.mock import MagicMock
    dev_settings  = MagicMock(APP_MODE="development")
    prod_settings = MagicMock(APP_MODE="production",
                              GEMINI_API_KEY="key", LANGCHAIN_PROJECT="proj")

    dev_client  = create_llm_client(dev_settings)
    assert isinstance(dev_client, MockClient)
    assert dev_client.is_tracing_enabled() is False

    # production 분기는 실제 API 키 없이 클래스 타입만 검증
    with patch("app.infrastructure.llm.gemini_client.GeminiClient.__init__",
               return_value=None):
        prod_client = create_llm_client(prod_settings)
        assert isinstance(prod_client, GeminiClient)
```

#### T11. 유즈케이스 — Mock 주입 후 운영 DB 격리 통합 검증

| 항목 | 내용 |
|------|------|
| Spec (SDD) | MockClient가 주입된 상태에서 파이프라인을 실행하면 staging_concepts에만 DRAFT 레코드가 적재됨 |
| Assert | concepts 테이블과 Neo4j = 0건, staging_concepts DRAFT = 1건 |

```python
def test_pipeline_with_mock_llm_isolates_master_db(
    db_session, neo4j_session, celery_app
):
    # Arrange: MockClient 주입 (Gemini API 호출 없음)
    mock_llm = MockClient()
    usecase  = RunPipelineUsecase(
        llm_client=mock_llm,
        pg_repo=PgRepository(db_session),
        graph_service=Neo4jService(neo4j_session),
    )

    # Act: 파이프라인 실행 (ALWAYS_EAGER = 동기)
    asyncio.run(usecase.execute(
        doc_id="EXT_test_mock_abc12345",
        text_chunks=["dummy chunk"],
        metadata={"framework": "Django", "version": "5.0", "lang": "EN"},
    ))

    # Assert 1: 운영 테이블 미접촉
    assert db_session.execute("SELECT COUNT(*) FROM concepts").scalar() == 0
    assert neo4j_session.run("MATCH (c:Concept) RETURN count(c) AS n").single()["n"] == 0

    # Assert 2: staging에만 DRAFT 적재
    draft_count = db_session.execute(
        "SELECT COUNT(*) FROM staging_concepts WHERE state='DRAFT'"
    ).scalar()
    assert draft_count == len(_MOCK_CONCEPTS)  # 4종 Mock 개념 수
```

**DoD 업데이트 — QA 기준 추가**:

```
tests/harness/test_llm_eval.py       PASSED [100%]
  T07  스키마 유효성 (기존)
  T08  LangSmith 피드백 Mock (기존)
  T09  MockClient 4종 스펙 및 트레이싱 비활성화
  T10  factory APP_MODE 분기 주입
  T11  Mock 주입 + 운영 DB 격리 통합

==================== 11 passed in 3.12s ====================
```