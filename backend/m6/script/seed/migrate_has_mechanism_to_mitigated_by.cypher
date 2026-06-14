// migrate_has_mechanism_to_mitigated_by.cypher
// 기존 (c:Concept)-[:HAS_MECHANISM]->(m:Mechanism) 엣지를 MITIGATED_BY로 정합 (docs/schema.md §2.1).
// 멱등: 이미 변환된 환경에서 재실행해도 안전 (MATCH 결과가 없으면 변경 없음).

MATCH (c:Concept)-[old:HAS_MECHANISM]->(m:Mechanism)
MERGE (c)-[:MITIGATED_BY]->(m)
DELETE old;
