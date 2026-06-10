"""PR 코멘트 마크다운 생성 — '리뷰 판정 + 이슈 표' (7C).

확정된 코멘트 모양 (LLM 모드·휴리스틱 모드 둘 다 동일 구조):
  1) 헤더: 🤖 코드 리뷰 — verdict 라벨 + 왜(한 줄) + severity 카운트
  2) 이슈 표: | 심각도 | 규칙 | 위치 | 고칠 방향(suggestion) | 사내 규칙(rag_context|—) |
  3) 맨 아래: 리뷰 대시보드 링크 한 줄

구조(헤더 틀·표·📖 인용·대시보드 링크)는 항상 코드가 결정한다. LLM(키 있을 때)은
'왜(한 줄)'만 작성하며, 실패·쿼터(429)·빈 응답이면 휴리스틱 한 줄로 fallback한다 →
어느 모드든 같은 표/📖 구조가 나온다.

리뷰 앵글(판정·규칙·지표)만 담는다. 개념 설명·코드 스니펫·학습 추천은 넣지 않는다(dev4 영역).
사내 규칙 칸은 rag_context(Dev3가 검색·포맷)를 그대로 인용 — 링크는 있을 때만(가짜 링크 금지).
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

# verdict → 헤더 라벨(원시 verdict 문자열은 별도로 함께 표기)
_VERDICT_LABEL: dict[str, str] = {
    "lgtm": "✅ 통과",
    "rework": "🔧 수정 요청",
    "escalate": "⛔ 시니어 검토 필요",
}

# skill_level → LLM '왜 한 줄' 톤 힌트
_TONE_HINTS: dict[str, str] = {
    "junior": "왜 문제인지 한 줄로 친절하게 설명하세요.",
    "mid": "핵심 이유만 한 줄로 간결하게.",
    "senior": "한 줄 요약으로 핵심만.",
}

_PASS_MESSAGE = "## 🤖 코드 리뷰\n\n리뷰 통과 ✅"
_TABLE_HEADER = "| 심각도 | 규칙 | 위치 | 고칠 방향 | 사내 규칙 |"
_TABLE_SEP = "|---|---|---|---|---|"
_DEFAULT_DASHBOARD_URL = "http://localhost:5173/review"


# ── 공개 함수 ──────────────────────────────────────────────────────────────────

def refine(
    issues: list[CombinedIssue],
    verdict: str,
    skill_level: str = "mid",
    metrics: dict | None = None,
) -> str:
    """이슈 목록 → PR 코멘트 마크다운 문자열 반환.

    Args:
        issues: 집계된 CombinedIssue 목록.
        verdict: "lgtm" | "rework" | "escalate"
        skill_level: "junior" | "mid" | "senior" (LLM '왜 한 줄' 톤에만 반영)
        metrics: 측정 지표(선택) — {"coverage_pct": NN, "max_complexity": NN}.
            있으면 헤더 아래 '📊 …' 한 줄로 렌더. 없으면 생략(가짜 숫자 금지) — 7D.

    Returns:
        GitHub PR 코멘트 본문으로 사용할 markdown string (항상 반환).
    """
    if not issues:
        return _PASS_MESSAGE

    why = _heuristic_why(issues, verdict)  # 기본값(키 없음·LLM 실패 시 사용)
    if _has_api_key():
        llm_why = _llm_why(issues, verdict, skill_level)
        if llm_why:
            why = llm_why

    return _render(issues, verdict, why, metrics)


# ── 내부 함수 (테스트에서 patch 가능) ─────────────────────────────────────────

def _has_api_key() -> bool:
    """GOOGLE_API_KEY(Gemini)가 설정돼 있으면 True."""
    return bool(os.getenv("GOOGLE_API_KEY"))


def _dashboard_url() -> str:
    """리뷰 대시보드 URL — 환경값, 없으면 데모용 localhost(가짜 도메인 하드코딩 금지)."""
    return os.getenv("REVIEW_DASHBOARD_URL", _DEFAULT_DASHBOARD_URL)


def _heuristic_refine(
    issues: list[CombinedIssue], verdict: str, metrics: dict | None = None
) -> str:
    """LLM 없이(또는 fallback) 같은 표 구조로 렌더 — main.py fallback 경로가 직접 호출."""
    if not issues:
        return _PASS_MESSAGE
    return _render(issues, verdict, _heuristic_why(issues, verdict), metrics)


def _render(
    issues: list[CombinedIssue], verdict: str, why: str, metrics: dict | None = None
) -> str:
    """헤더 + (지표 줄) + 이슈 표 + 대시보드 링크 (구조는 항상 코드가 결정)."""
    label = f"{_VERDICT_LABEL.get(verdict, verdict)} ({verdict})"
    counts = _severity_counts(issues)

    lines: list[str] = [
        f"## 🤖 코드 리뷰 — {label}",
        "",
        why.strip(),
        "",
        counts,
    ]
    metric_line = _metrics_line(metrics)  # 측정값 있을 때만 헤더 아래 한 줄 (7D)
    if metric_line:
        lines.append(metric_line)
    lines += [
        "",
        _TABLE_HEADER,
        _TABLE_SEP,
    ]
    for issue in issues:
        emoji = _SEVERITY_EMOJI.get(issue.severity, "•")
        loc = f"{issue.file}:{issue.line}" if issue.line is not None else issue.file
        lines.append(
            f"| {emoji} | {_td(issue.rule_id)} | {_td(loc)} "
            f"| {_td(issue.suggestion)} | {_td(issue.rag_context)} |"
        )
    lines += ["", f"📊 [리뷰 대시보드에서 전체 보기]({_dashboard_url()})"]
    return "\n".join(lines)


def _severity_counts(issues: list[CombinedIssue]) -> str:
    c = sum(1 for i in issues if i.severity == "Critical")
    m = sum(1 for i in issues if i.severity == "Major")
    mi = sum(1 for i in issues if i.severity == "Minor")
    return f"🔴 Critical {c} · 🟡 Major {m} · 🔵 Minor {mi}"


def _metrics_line(metrics: dict | None) -> str:
    """측정 지표 → '📊 커버리지 NN% · 최대 복잡도 NN' 한 줄. 측정값 없으면 '' (7D).

    있는 값만 렌더 — coverage_pct 없거나 max_complexity 없으면 그 부분을 생략하고,
    둘 다 없으면 줄 자체를 빼서 가짜 0%·가짜 숫자를 만들지 않는다.
    """
    if not metrics:
        return ""
    parts: list[str] = []
    cov = metrics.get("coverage_pct")
    if cov is not None:
        parts.append(f"커버리지 {round(cov)}%")
    cx = metrics.get("max_complexity")
    if cx is not None:
        parts.append(f"최대 복잡도 {cx}")
    return f"📊 {' · '.join(parts)}" if parts else ""


def _td(text: str) -> str:
    """마크다운 표 셀 안전화: 빈 값 → '—', 파이프 이스케이프, 개행 → <br>."""
    s = (text or "").strip()
    if not s:
        return "—"
    return s.replace("|", "\\|").replace("\n", "<br>")


def _heuristic_why(issues: list[CombinedIssue], verdict: str) -> str:
    """verdict 기반 기본 '왜 한 줄' (LLM 없이도 의미 있는 한 줄)."""
    if verdict == "escalate":
        return "시니어 리뷰가 필요한 중대한 이슈가 있습니다."
    if verdict == "rework":
        return "머지 전에 아래 이슈를 수정해 주세요."
    return "사소한 참고사항만 있습니다. 머지할 수 있습니다."


def _llm_why(
    issues: list[CombinedIssue],
    verdict: str,
    skill_level: str,
) -> str:
    """LLM 으로 '왜 한 줄'만 생성. 실패·429·빈 응답 → '' (호출부가 휴리스틱으로 fallback)."""
    try:
        raw = _call_llm(_build_prompt(issues, verdict, skill_level))
    except Exception:
        return ""  # 네트워크·쿼터(429)·SDK 오류 → 휴리스틱 한 줄로
    if not raw or not raw.strip():
        return ""
    # 한 줄만 취하고 마크다운 헤더기호 제거(구조는 코드가 결정하므로 prose 한 줄만 필요)
    first = next((ln.strip() for ln in raw.splitlines() if ln.strip()), "")
    return first.lstrip("#").strip()


def _build_prompt(
    issues: list[CombinedIssue],
    verdict: str,
    skill_level: str,
) -> str:
    """LLM 프롬프트 — '왜 이 판정인지 한 줄'만 요청(표/제목/링크/설명은 코드가 담당)."""
    tone = _TONE_HINTS.get(skill_level, _TONE_HINTS["mid"])
    summary = "\n".join(
        f"- [{i.severity}] {i.rule_id} ({i.file}:{i.line}): {i.suggestion}"
        for i in issues
    )
    return (
        f"당신은 코드 리뷰 봇입니다. 대상 개발자 수준: {skill_level}.\n"
        f"톤 지침: {tone}\n"
        f"판정: {verdict}\n"
        f"이슈 목록:\n{summary}\n\n"
        "이 판정을 내린 이유를 한국어 '한 줄'로만 작성하세요. "
        "개념 설명·코드 예시·학습 추천·표·제목·링크는 절대 넣지 마세요."
    )


def _call_llm(prompt: str) -> str:
    """실제 LLM API 호출 (Gemini) — 테스트에서 mock 대상."""
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        return ""

    from google import genai  # type: ignore  # noqa: PLC0415

    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(
        model=os.getenv("LLM_MODEL", "gemini-2.5-flash"),
        contents=prompt,
    )
    return response.text
