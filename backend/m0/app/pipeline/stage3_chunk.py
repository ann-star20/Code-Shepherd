"""
Stage 3: 청킹 Agent (trc_0003)

Parent-Child 계층 청킹:
    Parent: 800~1500 tokens  — 의미적 완결성 우선 (RAG 상위 컨텍스트)
    Child:  300~500 tokens   — 정밀 검색용 (pgVector 임베딩 단위)

출력:
    state["chunks"]  ChunkItem 목록 (parent + child 모두 포함)
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING
from uuid import uuid4

if TYPE_CHECKING:
    from app.pipeline.models import ChunkItem, DocPipelineState

logger = logging.getLogger(__name__)

# 청크 크기 기준 (토큰 수 — tiktoken 기준 대략 1 token ≈ 4자)
PARENT_MIN_TOKENS = 800
PARENT_MAX_TOKENS = 1500
CHILD_MIN_TOKENS = 300
CHILD_MAX_TOKENS = 500

try:
    import tiktoken
except ImportError:
    tiktoken = None  # type: ignore[assignment]

_tiktoken_enc = None


# ---------------------------------------------------------------------------
# 토큰 수 추정 (tiktoken 없으면 근사치 사용)
# ---------------------------------------------------------------------------

def _get_tiktoken_encoder():
    """
    tiktoken 인코더를 싱글턴으로 반환한다.
    get_encoding()은 대용량 vocabulary 파일을 로드하므로
    청크마다 호출하면 파이프라인 전체 속도를 저하시킨다.
    """
    global _tiktoken_enc
    if tiktoken is None:
        return None
    if _tiktoken_enc is None:
        _tiktoken_enc = tiktoken.get_encoding("cl100k_base")
    return _tiktoken_enc


def _count_tokens(text: str) -> int:
    enc = _get_tiktoken_encoder()
    if enc is not None:
        return len(enc.encode(text))
    # tiktoken 없으면 한국어 기준 글자 수 / 2로 근사
    return max(1, len(text) // 2)


# ---------------------------------------------------------------------------
# Markdown → 섹션 분할
# ---------------------------------------------------------------------------

def _split_by_headers(markdown: str) -> list[tuple[str, str]]:
    """
    ## 또는 ### 헤더 기준으로 섹션 분리.
    반환: [(header, content), ...]

    첫 번째 헤더 이전의 내용(문서 제목, 메타 표 등)도 빈 헤더("")로 첫 섹션에 포함한다.
    """
    pattern = re.compile(r"^(#{1,3} .+)$", re.MULTILINE)
    positions = [(m.start(), m.group()) for m in pattern.finditer(markdown)]

    if not positions:
        return [("", markdown)]

    sections = []

    # 첫 번째 헤더 이전 내용 보존 (제목·커버 표 등)
    pre_header = markdown[: positions[0][0]].strip()
    if pre_header:
        sections.append(("", pre_header))

    for i, (pos, header) in enumerate(positions):
        start = pos + len(header)
        end = positions[i + 1][0] if i + 1 < len(positions) else len(markdown)
        content = markdown[start:end].strip()
        sections.append((header, content))

    return sections


def _extract_section_header(raw: str) -> str:
    """헤더 문자열에서 # 제거 후 반환."""
    return raw.lstrip("#").strip()


# ---------------------------------------------------------------------------
# Parent 청크 생성
# ---------------------------------------------------------------------------

def _make_parent_chunks(
    sections: list[tuple[str, str]],
    doc_id: str,
) -> list["ChunkItem"]:
    """
    섹션을 병합하여 PARENT_MIN_TOKENS ~ PARENT_MAX_TOKENS 범위의 Parent 청크 생성.
    범위를 초과하면 강제로 분할한다.
    여러 섹션이 병합될 때 section_header는 첫 번째 섹션 헤더를 사용한다.
    """
    parents: list["ChunkItem"] = []
    buffer: list[str] = []
    buffer_tokens = 0
    first_header = ""  # 현재 버퍼에서 첫 번째 섹션의 헤더

    def _flush() -> None:
        nonlocal buffer, buffer_tokens, first_header
        if not buffer:
            return
        text = "\n\n".join(buffer)
        parents.append(
            {
                "chunk_id": str(uuid4()),
                "doc_id": doc_id,
                "parent_chunk_id": None,
                "chunk_type": "parent",
                "content": text,
                "token_count": buffer_tokens,
                "page_number": None,
                "section_header": first_header or None,
            }
        )
        buffer = []
        buffer_tokens = 0
        first_header = ""

    # H1이 단독으로 비어있는 경우 다음 섹션의 부모 제목으로 전달
    pending_h1: str = ""

    for header, content in sections:
        level = len(header) - len(header.lstrip("#"))
        if not content:
            # 내용 없는 H1은 이후 섹션의 상위 제목으로 보존
            if level == 1:
                pending_h1 = _extract_section_header(header)
            continue

        tokens = _count_tokens(content)
        extracted = _extract_section_header(header)

        # 상위 H1이 있으면 "H1 > 현재제목" 형태로 컨텍스트 보강
        # 또한 H1 제목을 section_text 앞에 붙여 청크 내용에서 사라지지 않도록 함
        h1_prefix = ""
        if pending_h1 and level > 1:
            extracted = f"{pending_h1} > {extracted}" if extracted else pending_h1
            h1_prefix = f"# {pending_h1}\n\n"
            pending_h1 = ""  # 첫 번째 하위 섹션에만 적용, 이후는 초기화

        # 단일 섹션이 PARENT_MAX_TOKENS 초과 시 강제 분할
        if tokens > PARENT_MAX_TOKENS:
            _flush()
            for sub_chunk in _hard_split(content, PARENT_MAX_TOKENS, doc_id, header):
                parents.append(sub_chunk)
            continue

        # 버퍼 + 새 섹션이 PARENT_MAX_TOKENS 초과하면 먼저 flush
        if buffer_tokens + tokens > PARENT_MAX_TOKENS:
            _flush()

        if not buffer:
            # 새 버퍼의 첫 번째 섹션 헤더 기록
            first_header = extracted

        # 헤딩을 content에 포함시켜 임베딩 품질 보장
        # h1_prefix: 빈 content였던 H1 제목을 첫 번째 하위 청크 앞에 포함
        base_text = f"{header}\n\n{content}" if header else content
        section_text = h1_prefix + base_text if h1_prefix else base_text
        buffer.append(section_text)
        buffer_tokens += tokens

    _flush()
    return parents


def _split_sentences(text: str) -> list[str]:
    """텍스트를 문장 단위로 분리한다 (. ? ! 뒤 공백 기준).

    마침표 없는 텍스트는 단일 요소 리스트로 반환.
    빈 문자열은 빈 리스트 반환.
    """
    if not text:
        return []
    pattern = re.compile(r"(?<=[.?!])\s+")
    sentences = pattern.split(text)
    return [s.strip() for s in sentences if s.strip()]


def _hard_split(text: str, max_tokens: int, doc_id: str, header: str) -> list["ChunkItem"]:
    """단일 텍스트를 max_tokens 이하로 강제 분할. 문장 경계를 우선 존중한다.

    문장 단위로 버퍼를 채우다가 max_tokens 초과 시 청크로 flush.
    단일 문장이 max_tokens를 초과하면 단어 단위 fallback 분할.
    """
    section_header = _extract_section_header(header) or None
    chunks: list["ChunkItem"] = []
    sentences = _split_sentences(text) or [text]

    current: list[str] = []
    current_tokens = 0

    def _flush() -> None:
        nonlocal current, current_tokens
        if not current:
            return
        content = " ".join(current)
        chunks.append(
            {
                "chunk_id": str(uuid4()),
                "doc_id": doc_id,
                "parent_chunk_id": None,
                "chunk_type": "parent",
                "content": content,
                "token_count": current_tokens,
                "page_number": None,
                "section_header": section_header,
            }
        )
        current = []
        current_tokens = 0

    for sentence in sentences:
        sentence_tokens = _count_tokens(sentence)

        # 단일 문장이 max_tokens 초과 → 단어 단위 fallback
        if sentence_tokens > max_tokens:
            _flush()
            chunks.extend(_hard_split_words(sentence, max_tokens, doc_id, section_header))
            continue

        if current_tokens + sentence_tokens > max_tokens and current:
            _flush()

        current.append(sentence)
        current_tokens += sentence_tokens

    _flush()
    return chunks


def _hard_split_words(
    text: str, max_tokens: int, doc_id: str, section_header: str | None
) -> list["ChunkItem"]:
    """단어 단위 강제 분할 (문장 경계 없는 경우 fallback)."""
    chunks: list["ChunkItem"] = []
    words = text.split()
    current: list[str] = []
    current_tokens = 0

    for word in words:
        word_tokens = _count_tokens(word)
        if current_tokens + word_tokens > max_tokens and current:
            chunks.append(
                {
                    "chunk_id": str(uuid4()),
                    "doc_id": doc_id,
                    "parent_chunk_id": None,
                    "chunk_type": "parent",
                    "content": " ".join(current),
                    "token_count": current_tokens,
                    "page_number": None,
                    "section_header": section_header,
                }
            )
            current = []
            current_tokens = 0
        current.append(word)
        current_tokens += word_tokens

    if current:
        chunks.append(
            {
                "chunk_id": str(uuid4()),
                "doc_id": doc_id,
                "parent_chunk_id": None,
                "chunk_type": "parent",
                "content": " ".join(current),
                "token_count": current_tokens,
                "page_number": None,
                "section_header": section_header,
            }
        )
    return chunks


# ---------------------------------------------------------------------------
# Child 청크 생성
# ---------------------------------------------------------------------------

CHILD_COMPLIANCE_MIN = 100  # eval 준수 기준 하한 (CHILD_MIN_TOKENS=300과 별개)


def _merge_small_children(children: list["ChunkItem"]) -> list["ChunkItem"]:
    """
    100 토큰 미만 child를 인접 child와 병합한다.

    trailing 단락이 CHILD_MAX_TOKENS 초과로 인해 단독 flush될 때
    60 토큰 안팎의 비준수 child가 생기는 문제를 해소한다.
    병합 후 token_count가 CHILD_MAX_TOKENS * 3 (=1500) 이하이면 항상 준수 범위.
    """
    if len(children) <= 1:
        return children

    result: list["ChunkItem"] = []
    for child in children:
        if result and child["token_count"] < CHILD_COMPLIANCE_MIN:
            prev = result[-1]
            combined_tokens = prev["token_count"] + child["token_count"]
            # 1500 토큰(CHILD_COMPLIANCE_MAX) 이내면 병합
            if combined_tokens <= CHILD_MAX_TOKENS * 3:
                result[-1] = {
                    **prev,
                    "content": prev["content"] + "\n\n" + child["content"],
                    "token_count": combined_tokens,
                }
                continue
        result.append(child)

    # 첫 번째 child가 여전히 작으면 다음 child에 병합
    if len(result) >= 2 and result[0]["token_count"] < CHILD_COMPLIANCE_MIN:
        first = result.pop(0)
        combined_tokens = first["token_count"] + result[0]["token_count"]
        result[0] = {
            **result[0],
            "content": first["content"] + "\n\n" + result[0]["content"],
            "token_count": combined_tokens,
        }

    return result


def _make_child_chunks(
    parent: "ChunkItem",
) -> list["ChunkItem"]:
    """
    Parent 청크를 CHILD_MIN_TOKENS ~ CHILD_MAX_TOKENS 단위로 분할하여 Child 청크 생성.
    분할 후 100 토큰 미만 child는 인접 child와 병합한다.
    """
    content = parent["content"]
    parent_id = parent["chunk_id"]
    doc_id = parent["doc_id"]

    # 문단 기준으로 1차 분할
    paragraphs = [p.strip() for p in content.split("\n\n") if p.strip()]

    children: list["ChunkItem"] = []
    buffer: list[str] = []
    buffer_tokens = 0

    def _flush() -> None:
        nonlocal buffer, buffer_tokens
        if not buffer:
            return
        text = "\n\n".join(buffer)
        children.append(
            {
                "chunk_id": str(uuid4()),
                "doc_id": doc_id,
                "parent_chunk_id": parent_id,
                "chunk_type": "child",
                "content": text,
                "token_count": buffer_tokens,
                "page_number": parent.get("page_number"),
                "section_header": parent.get("section_header"),
            }
        )
        buffer = []
        buffer_tokens = 0

    for para in paragraphs:
        tokens = _count_tokens(para)
        if buffer_tokens + tokens > CHILD_MAX_TOKENS:
            _flush()
        buffer.append(para)
        buffer_tokens += tokens

    _flush()
    return _merge_small_children(children)


# ---------------------------------------------------------------------------
# Stage 3 노드 함수
# ---------------------------------------------------------------------------

async def stage3_chunk(state: "DocPipelineState") -> dict:
    """LangGraph 노드: Markdown을 Parent-Child 계층으로 청킹."""

    markdown = state.get("validated_markdown") or ""
    doc_id = state["doc_id"]

    if not markdown:
        logger.error("Stage 3: validated_markdown이 없음", extra={"doc_id": doc_id})
        return {
            "chunks": [],
            "status": "failed",
            "error": "Stage3: validated_markdown 없음",
            "current_stage": "stage3_chunk",
        }

    sections = _split_by_headers(markdown)
    parent_chunks = _make_parent_chunks(sections, doc_id)

    all_chunks: list["ChunkItem"] = []
    for parent in parent_chunks:
        all_chunks.append(parent)
        children = _make_child_chunks(parent)
        all_chunks.extend(children)

    # 문서 순서를 보장하는 인덱스 부여 (page_number = None인 DOCX 청크 정렬용)
    for i, chunk in enumerate(all_chunks):
        chunk["chunk_index"] = i

    logger.info(
        "Stage 3 완료",
        extra={
            "doc_id": doc_id,
            "parent_count": len(parent_chunks),
            "child_count": len(all_chunks) - len(parent_chunks),
        },
    )

    return {
        "chunks": all_chunks,
        "current_stage": "stage3_chunk",
    }
