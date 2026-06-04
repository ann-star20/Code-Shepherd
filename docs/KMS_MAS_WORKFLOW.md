# KMS 문서 구조화 모듈 — MAS 상세 워크플로우

> 버전: v1.0 | 브랜치: 3rd-project-final-plan | 작성일: 2026-05-27

---

## 1. 시스템 개요

KMS 문서 구조화 파이프라인은 **LangGraph StateGraph** 기반이다.
7개 노드 중 **3개 노드만 LLM을 호출하는 AI 에이전트**이고, 나머지 4개는 순수 Python 함수(도구)다.
모든 노드는 `AgentHarness`로 감싸져 LangSmith 추적과 PostgreSQL `agent_traces` 기록이 자동 처리된다.

| 노드 | 종류 | LLM |
|------|------|-----|
| Stage 1 (Convert) | **도구** | 없음 — python-docx, pdfplumber |
| Stage 2 (Validate) | **AI 에이전트** | Gemini 2.5 Flash |
| Stage 3 (Chunk) | **도구** | 없음 — tiktoken 알고리즘 |
| Stage 4 (ChunkValidate) | **도구** | 없음 — 규칙 기반 검증 |
| Stage 5 (MetadataExtract) | **AI 에이전트** | Gemini 2.5 Flash |
| Stage 5b (MetadataValidate) | **AI 에이전트** | Gemini 2.5 Flash |
| Stage 6 (Store) | **도구** | 없음 — DB/Storage I/O |

```mermaid
flowchart TD
    INPUT["PDF / DOCX / PPTX / TXT / MD"]
    UPLOAD["FastAPI\nPOST /kms/upload"]
    HITL(["hitl_pending\nDB 기록 + 파이프라인 종료"])
    DONE(["stored / stored_partial"])

    subgraph PIPELINE ["LangGraph StateGraph — BackgroundTasks"]
        S1["Stage1\nMarkdownConverter"]
        S2["Stage2\nMarkdownValidateAgent"]
        S3["Stage3\nChunkingTool"]
        S4["Stage4\nChunkValidateTool"]
        S5["Stage5\nMetadataExtractAgent"]
        S5b["Stage5b\nMetadataValidateAgent"]
        S6["Stage6\nStoreRouteTool"]

        S1 --> S2
        S2 -->|통과| S3
        S3 --> S4
        S4 -->|통과| S5
        S5 --> S5b
        S5b -->|통과| S6
    end

    INPUT --> UPLOAD --> S1
    S2 -->|HITL| HITL
    S4 -->|HITL| HITL
    S5b -->|HITL| HITL
    S6 --> DONE
```

---

## 2. 공유 상태 (DocPipelineState)

LangGraph 전 노드가 읽고 쓰는 TypedDict. 단방향으로 채워진다.

```python
class DocPipelineState(TypedDict):
    # 입력
    doc_id: str              # UUID str
    source: str              # "upload | notion | confluence | slack"
    file_path: str
    file_type: str           # "pdf | docx | pptx | txt | md"
    original_filename: str

    # Stage 1 출력
    raw_markdown: str | None
    markdown_storage_path: str | None

    # Stage 2 출력
    validated_markdown: str | None
    quality_score: float | None    # 0.0 ~ 1.0
    quality_issues: list[str] | None
    hitl_required: bool

    # Stage 3 출력
    chunks: list[ChunkItem] | None

    # Stage 4 출력
    chunk_validation_passed: bool
    chunk_validation_issues: list[str] | None

    # Stage 5 출력
    metadata: DocumentMetadata | None
    neo4j_entities: list[dict] | None
    neo4j_relations: list[dict] | None

    # Stage 5b 출력
    metadata_valid: bool | None
    metadata_score: float | None
    metadata_issues: list[str] | None

    # Stage 6 출력
    stored: bool
    neo4j_stored: bool | None     # None=미실행, True=성공, False=실패
    storage_paths: StoragePaths | None

    # 파이프라인 제어
    status: str              # "processing|validated|stored|stored_partial|failed|hitl_pending"
    error: str | None
    current_stage: str
```

---

## 3. 노드별 상세 워크플로우

### Stage 1: MarkdownConverter — 도구 (trc_0001)

**역할:** 원본 파일을 Markdown으로 변환하고 스토리지에 저장

**입력:** `file_path`, `file_type`, `doc_id`

**처리 흐름:**
```mermaid
flowchart TD
    FT{file_type 판별}
    TXT["직접 읽기\n(.txt / .md)"]
    DOCX["python-docx\nheading / table / list 변환"]
    PPTX["python-pptx\n슬라이드별 텍스트 추출"]
    PDF["pdfplumber\n텍스트 레이어 추출"]
    GEMINI["Gemini Multimodal fallback\n(이미지 비율 > 0.3)"]
    SAVE["storage.save(markdown_path, content)"]
    LOCAL["LocalStorage\n./data/markdown/{doc_id}/raw.md"]
    GCS["GCSStorage\ngs://tasklink-kms-storage/{doc_id}/raw.md"]

    FT -->|".txt / .md"| TXT
    FT -->|".docx"| DOCX
    FT -->|".pptx"| PPTX
    FT -->|".pdf"| PDF
    PDF -->|"이미지 비율 > 0.3"| GEMINI

    TXT & DOCX & PPTX & PDF & GEMINI --> SAVE
    SAVE --> LOCAL & GCS
```

**출력:** `raw_markdown`, `markdown_storage_path`

**에러 처리:** 변환 실패 시 `status="failed"`, `error=` 메시지 반환. 파이프라인 END.

---

### Stage 2: MarkdownValidateAgent — AI 에이전트 (trc_0002)

**역할:** Gemini 2.5 Flash로 Markdown 품질 점수화, HITL 분기 결정

**입력:** `raw_markdown`

**처리 흐름:**
```mermaid
flowchart TD
    A{raw_markdown 존재?}
    B["hitl_required = True\nstatus = 'hitl_pending'"]
    C["Gemini API 호출\n(_QUALITY_PROMPT)"]
    D["JSON 응답 파싱\nscore / issues / structure_loss / table_loss / image_loss"]
    E{품질 판정}
    F["hitl_required = True"]
    G["validated_markdown = raw_markdown\nhitl_required = False"]

    A -->|없음| B
    A -->|있음| C --> D --> E
    E -->|"score < 0.8\n또는 구조/표/이미지 손실 감지"| F
    E -->|통과| G
```

**HITL 트리거 조건:**
| 조건 | 임계값 |
|------|--------|
| 품질 점수 미달 | score < 0.8 |
| 구조 손실 감지 | structure_loss = True |
| 표 변환 실패 | table_loss = True |
| 이미지 설명 누락 | image_loss = True |

**라우터 (`_route_after_validate`):**
```python
if hitl_required or status == "hitl_pending" → "hitl_pending"
if status == "failed"                         → END
else                                          → "stage3_chunk"
```

**출력:** `validated_markdown`, `quality_score`, `quality_issues`, `hitl_required`

---

### Stage 3: ChunkingTool — 도구 (trc_0003)

**역할:** Markdown을 Parent-Child 계층 청크로 분할

**입력:** `validated_markdown`

**처리 흐름:**
```mermaid
flowchart TD
    A["_split_by_headers(markdown)\n## / ### 헤더 기준 섹션 분리"]
    B{섹션 크기 확인}
    PS["추가 분할\n(PARENT_MAX 초과 시)"]
    P["Parent 청크 생성\n(800~1500 tokens)"]
    C["Child 청크 생성\n(300~500 tokens per Parent)\nparent_chunk_id 연결"]
    TK["토큰 수 계산\ntiktoken cl100k_base"]
    OUT["chunks 리스트 반환\n(parent + child 포함)"]

    A --> B
    B -->|크기 적정| P
    B -->|PARENT_MAX 초과| PS --> P
    P --> C --> TK --> OUT
```

**청크 크기 기준:**
| 타입 | 최소 tokens | 최대 tokens | 용도 |
|------|-------------|-------------|------|
| Parent | 800 | 1500 | RAG 상위 컨텍스트, 의미 완결성 |
| Child | 300 | 500 | pgVector 임베딩 단위, 정밀 검색 |

**출력:** `chunks` (parent + child 모두 포함한 리스트)

---

### Stage 4: ChunkValidateTool — 도구 (trc_0004)

**역할:** 청크 구조 품질 검증, HITL 분기 결정

**입력:** `chunks`

**처리 흐름:**
```mermaid
flowchart TD
    A["_validate_chunks(chunks) 실행"]
    B["검증 항목\n빈 청크 탐지\nParent 토큰 > 1800\nChild 토큰 < 300 또는 > 600\nParent-Child 연결 확인"]
    C{구조적 이슈 존재?}
    D["hitl_required = True\n(Parent-Child 연결 실패 또는 Child < 300)"]
    E["chunk_validation_passed = False\nissues 기록 (경고 수준, HITL 불필요)"]
    F["chunk_validation_passed = True"]

    A --> B --> C
    C -->|"연결 실패 / Child < 300"| D
    C -->|"토큰 범위 초과만"| E
    C -->|이상 없음| F
```

**HITL 트리거 조건:**
| 조건 | 판별 함수 |
|------|-----------|
| `parent_chunk_id` 관련 오류 | `_is_structural_issue()` |
| "연결" 키워드 포함 | `_is_structural_issue()` |
| Child 토큰 < 300 | 직접 감지 |

**라우터 (`_route_after_chunk_validate`):**
```python
if hitl_required or status == "hitl_pending" → "hitl_pending"
if status == "failed"                         → END
else                                          → "stage5_metadata"
```

**출력:** `chunk_validation_passed`, `chunk_validation_issues`

---

### Stage 5: MetadataExtractAgent — AI 에이전트 (trc_0005)

**역할:** Gemini로 문서 메타데이터 + Neo4j 엔티티 추출

**입력:** `validated_markdown`, `chunks`

**처리 흐름:**
```mermaid
flowchart TD
    A["Gemini API 호출\n(_METADATA_PROMPT)"]
    B["JSON 응답 파싱\ntitle / category / team / author / tags / entities"]
    C["_build_relations(chunks, entities)\n각 청크 내용에 entity.name 포함 여부 확인"]
    D["Neo4jRelation 생성\n(chunk_id → entity, MENTIONS)"]
    E["출력\nmetadata (DocumentMetadata)\nneo4j_entities / neo4j_relations"]

    A --> B --> C --> D --> E
```

**출력:** `metadata` (DocumentMetadata), `neo4j_entities`, `neo4j_relations`

---

### Stage 5b: MetadataValidateAgent — AI 에이전트 (trc_0005b)

**역할:** 추출된 메타데이터가 문서 내용과 일치하는지 재검증, HITL 분기

**입력:** `metadata`, `validated_markdown`

**처리 흐름:**
```mermaid
flowchart TD
    A{Fallback 감지}
    B["hitl_required = True (즉시)"]
    C["Gemini API 호출\n(_VALIDATE_PROMPT)"]
    D["JSON 응답 파싱\nscore / category_correct / title_representative / issues"]
    E{품질 판정}
    F["hitl_required = True"]
    G["metadata_valid = True\nmetadata_score 기록"]

    A -->|"title == '제목 없음'\n또는 category 비허용값"| B
    A -->|정상| C --> D --> E
    E -->|"score < 0.7"| F
    E -->|통과| G
```

**HITL 트리거 조건:**
| 조건 | 임계값 |
|------|--------|
| 메타데이터 정확도 점수 미달 | score < 0.7 |
| title fallback 감지 | title == "제목 없음" |
| 유효하지 않은 category | VALID_CATEGORIES 외 |

**라우터 (`_route_after_metadata_validate`):**
```python
if hitl_required or status == "hitl_pending" → "hitl_pending"
if status == "failed"                         → END
else                                          → "stage6_store"
```

**출력:** `metadata_valid`, `metadata_score`, `metadata_issues`

---

### Stage 6: StoreRouteTool — 도구 (trc_0006)

**역할:** 전체 처리 결과를 4개 스토리지에 분산 저장

**입력:** 파이프라인 전체 State

**처리 흐름:**
```mermaid
flowchart TD
    A["asyncio.gather() 병렬 실행"]

    subgraph PARALLEL ["병렬 저장 작업"]
        PG["PostgreSQL\ndocuments + chunks INSERT"]
        VEC["pgVector\n임베딩 생성 (bge-m3 1024차원)\nchunk_embeddings INSERT"]
        STR["Storage\n원본 파일 + Markdown 저장"]
        NEO["Neo4j (선택)\nDocument / Chunk / Entity 그래프\nMENTIONS 관계"]
    end

    A --> PG
    A --> VEC
    A --> STR
    A --> NEO

    R{Neo4j 결과}
    OK(["status = stored\nneo4j_stored = True"])
    PARTIAL(["status = stored_partial\nneo4j_stored = False"])

    PG --> R
    VEC --> R
    STR --> R
    NEO --> R
    R -->|Neo4j 성공| OK
    R -->|Neo4j 실패| PARTIAL
```

**출력:** `stored=True`, `storage_paths`, `status="stored" | "stored_partial"`

---

## 4. HITL (Human-in-the-Loop) 워크플로우

### 4.1 HITL 진입 경로

```mermaid
flowchart TD
    H["hitl_pending 노드 실행"]
    S{어느 단계에서?}
    I2["issues = {quality_issues, markdown_storage_path}"]
    I4["issues = {chunk_issues, markdown_storage_path}"]
    I5b["issues = {metadata_issues, metadata, markdown_storage_path}"]
    Q["hitl_queue INSERT\n(stage, reason, quality_score, issues)"]
    U["documents UPDATE\nupload_status = 'hitl_pending'"]
    E(["파이프라인 종료 (END)"])

    H --> S
    S -->|stage2| I2 --> Q
    S -->|stage4| I4 --> Q
    S -->|stage5b| I5b --> Q
    Q --> U --> E
```

### 4.2 HITL 큐 관리 API

| 엔드포인트 | 역할 |
|-----------|------|
| `GET /hitl/queue` | 대기 중인 항목 목록 조회 |
| `GET /hitl/queue/{queue_id}` | 항목 상세 조회 |
| `POST /hitl/queue/{queue_id}/approve` | 승인 (선택적 자동 재처리) |
| `POST /hitl/queue/{queue_id}/reject` | 거부 (upload_status = 'rejected') |
| `POST /hitl/queue/{queue_id}/reprocess` | 수동 재처리 트리거 |

### 4.3 승인 후 재처리 워크플로우

```
POST /hitl/queue/{queue_id}/approve (auto_reprocess=True)
   │
   ├── hitl_queue UPDATE status = 'approved'
   ├── documents UPDATE upload_status = 'approved'
   └── BackgroundTask: _reprocess_document()
           │
           ├── documents UPDATE upload_status = 'reprocessing'   ← Bug 1 수정
           │
           ├── markdown 로드 결정:
           │   ├── corrected_markdown 제공 → 그대로 사용 (start_validated=False)
           │   ├── issues.markdown_storage_path 있음 → storage.load()
           │   └── 없으면 → _mark_reprocess_failed() → 종료
           │
           ├── make_reprocess_state() 생성
           │
           └── 직접 에이전트 실행 (LangGraph 없이 AgentHarness 사용):
               │
               ├── [corrected_markdown 있는 경우]
               │   Stage2 → Stage3 → Stage4 → Stage5 → Stage5b → Stage6
               │
               └── [skip_validation=True 또는 markdown만 로드한 경우]
                   Stage3 → Stage4 → Stage5 → Stage5b → Stage6

재처리 중 HITL 재트리거:
   └── _abort_reprocess_with_hitl()
       ├── hitl_queue INSERT (새 항목)
       └── _mark_reprocess_failed()
```

### 4.4 HITL 상태 전이 다이어그램

```mermaid
stateDiagram
    [*] --> processing : 업로드

    processing --> hitl_pending : 품질 기준 미달

    hitl_pending --> rejected : 관리자 거부
    hitl_pending --> approved : 관리자 승인

    approved --> reprocessing : 자동 재처리

    reprocessing --> stored : 재처리 성공
    reprocessing --> stored_partial : Neo4j 실패
    reprocessing --> reprocess_failed : 복원 실패
    reprocessing --> hitl_pending : HITL 재트리거

    stored --> [*]
    stored_partial --> [*]
    rejected --> [*]
    reprocess_failed --> [*]
```

---

## 5. AgentHarness & 추적 체계

### 5.1 Trace ID 체계

```
문서 파이프라인:
  trc_0001_{doc_id_8hex}  Stage1 Markdown 변환
  trc_0002_{doc_id_8hex}  Stage2 Markdown 검증
  trc_0003_{doc_id_8hex}  Stage3 청킹
  trc_0004_{doc_id_8hex}  Stage4 Chunk 검증
  trc_0005_{doc_id_8hex}  Stage5 메타데이터 추출
  trc_0005b_{doc_id_8hex} Stage5b 메타데이터 검증
  trc_0006_{doc_id_8hex}  Stage6 저장
```

### 5.2 AgentHarness 실행 흐름

```python
async with AgentHarness(
    trace_id=trace_id,
    agent_name="MarkdownValidateAgent",
    db_pool=pool,
    doc_id=doc_id,
) as harness:
    result = await harness.run(stage2_validate, state)

# __aenter__:
#   INSERT agent_traces (status='running')
#   LangSmith trace_metadata 주입 (config['metadata'])

# harness.run():
#   fn(state, config={metadata: {trace_id, agent_name, doc_id}}) 호출
#   30초 타임아웃 강제

# __aexit__:
#   UPDATE agent_traces SET status='success'|'fail', execution_ms=N
```

### 5.3 PostgreSQL agent_traces 스키마

```sql
CREATE TABLE agent_traces (
    trace_id      TEXT PRIMARY KEY,
    task_id       UUID,            -- PR 리뷰 파이프라인용
    agent_name    TEXT NOT NULL,
    doc_id        UUID,
    status        TEXT NOT NULL,   -- 'running' | 'success' | 'fail'
    started_at    TIMESTAMPTZ,
    ended_at      TIMESTAMPTZ,
    execution_ms  INTEGER,
    error_message TEXT
);
```

---

## 6. 스토리지 구조

### 6.1 파일 저장 경로

| 백엔드 | 원본 파일 | Markdown |
|--------|-----------|----------|
| LocalStorage | `./data/originals/{doc_id}/{filename}` | `./data/markdown/{doc_id}/raw.md` |
| GCSStorage | `gs://{bucket}/originals/{doc_id}/{filename}` | `gs://{bucket}/markdown/{doc_id}/raw.md` |

### 6.2 환경변수 전환

```bash
STORAGE_BACKEND=local  # 또는 gcs
GCS_BUCKET=tasklink-kms-storage
GOOGLE_APPLICATION_CREDENTIALS=/path/to/adc.json
```

---

## 7. 전체 파이프라인 시퀀스 다이어그램

```mermaid
sequenceDiagram
    participant Client
    participant FastAPI
    participant LangGraph
    participant AgentHarness
    participant DB_Storage as DB/Storage

    Client->>FastAPI: POST /kms/upload
    FastAPI->>DB_Storage: INSERT documents (status='processing')
    FastAPI->>Client: 202 doc_id
    FastAPI->>LangGraph: BackgroundTask: pipeline.ainvoke()

    Note over LangGraph,AgentHarness: Stage1: MarkdownConverterAgent
    LangGraph->>AgentHarness: Stage1 실행
    AgentHarness->>DB_Storage: INSERT agent_traces (running)
    AgentHarness->>AgentHarness: convert()
    AgentHarness->>DB_Storage: storage.save()
    AgentHarness->>DB_Storage: UPDATE agent_traces (success)

    Note over LangGraph,AgentHarness: Stage2: MarkdownValidateAgent
    LangGraph->>AgentHarness: Stage2 실행
    AgentHarness->>AgentHarness: Gemini API 호출

    alt score < 0.8 — HITL 분기
        LangGraph->>DB_Storage: INSERT hitl_queue
        LangGraph->>DB_Storage: UPDATE documents (hitl_pending)
        Note over LangGraph: END

        Client->>FastAPI: GET /kms/status/{doc_id}
        FastAPI->>Client: hitl_pending

        Note over Client: 사람 검토

        Client->>FastAPI: POST /hitl/queue/{id}/approve
        FastAPI->>DB_Storage: UPDATE documents (approved)
        FastAPI->>LangGraph: BackgroundTask: _reprocess_document()
        LangGraph->>DB_Storage: UPDATE documents (reprocessing)
        LangGraph->>LangGraph: Stage2 → Stage3 → Stage4 → Stage5 → Stage5b → Stage6
        LangGraph->>DB_Storage: UPDATE documents (stored)
    else 통과
        LangGraph->>LangGraph: Stage3 → Stage4 → Stage5 → Stage5b → Stage6
        LangGraph->>DB_Storage: UPDATE documents (stored)
    end

    Client->>FastAPI: GET /kms/status/{doc_id}
    FastAPI->>Client: stored
```
