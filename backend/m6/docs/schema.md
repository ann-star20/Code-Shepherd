# schema.md — 하이브리드 스토리지 & 4-Layer 온톨로지 스펙

> 출처: `backend/scripts/seed/schema.sql`, `startup/02-setup-schema.cypher`, `backend/app/domain/models.py`. 수치는 **실제 코드 기준**.

## 2.1 4-Layer 온톨로지 개념 구조

| Layer | Neo4j 라벨 | 키 | 상위 관계 |
|-------|-----------|-----|----------|
| L1 Domain | `:Domain` | `name`(소문자) | — |
| L2 Concept | `:Concept` + 동적(`:Security`/`:Performance`) | `name`(=concept_name, UNIQUE) | `(c)-[:BELONGS_TO]->(d)` |
| L3 Mechanism | `:Mechanism` | `name`(snake_case) | `(c)-[:MITIGATED_BY]->(m)` |
| L3 Property | `:Property` | `unq_key`(snake_case) | `(c)-[:TUNED_BY]->(p)` |
| L3 RootCause | `:RootCause` | `name`(snake_case) | `(c)-[:CAUSED_BY]->(r)` |
| L3 Component | `:Component` | `name`(snake_case) | `(c)-[:AFFECTS]->(comp)` |
| L4 CodeExample | `:CodeExample` | `unq_id` | `(m)-[:HAS_EXAMPLE]->(ce)` |

- `domains` 배열 → `apoc.create.addLabels`로 L2에 동적 라벨 부여(`{"security":"Security","performance":"Performance"}`).
- 출처 추적: `(:Document)-[:REFERENCES]->(:Concept)`.

## 2.2 PostgreSQL DDL 핵심 요약 (`schema.sql`)

```sql
-- concepts: 개념 마스터 (듀얼 벡터)
name_vector  vector(1024)   -- 이름+aliases 융합 (3-Factor name 30%)
desc_vector  vector(1024)   -- 설명문 시맨틱 (3-Factor desc 30%)
domains TEXT[] NOT NULL,  aliases TEXT[] DEFAULT '{}'
-- HNSW: name(m=16, ef_construction=64) / desc(m=24, ef_construction=100), vector_cosine_ops

-- staging_concepts: DRAFT→APPROVED→COMMITTED
infer_action TEXT,            infer_confidence FLOAT DEFAULT 0.0   -- 최종 결합 점수
score_jaro_winkler FLOAT DEFAULT 0.0   -- 40%
score_name_vector  FLOAT DEFAULT 0.0   -- 30%
score_desc_vector  FLOAT DEFAULT 0.0   -- 30%
target_concept_name TEXT,    known_domains/unknown_domains TEXT[]

-- knowledge_documents: content_hash CHAR(8), etag TEXT
--   state CHECK IN (PENDING,CRAWLING,EXTRACTING,EXTRACTED,COMMITTED,FAILED)
-- domain_registry / framework_metadata(url_patterns[], supported_langs[], default_lang)
```
- 멱등성: 전 DDL `IF NOT EXISTS`, 영속 볼륨 마이그레이션은 `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`.

## 2.3 Neo4j 스키마 제약 조건 (Constraints)

- UNIQUE: `Domain.name`, `Concept.name`, `Mechanism.name`, `RootCause.name`, `Component.name`, `Property.unq_key`, `CodeExample.unq_id`.
- Fulltext: `concept_aliases_fulltext_idx`(alias 사전 dedup 조회용).

## ★ 보정점 (코드↔문서 불일치)

- ★ **벡터 차원 1024**: 코드(`vector(1024)`, `BAAI/bge-m3`)가 진실. 일부 구 PRD의 `768`은 **드리프트** — 이식 시 1024로 통일.
- ★ **score_metrics 유실 버그**: `hybrid_resolver.ResolveResult.score_metrics`가 `{jaro,name_vec,desc_vec}`를 0.0 기본값으로만 두고 재기록하지 않아, staging의 `score_jaro_winkler/name_vector/desc_vector`에 **0.0이 적재**됨. 최종 `infer_confidence`만 유효. → 컴포넌트 점수 역추적이 필요하면 `_resolve()`에서 dict 채워 반환하도록 수정.
