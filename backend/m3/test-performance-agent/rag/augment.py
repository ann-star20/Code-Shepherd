"""검색결과 → 코멘트용 rag_context 포맷 (정성 가이드만, RAG 설계서 §5ⓑ·§6).

미들웨어 역할: 탐지된 이슈의 message로 사내 가이드를 검색해 issue.rag_context를 채운다.
출력 계약(AgentOutput)은 불변 — Issue의 선택 필드 rag_context만 채움.
정량 판정(커버리지% 등)엔 절대 관여하지 않는다.
"""
from __future__ import annotations

from contracts import Issue
from harness import instrument
from rag.retriever import search_convention

_SUMMARY_MAX = 120  # 인용 요약 최대 글자 수 (SESSION F1 §2-B)


def _first_sentence(text: str) -> str:
    """content에서 첫 '산문' 문장을 최대 _SUMMARY_MAX자로 잘라 반환.

    마크다운 제목 줄(#…)과 빈 줄은 건너뛴다 — 제목은 📖 줄이 이미 보여주므로
    같은 제목을 두 번 인용하지 않는다(F1 중복 인용 방지). 산문이 없으면 빈 문자열.
    """
    lines = text.strip().splitlines()
    start = 0
    # YAML 머리말(--- … ---) 블록 건너뛰기 — KMS 업로드 청크가 머리말로 시작할 수 있음
    if lines and lines[0].strip() == "---":
        closing = next(
            (j for j in range(1, len(lines)) if lines[j].strip() == "---"), None
        )
        start = (closing + 1) if closing is not None else 1
    for line in lines[start:]:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        dot_idx = line.find(". ")
        if dot_idx >= 0:
            line = line[: dot_idx + 1].strip()
        return line[:_SUMMARY_MAX]
    return ""


def format_context(docs: list[dict]) -> str:
    """검색 문서 조각들을 코멘트에 인용할 문자열로 포맷. 없으면 빈 문자열.

    top-1 문서만 인용, 요약 한 줄(≤120자)로 제한 — SESSION F1 §2-B.
    가짜 링크 금지: source_url 없으면 텍스트 제목만.
    """
    if not docs:
        return ""
    d = docs[0]  # top-1만 인용 (검색은 top_k 유지, 인용은 가장 관련 높은 1개)
    title = d.get("doc_title") or "사내 가이드"
    url = d.get("source_url") or ""
    content = (d.get("content") or "").strip()
    head = f"📖 [{title}]({url})" if url else f"📖 {title}"
    summary = _first_sentence(content)
    return f"{head}\n{summary}" if summary else head


@instrument("rag")
def augment_issues(issues: list[Issue], search=search_convention) -> None:
    """각 이슈 message로 사내 가이드를 검색해 issue.rag_context를 채운다(제자리 수정).

    search는 주입 가능(테스트용). 검색 실패/결과없음 → rag_context는 빈 문자열로 남음.
    """
    for issue in issues:
        docs = search(issue.message)  # 위험 4: message 통째로
        issue.rag_context = format_context(docs)
