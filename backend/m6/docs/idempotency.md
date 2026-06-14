# idempotency.md — 그래프 DB 멱등성 Upsert/Append & 3-Factor 중복 검사

> 출처: `backend/app/adapters/db/neo4j_repo.py`, `backend/app/infrastructure/graph/hybrid_resolver.py`, `neo4j_service.py`.

## 3.1 멱등성 보장 노드/관계 갱신 가이드

- 모든 노드는 **자연키 `MERGE`** (속성 매칭): `MERGE (c:Concept {name:$name})`. 반복 실행해도 단일 노드.
- 단일값 필드(severity, cwe_id 등): `ON MATCH SET`으로 **덮어쓰기(Overwrite)**.
- 리스트 필드(aliases, domains): `apoc.coll.toSet(c.aliases + $aliases)`로 **Append+Dedup**(중복 누적 차단).
- 동적 라벨: `apoc.create.addLabels(c, $labels)` — `:Security:Security` 같은 중복 방지.
- 관계도 `MERGE`로 생성(`MERGE (c)-[:MITIGATED_BY]->(m)`) → 엣지 중복 방지.

## 3.2 3-Factor 유사도 검사 및 중복 체크 메커니즘

```
Score = JaroWinkler×0.4 + Cosine(name_vector)×0.3 + Cosine(desc_vector)×0.3
```
- `MERGE_THRESHOLD = 0.88`, `RELATED_THRESHOLD = 0.72` (`hybrid_resolver.py`).
- Jaro-Winkler: aliases 풀 1:1 비교 **최고점**(대소문자 무시, prefix p=0.1, 4글자).
- 코사인: L2 정규화 벡터 내적.
- **사전 dedup 단축경로**: incoming alias가 PG `aliases` 배열에 정확 일치 시 score=1.0 즉시 MERGE(벡터 연산 생략).
- **Centroid Shifting**(`_do_merge`): MERGE 확정 시 기존+신규 alias 풀을 **재임베딩**하여 PG `name_vector` UPDATE(중심점 이동) + `description_ko`는 `COALESCE`로 보강.

## 3.3 스테이징(Staging) 결정 트리 매트릭스

| Score | infer_action | 동작 |
|-------|-------------|------|
| ≥ 0.88 | `MERGE` | 기존 마스터에 병합 + Centroid Shifting + 4-Layer 보강 |
| 0.72 ≤ s < 0.88 | `RELATED_TO` | 신규 노드 생성 후 `[:RELATED_TO]` 의미선 연결 |
| < 0.72 | `NEW` | 독립 마스터 노드 신규 생성 |

> 구형 `SAME_AS` 엣지는 **완전 폐기**.

## 3.4 Lang/Framework/Version별 CodeExample 관리 기법

- 복합키 `unq_id = f"{mechanism}_{lang}_{lang_version}_{framework}_{framework_version}"` — **Graph Writer가 생성**(LLM 아님).
- `MERGE (ce:CodeExample {unq_id:$unq_id})` → 동일 버전 중복 노드 차단, 신규 버전은 별도 노드로 **Append**.
- Mechanism→CodeExample 은 1:N.

## ★ 버그 방지 및 누락 제거 요건

- ★ **MERGE 4-Layer 재적용 중복**: MERGE 액션에서도 4-Layer MERGE가 재실행되어 alias/domains를 재적용함(멱등하나 불필요 비용). 핫패스면 라벨/배열 갱신만 분리 권장.
- ★ **관계 누락 방지**: RELATED_TO는 NEW 노드 **생성 이후** 엣지 생성 순서 보장(노드 미존재 시 엣지 유실).
- ★ **Centroid Shifting 무결성**: 재임베딩 실패 시 트랜잭션 롤백으로 PG/Neo4j alias 풀 불일치 방지.
- ★ **컴포넌트 점수 0.0**: §schema.md 참조 — 역추적 필요 시 score_metrics 기록 보완.
