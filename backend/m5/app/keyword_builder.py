from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

_LABELS_CASE_A = {
    1: "프레임워크 맞춤형",
    2: "언어별 가이드",
    3: "컴포넌트 취약점",
    4: "핵심 매커니즘",
    5: "기본 개념",
}

_LABELS_CASE_B = {
    1: "개념+매커니즘 방어",
    2: "컴포넌트 취약점",
    3: "보안 표준 분석",
    4: "원인 분석",
    5: "기본 개념",
}

def build_query(*args):
    return " ".join(arg.strip() for arg in args if arg and arg.strip())

def build_queries(
    concept_name: str,
    mechanism_name: str | None,
    code_lang: str | None,
    code_framework: str | None,
    cwe_id: str | None,
    owasp_id: str | None,
    affected_components: list[str],
) -> tuple[list[str], dict[int, str]]:
    """5개 YouTube 검색 쿼리와 랭킹 레이블을 반환한다."""
    concept_query = concept_name.replace("_", " ") if concept_name else ""
    components_str = " ".join(c.replace("_", " ").strip() for c in affected_components if c)
    components = components_str if components_str else concept_query
    has_code = bool(code_lang or code_framework)
    mech_query = mechanism_name.replace("_", " ") if mechanism_name else ""
    if has_code:
        fw = code_framework or code_lang or ""
        lang = code_lang or code_framework or ""
        mech = mech_query or ""
        raw = [
            build_query(fw, concept_query, mech, "구현 방어"),
            build_query(lang, concept_query, "실전 예제"),
            build_query(components, concept_query, "취약점"), # 수정
            build_query(concept_query, mech, "개념"),        # 수정
            build_query(concept_query, "취약점 공격 원리 총정리"), # 수정
        ]
        labels = _LABELS_CASE_A
    else:
        cwe_owasp = " ".join(x for x in [cwe_id, owasp_id] if x)
        if mechanism_name:
            q1 = build_query(concept_query, mech_query, "방어 대책")
            q4 = build_query(concept_query, mech_query, "원리")
        else:
            q1 = build_query(cwe_owasp, concept_query, "보안 표준 분석")
            q4 = build_query(concept_query, "취약점 근본 원인 분석")
        raw = [
            q1,
            build_query(components_str, "구조에서 발생하는", concept_query, "취약점") if components_str else build_query(concept_query, "발생 구조 및 취약점"),
            build_query(cwe_owasp, concept_query, "분석"),
            q4,
            build_query(concept_query, "취약점 공격 원리 총정리"),
        ]
        labels = _LABELS_CASE_B

    seen: set[str] = set()
    queries: list[str] = []
    for q in raw:
        q = q.strip()
        if q and q not in seen:
            seen.add(q)
            queries.append(q)
        if len(queries) == 5:
            break

    final_labels = {i + 1: labels.get(i + 1, "관련 영상") for i in range(len(queries))}
    logger.debug(f"Built queries for {concept_name}: {queries} with labels: {final_labels}")
    
    return queries, final_labels

