"""[임시 점검용 — 필요 없어지면 삭제] RAG 검색 단계만 따로 호출해서
어떤 KMS 문서 청크가 검색됐는지(content/유사도/출처) 직접 눈으로 확인한다.

generate_card()는 검색 결과를 카드 생성에만 쓰고 저장하지 않으므로,
"검색이 잘 되고 있는지/보강이 필요한지" 판단하려면 이렇게 검색 단계만 떼서
점검해야 한다.

[삭제 가능 시점] T17(AgentHarness/LangSmith 통합, BACKEND_SPEC.md)이 완료되면
generate_card() 호출마다 검색된 문서/유사도/프롬프트가 LangSmith 트레이스에
영구적으로 자동 기록되므로, 이렇게 매번 스크립트를 실행해서 눈으로 확인할
필요가 없어진다 — 그때 이 파일은 통째로 지워도 된다.
"""

import asyncio
import sys
import uuid
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[3] / ".env")

from sqlalchemy import select

from app.kms.search_adapter import (
    PgvectorAdapter,
    build_search1_text,
    build_search2_text,
    build_search3_text,
    embed_query,
    rag_search,
)
from app.models.review_issue import ReviewIssue
from shared.config import get_settings
from shared.db import create_engine_from_url, create_session_factory

CATEGORIES = [
    ("security_guide", build_search1_text),
    ("coding_convention", build_search2_text),
    ("learning_resource", build_search3_text),
]


def _print_docs(label: str, query_text: str, docs: list[dict] | None) -> None:
    print(f"\n--- [{label}] 검색 쿼리 텍스트 ---")
    print(query_text)
    print(f"--- [{label}] 검색 결과: {0 if docs is None else len(docs)}건 ---")
    if not docs:
        print("  (없음 → llm_fallback 후보)")
        return
    for i, doc in enumerate(docs, 1):
        print(f"  [{i}] similarity={doc.get('similarity'):.4f}  metadata={doc.get('metadata')}")
        print(f"      content: {doc.get('content', '')[:120]}...")


async def main(issue_id: uuid.UUID | None) -> None:
    settings = get_settings()
    engine = create_engine_from_url(settings.database_url)
    sf = create_session_factory(engine)

    async with sf() as session:
        if issue_id is not None:
            issue = await session.get(ReviewIssue, issue_id)
        else:
            result = await session.execute(select(ReviewIssue).order_by(ReviewIssue.created_at.desc()).limit(1))
            issue = result.scalars().first()

        if issue is None:
            print("review_issue를 찾지 못했습니다.")
            await engine.dispose()
            return

        print(f"issue: id={issue.id} keyword={issue.keyword} severity={issue.severity}")
        adapter = PgvectorAdapter(session)

        for category, build_text in CATEGORIES:
            query_text = build_text(issue)
            embedding = await embed_query(query_text)
            docs = await rag_search(adapter, embedding, category=category)
            _print_docs(category, query_text, docs)

    await engine.dispose()


if __name__ == "__main__":
    raw_id = sys.argv[1] if len(sys.argv) > 1 else None
    parsed_id = uuid.UUID(raw_id) if raw_id else None
    asyncio.run(main(parsed_id))
