"""검색결과 → 코멘트용 rag_context 포맷 (정성 가이드만, RAG 설계서 §5ⓑ·§6).

미들웨어 역할: 탐지된 이슈의 message로 사내 가이드를 검색해 issue.rag_context를 채운다.
출력 계약(AgentOutput)은 불변 — Issue의 선택 필드 rag_context만 채움.
정량 판정(커버리지% 등)엔 절대 관여하지 않는다.
"""
from __future__ import annotations

from contracts import Issue
from rag.retriever import search_convention


def format_context(docs: list[dict]) -> str:
    """검색 문서 조각들을 코멘트에 인용할 문자열로 포맷. 없으면 빈 문자열."""
    if not docs:
        return ""
    blocks: list[str] = []
    for d in docs:
        title = d.get("doc_title") or "사내 가이드"
        url = d.get("source_url") or ""
        content = (d.get("content") or "").strip()
        head = f"📖 [{title}]({url})" if url else f"📖 {title}"
        blocks.append(f"{head}\n{content}" if content else head)
    return "\n\n".join(blocks)


def augment_issues(issues: list[Issue], search=search_convention) -> None:
    """각 이슈 message로 사내 가이드를 검색해 issue.rag_context를 채운다(제자리 수정).

    search는 주입 가능(테스트용). 검색 실패/결과없음 → rag_context는 빈 문자열로 남음.
    """
    for issue in issues:
        docs = search(issue.message)  # 위험 4: message 통째로
        issue.rag_context = format_context(docs)
