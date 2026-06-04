# KMS 문서 구조화 모듈 — 주요 기능 문서

**버전**: v1.0  
**작성일**: 2026-05-27

---

## 기능 목차

1. [문서 업로드 & 비동기 처리](#1-문서-업로드--비동기-처리)
2. [7단계 AI 파이프라인](#2-7단계-ai-파이프라인)
3. [Parent-Child 청킹 구조](#3-parent-child-청킹-구조)
4. [HITL (Human-in-the-Loop) 검토 시스템](#4-hitl-human-in-the-loop-검토-시스템)
5. [pgVector 의미 검색](#5-pgvector-의미-검색)
6. [실시간 상태 폴링 UI](#6-실시간-상태-폴링-ui)
7. [AgentHarness — 추적 & 관찰](#7-agentharness--추적--관찰)
8. [Storage 추상화 (Local / GCS)](#8-storage-추상화-local--gcs)

---

## 1. 문서 업로드 & 비동기 처리

### 무엇인가

웹 UI에서 파일을 업로드하면 즉시 `doc_id`를 발급하고, 실제 처리는 백그라운드에서 비동기로 실행한다. 사용자는 업로드 직후 돌아올 수 있다.

### 지원 형식

| 형식 | 변환 방법 |
|------|-----------|
| PDF | pdfplumber → Gemini 멀티모달 폴백 |
| DOCX | python-docx (heading 구조 보존) |
| PPTX | python-pptx (슬라이드별 변환) |
| TXT | 인코딩 자동 감지 (UTF-8 → EUC-KR) |
| MD | 직접 사용 |

파일 크기 한도: **50MB**

### 흐름

```mermaid
flowchart TD
    A["POST /kms/upload (file)"]
    B[UUID doc_id 발급]
    C["documents 테이블 INSERT\n(status='processing')"]
    D[임시 파일 저장]
    E[BackgroundTasks에 파이프라인 등록]
    F[HTTP 202 즉시 반환]
    G["[백그라운드]\n파이프라인 실행 완료 후\ndocuments 상태 업데이트"]

    A --> B --> C --> D --> E
    E --> F
    E --> G
```

### 핵심 코드 위치

- 엔드포인트: [src/kms/api.py:125](../src/kms/api.py#L125) — `upload_document()`
- 초기 상태 구성: [src/kms/api.py:189](../src/kms/api.py#L189) — `_build_initial_state()`
- 백그라운드 실행: [src/kms/api.py:226](../src/kms/api.py#L226) — `_run_pipeline_background()`

---

## 2. 7단계 AI 파이프라인

### 무엇인가

업로드된 문서를 LangGraph StateGraph로 순차 처리한다. **7개 노드 중 3개만 LLM을 호출하는 AI 에이전트**이고, 나머지 4개는 순수 Python 함수다. 모든 노드는 `AgentHarness`로 감싸져 실행 추적, 오류 기록, LangSmith 연동이 자동 처리된다.

### 파이프라인 구조

```mermaid
flowchart TD
    S1["Stage 1: MarkdownConverter [도구]\nPDF/DOCX/PPTX → Markdown 변환, Storage 저장\npython-docx / pdfplumber / python-pptx"]
    S2["Stage 2: MarkdownValidateAgent [AI — Gemini 2.5 Flash]\nGemini 품질 점수 산출"]
    S3["Stage 3: ChunkingTool [도구]\ntiktoken 기반 Parent(800~1500) + Child(300~500) 분할"]
    S4["Stage 4: ChunkValidateTool [도구]\n길이 범위 검증, Parent-Child 연결 검증"]
    S5["Stage 5: MetadataExtractAgent [AI — Gemini 2.5 Flash]\ntitle/category/tags 추출, Neo4j 엔티티 추출"]
    S5b["Stage 5b: MetadataValidateAgent [AI — Gemini 2.5 Flash]\n메타데이터 품질 검증"]
    S6["Stage 6: StoreRouteTool [도구]\nPostgreSQL + pgVector + Neo4j 저장"]
    HITL(["hitl_pending"])
    DONE(["stored / stored_partial"])

    S1 --> S2
    S2 -->|"quality_score < 0.8"| HITL
    S2 -->|통과| S3
    S3 --> S4
    S4 -->|이슈 감지| HITL
    S4 -->|통과| S5
    S5 --> S5b
    S5b -->|"score < 0.7"| HITL
    S5b -->|통과| S6
    S6 --> DONE
```

### 조건부 분기 (HITL)

Stage 2, Stage 4, Stage 5b 이후 3곳에서 HITL 분기가 발생한다.

```python
# graph.py의 라우터 패턴
def _route_after_validate(state) -> str:
    if state.get("hitl_required") or state.get("status") == "hitl_pending":
        return "hitl_pending"
    if state.get("status") == "failed":
        return END
    return "stage3_chunk"
```

### DocPipelineState — 파이프라인 공유 상태

```python
class DocPipelineState(TypedDict):
    doc_id: str                  # UUID — 문서 단위 공통 키
    raw_markdown: Optional[str]  # Stage 1 출력
    validated_markdown: Optional[str]  # Stage 2 출력
    quality_score: Optional[float]     # 0.0~1.0
    hitl_required: bool                # HITL 트리거 플래그
    chunks: Optional[list[ChunkItem]]  # Stage 3 출력
    metadata: Optional[DocumentMetadata]  # Stage 5 출력
    status: str                  # 현재 문서 상태
    current_stage: str           # 현재 실행 단계명
```

전체 필드 정의: [src/kms/pipeline/models.py](../src/kms/pipeline/models.py)

### 핵심 코드 위치

- 파이프라인 빌더: [src/kms/pipeline/graph.py:193](../src/kms/pipeline/graph.py#L193) — `build_pipeline()`
- Stage 1: [src/kms/pipeline/stage1_convert.py](../src/kms/pipeline/stage1_convert.py)
- Stage 2: [src/kms/pipeline/stage2_validate_agent.py](../src/kms/pipeline/stage2_validate_agent.py)
- Stage 3: [src/kms/pipeline/stage3_chunk.py](../src/kms/pipeline/stage3_chunk.py)
- Stage 4: [src/kms/pipeline/stage4_chunk_validate.py](../src/kms/pipeline/stage4_chunk_validate.py)
- Stage 5: [src/kms/pipeline/stage5_metadata_agent.py](../src/kms/pipeline/stage5_metadata_agent.py)
- Stage 5b: [src/kms/pipeline/stage5b_metadata_validate_agent.py](../src/kms/pipeline/stage5b_metadata_validate_agent.py)
- Stage 6: [src/kms/pipeline/stage6_store.py](../src/kms/pipeline/stage6_store.py)

---

## 3. Parent-Child 청킹 구조

### 무엇인가

하나의 문서를 두 크기의 청크로 계층화한다. Parent는 LLM 응답 생성 시 넓은 컨텍스트를 제공하고, Child는 pgVector 검색의 정밀도를 높인다.

```mermaid
flowchart TD
    DOC[문서]
    P1["Parent Chunk 1\n(800~1500 토큰) — LLM 컨텍스트용"]
    P2["Parent Chunk 2\n(800~1500 토큰)"]
    C11["Child Chunk 1-1\n(300~500 토큰) — pgVector 검색 단위"]
    C12["Child Chunk 1-2\n(300~500 토큰)"]
    C21["Child Chunk 2-1\n(300~500 토큰)"]
    C22["Child Chunk 2-2\n(300~500 토큰)"]

    DOC --> P1 & P2
    P1 --> C11 & C12
    P2 --> C21 & C22
```

### 청크 메타데이터

각 청크는 원본 추적을 위한 메타데이터를 보관한다.

```python
class ChunkItem(TypedDict):
    chunk_id: str               # UUID
    doc_id: str                 # 소속 문서
    parent_chunk_id: str | None # None이면 Parent 청크
    chunk_type: "parent" | "child"
    content: str
    token_count: int
    page_number: int | None     # 원본 페이지
    section_header: str | None  # "3.2 API 설계 원칙"
```

### 검색 흐름

```mermaid
flowchart LR
    Q[사용자 쿼리]
    CS["Child 청크 검색\n(pgVector cosine similarity)"]
    PL["상위 N개 Child의\nparent_chunk_id로 Parent 조회"]
    LLM[Parent 내용을 LLM 컨텍스트로 제공]

    Q --> CS --> PL --> LLM
```

pgVector 검색 시 `stored` / `stored_partial` 문서의 Child 청크만 대상이다.

---

## 4. HITL (Human-in-the-Loop) 검토 시스템

### 무엇인가

AI가 품질 기준을 통과하지 못한 문서를 사람이 검토하도록 대기 큐에 등록한다. 관리자가 승인하면 파이프라인이 자동으로 재개된다.

### HITL 트리거 3지점

| 단계 | 트리거 조건 | 이슈 정보 |
|------|-------------|-----------|
| Stage 2 (품질 검증) | quality_score < 0.8 또는 구조 손실 | quality_issues 목록 + markdown 경로 |
| Stage 4 (청크 검증) | 길이 범위 초과 또는 Parent-Child 연결 실패 | chunk_issues 목록 + markdown 경로 |
| Stage 5b (메타데이터 검증) | metadata_score < 0.7 | metadata_issues + metadata 객체 + markdown 경로 |

### 승인 후 재처리 흐름

```mermaid
flowchart TD
    A["POST /hitl/queue/{item_id}/approve\nbody: corrected_markdown (선택)"]
    B["upload_status: approved → reprocessing\n(즉시 UI 반영)"]
    C{corrected_markdown 있음?}
    D["Stage 3부터 재처리\n(검증 생략)"]
    E["Storage에서 원본 markdown 로드\n→ Stage 2부터 재처리"]
    F["markdown 복원 실패\nupload_status = 'reprocess_failed'"]
    G["재처리 완료\nupload_status = 'stored' 또는 'stored_partial'"]

    A --> B --> C
    C -->|Yes| D --> G
    C -->|No| E
    E -->|복원 실패| F
    E -->|복원 성공| G
```

### HITL API 엔드포인트

```
GET  /hitl/queue/pending                대기 중인 검토 목록
GET  /hitl/queue/{item_id}             항목 상세 (이슈, 품질 점수 포함)
POST /hitl/queue/{item_id}/approve     승인 + 파이프라인 자동 재개
POST /hitl/queue/{item_id}/reject      거부 → 문서 상태 'rejected'
GET  /hitl/queue/{doc_id}/history      문서별 HITL 이력
```

### 문서 상태 전이 (HITL 포함 전체)

```mermaid
stateDiagram
    [*] --> processing : 업로드

    processing --> stored : 정상 완료
    processing --> stored_partial : Neo4j만 실패
    processing --> hitl_pending : 품질 기준 미달
    processing --> failed : 오류 발생

    hitl_pending --> approved : 관리자 승인
    hitl_pending --> rejected : 관리자 거부

    approved --> reprocessing : 자동 재처리 시작

    reprocessing --> stored : 재처리 성공
    reprocessing --> stored_partial : Neo4j만 실패
    reprocessing --> hitl_pending : HITL 재트리거
    reprocessing --> reprocess_failed : 복원 실패

    stored --> [*]
    stored_partial --> [*]
    rejected --> [*]
    failed --> [*]
    reprocess_failed --> [*]
```

### 핵심 코드 위치

- HITL API: [src/kms/hitl_api.py](../src/kms/hitl_api.py)
- HITL 노드 + DB INSERT: [src/kms/pipeline/graph.py:118](../src/kms/pipeline/graph.py#L118)
- 재처리 팩토리: [src/kms/pipeline/models.py:124](../src/kms/pipeline/models.py#L124) — `make_reprocess_state()`

---

## 5. pgVector 의미 검색

### 무엇인가

키워드 매칭이 아닌 의미적 유사도로 문서를 검색한다. "N+1 쿼리 최적화 방법" 같은 질문에 "for 루프 안 DB 호출 금지" 내용이 담긴 문서를 찾아낸다.

### 기술 스택

| 컴포넌트 | 역할 |
|----------|------|
| Ollama bge-m3 | 1024차원 한국어+영어 임베딩 모델 |
| pgVector | PostgreSQL 확장 — `<=>` 코사인 거리 연산자 |
| HNSW 인덱스 | 근사 최근접 이웃 (ANN) 고속 검색 |

### 검색 쿼리 구조

```sql
SELECT
    ce.chunk_id, ce.content,
    1 - (ce.embedding <=> $1::vector) AS score,  -- 코사인 유사도 (1에 가까울수록 유사)
    d.title AS doc_title
FROM chunk_embeddings ce
LEFT JOIN chunks c ON ce.chunk_id = c.chunk_id
LEFT JOIN documents d ON c.doc_id = d.doc_id
WHERE d.upload_status IN ('stored', 'stored_partial')
ORDER BY ce.embedding <=> $1::vector  -- 거리 오름차순
LIMIT $2
```

### 임베딩 생성

```python
# 문서 청크: Stage 6에서 asyncio.Semaphore(5)로 병렬 처리
# 검색 쿼리: 실시간 Ollama API 호출
async def _embed_query(text: str) -> list[float]:
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            f"{OLLAMA_BASE_URL}/api/embeddings",
            json={"model": "bge-m3", "prompt": text},
        )
        return response.json()["embedding"]
```

### API 사용 예시

```bash
# 기본 검색
GET /kms/search?q=N+1+쿼리+방지

# 카테고리 필터 + 결과 개수 조정
GET /kms/search?q=SQL+인젝션&category=보안&limit=10
```

응답에는 유사도 점수(`score`)와 문서 제목(`doc_title`)이 포함된다.

---

## 6. 실시간 상태 폴링 UI

### 무엇인가

업로드 후 처리가 완료될 때까지 프론트엔드가 상태 API를 폴링하여 파이프라인 진행 상황을 실시간으로 표시한다.

### 폴링 로직

```typescript
// useUploadStatus.ts — 2초 간격 폴링, 종료 상태 도달 시 자동 중단
const FINAL_STATUSES = new Set(["stored", "stored_partial", "failed", "rejected"]);

// DocumentUpload.tsx — 폴링 재시작 조건
useEffect(() => {
    if (isVisible && uploadResult?.doc_id) {
        if (!FINAL_STATUSES.has(currentStatusRef.current ?? "")) {
            setPollKey((k) => k + 1);  // 탭 전환 후 복귀 시 재시작
        }
    }
}, [isVisible]);
```

### 상태별 UI

| 상태 | 색상 | 표시 내용 |
|------|------|-----------|
| `processing` | 황색 | 진행 바 애니메이션 |
| `hitl_pending` | 청색 | "HITL 검토 큐에서 승인하면 자동 재개" |
| `approved` | 보라 | "검토 승인됨. 재처리 시작 중..." |
| `reprocessing` | 황색 | "재처리 중입니다. 파이프라인이 진행 중이에요." |
| `stored` | 녹색 | "DB에 저장 완료" + 청크 분석 토글 |
| `stored_partial` | 연녹 | "PostgreSQL/pgVector 완료 (Neo4j 실패)" |
| `failed` | 적색 | 오류 메시지 |
| `rejected` | 회색 | "새 파일을 업로드하세요" |

### 완료 후 청크 분석

파이프라인 종료 상태 도달 시 `GET /kms/docs/{doc_id}/details`를 자동 호출하여 청크 목록과 에이전트 트레이스를 표시한다.

```mermaid
flowchart TD
    T["isTerminal === true"]
    D["getDocDetails(doc_id) 자동 호출"]
    A["DocumentAnalyzer\n청크 내용 / 타입 / 토큰수 표시"]
    P["PipelineFlow\n에이전트 실행 흐름 시각화"]

    T --> D
    D --> A & P
```

### 세션 복원

페이지 새로고침 후에도 마지막 추적 문서를 복원한다.

```typescript
// sessionStorage에 마지막 doc_id 보관
const SESSION_KEY = "kms_upload_result";
const [uploadResult] = useState(() => {
    const saved = sessionStorage.getItem(SESSION_KEY);
    return saved ? JSON.parse(saved) : null;
});
```

### 핵심 코드 위치

- 메인 업로드 컴포넌트: [frontend/src/components/DocumentUpload.tsx](../frontend/src/components/DocumentUpload.tsx)
- 폴링 훅: [frontend/src/hooks/useUploadStatus.ts](../frontend/src/hooks/useUploadStatus.ts)
- 파이프라인 시각화: [frontend/src/components/PipelineFlow.tsx](../frontend/src/components/PipelineFlow.tsx)
- 청크 분석기: [frontend/src/components/DocumentAnalyzer.tsx](../frontend/src/components/DocumentAnalyzer.tsx)

---

## 7. AgentHarness — 추적 & 관찰

### 무엇인가

모든 파이프라인 노드를 공통 래퍼로 감싸 실행 추적, DB 로깅, LangSmith 연동을 자동 처리한다. 에이전트 코드는 추적 로직 없이 비즈니스 로직만 작성한다.

### 래핑 패턴

```python
# graph.py — 모든 Stage를 동일한 방식으로 래핑
graph.add_node(
    "stage2_validate",
    _wrap_with_harness(
        DocPipelineStage.MARKDOWN_VALIDATE,  # trace_id 접두사 결정
        "MarkdownValidateAgent",             # agent_name
        stage2_validate,                     # 실제 비즈니스 함수
        db_pool,                             # harness용 풀
    ),
)
```

### Trace ID 체계

```
trc_0001_{doc_id_8hex}  — MarkdownConverterAgent
trc_0002_{doc_id_8hex}  — MarkdownValidateAgent
trc_0003_{doc_id_8hex}  — ChunkingAgent
trc_0004_{doc_id_8hex}  — ChunkValidateAgent
trc_0005_{doc_id_8hex}  — MetadataExtractAgent
trc_0005b_{doc_id_8hex} — MetadataValidateAgent
trc_0006_{doc_id_8hex}  — StoreRouteAgent

예시: trc_0001_3a9f1c2b
```

### agent_traces 기록 구조

```sql
INSERT INTO agent_traces (
    trace_id, agent_name, doc_id, status,
    started_at, ended_at, execution_ms, error_message
) VALUES (...)
```

- 에이전트 시작 시 `started_at` 기록
- 정상 종료 시 `status = 'success'`
- 예외 발생 시 `status = 'fail'`, `error_message` 기록

### LangSmith 자동 추적

환경변수만 설정하면 LangGraph 실행이 LangSmith에 자동 추적된다. 코드 변경 불필요.

```bash
LANGCHAIN_TRACING_V2=true
LANGCHAIN_API_KEY=ls__xxxx
LANGCHAIN_PROJECT=dev1-alice  # 개발자별 프로젝트 분리
```

### 핵심 코드 위치

- AgentHarness 구현: [src/common/harness.py](../src/common/harness.py)
- Trace ID 생성: [src/common/trace.py](../src/common/trace.py) — `new_pipeline_trace()`
- 래핑 헬퍼: [src/kms/pipeline/graph.py:49](../src/kms/pipeline/graph.py#L49) — `_wrap_with_harness()`

---

## 8. Storage 추상화 (Local / GCS)

### 무엇인가

파일 저장 백엔드를 환경변수 하나로 전환할 수 있다. 로컬 개발 시 `LocalStorage`, 프로덕션(Cloud Run)에서는 `GCSStorage`를 사용한다.

### Storage 인터페이스

```python
class Storage(ABC):
    async def save(self, path: str, data: bytes | str) -> str
    async def load(self, path: str) -> bytes
    async def exists(self, path: str) -> bool
    async def delete(self, path: str) -> None
```

### 전환 방법

```bash
# 로컬 개발 (기본값)
STORAGE_BACKEND=local
STORAGE_LOCAL_ROOT=/tmp/kms_storage

# GCS (Cloud Run)
STORAGE_BACKEND=gcs
GOOGLE_CLOUD_PROJECT=my-project
GCS_BUCKET=my-kms-bucket
GOOGLE_APPLICATION_CREDENTIALS=/path/to/adc.json
```

### GCS 인증

```python
# storage.py — 명시적 ADC 로딩
adc_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
if adc_path and os.path.isfile(adc_path):
    from google.oauth2.credentials import Credentials as UserCredentials
    credentials = UserCredentials.from_authorized_user_file(adc_path)
    self._client = gcs.Client(project=project, credentials=credentials)
else:
    self._client = gcs.Client(project=project)  # Cloud Run 메타데이터 서버 ADC
```

### 저장 경로 구조

```
Storage 루트/
├── {doc_id}/
│   ├── original.{ext}     # 원본 파일 (pdf, docx, ...)
│   └── converted.md       # Stage 1 변환 결과
```

HITL 재처리 시 `markdown_storage_path`로 `converted.md`를 불러와 파이프라인을 재개한다.

### 핵심 코드 위치

- Storage 구현: [src/kms/storage.py](../src/kms/storage.py)
- Docker Compose GCS 마운트: [docker-compose.yml](../docker-compose.yml)

---

## 빠른 참조 — 엔드포인트 목록

| 메서드 | 경로 | 기능 |
|--------|------|------|
| POST | `/kms/upload` | 문서 업로드 + 파이프라인 실행 |
| GET | `/kms/status/{doc_id}` | 처리 상태 + agent_traces 조회 |
| GET | `/kms/docs/{doc_id}/details` | 청크 목록 + 에이전트 트레이스 상세 |
| GET | `/kms/search` | pgVector 의미 검색 |
| GET | `/hitl/queue/pending` | HITL 대기 목록 |
| GET | `/hitl/queue/{item_id}` | HITL 항목 상세 |
| POST | `/hitl/queue/{item_id}/approve` | HITL 승인 + 재처리 |
| POST | `/hitl/queue/{item_id}/reject` | HITL 거부 |
| GET | `/hitl/queue/{doc_id}/history` | 문서별 HITL 이력 |

---

## 빠른 참조 — 주요 환경변수

```bash
POSTGRES_URL=postgresql://user:pass@localhost:5432/onboarding_db
PGVECTOR_DIMENSION=1024              # bge-m3, schema.sql vector(1024)과 일치
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_EMBEDDING_MODEL=bge-m3
STORAGE_BACKEND=local                # local | gcs
STORAGE_LOCAL_ROOT=/tmp/kms_storage
MARKDOWN_QUALITY_THRESHOLD=0.8       # Stage 2 HITL 임계값
METADATA_QUALITY_THRESHOLD=0.7       # Stage 5b HITL 임계값
USE_MOCK_LLM=true                    # 개발 중 true, 통합/데모 시 false
LANGCHAIN_TRACING_V2=true
LANGCHAIN_PROJECT=dev1-alice         # 개발자별 분리
```
