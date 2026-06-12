# V2 KMS 통합 설계 메모 — m0 청크 → dev3 ingestion

> D4 읽기 전용 분석 결과. 코드 변경 금지. v2 구현 참고용.

## m0 청크 포맷 (Code-Shepherd/backend/m0)

**모델**: `app/pipeline/models.py` → `ChunkItem`

```python
class ChunkItem(TypedDict):
    chunk_id: str                # UUID
    doc_id: str                  # 문서 UUID
    parent_chunk_id: str | None  # None = Parent 청크
    chunk_type: "parent"|"child"
    content: str                 # 청크 본문 텍스트
    token_count: int
    page_number: int | None
    section_header: str | None   # "3.2 API 설계 원칙" 형태
    chunk_index: int | None      # 문서 내 0-based 순서
```

**메타데이터**: `DocumentMetadata`

```python
class DocumentMetadata(TypedDict):
    title: str
    category: str   # "코딩컨벤션|아키텍처|온보딩"
    team: str | None
    author: str | None
    tags: list[str]
    source: str     # "upload|notion|confluence|slack"
```

**저장 경로** (`StoragePaths`):
- `original`: 원본 파일
- `markdown`: 변환 Markdown
- `page_images`: 페이지별 이미지 경로

## rule_id 필드 유무

m0 ChunkItem에는 **`rule_id` 필드 없음**. dev3 코퍼스(`corpus/*.md`)의 `rule_id`와 직접 매핑 불가.

현재 ingestion.py는 `§`-단위 청크를 생성하며 `rule_id`를 파일명 + 섹션에서 추출:
```python
# src/ingestion.py 현재 패턴
rule_id = f"{file_stem}"  # 예: CONV-API-001
section = header_text     # 예: "§1 규칙"
```

## v2 통합 포인트 — ingestion.py 수정

### 변경 전 (현재 MVP)
```
corpus/*.md → §단위 청크 → text-embedding-3-small → Chroma
```

### 변경 후 (v2 — m0 연동)
```
m0 /kms/search API → ChunkItem[] → 변환 → Chroma
```

**수정 포인트 1** — `src/ingestion.py` `reindex()`:

```python
# v2: m0 GET /kms/docs → 각 doc의 chunks 조회
# m0 API: GET /kms/docs?status=approved&limit=100
# 응답: {docs: [{doc_id, title, status, ...}]}
# 각 doc에 대해: GET /kms/docs/{doc_id}/details → .chunks (ChunkItem[])

def _fetch_m0_chunks(m0_url: str) -> list[Chunk]:
    chunks = []
    docs = requests.get(f"{m0_url}/kms/docs?status=approved").json()["docs"]
    for doc in docs:
        detail = requests.get(f"{m0_url}/kms/docs/{doc['doc_id']}/details").json()
        for c in detail.get("chunks", []):
            # section_header → §1, §2 매핑
            # rule_id → title + chunk_index로 생성 (예: CONV-API-001_s1)
            ...
```

**수정 포인트 2** — `Chunk` 계약 확장(게이트 2 승인 필요):
- `source_url: str` 필드 추가 → m0 doc_id → KMS URL 생성
- `source_type: str` 필드 추가 ("m0_chunk" | "local_md")

**수정 포인트 3** — `rule_id` 생성 규칙 합의:
- 현재 m0 청크엔 `rule_id` 없음
- 옵션 A: `category + chunk_index` → `"CONV-{chunk_id[:8]}"`
- 옵션 B: m0에 `rule_id` 메타 필드 추가 (m0팀 협의 필요)
- **추천**: 옵션 B — section_header의 규칙 번호를 m0 메타로 저장

## 핫스왑 호환성

현재 `make reindex`는 로컬 corpus/*.md를 사용. v2에서:
- `make reindex`가 m0 API를 호출해 최신 chunks 가져옴
- m0의 문서 업데이트 → `make reindex` → Chroma 재구축 → 즉시 반영
- 현재 핫스왑(corpus/ 파일 수정)은 v2에서 "m0 HITL 승인 + reindex"로 대체

## 구현 타임라인 (v2)

1. m0팀과 `rule_id` 메타 필드 합의 (1-2일)
2. `src/ingestion.py` `_fetch_m0_chunks()` 구현 (1일)
3. contracts `Chunk` 스키마 확장 → 게이트 2 통과 (0.5일)
4. E2E 테스트: m0 문서 업로드 → reindex → eval 12/12 유지 (1일)

## 참고 파일

- `Code-Shepherd/backend/m0/app/pipeline/models.py` — ChunkItem, DocPipelineState
- `Code-Shepherd/backend/m0/app/routes/kms_routes.py` — /kms/docs, /kms/search 엔드포인트
- `Code-Shepherd/backend/m0/app/pipeline/stage3_chunk.py` — 청킹 로직
- `src/ingestion.py` — 현재 로컬 파일 기반 수정 포인트
