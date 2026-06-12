"""
comment_builder.py — GitHub PR 코멘트 생성 프롬프트 빌더

이 모듈은 LLM에 전달할 프롬프트 문자열만 생성한다. LLM을 직접 호출하지 않는다.
→ 테스트 용이성: LLM/API 없이 순수 Python으로 테스트 가능

프롬프트 구성 요소:
    ① 개발자 수준(skill_level)에 따른 설명 톤 지정
    ② 이슈 목록 (severity / file / line / message / suggestion)
    ③ Structured Output: 마크다운 형식 강제
"""


def build_comment_prompt(
    issues: list[dict],
    skill_level: str,
    pr_id: str,
) -> str:
    """
    LLM에 전달할 PR 코멘트 생성 프롬프트를 조립한다.

    Args:
        issues: enriched 이슈 목록 (severity / file / line / message / suggestion 포함)
        skill_level: 개발자 수준 ("junior" | "mid" | "senior")
        pr_id: GitHub PR 번호 (컨텍스트용)

    Returns:
        LLM에 전달할 완성된 프롬프트 문자열
    """
    tone_guide = {
        "junior": "초보 개발자도 이해할 수 있도록 쉬운 말로, 왜 문제인지 배경부터 설명하고 구체적인 수정 예시를 포함하라.",
        "mid": "중급 개발자 수준으로, 핵심 원인과 수정 방법을 간결하게 설명하라.",
        "senior": "시니어 개발자 수준으로, 기술적 맥락과 트레이드오프 중심으로 간략히 설명하라.",
    }.get(skill_level, "적절한 수준으로 설명하라.")

    if not issues:
        return ""

    issues_text = ""
    for i, issue in enumerate(issues, 1):
        issues_text += (
            f"\n이슈 {i})\n"
            f"  심각도: {issue.get('severity', '?')}\n"
            f"  파일: {issue.get('file', '?')} (라인 {issue.get('line', '?')})\n"
            f"  내용: {issue.get('message', '?')}\n"
            f"  제안: {issue.get('suggestion', '?')}\n"
        )

    return f"""당신은 코드 리뷰 코멘트를 작성하는 AI입니다.
아래 이슈 목록을 바탕으로 PR #{pr_id}에 달 GitHub 코멘트를 마크다운 형식으로 작성하라.

[개발자 수준]
{skill_level} — {tone_guide}

[발견된 이슈]
{issues_text}

[작성 규칙]
- 마크다운 형식으로 작성 (## 제목, - 항목, 코드블록 활용)
- Critical 이슈는 🚨, Major는 ⚠️, Minor는 ℹ️ 이모지로 구분
- 각 이슈마다 파일명과 라인 번호 명시
- 수정 방법을 코드 예시와 함께 제시
- 마지막에 전체 요약 한 줄 추가
- 친근하고 건설적인 톤 유지

마크다운 코멘트만 출력하라. 다른 설명은 붙이지 마라."""
