"""PR 코멘트 마크다운 생성 — LLM 모드 또는 휴리스틱 fallback.

API 키(OPENAI / ANTHROPIC / GOOGLE) 중 하나 있으면 LLM 호출,
없으면 메시지+suggestion을 그대로 마크다운 템플릿으로 조합한다.
호출 측은 어느 모드인지 신경 쓸 필요 없다 — 항상 같은 구조의 markdown string 반환.
"""
from __future__ import annotations

import os

from contracts import CombinedIssue

# severity → 이모지 매핑
_SEVERITY_EMOJI: dict[str, str] = {
    "Critical": "🔴",
    "Major": "🟡",
    "Minor": "🔵",
}

# skill_level → LLM 프롬프트 톤 힌트
_TONE_HINTS: dict[str, str] = {
    "junior": "자세한 설명, 예시 코드, 왜 문제인지, 다음 단계를 포함하세요.",
    "mid": "핵심과 개선안을 간결하게 설명하세요.",
    "senior": "한 줄 요약으로 핵심만 전달하세요.",
}


# ── 공개 함수 ──────────────────────────────────────────────────────────────────

def refine(
    issues: list[CombinedIssue],
    verdict: str,
    skill_level: str = "mid",
) -> str:
    """이슈 목록 → PR 코멘트 마크다운 문자열 반환.

    Args:
        issues: 집계된 CombinedIssue 목록.
        verdict: "lgtm" | "rework" | "escalate"
        skill_level: "junior" | "mid" | "senior" (LLM 모드일 때만 톤에 반영)

    Returns:
        GitHub PR 코멘트 본문으로 사용할 markdown string.
    """
    if not issues:
        return "## 🤖 자동 리뷰\n\n리뷰 통과 ✅"

    if _has_api_key():
        prompt = _build_prompt(issues, verdict, skill_level)
        return _call_llm(prompt)

    return _heuristic_refine(issues, verdict)


# ── 내부 함수 (테스트에서 patch 가능) ─────────────────────────────────────────

def _has_api_key() -> bool:
    """GOOGLE_API_KEY(Gemini)가 설정돼 있으면 True."""
    return bool(os.getenv("GOOGLE_API_KEY"))


def _build_header(verdict: str, issues: list[CombinedIssue]) -> str:
    major = sum(1 for i in issues if i.severity == "Major")
    minor = sum(1 for i in issues if i.severity == "Minor")
    return f"## 🤖 자동 리뷰 ({verdict} · Major {major} · Minor {minor})"


def _heuristic_refine(issues: list[CombinedIssue], verdict: str) -> str:
    """API 키 없을 때 — 메시지+suggestion을 마크다운 구조로 조합."""
    lines: list[str] = [_build_header(verdict, issues), ""]

    for issue in issues:
        emoji = _SEVERITY_EMOJI.get(issue.severity, "•")
        line_info = f"{issue.file}:{issue.line}" if issue.line is not None else issue.file
        lines.append(f"### {emoji} {issue.severity}: {issue.rule_id} ({line_info})")
        lines.append(issue.message)
        lines.append("")
        if issue.suggestion:
            lines.append(f"💡 {issue.suggestion}")
        lines.append("")

    return "\n".join(lines).rstrip()


def _build_prompt(
    issues: list[CombinedIssue],
    verdict: str,
    skill_level: str,
) -> str:
    """LLM에 보낼 프롬프트 구성."""
    tone = _TONE_HINTS.get(skill_level, _TONE_HINTS["mid"])
    header = _build_header(verdict, issues)

    issues_text = "\n".join(
        f"- [{i.severity}] {i.rule_id} ({i.file}:{i.line}): {i.message}. 제안: {i.suggestion}"
        for i in issues
    )

    template_example = (
        "### {emoji} {severity}: {rule_id} ({file}:{line})\n"
        "{message}\n\n"
        "💡 {suggestion}"
    )

    return (
        f"당신은 코드 리뷰 봇입니다. 대상 개발자 수준: {skill_level}.\n"
        f"톤 지침: {tone}\n\n"
        f"verdict: {verdict}\n"
        f"이슈 목록:\n{issues_text}\n\n"
        f"아래 마크다운 형식으로 PR 코멘트를 작성하세요:\n\n"
        f"{header}\n\n"
        f"{template_example}"
    )


def _call_llm(prompt: str) -> str:
    """실제 LLM API 호출 (Gemini 2.5 Flash) — 테스트에서 mock 대상."""
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        return ""

    import google.generativeai as genai  # type: ignore

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(os.getenv("LLM_MODEL", "gemini-2.5-flash"))
    response = model.generate_content(prompt)
    return response.text
