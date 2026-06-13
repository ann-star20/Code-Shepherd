"""RAG 검색 어댑터 — SearchAdapter 인터페이스(D33) + embed_query + 검색 텍스트 빌더 (Section 5)."""

import json
import os
from abc import ABC, abstractmethod

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.review_issue import ReviewIssue


def build_search1_text(issue: ReviewIssue) -> str:
    """검색1 — keyword + sub_category + code_context → security_guide(개념 설명) 검색용."""
    parts = []
    if issue.keyword:
        parts.append(f"keyword: {issue.keyword}")
    if issue.sub_category:
        parts.append(f"sub_category: {issue.sub_category}")
    if issue.code_context:
        parts.append(f"code_context: {issue.code_context}")
    return " ".join(parts)


def build_search2_text(issue: ReviewIssue) -> str:
    """검색2 — keyword + sub_category + code_snippet(있으면) + language/framework/version → coding_convention 검색용."""
    parts = []
    if issue.keyword:
        parts.append(f"keyword: {issue.keyword}")
    if issue.sub_category:
        parts.append(f"sub_category: {issue.sub_category}")
    if issue.code_snippet:
        parts.append(f"code_snippet: {issue.code_snippet[:300]}")
    if issue.programming_language:
        parts.append(f"language: {issue.programming_language}")
    if issue.framework:
        parts.append(f"framework: {issue.framework}")
    if issue.framework_version:
        parts.append(f"version: {issue.framework_version}")
    return " ".join(parts)


def build_search3_text(issue: ReviewIssue) -> str:
    """검색3 — keyword + sub_category + language/framework/version + code_snippet(있으면) → learning_resource 검색용."""
    parts = []
    if issue.keyword:
        parts.append(f"keyword: {issue.keyword}")
    if issue.sub_category:
        parts.append(f"sub_category: {issue.sub_category}")
    if issue.programming_language:
        parts.append(f"language: {issue.programming_language}")
    if issue.framework:
        parts.append(f"framework: {issue.framework}")
    if issue.framework_version:
        parts.append(f"version: {issue.framework_version}")
    if issue.code_snippet:
        parts.append(f"code_snippet: {issue.code_snippet[:300]}")
    return " ".join(parts)


async def embed_query(query_text: str) -> list[float]:
    """bge-m3(Ollama) 쿼리 임베딩 — 1024차원. KMS 문서 임베딩(scripts/embed_kms_docs.py)과 동일 모델 사용 필수."""
    base_url = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
    model = os.environ.get("OLLAMA_EMBEDDING_MODEL", "bge-m3")
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            f"{base_url}/api/embeddings",
            json={"model": model, "prompt": query_text},
        )
        response.raise_for_status()
        return response.json()["embedding"]


class SearchAdapter(ABC):
    """RAG 검색 백엔드 인터페이스 (D33). Phase 1: PgvectorAdapter, 추후 FTS/Hybrid로 교체 가능 (pipeline 코드 변경 없음)."""

    @abstractmethod
    async def search(self, embedding: list[float], category: str | None = None, limit: int = 3) -> list[dict]:
        ...


class PgvectorAdapter(SearchAdapter):
    """chunk_embeddings 테이블 코사인 유사도 검색 + metadata.category JSONB 필터 (D33 Phase 1 구현체)."""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def search(self, embedding: list[float], category: str | None = None, limit: int = 5) -> list[dict]:
        if not embedding:
            return []
        vector_literal = "[" + ",".join(str(v) for v in embedding) + "]"
        params: dict = {"embedding": vector_literal, "limit": limit}
        category_clause = ""
        if category:
            category_clause = "WHERE metadata @> CAST(:category_filter AS JSONB)"
            params["category_filter"] = json.dumps({"category": category})

        stmt = text(
            f"""
            SELECT content, metadata, 1 - (embedding <=> CAST(:embedding AS vector)) AS similarity
            FROM chunk_embeddings
            {category_clause}
            ORDER BY embedding <=> CAST(:embedding AS vector)
            LIMIT :limit
            """
        )
        result = await self._session.execute(stmt, params)
        return [dict(row) for row in result.mappings().all()]


async def rag_search(adapter: SearchAdapter, embedding: list[float], category: str) -> list[dict] | None:
    """D15 — category 필터 검색 결과가 2개 미만이면 필터를 제거하고 1회 재시도한다.

    재시도 후에도 결과가 비어 있으면 None을 반환해 LLM 자체 생성 fallback 신호로 사용한다.
    """
    results = await adapter.search(embedding, category=category)
    if len(results) < 2:
        results = await adapter.search(embedding, category=None)
    return results or None
