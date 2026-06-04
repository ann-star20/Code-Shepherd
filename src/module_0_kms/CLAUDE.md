# Module 0 KMS — 사내 지식 파이프라인 세부 구현 지침

**담당**: Dev1 (KMS 파이프라인 구현 완료)  
**위치**: `src/kms/` (현재 디렉토리)  
**상태**: 구현 완료 (Sessions 1~55 기준)

> 루트 `CLAUDE.md`는 팀 전역 규칙. 이 파일은 Module 0 KMS 파이프라인 전용 세부 규칙이다.

---

## 1. Stage별 처리 흐름

```
문서 업로드 (PDF/DOCX/PPTX/TXT)
    │
    ▼ Stage 1: DocumentParserAgent
    │   Upstage API (HIGH complexity PDF) → Gemini Multimodal 폴백
    │   파일: src/kms/pipeline/stage1_document_parser_agent.py
    │
    ▼ Stage 2: MarkdownValidateAgent  ← Agent (retry loop 포함)
    │   quality_score >= 0.8 목표
    │   _apply_targeted_fix(): table_loss → post_process / heading → normalize / 기타 → gemini
    │   STAGE2_MAX_FIX_ATTEMPTS=2 (env 조정 가능)
    │   파일: src/kms/pipeline/stage2_validate_agent.py
    │
    ▼ Stage 3: ChunkingTool  ← Tool (결정론적)
    │   512토큰 / overlap 128 / Parent-Child 구조
    │   파일: src/kms/pipeline/stage3_chunk.py
    │
    ▼ Stage 4: ChunkValidateTool  ← Tool (규칙 기반)
    │   100~1500 토큰 범위 검증 / Parent-Child 연결 확인
    │   파일: src/kms/pipeline/stage4_chunk_validate.py
    │
    ▼ Stage 5: MetadataExtractAgent  ← LLM (카테고리/태그/엔티티)
    │   파일: src/kms/pipeline/stage5_metadata_agent.py
    │   Stage 5b: MetadataValidateAgent (최종 게이트)
    │   파일: src/kms/pipeline/stage5b_metadata_validate_agent.py
    │
    ▼ Stage 6: StoreRouteTool  ← Tool (저장 + 라우팅)
        pgVector + PostgreSQL + GCS
        파일: src/kms/pipeline/stage6_store.py
```

---

## 2. Stage별 Trace ID 체계

```
trc_0001_{doc_id_8hex}   Stage 1: Markdown 변환
trc_0002_{doc_id_8hex}   Stage 2: Markdown 검증
trc_0003_{doc_id_8hex}   Stage 3: 청킹
trc_0004_{doc_id_8hex}   Stage 4: Chunk 검증
trc_0005_{doc_id_8hex}   Stage 5: 메타데이터 추출
trc_0006_{doc_id_8hex}   Stage 6: 저장 & 라우팅

예시: trc_0001_3a9f1c2b
```

> ⚠️ `new_pipeline_trace(stage)` 호출 시 반드시 `doc_id` 전달.  
> 없으면 trc_0001 고정값 → 두 번째 문서 처리 시 첫 번째 기록 덮어씀.

```python
trace_id = new_pipeline_trace(DocPipelineStage.MARKDOWN_CONVERT, doc_id=doc_id)
```

---

## 3. HITL 발동 조건 (KMS 전용)

| 조건 | 임계값 | 처리 |
|------|--------|------|
| Markdown 품질 점수 | < 0.8 | HITL 큐 등록, Stage 2 중단 |
| 표/이미지 구조 손실 | 발생 시 | HITL 큐 등록 |
| Chunk 길이 기준 초과/미달 | 발생 시 | HITL 큐 등록 |
| Parent-Child 연결 실패 | 발생 시 | HITL 큐 등록 |

```python
# HITL 큐 등록 패턴
MARKDOWN_QUALITY_THRESHOLD = float(os.getenv("MARKDOWN_QUALITY_THRESHOLD", "0.8"))

if score < MARKDOWN_QUALITY_THRESHOLD:
    await hitl_queue.enqueue({
        "doc_id": doc_id,
        "reason": issues,
        "quality_score": score,
        "agent_name": "MarkdownValidateAgent"
    })
    return {"status": "hitl_pending", "validated_markdown": None}
```

---

## 4. SQL 방어 규칙 (Chat API)

```python
# src/kms/chat_api.py:147
_SQL_ALLOWED_TABLES = frozenset({"documents", "chunks", "agent_traces"})

# src/kms/chat_api.py:170
def _validate_sql_v2(sql: str) -> bool:
    """sqlglot AST 기반 SQL 검증 — UNION/stacked query/unauthorized table 차단."""
    import sqlglot
    from sqlglot import exp
    # 1. Parse 실패 → False
    # 2. 복수 statements → False (stacked query 차단)
    # 3. SELECT 외 → False
    # 4. LIMIT 없음 → False
    # 5. 허용 테이블 외 접근 → False
```

---

## 5. 임베딩 모델

```
모델: Ollama bge-m3 (1024차원, 한국어 포함 다국어)
차원: 1024 → PGVECTOR_DIMENSION=1024 (환경변수)
DDL: vector(1024)
seed INSERT: ::vector(1024)
이 세 곳이 반드시 일치해야 한다 — 하나라도 다르면 첫 번째 INSERT에서 오류.
```

---

## 6. 파이프라인 API 엔드포인트

| 엔드포인트 | 파일 | 설명 |
|-----------|------|------|
| `POST /kms/upload` | api.py | 문서 업로드 + 파이프라인 시작 |
| `GET /kms/status/{doc_id}` | api.py | 파이프라인 진행 상태 폴링 |
| `GET /kms/docs` | api.py | 문서 목록 |
| `GET /kms/docs/{id}/markdown` | api.py | 변환된 Markdown |
| `GET /kms/docs/{id}/details` | api.py | 파싱 상세 (quality_score 등) |
| `GET /kms/search` | api.py | pgVector 유사도 검색 |
| `GET /hitl/queue` | hitl_api.py | HITL 큐 목록 |
| `POST /hitl/queue/{id}/approve` | hitl_api.py | HITL 승인 |
| `POST /hitl/queue/{id}/suggest-category` | hitl_api.py | KB Evolution AI 제안 |
| `POST /chat` | chat_api.py | 멀티 스토리지 RAG 챗봇 |

---

## 7. 테스트 현황 및 실행

```bash
# 전체 실행 (stack overflow 파일 제외)
C:\Users\user\anaconda3\envs\myenv11\Scripts\pytest.exe src/tests/ \
  --ignore=src/tests/kms/test_stage1_document_parser_agent.py \
  -v

# 특정 모듈 테스트
pytest src/tests/kms/test_chat_api.py -v       # Chat API + SQL 방어
pytest src/tests/kms/test_stage2_validate.py    # Stage 2 retry loop
```

**주의**: `test_stage1_document_parser_agent.py` 포함 전체 실행 시 Windows stack overflow 발생 (기존 이슈, 제외 후 실행).

---

## 8. 환경변수 (KMS 전용)

> **실제 값은 `.env` 파일에만 저장한다. 이 파일에 API key, IP, 비밀번호를 절대 적지 않는다.**

아래 키 이름을 `.env`에 설정해야 한다.

```bash
# Upstage (PDF 파싱)
UPSTAGE_API_KEY=                  # .env에서 설정 (HIGH complexity PDF에 사용)

# Gemini (멀티모달 폴백 + 품질 개선)
GOOGLE_API_KEY=                   # .env에서 설정
GEMINI_MODEL=gemini-2.5-flash

# KMS 파이프라인 설정 (기본값 — 필요 시 .env로 오버라이드)
MARKDOWN_QUALITY_THRESHOLD=0.8
STAGE2_MAX_FIX_ATTEMPTS=2
GEMINI_FALLBACK_IMAGE_RATIO=0.3

# 저장소
STORAGE_BACKEND=gcs
GCS_BUCKET=                       # .env에서 설정

# LangSmith (본인 GitHub ID로 교체)
LANGCHAIN_PROJECT=dev1-yourGitHubId
```

---

## 9. DB 연결 정보

> **실제 연결 정보는 `.env` 파일의 `POSTGRES_URL`에만 저장한다.**

```bash
# .env 파일에서 설정
POSTGRES_URL=postgresql://user:password@host:5432/dbname

# DB 스펙 (연결 정보 제외)
# - Google Cloud SQL (PostgreSQL + pgVector v0.8.1)
# - pgVector 차원: 1024 (Ollama bge-m3)
# - migration 004: categories 테이블 추가 완료
```

---

## 10. 현재 구현 상태 (2026-06-04 기준)

| 기능 | 상태 | 비고 |
|------|------|------|
| Stage 1~6 파이프라인 | ✅ 완료 | |
| HITL 큐 + 승인/거부/재처리 | ✅ 완료 | |
| KB Evolution (AI 카테고리 제안) | ✅ 완료 | E2E 미확인 |
| Chat RAG | ✅ 완료 | SQL 방어 강화됨 |
| Stage 2 retry loop | ✅ 완료 | STAGE2_MAX_FIX_ATTEMPTS=2 |
| sqlglot SQL 방어 | ✅ 완료 | _validate_sql_v2() |
| PDF E2E 검증 | ⚠️ 미완 | Upstage 할당량 리셋 후 확인 필요 |
