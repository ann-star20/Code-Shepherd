# MODULE_5_GRAPH_YOUTUBE_RULE.md — 독립 GraphDB + YouTube 추천 모듈 규칙

**버전**: v1.0 | **작성일**: 2026-06-04  
**이 모듈은 Module 0~4와 독립적으로 동작하나, 향후 KMS 연결을 위한 확장 포인트를 반드시 보존한다.**

---

## 1. 모듈 개요

```
별도 웹 UI
    │ 문서 업로드
    ▼
Module 5 파이프라인
    ├── 엔티티/관계 추출 (LLM)
    ├── Neo4j Aura 저장
    ├── 관계 그래프 시각화
    └── YouTube 키워드 기반 추천

향후 연결 포인트:
    doc_id ──────► KMS documents.doc_id
    file_hash ───► KMS 중복 문서 감지
    (MVP 이후) chunk_id / embedding / pgVector 연결
```

---

## 2. 필수 저장 필드 (MVP 최소 요구사항)

모든 문서 처리 시 아래 필드를 반드시 저장한다. **하나라도 누락되면 저장 거부.**

```python
class Module5Document(BaseModel):
    """Neo4j 저장 전 필수 검증 모델."""

    # ── KMS 연결 공통 키 (필수, MVP부터 저장) ──────────────
    doc_id:            str          # UUID v4 — 반드시 생성, 절대 생략 금지
    source_system:     str          # 항상 "graph_youtube" (고정값)
    original_filename: str          # 업로드된 원본 파일명
    file_hash:         str          # SHA-256 (권장, 미입력 시 "" 허용)

    # ── 추출 결과 (처리 후 저장) ──────────────────────────
    entities:          list[dict]   # 추출된 엔티티 (빈 리스트 허용)
    relations:         list[dict]   # 엔티티 간 관계 (빈 리스트 허용)
    keywords:          list[str]    # 핵심 키워드
    recommend_query:   list[str]    # YouTube 검색 쿼리

    # ── 상태 ──────────────────────────────────────────────
    created_at:        str          # ISO8601
    status:            str          # "stored | failed"
```

### 2-1. doc_id 생성 규칙

```python
from uuid import uuid4

# ❌ 잘못된 패턴 — doc_id를 외부에서 받거나 생략
doc_id = request.json.get("doc_id")  # 신뢰 불가

# ✅ 올바른 패턴 — 항상 서버에서 신규 생성
doc_id = str(uuid4())
```

### 2-2. source_system 고정값

```python
# 항상 이 값을 사용 (변경 금지)
SOURCE_SYSTEM = "graph_youtube"
```

### 2-3. file_hash 생성 방법

```python
import hashlib

def compute_file_hash(file_bytes: bytes) -> str:
    return hashlib.sha256(file_bytes).hexdigest()

# 향후 KMS와 동일 파일 감지 시 이 hash 값으로 매칭
```

---

## 3. 엔티티 / 관계 / 키워드 저장 규칙

### 3-1. 엔티티 형식

```python
# Neo4j Node 형식
entity = {
    "id":          str(uuid4()),    # 엔티티 고유 ID
    "doc_id":      doc_id,          # 출처 문서 (추적 가능성 필수)
    "name":        "Python",        # 엔티티 이름
    "type":        "Technology",    # 엔티티 유형 (Technology/Person/Concept 등)
    "description": "...",
    "source_system": SOURCE_SYSTEM
}
```

### 3-2. 관계 형식

```python
# Neo4j Edge 형식
relation = {
    "from_entity_id": entity_a["id"],
    "to_entity_id":   entity_b["id"],
    "relation_type":  "USES",       # 관계 유형 (대문자 언더스코어)
    "doc_id":         doc_id,       # 출처 문서 (추적 가능성 필수)
    "source_system":  SOURCE_SYSTEM
}
```

**출처 추적 규칙**: 모든 엔티티와 관계에 `doc_id`와 `source_system`을 반드시 포함한다.  
"어느 문서에서 나온 관계인지" 추적 가능해야 한다.

### 3-3. 키워드 추출 기준

```python
# MVP: LLM 기반 키워드 추출
# 형식: 단어 또는 짧은 구 (2~4 단어)
keywords = ["Python 비동기", "FastAPI 라우팅", "PostgreSQL 인덱스"]

# recommend_query: YouTube 검색에 직접 사용할 쿼리 (3~5개)
recommend_query = [
    "Python async await 튜토리얼",
    "FastAPI 입문 강의",
    "PostgreSQL 인덱스 최적화"
]
```

---

## 4. Neo4j Aura 사용 규칙

### 4-1. 환경변수

```bash
NEO4J_URI=neo4j+s://xxxx.databases.neo4j.io   # Aura 연결 URI
NEO4J_USER=neo4j
NEO4J_PASSWORD=your-password
NEO4J_DATABASE=neo4j                            # Aura 기본값
```

### 4-2. 연결 패턴

```python
from neo4j import AsyncGraphDatabase

driver = AsyncGraphDatabase.driver(
    uri=os.getenv("NEO4J_URI"),
    auth=(os.getenv("NEO4J_USER"), os.getenv("NEO4J_PASSWORD")),
)

async def store_entity(entity: dict) -> None:
    async with driver.session() as session:
        await session.run(
            """
            MERGE (e:Entity {id: $id})
            SET e.name = $name,
                e.type = $type,
                e.doc_id = $doc_id,
                e.source_system = $source_system
            """,
            **entity,
        )
```

### 4-3. 임베딩 처리 (MVP 기준)

**MVP에서 임베딩은 필수가 아니다.**

```python
# MVP: 임베딩 없이 키워드 기반 검색
# 향후: pgVector 연결 시 아래 필드 추가
EMBEDDING_EXTENSION_POINT = {
    # "embedding": List[float],     # 향후 추가 예정
    # "chunk_id":  str,             # KMS chunk_id 연결 시 추가
}
```

---

## 5. YouTube 추천 규칙 (MVP: 키워드 기반)

### 5-1. 추천 방식

```python
# MVP: YouTube Data API v3 키워드 검색
# 환경변수: YOUTUBE_API_KEY=AIzaxxxx

async def search_youtube(query: str, max_results: int = 5) -> list[dict]:
    """키워드로 YouTube 영상 검색. 임베딩 없이 동작."""
    url = "https://www.googleapis.com/youtube/v3/search"
    params = {
        "key":         os.getenv("YOUTUBE_API_KEY"),
        "q":           query,
        "part":        "snippet",
        "type":        "video",
        "maxResults":  max_results,
        "relevanceLanguage": "ko",
    }
    # ...
    return results
```

### 5-2. 추천 결과 형식

```python
youtube_result = {
    "video_id":     "dQw4w9WgXcQ",
    "title":        "Python 비동기 프로그래밍 완벽 가이드",
    "channel":      "코딩 채널",
    "url":          "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
    "thumbnail":    "https://img.youtube.com/vi/dQw4w9WgXcQ/default.jpg",
    "query_used":   "Python async await 튜토리얼",   # 어떤 쿼리로 찾았는지
    "doc_id":       doc_id,                          # 출처 문서
}
```

### 5-3. YouTube API 실패 처리

```python
# YouTube API 실패는 파이프라인을 중단하지 않는다
try:
    results = await search_youtube(query)
except Exception as e:
    logger.warning(f"YouTube 검색 실패 (무시): {e}")
    results = []    # 빈 목록 반환, 계속 진행
```

---

## 6. KMS 확장 포인트 (향후 연결 계획)

**MVP에서는 구현하지 않지만, 이 필드들을 반드시 보존하여 확장 가능하게 설계한다.**

### 6-1. 데이터 구조 확장 계획

```python
# MVP 현재 저장
{
    "doc_id":         "uuid",           # ← KMS 연결 키 1
    "file_hash":      "sha256hex",      # ← KMS 연결 키 2
    "source_system":  "graph_youtube",
    "original_filename": "...",
    "entities": [...],
    "relations": [...],
}

# 향후 KMS 연결 시 추가 예정 (확장 포인트)
{
    # ... 위 필드 유지 ...
    "kms_doc_id":   "uuid",    # KMS documents 테이블 연결
    "chunk_ids":    ["uuid"],  # KMS chunk_embeddings 연결
    "embedding":    [0.1, ...],# 1024차원 bge-m3 임베딩
    "pgvector_id":  "uuid",   # chunk_embeddings.chunk_id
}
```

### 6-2. KMS 연결 매칭 전략

```python
# 방법 1: doc_id 직접 매칭
# → Module 5가 KMS에 같은 파일을 업로드한 경우 동일 doc_id 사용

# 방법 2: file_hash 기반 중복 감지
# → 동일 파일이 KMS와 Module 5에 모두 존재하는 경우 file_hash로 매칭
async def find_kms_doc_by_hash(file_hash: str) -> Optional[str]:
    """KMS documents 테이블에서 file_hash로 doc_id 조회."""
    row = await conn.fetchrow(
        "SELECT doc_id FROM documents WHERE file_hash = $1",
        file_hash,
    )
    return str(row["doc_id"]) if row else None
```

### 6-3. 확장 시 변경 없이 연결 가능한 이유

```
Module 5 Neo4j 노드:  {doc_id: "uuid-A", source_system: "graph_youtube"}
KMS PostgreSQL:       {doc_id: "uuid-A", status: "stored"}

→ doc_id "uuid-A" 기준으로 JOIN 가능 (추가 마이그레이션 불필요)
```

---

## 7. API 엔드포인트 설계

```
POST   /graph/upload          문서 업로드 → 처리 시작
GET    /graph/status/{doc_id} 처리 상태 조회
GET    /graph/docs            저장된 문서 목록
GET    /graph/docs/{doc_id}/entities   엔티티 목록
GET    /graph/docs/{doc_id}/relations  관계 목록
GET    /graph/docs/{doc_id}/youtube    YouTube 추천 목록
GET    /graph/visualize/{doc_id}       관계 그래프 데이터 (FE 시각화용)
```

---

## 8. 오류 처리

| 오류 | 처리 |
|------|------|
| 파일 파싱 실패 | status=failed, error_message 기록, 즉시 반환 |
| 엔티티 추출 실패 | 1회 재시도 후 빈 목록 반환, 계속 진행 |
| Neo4j 연결 실패 | 1회 재시도 후 status=failed |
| Neo4j 저장 실패 | 1회 재시도 후 status=failed |
| YouTube API 실패 | 빈 목록 반환, 파이프라인 중단 없음 |
| doc_id 누락 | 즉시 거부 (저장 자체를 막음) |

---

## 9. 단위 테스트 최소 요구사항

```python
# tests/module_5/ 폴더에 작성

class TestModule5Document:
    def test_doc_id_always_generated(self):
        """doc_id는 항상 서버에서 생성해야 한다."""
        doc = process_upload(file=b"test", filename="test.pdf")
        assert doc["doc_id"] is not None
        assert len(doc["doc_id"]) == 36  # UUID 형식

    def test_source_system_fixed(self):
        """source_system은 항상 'graph_youtube'여야 한다."""
        doc = process_upload(file=b"test", filename="test.pdf")
        assert doc["source_system"] == "graph_youtube"

    def test_youtube_failure_does_not_block(self, mock_youtube_fail):
        """YouTube API 실패 시 파이프라인이 멈추면 안 된다."""
        doc = process_upload(file=b"test", filename="test.pdf")
        assert doc["status"] == "stored"
        assert doc["youtube_results"] == []

    def test_neo4j_entity_has_doc_id(self, mock_neo4j):
        """모든 엔티티에 doc_id가 포함되어야 추적 가능하다."""
        entities = extract_and_store(file=b"test", doc_id="uuid-A")
        for entity in entities:
            assert entity["doc_id"] == "uuid-A"

    def test_kms_extension_fields_preserved(self):
        """향후 KMS 연결을 위한 doc_id, file_hash가 보존되어야 한다."""
        doc = process_upload(file=b"test content", filename="guide.pdf")
        assert "doc_id" in doc
        assert "file_hash" in doc
        assert "source_system" in doc
        assert "original_filename" in doc
```
