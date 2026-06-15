"""Neo4j 지식 그래프 CRUD — 스텁."""

from app.schemas.graph import GraphEdge, GraphNode


async def upsert_document_node(doc_id: str, title: str, url: str) -> None:
    """KG_Document 노드 생성/업데이트 (스텁)."""
    # TODO: MERGE (d:KG_Document {id: $doc_id}) SET d.title=$title, d.url=$url
    pass


async def upsert_entity_node(entity_id: str, name: str, entity_type: str) -> None:
    """KG_Entity 노드 생성/업데이트 (스텁)."""
    # TODO: MERGE (e:KG_Entity {id: $entity_id}) SET e.name=$name, e.type=$type
    pass


async def create_relation(source_id: str, target_id: str, relation: str) -> None:
    """두 노드 간 관계 생성 (스텁)."""
    # TODO: MATCH (a {id:$src}),(b {id:$tgt}) MERGE (a)-[:KG_RELATION {type:$rel}]->(b)
    pass


async def query_graph(query: str, limit: int) -> tuple[list[GraphNode], list[GraphEdge]]:
    """키워드 기반 그래프 서브셋 조회 (스텁)."""
    # TODO: MATCH path = (n:KG_Entity)-[r]-(m) WHERE n.name CONTAINS $query RETURN path LIMIT $limit
    return [], []
