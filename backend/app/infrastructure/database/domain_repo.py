"""도메인 레지스트리 DB 접근 + 도메인 분류 유틸리티 (task1_multi_domain §2~§4)."""

from difflib import SequenceMatcher


async def get_registered_domains(conn) -> set[str]:
    """DB에서 활성 도메인 목록 로드."""
    rows = await conn.fetch("SELECT name FROM domain_registry WHERE is_active = true")
    return {row["name"] for row in rows}


def classify_domains(concept_domains: list[str], registered: set[str]) -> tuple[list[str], list[str]]:
    """등록/미등록 도메인 분류. 반환: (known, unknown)."""
    known   = [d for d in concept_domains if d in registered]
    unknown = [d for d in concept_domains if d not in registered]
    return known, unknown


def suggest_similar_domains(unknown: str, registered: set[str], top_k: int = 3) -> list[dict]:
    """문자열 유사도 기반 도메인 추천."""
    scores = [
        {"domain": r, "similarity": round(SequenceMatcher(None, unknown, r).ratio(), 2)}
        for r in registered
    ]
    return sorted(scores, key=lambda x: x["similarity"], reverse=True)[:top_k]
