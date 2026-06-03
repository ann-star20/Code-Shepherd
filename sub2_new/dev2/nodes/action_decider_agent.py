"""
action_decider_agent 노드 — 분석 결과 기반 후속 액션 추천

llm_judge 이후에 실행되는 노드.
최종 이슈 목록을 보고 M0/Dev4가 참고할 recommended_action을 생성한다.

중요: M2는 PR 승인/반려를 결정하지 않는다.
     recommended_action은 추천값이며, 실제 결정은 M0/Dev4가 담당한다.

실제 그래프 분기:
    early_escalation → escalate → store
    그 외 → store

recommended_action 후보:
    early_escalation   Critical ≥ 1
    request_rework     Major ≥ 3 (store로 이동, M2가 직접 처리 안 함)
    needs_human_review 중요 파일 Major 이슈 / confidence 낮음
    store_only         해당 없음
"""

import logging

from dev2.schema import ActionDecision, Dev2State

logger = logging.getLogger(__name__)

# ── 상수 ──────────────────────────────────────────────────────────────────────

IMPORTANT_FILE_KEYWORDS: list[str] = [
    "auth", "login", "password", "token", "session",
    "permission", "admin", "payment", "billing", "order", "checkout",
]

_LOW_CONFIDENCE_THRESHOLD = 0.6
_MAJOR_REWORK_THRESHOLD = 3


# ── 핵심 로직 ─────────────────────────────────────────────────────────────────

def _is_important_file(filepath: str) -> bool:
    lower = filepath.lower()
    return any(kw in lower for kw in IMPORTANT_FILE_KEYWORDS)


def decide_action(enriched: list[dict]) -> ActionDecision:
    """
    이슈 목록 분석 → ActionDecision 생성.

    판단 우선순위:
        1. Critical ≥ 1           → early_escalation
        2. Major ≥ 3              → request_rework
        3. 중요 파일 Major 이슈   → needs_human_review
        4. confidence < 0.6       → needs_human_review
        5. 그 외                  → store_only

    Args:
        enriched: llm_judge까지 처리된 이슈 목록

    Returns:
        ActionDecision
    """
    critical_count = sum(1 for i in enriched if i.get("severity") == "Critical")
    major_count    = sum(1 for i in enriched if i.get("severity") == "Major")
    minor_count    = sum(1 for i in enriched if i.get("severity") == "Minor")

    # 중요 파일에서 Major 이상 이슈
    important_file_issue = any(
        _is_important_file(i.get("file", ""))
        for i in enriched
        if i.get("severity") in ("Critical", "Major")
    )

    # confidence_score 0.6 미만 이슈 (매핑된 이슈만 — 0.0은 미매핑이므로 제외)
    low_confidence_issue = any(
        0.0 < i.get("confidence_score", 1.0) < _LOW_CONFIDENCE_THRESHOLD
        for i in enriched
    )

    signals: dict = {
        "critical_count":      critical_count,
        "major_count":         major_count,
        "minor_count":         minor_count,
        "important_file_issue": important_file_issue,
        "low_confidence_issue": low_confidence_issue,
    }

    # ── 판정 ──────────────────────────────────────────────────────────────────
    if critical_count >= 1:
        files = [i.get("file", "") for i in enriched if i.get("severity") == "Critical"]
        return ActionDecision(
            recommended_action="early_escalation",
            reason=f"Critical 이슈 {critical_count}개 감지 (파일: {', '.join(set(files))})",
            confidence=0.95,
            signals=signals,
        )

    if major_count >= _MAJOR_REWORK_THRESHOLD:
        return ActionDecision(
            recommended_action="request_rework",
            reason=f"Major 이슈 {major_count}개 감지 — 재작업 권장 (M2는 store만 수행, M0/Dev4 판단)",
            confidence=0.85,
            signals=signals,
        )

    if important_file_issue:
        files = [
            i.get("file", "") for i in enriched
            if i.get("severity") in ("Critical", "Major") and _is_important_file(i.get("file", ""))
        ]
        return ActionDecision(
            recommended_action="needs_human_review",
            reason=f"중요 파일에서 Major 이상 이슈 감지 ({', '.join(set(files))})",
            confidence=0.80,
            signals=signals,
        )

    if low_confidence_issue:
        return ActionDecision(
            recommended_action="needs_human_review",
            reason="이슈 분류 신뢰도 0.6 미만 — 사람 검토 권장",
            confidence=0.70,
            signals=signals,
        )

    return ActionDecision(
        recommended_action="store_only",
        reason="Critical/Major 임계치 미달, 중요 파일 이슈 없음 — 일반 저장",
        confidence=0.90,
        signals=signals,
    )


# ── LangGraph 노드 ────────────────────────────────────────────────────────────

async def action_decider_agent_node(state: Dev2State) -> dict:
    """
    LangGraph 노드: 분석 결과 기반 후속 액션 추천.

    llm_judge 이후에 실행되어 state["action_decision"]을 채운다.
    그래프 라우터(route_after_action_decider)가 이 값을 읽어 분기한다.

    주의: M2는 결정을 실행하지 않는다.
          early_escalation → 실제 escalate 노드가 알림 발송.
          request_rework / needs_human_review → store로 이동, M0/Dev4가 판단.

    Args:
        state: Dev2State — enriched 필드 사용

    Returns:
        {"action_decision": dict} — ActionDecision.model_dump()
    """
    enriched: list[dict] = state.get("enriched", [])

    if not enriched:
        logger.warning("action_decider_agent: enriched 없음 — store_only 반환")
        decision = ActionDecision(
            recommended_action="store_only",
            reason="분석 이슈 없음",
            confidence=1.0,
            signals={"critical_count": 0, "major_count": 0, "minor_count": 0,
                     "important_file_issue": False, "low_confidence_issue": False},
        )
        return {"action_decision": decision.model_dump()}

    decision = decide_action(enriched)

    logger.info(
        "action_decider_agent: recommended_action=%s (confidence=%.2f) | %s",
        decision.recommended_action, decision.confidence, decision.reason,
    )
    return {"action_decision": decision.model_dump()}
