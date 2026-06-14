"""지식 그래프 쿼리 스키마."""

from pydantic import BaseModel


class GraphNode(BaseModel):
    id: str
    label: str
    properties: dict = {}


class GraphEdge(BaseModel):
    source: str
    target: str
    relation: str
    properties: dict = {}


class GraphQueryRequest(BaseModel):
    query: str
    limit: int = 50


class GraphQueryResponse(BaseModel):
    nodes: list[GraphNode]
    edges: list[GraphEdge]
    total: int
