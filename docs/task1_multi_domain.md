# 도메인 확장성 설계 명세
## `concept_domain` 동적 확장 + Human-in-the-Loop 도메인 등록 정책

**작성일**: 2026-06-05   
**핵심 결정**: `"both"` 하드코딩 폐기 → `list[str]` + REGISTERED_DOMAINS 동적 등록

---

## 0. 결정 배경

| 구분 | 이전 설계 | 새 설계 |
|------|-----------|---------|
| LLM 출력 타입 | `Literal["security","performance","both"]` | `list[str]` |
| 교차 도메인 | `"both"` (security+performance 2개 고정) | `["security","performance"]` |
| 신규 도메인 | 소스코드 수정 필요 | HITL 승인 → DB 등록만으로 확장 |
| 알 수 없는 도메인 | ValidationError → 파이프라인 실패 | DOMAIN_PENDING → 관리자 검토 후 결정 |

**"both"가 위험한 이유**: 도메인이 3개가 되는 순간 `"both"`로 표현 불가능한 조합이 생긴다.  
예) `["security","compliance"]`, `["performance","reliability"]`, `["security","performance","compliance"]`  
→ 확장할 때마다 `Literal` 값 추가 + 매핑 테이블 수정 = 소스코드 영구 동결

---

## 1. LLM 입출력 스키마 변경

### 1-1. `ConceptExtractionSchema` — `concept_domain` 타입 변경

```python
# backend/app/interfaces/schemas/concept_extraction.py

# 변경 전 (폐기)
concept_domain: Literal["security", "performance", "both"]

# 변경 후
from pydantic import validator

REGISTERED_DOMAINS: set[str] = {"security", "performance"}
# DB에서 로드하여 런타임에 동적으로 갱신 (§3 참조)

class ConceptExtractionSchema(BaseModel):
    concept_name:   str
    concept_domain: list[str]          # ← 배열로 변경, "both" 없음
    # 나머지 필드 동일
    ...

    @validator("concept_domain")
    def validate_domains(cls, v: list[str]) -> list[str]:
        if not v:
            raise ValueError("concept_domain은 최소 1개 이상이어야 합니다")
        # 알 수 없는 도메인은 ValidationError 아님 → DOMAIN_PENDING 처리
        # (validator는 형식만 검증, 등록 여부는 graph_writer에서 분기)
        if not all(isinstance(d, str) and d.strip() for d in v):
            raise ValueError("concept_domain 값은 비어있지 않은 문자열이어야 합니다")
        return [d.lower().strip() for d in v]  # 소문자 정규화
```

### 1-2. Gemini 프롬프트 지시문 변경

```
# 변경 전 (폐기)
"concept_domain": "security" | "performance" | "both"

# 변경 후
"concept_domain": 배열 형식으로 반환할 것.
예시:
  - 보안 취약점만 해당: ["security"]
  - 성능 결함만 해당: ["performance"]
  - 보안+성능 모두 해당: ["security", "performance"]
  - 규정 준수 관련: ["compliance"]  ← 시스템이 감지하여 관리자에게 검토 요청
허용값: "security", "performance" (그 외 값은 관리자 검토 대상)
복수 도메인 해당 시 배열에 모두 포함.
```

### 1-3. `mock_client.py` Mock 데이터 수정

```python
# 변경 전
{"concept_domain": "security", ...}
{"concept_domain": "both", ...}      # ← 폐기

# 변경 후
{"concept_domain": ["security"], ...}
{"concept_domain": ["security", "performance"], ...}   # ← 직접 배열
```

---

## 2. REGISTERED_DOMAINS — 동적 등록 체계

### 2-1. PostgreSQL 도메인 레지스트리 테이블

```sql
-- 신규 테이블: 등록된 도메인 목록 관리
CREATE TABLE IF NOT EXISTS domain_registry (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name        TEXT NOT NULL UNIQUE,          -- "security", "performance", "compliance"
  label_ko    TEXT NOT NULL,                 -- "보안", "성능", "규정 준수"
  description TEXT,                          -- 도메인 설명
  color_hex   TEXT DEFAULT '#888780',        -- 프론트엔드 토폴로지 색상
  is_active   BOOLEAN DEFAULT true,
  created_at  TIMESTAMPTZ DEFAULT now(),
  created_by  TEXT DEFAULT 'system'          -- 'system' | 관리자 ID
);

-- 초기 시드 (보안 + 성능)
INSERT INTO domain_registry (name, label_ko, description, color_hex) VALUES
  ('security',    '보안',  '웹 애플리케이션 보안 취약점 도메인', '#1D9E75'),
  ('performance', '성능',  '백엔드 성능 안티패턴 도메인',       '#BA7517')
ON CONFLICT (name) DO NOTHING;
```

### 2-2. 런타임 도메인 목록 로드

```python
# backend/app/infrastructure/database/domain_repo.py

async def get_registered_domains(conn: asyncpg.Connection) -> set[str]:
    """DB에서 활성 도메인 목록을 로드. 캐시 TTL: 60초"""
    rows = await conn.fetch(
        "SELECT name FROM domain_registry WHERE is_active = true"
    )
    return {row["name"] for row in rows}

# settings.py 또는 startup event에서 캐싱
# 신규 도메인 등록 후 캐시 무효화
```

---

## 3. 파이프라인 분기 — 미등록 도메인 감지

### 3-1. Graph Writer Agent 분기 로직

```python
# backend/app/usecases/write_staging_draft.py 또는 graph_writer.py

async def classify_domains(
    concept_domains: list[str],
    registered: set[str],
) -> tuple[list[str], list[str]]:
    """
    반환: (known_domains, unknown_domains)
    """
    known   = [d for d in concept_domains if d in registered]
    unknown = [d for d in concept_domains if d not in registered]
    return known, unknown

async def write_concept_node(
    concept: ConceptExtractionSchema,
    driver: neo4j.AsyncDriver,
    conn: asyncpg.Connection,
) -> str:
    """
    반환: "committed" | "domain_pending"
    """
    registered = await get_registered_domains(conn)
    known, unknown = classify_domains(concept.concept_domain, registered)

    if unknown:
        # 미등록 도메인 포함 → DOMAIN_PENDING 상태로 staging 보관
        await write_domain_pending_staging(
            concept=concept,
            known_domains=known,
            unknown_domains=unknown,
            conn=conn,
        )
        return "domain_pending"

    # 모두 등록된 도메인 → 즉시 Neo4j 적재
    await _merge_concept_neo4j(concept, concept.concept_domain, driver)
    return "committed"
```

### 3-2. `staging_concepts` 상태 확장

```sql
-- state 컬럼 허용값 추가
-- 기존: DRAFT | APPROVED | COMMITTED | REJECTED
-- 추가: DOMAIN_PENDING

-- staging_concepts에 미등록 도메인 정보 컬럼 추가
ALTER TABLE staging_concepts
  ADD COLUMN IF NOT EXISTS unknown_domains TEXT[] DEFAULT '{}',
  ADD COLUMN IF NOT EXISTS known_domains   TEXT[] DEFAULT '{}';

-- 인덱스
CREATE INDEX IF NOT EXISTS idx_staging_domain_pending
  ON staging_concepts(state) WHERE state = 'DOMAIN_PENDING';
```

---

## 4. HITL 도메인 검토 UI — 관리자 화면

### 4-1. 검토 화면 스펙 (S7 — 신규 화면)

```
[DOMAIN_PENDING 감지 알림]
───────────────────────────────────────────────────────────
개념명: "GDPR 데이터 처리 제한"
LLM이 반환한 도메인: ["compliance"]     ← 미등록 도메인
알려진 도메인: []

유사 도메인 추천 (연관성 분석):
  ● security     유사도 68%  [이것으로 매핑]
  ○ performance  유사도 12%

─────────────────── 선택 ───────────────────
[① 기존 도메인에 매핑]  [② 신규 도메인 등록]  [③ 이 개념 거부]
───────────────────────────────────────────────────────────

② 신규 도메인 등록 선택 시 펼침:
  도메인 이름 (영문): [compliance        ]
  한국어 라벨:       [규정 준수          ]
  설명:              [GDPR, HIPAA 등 규정 ]
  토폴로지 색상:     [🎨 #7F4BAA         ]
  [등록 및 승인]
```

### 4-2. 선택지별 동작

| 선택 | 동작 | DB 변경 |
|------|------|---------|
| ① 기존 도메인 매핑 | "compliance" → "security"로 치환 후 Graph Writer 재실행 | staging state → COMMITTED |
| ② 신규 도메인 등록 | `domain_registry`에 "compliance" 추가 → Graph Writer 재실행 | domain_registry INSERT + staging COMMITTED |
| ③ 거부 | staging 레코드 삭제 | staging DELETE |

### 4-3. API 명세 (신규 엔드포인트)

```
GET  /api/domains                              → 등록된 도메인 목록
POST /api/domains                              → 신규 도메인 등록
GET  /api/staging/domain-pending               → DOMAIN_PENDING 목록
POST /api/staging/{id}/resolve-domain          → 도메인 결정 (매핑/등록/거부)
```

```python
# POST /api/staging/{id}/resolve-domain 요청 바디
class ResolveDomainRequest(BaseModel):
    action: Literal["map", "register", "reject"]

    # action="map"일 때
    target_domain: str | None = None      # 매핑할 기존 도메인 이름

    # action="register"일 때
    new_domain: NewDomainPayload | None = None

class NewDomainPayload(BaseModel):
    name:        str   # 영문, 소문자, 하이픈 허용
    label_ko:    str
    description: str
    color_hex:   str = "#888780"
```

### 4-4. 유사 도메인 추천 로직

```python
# backend/app/usecases/suggest_similar_domains.py

def suggest_similar_domains(
    unknown_domain: str,
    registered: set[str],
    top_k: int = 3,
) -> list[dict]:
    """
    간단한 문자열 유사도(SequenceMatcher) + 키워드 매칭으로 추천.
    벡터 임베딩 불필요 — 도메인 이름 수가 적으므로 단순 비교로 충분.
    """
    from difflib import SequenceMatcher
    scores = []
    for reg in registered:
        ratio = SequenceMatcher(None, unknown_domain, reg).ratio()
        scores.append({"domain": reg, "similarity": round(ratio, 2)})
    return sorted(scores, key=lambda x: x["similarity"], reverse=True)[:top_k]
```

---

## 5. Neo4j — `domains` 배열 MERGE (변경 없음, 확인)

```cypher
// DOMAIN_LABEL_MAP 완전 삭제 — concept.concept_domain을 그대로 사용
MERGE (c:Concept {name: $name})
ON CREATE SET
  c.domains        = $domains,    -- concept.concept_domain 그대로 전달
  c.cwe_id         = $cwe_id,
  c.description_ko = $description_ko,
  c.aliases        = $aliases,
  c.severity       = $severity,
  c.created_at     = timestamp()
ON MATCH SET
  c.domains        = [x IN c.domains + $domains
                       WHERE x IS NOT NULL | x],
  c.updated_at     = timestamp()
```

**신규 도메인 등록 후 자동 처리**: `domain_registry`에 "compliance"가 추가되면  
DOMAIN_PENDING 레코드가 자동으로 Graph Writer 재실행 → `domains: ["compliance"]` 그대로 Neo4j에 저장됨.  
Cypher 쿼리 수정 없음.

---

## 6. 프론트엔드 변경 (task3.md 반영)

### 6-1. `ConceptNode` 타입 (F1 변경)

```typescript
// src/types/concept.ts

// 변경 전 (폐기)
export type ConceptDomain = "security" | "performance" | "both"

// 변경 후
export interface ConceptNode {
  ...
  domains: string[]    // ["security"], ["performance"], ["security","performance"], ["compliance"]
}

export interface DomainRegistryEntry {
  name:       string
  label_ko:   string
  color_hex:  string
  is_active:  boolean
}
```

### 6-2. `getDomainColor` — 동적 색상 매핑 (F1 변경)

```typescript
// src/utils/nodeStyler.ts

// 변경 전 (하드코딩 폐기)
// if (domain === "security") return "#1D9E75"
// if (domain === "performance") return "#BA7517"
// if (domain === "both") return "#534AB7"

// 변경 후 — DB에서 로드한 도메인 레지스트리 참조
export function getDomainColor(
  domains: string[],
  registry: DomainRegistryEntry[]
): string {
  if (domains.length > 1) return "#534AB7"  // 교차 도메인 = 보라 (고정)
  const entry = registry.find(r => r.name === domains[0])
  return entry?.color_hex ?? "#888780"       // 미등록 = 회색 fallback
}
```

### 6-3. DOMAIN_PENDING 노드 시각 처리 (F7, F10 변경)

```typescript
// 기존 NodeStatus에 DOMAIN_PENDING 추가
export type NodeStatus = "DRAFT" | "APPROVED" | "COMMITTED" | "REJECTED" | "DOMAIN_PENDING"

// nodeStyler.ts
case "DOMAIN_PENDING":
  return { opacity: 0.5, strokeDasharray: "8,4", color: "#BA7517" }  // 주황 점선
```

### 6-4. 도메인 레지스트리 서비스 (F3 추가)

```typescript
// src/services/domainService.ts
export const domainService = {
  getAll:    () => apiClient.get<DomainRegistryEntry[]>("/api/domains"),
  register:  (payload: NewDomainPayload) => apiClient.post("/api/domains", payload),
  getPending: () => apiClient.get<StagingRecord[]>("/api/staging/domain-pending"),
  resolve:   (id: string, body: ResolveDomainRequest) =>
               apiClient.post(`/api/staging/${id}/resolve-domain`, body),
}
```

---

## 7. TDD — 신규 테스트 명세

### T_domain_01: 알려진 도메인 → 즉시 적재

```python
def test_known_domains_proceed_to_graph_writer():
    # Arrange
    registered = {"security", "performance"}
    concept = make_concept(domain=["security"])
    # Act
    known, unknown = classify_domains(concept.concept_domain, registered)
    # Assert
    assert unknown == []
    assert known == ["security"]
```

### T_domain_02: 미등록 도메인 → DOMAIN_PENDING

```python
def test_unknown_domain_triggers_domain_pending(db_session, neo4j_session):
    # Arrange
    registered = {"security", "performance"}
    concept = make_concept(domain=["compliance"])   # 미등록
    # Act
    result = asyncio.run(write_concept_node(concept, neo4j_driver, conn))
    # Assert
    assert result == "domain_pending"
    # Neo4j에 적재 없음
    cnt = neo4j_session.run("MATCH (c:Concept {name:$n}) RETURN count(c) AS n",
                            n=concept.concept_name).single()["n"]
    assert cnt == 0
    # staging에 DOMAIN_PENDING 상태로 보관
    row = db_session.execute(
        "SELECT state, unknown_domains FROM staging_concepts WHERE state='DOMAIN_PENDING'"
    ).fetchone()
    assert row["state"] == "DOMAIN_PENDING"
    assert "compliance" in row["unknown_domains"]
```

### T_domain_03: 교차 도메인 — "both" 없이 배열로 처리

```python
def test_cross_domain_list_no_both_literal():
    # Arrange
    schema = ConceptExtractionSchema(
        concept_name="MemoryLeak",
        concept_domain=["security", "performance"],   # "both" 아님
        description_ko="메모리 누수",
        aliases=[],
    )
    # Assert
    assert "both" not in schema.concept_domain
    assert "security" in schema.concept_domain
    assert "performance" in schema.concept_domain
```

### T_domain_04: 신규 도메인 등록 후 DOMAIN_PENDING → COMMITTED

```python
def test_domain_registration_resolves_pending(db_session, neo4j_session):
    # Arrange — DOMAIN_PENDING 레코드 존재
    create_domain_pending_staging(conn, concept_domain=["compliance"])
    # Act — 관리자가 신규 도메인 등록
    asyncio.run(register_domain(conn, name="compliance", label_ko="규정 준수"))
    asyncio.run(resolve_domain_pending(conn, neo4j_driver, action="register",
                                       new_domain="compliance"))
    # Assert — Neo4j에 적재됨
    result = neo4j_session.run(
        "MATCH (c:Concept) WHERE 'compliance' IN c.domains RETURN c.name"
    ).data()
    assert len(result) >= 1
    # staging 상태 COMMITTED
    row = db_session.execute(
        "SELECT state FROM staging_concepts WHERE state='COMMITTED'"
    ).fetchone()
    assert row is not None
```

### T_domain_05: domain_registry DB 로드 → 런타임 반영

```python
def test_registered_domains_loaded_from_db(db_session):
    # Arrange — DB에 "compliance" 추가
    db_session.execute(
        "INSERT INTO domain_registry(name, label_ko) VALUES('compliance','규정 준수')"
    )
    # Act
    registered = asyncio.run(get_registered_domains(conn))
    # Assert
    assert "compliance" in registered
    assert "security" in registered      # 기존 도메인도 포함
```

### T_domain_06: 유사 도메인 추천

```python
def test_suggest_similar_domains():
    # Arrange
    registered = {"security", "performance", "compliance"}
    # Act
    suggestions = suggest_similar_domains("sec", registered, top_k=2)
    # Assert
    assert suggestions[0]["domain"] in {"security", "compliance"}  # 유사한 것이 상위
    assert suggestions[0]["similarity"] > suggestions[1]["similarity"]
```

---

## 8. 파일별 수정 요약

| 파일 | 수정 내용 | 우선순위 |
|------|-----------|---------|
| `PRD-schema.md` | `domain_registry` 테이블 추가, `staging_concepts` 컬럼 추가 | 즉시 |
| `prd_domain_db.md` | `concept_domain: list[str]` 변경, DOMAIN_PENDING 상태 추가, §3.6.4 교체 | 즉시 |
| `ontology_migration_guide.md` | §3 "Concept 도메인 귀속 표현" → 이 문서 참조로 교체 | 즉시 |
| `task.md` (Phase 1) | C1-Spec에 `domain_registry` 테이블 추가, T_domain_01~06 추가 | Phase 1 시작 전 |
| `task2.md` (Phase 2) | G8 SDD에서 `DOMAIN_LABEL_MAP` 제거, G7에 `/resolve-domain` API 추가 | G8 전 |
| `task3.md` (Phase 3) | F1 타입, F3 domainService, F10 DOMAIN_PENDING 노드 시각 처리 | F1/F3 전 |

---

## 9. 구현 순서 (의존성 기준)

```
[즉시]
  ① domain_registry 테이블 DDL 추가 (schema.sql)
  ② staging_concepts.unknown_domains 컬럼 추가
  ③ ConceptExtractionSchema.concept_domain → list[str]
  ④ mock_client.py "both" → ["security","performance"]

[Phase 1 — DB 태스크와 함께]
  ⑤ get_registered_domains() DB 로드 함수
  ⑥ classify_domains() 분기 로직
  ⑦ T_domain_01 ~ T_domain_06 테스트 작성 → RED → 구현 → GREEN

[Phase 2 — G8 전]
  ⑧ DOMAIN_LABEL_MAP 삭제 → concept.concept_domain 직접 전달
  ⑨ write_concept_node() DOMAIN_PENDING 분기
  ⑩ /api/domains, /api/staging/{id}/resolve-domain API

[Phase 3 — F1/F3 전]
  ⑪ ConceptNode.domains 타입, getDomainColor 동적 매핑
  ⑫ DomainRegistryEntry 타입, domainService
  ⑬ DOMAIN_PENDING 노드 시각 처리 (주황 점선)
  ⑭ S7 도메인 검토 UI (HITL)
```