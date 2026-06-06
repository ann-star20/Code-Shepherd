"""
prompts/comment_refine.py — 파이프라인 2 PR 코멘트 프롬프트 (PRD 노드 M)

개발자 수준(skill_level)에 맞춰 GitHub PR 코멘트를 생성하기 위한 프롬프트를 조립한다.
aggregate_node가 취합한 전체 이슈 + 요약 + KMS 문서 chunk_id를 주입한다.

CLAUDE.md 준수:
    §4   skill_level: junior | mid | senior 기반 개인화
    §5-C learning_resources(KMS 링크)는 Dev4(M4) 담당 — 여기서는 chunk_id만 참조 정보로 전달
"""

# 개발자 수준별 코멘트 작성 지침
LEVEL_GUIDE = {
    "junior": "왜 문제인지 이유와 수정 예시 코드를 반드시 포함하세요.",
    "mid":    "문제 원인과 관련 패턴을 설명하세요. 코드 예시는 선택.",
    "senior": "이슈 목록과 핵심 포인트만 간결하게 작성하세요.",
}


def build_comment_prompt(
    issues: list[dict],
    summary: dict,
    skill_level: str,
    tech_stack: list[str],
    architecture_docs: list[str],
    previous_pr_issues: list[str],
) -> str:
    """
    수준별 PR 코멘트 생성 프롬프트를 조립한다.

    Args:
        issues: aggregate_node가 정렬한 전체 이슈 목록
        summary: {"critical": n, "major": n, "minor": n}
        skill_level: junior | mid | senior
        tech_stack: 개발자 기술 스택
        architecture_docs: 참조 가능 KMS chunk_id 목록
        previous_pr_issues: 과거 반복 이슈

    Returns:
        LLM에 전달할 프롬프트 문자열
    """
    level_guide = LEVEL_GUIDE.get(skill_level, LEVEL_GUIDE["junior"])
    issue_lines = "\n".join(
        f"- [{i.get('severity', '?')}] {i.get('file', '?')}:{i.get('line', '?')} "
        f"({i.get('agent', '?')}) — {i.get('message', '')} / 제안: {i.get('suggestion', '')}"
        for i in issues
    )
    prev = ", ".join(previous_pr_issues) if previous_pr_issues else "없음"
    docs = ", ".join(architecture_docs) if architecture_docs else "없음"

    return f"""당신은 신입 개발자 코드 리뷰 전문가입니다.

[개발자 수준]: {skill_level}
[작성 지침]: {level_guide}
[기술 스택]: {", ".join(tech_stack)}
[과거 반복 이슈]: {prev}
[참조 가능 KMS chunk_id]: {docs}

[분석 결과]
Critical: {summary.get("critical", 0)}건 | Major: {summary.get("major", 0)}건 | Minor: {summary.get("minor", 0)}건

[이슈 목록]
{issue_lines if issue_lines else "이슈 없음"}

위 정보를 바탕으로 GitHub PR 코멘트를 마크다운으로 작성하세요.
구조: ## 자동 코드 리뷰 결과 → Critical 섹션 → Major 섹션 → Minor 섹션 → 관련 문서 링크
"""
