# KMS 파이프라인 엔지니어링 리뷰

**작성일**: 2026-05-28
**브랜치**: 3rd-project-final-plan
**리뷰 대상**: `src/kms/pipeline/` 전체 + `src/kms/api.py`

---

## 1. 발견된 문제 — 성능 (P0, 즉시 수정 필요)

### P0-1: `_save_chunks()` N+1 INSERT

**파일**: `src/kms/pipeline/stage6_store.py:105-122`

```python
# 현재: 청크 50개 → DB 왕복 50번
for chunk in chunks:
    await conn.execute("INSERT INTO chunks ...", ...)

# 수정: executemany() 로 1번 왕복
await conn.executemany("INSERT INTO chunks ...", [(...) for chunk in chunks])
```

청크 50개 기준 ~200ms → ~5ms. 트랜잭션 점유 시간이 40배 줄어든다.

### P0-2: `_insert_embedding_rows()` N+1 INSERT

**파일**: `src/kms/pipeline/stage6_store.py:167-187`

동일한 패턴. child 청크 30개라면 임베딩 INSERT도 30번 왕복.
`executemany()`로 일괄 처리해야 한다.

> `$2::vector` 캐스트는 executemany에서 PostgreSQL 타입 추론이 안 될 수 있다.
> 각 row를 `(chunk_id, str(embedding), model, content, meta_json)` 형태로 넘기고
> 함수 내에서 `::vector` 캐스트를 유지한다.

### P0-3: 파일 전체를 메모리에 올린 뒤 크기 검사

**파일**: `src/kms/api.py:125`

```python
content = await file.read()   # 50MB 파일 → 50MB 메모리 사용
if len(content) > MAX_FILE_SIZE:
    raise ...
```

요청이 동시에 10개 들어오면 500MB 순간 메모리 사용.
`Content-Length` 헤더를 먼저 확인하거나 `SpooledTemporaryFile`로 스트리밍해야 한다.

---

## 2. 발견된 문제 — 성능 (P1, 운영 전 수정)

### P1-1: Neo4j 드라이버 문서마다 신규 생성

**파일**: `src/kms/pipeline/stage6_store.py:211-213`

```python
async with AsyncGraphDatabase.driver(uri, auth=(user, password)) as driver:
```

문서 1건 = TCP 핸드셰이크 + 인증 1회. 100건 처리 시 100번 반복.
모듈 레벨 싱글턴 드라이버로 교체해야 한다.

### P1-2: `_count_tokens()` 안에서 tiktoken 인코더를 매 호출마다 생성

**파일**: `src/kms/pipeline/stage3_chunk.py:36-41`

```python
def _count_tokens(text: str) -> int:
    import tiktoken
    enc = tiktoken.get_encoding("cl100k_base")   # ← 매번 호출
```

`_hard_split()`에서 단어별로 호출되면 수천 번 실행된다.
tiktoken 내부 캐시 덕분에 크래시는 안 나지만, 함수 호출 오버헤드가 누적된다.
모듈 레벨 lazy singleton으로 분리해야 한다.

```python
_TOKENIZER = None

def _get_tokenizer():
    global _TOKENIZER
    if _TOKENIZER is None:
        import tiktoken
        _TOKENIZER = tiktoken.get_encoding("cl100k_base")
    return _TOKENIZER
```

### P1-3: Gemini LLM 객체를 매 호출마다 인스턴스화

**파일**: `src/kms/pipeline/stage2_validate_agent.py:121`, `stage5b_metadata_validate_agent.py:156`

```python
llm = ChatGoogleGenerativeAI(model=GEMINI_MODEL, google_api_key=GEMINI_API_KEY, temperature=0)
```

HTTP 세션 재사용 불가. 모듈 레벨 lazy singleton으로 분리해야 한다.

### P1-4: Gemini API 재시도 로직 없음

**파일**: stage2, stage5, stage5b 전체

Gemini 429/503 응답 시 즉시 HITL 큐로 빠진다. 일시적인 API 오류가 사람 검토 큐를 채운다.
`tenacity` 또는 `asyncio.sleep` + 재시도 1~2회를 추가해야 한다.

---

## 3. 발견된 문제 — 설계 완성도 (P2)

### P2-1: Stage 2 품질 평가가 앞 3000자만 샘플링

**파일**: `src/kms/pipeline/stage2_validate_agent.py:123-124`

50페이지 PDF 변환 결과의 후반부 표 손실을 탐지하지 못한다.
앞/중간/끝 섹션을 균등 샘플링하거나 전체를 보내야 한다 (Gemini 2.5 Flash는 1M 컨텍스트 지원).

### P2-2: `_hard_split()`이 단어 경계에서 강제 절단

**파일**: `src/kms/pipeline/stage3_chunk.py:143-185`

문장 중간에서 잘리면 임베딩 품질이 떨어진다.
마침표/개행 기준 분할로 교체하는 게 낫다.

### P2-3: HITL 재처리 경로에 테스트 없음

**파일**: `src/kms/pipeline/models.py:124-162`

`make_reprocess_state()`의 HITL 승인 후 재처리 시 `file_path=""`, `file_type=""` 상태로
파이프라인이 재진입한다. Stage 1이 이 상태를 어떻게 처리하는지 검증되지 않았다.

### P2-4: `chunk_validation_passed` 기본값 미설정으로 KeyError 위험

`DocPipelineState`에서 `chunk_validation_passed: bool`은 Optional이 아닌 필수 필드인데,
초기 state 생성 시 누락하면 TypedDict가 런타임에서 `KeyError`를 던진다.

---

## 4. 테스트 커버리지 갭

| 파일 | 커버리지 | 미커버 경로 |
|------|----------|------------|
| `stage6_store.py` | 58% | Neo4j 실패 → `stored_partial`, 파일 복사 실패, `_insert_embedding_rows` |
| `graph.py` | 60% | `_route_after_metadata_validate` (3-way), `_insert_hitl_queue` stage5b 분기 |
| `stage5b_metadata_validate_agent.py` | 75% | JSON 파싱 실패, Gemini API 실패, LLM score < threshold |
| `stage1_convert.py` | 66% | Gemini fallback 내부 경로 |
| `stage3_chunk.py` | 76% | `_hard_split()` 강제 분할 로직 |

---

## 5. 태스크 분할

### T1 — N+1 INSERT 배치 처리 (P0, ~2h)

**목표**: `_save_chunks()` + `_insert_embedding_rows()` → `executemany()` 전환

| 서브태스크 | 내용 |
|-----------|------|
| T1-A | `stage6_store.py`: `_save_chunks()` executemany 전환 |
| T1-B | `stage6_store.py`: `_insert_embedding_rows()` executemany 전환 |
| T1-C | `test_stage6_store.py`: 배치 INSERT 단위 테스트 추가 (TDD RED → GREEN) |

---

### T2 — 파일 업로드 메모리 스트리밍 (P0, ~1h)

**목표**: `api.py`에서 Content-Length 선행 검사로 대용량 파일 메모리 spike 제거

| 서브태스크 | 내용 |
|-----------|------|
| T2-A | `api.py`: `upload_document()` Content-Length 헤더 선행 검사 |
| T2-B | `api.py`: 크기 초과 시 즉시 413 반환 (파일 미적재) |
| T2-C | `test_api.py`: 50MB 초과 업로드 → 413 반환 테스트 |

---

### T3 — Neo4j 드라이버 싱글턴화 (P1, ~1h)

**목표**: 문서마다 TCP 연결 생성 → 모듈 레벨 드라이버 재사용

| 서브태스크 | 내용 |
|-----------|------|
| T3-A | `stage6_store.py`: `_get_neo4j_driver()` 싱글턴 팩토리 추가 |
| T3-B | `_save_to_neo4j()`: driver를 인자로 주입받는 구조로 변경 |
| T3-C | `test_stage6_store.py`: Neo4j 실패 → `stored_partial` 경로 테스트 (현재 미커버) |

---

### T4 — Gemini 클라이언트 싱글턴 + 재시도 (P1, ~2h)

**목표**: stage2/5/5b의 매 호출마다 LLM 객체 생성 제거 + 재시도 추가

| 서브태스크 | 내용 |
|-----------|------|
| T4-A | `stage2_validate_agent.py`: 모듈 레벨 `_get_llm()` 싱글턴 |
| T4-B | `stage5b_metadata_validate_agent.py`: 동일 |
| T4-C | `stage5_metadata_agent.py`: 동일 |
| T4-D | 공통: Gemini 429/503 → tenacity 재시도 2회 (backoff 2s, 4s) |
| T4-E | `test_stage2.py`, `test_stage5b.py`: Gemini 실패 경로 테스트 |

---

### T5 — tiktoken 싱글턴 분리 (P1, ~30m)

| 서브태스크 | 내용 |
|-----------|------|
| T5-A | `stage3_chunk.py`: `_count_tokens()` 내 tiktoken 인코더 모듈 레벨 캐싱 |
| T5-B | `test_stage3.py`: `_hard_split()` 강제 분할 로직 테스트 (현재 미커버) |

---

### T6 — 테스트 커버리지 보강 (P1, ~3h)

| 서브태스크 | 내용 |
|-----------|------|
| T6-A | `test_graph_hitl.py`: `_route_after_metadata_validate` 3-way 분기 (hitl/failed/stage6_store) |
| T6-B | `test_graph_hitl.py`: `_insert_hitl_queue` stage5b 분기 (`stage5b in current_stage`) |
| T6-C | `test_stage6_store.py`: 파일 복사 실패 → `status=failed` 경로 |
| T6-D | `test_stage6_store.py`: 모든 임베딩 실패 → `RuntimeError` → `failed` 경로 |
| T6-E | `test_stage1.py`: Gemini fallback 내부 경로 (short_text 조건) |

---

### T7 — Stage 2 품질 평가 샘플링 개선 (P2, ~1h)

**목표**: 앞 3000자 고정 → 앞/중간/끝 균등 샘플링

| 서브태스크 | 내용 |
|-----------|------|
| T7-A | `stage2_validate_agent.py`: `_sample_markdown()` 헬퍼 추가 (앞 1000 + 중간 1000 + 끝 1000) |
| T7-B | `test_stage2.py`: 샘플링 로직 단위 테스트 |

---

### T8 — `_hard_split()` 문장 경계 분할 (P2, ~1h)

| 서브태스크 | 내용 |
|-----------|------|
| T8-A | `stage3_chunk.py`: 단어 기준 분할 → 문장 기준 분할 (`re.split(r'[.!?]\s+')`) |
| T8-B | `test_stage3.py`: 문장 중간 절단 없음 확인 테스트 |

---

## 6. 우선순위 요약

| 태스크 | 임팩트 | 공수 | 순서 |
|--------|--------|------|------|
| T1 (N+1 chunks/embeddings) | 성능 40x | 2h | 1 |
| T2 (파일 메모리) | 안정성 | 1h | 2 |
| T3 (Neo4j 싱글턴) | 성능 | 1h | 3 |
| T6 (커버리지 보강) | 안전망 | 3h | 4 |
| T4 (Gemini 싱글턴+재시도) | 안정성 | 2h | 5 |
| T5 (tiktoken 싱글턴) | 성능 미세 | 30m | 6 |
| T7 (샘플링 개선) | 품질 정확도 | 1h | 7 |
| T8 (문장 경계 분할) | 임베딩 품질 | 1h | 8 |

**총 예상 공수**: 약 11.5시간
