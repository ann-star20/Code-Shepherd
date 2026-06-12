"""
issues.py — PATCH /issues/{id}/dismiss 엔드포인트 (이슈 오탐 표시)

개발자가 정적 분석 결과 중 오탐(false positive)을 직접 표시하는 엔드포인트.
피드백 루프(Dev5)에서 반복 오탐 패턴을 학습해 탐지 정확도를 높이는 데 사용.

엔드포인트:
    PATCH /issues/{issue_id}/dismiss  is_false_positive = true 업데이트

HTTP PATCH 사용 이유:
    - 이슈 레코드 '전체' 교체(PUT)가 아니라 is_false_positive 한 필드만 수정
    - 멱등(idempotent): 여러 번 호출해도 결과 동일 → 네트워크 재시도 안전
    - DELETE가 아닌 이유: 이슈 기록 자체는 유지 (감사 추적용)

CLAUDE.md §6 보안:
    issue_id는 URL 경로에서 int로 받음 (FastAPI 자동 타입 변환·검증).
    쿼리는 파라미터 바인딩 `:id` 사용.
"""

import logging

from fastapi import APIRouter
from sqlalchemy import text

# [CLAUDE.md §10-3] lazy import 패턴 (insights.py와 동일)
# AsyncSessionLocal은 각 엔드포인트 함수 내부에서 import

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/issues", tags=["issues"])


@router.patch("/{issue_id}/dismiss")
async def dismiss_issue(issue_id: int):
    """
    이슈를 오탐(false positive)으로 표시한다.

    개발자가 분석 결과 중 실제 문제가 아닌 이슈를 "오탐"으로 마킹.
    is_false_positive = true로 업데이트하고 이슈 기록은 유지한다.

    Dev5 피드백 루프:
        반복 오탐 패턴 → LLM 프롬프트 개선 / 룰 비활성화에 활용.

    Args:
        issue_id: URL 경로 파라미터 (int) — FastAPI가 타입 검증.
                  문자열 전달 시 422 Unprocessable Entity 자동 반환.

    Returns:
        {"issue_id": int, "is_false_positive": True} — 업데이트 확인
    """
    from dev2.db import AsyncSessionLocal  # noqa: PLC0415 — lazy import
    async with AsyncSessionLocal() as s:
        await s.execute(
            text("UPDATE scan_issues SET is_false_positive = true WHERE id = :id"),
            {"id": issue_id},  # 파라미터 바인딩 — SQL 인젝션 방지
        )
        await s.commit()

    logger.info(
        "PATCH /issues/%d/dismiss: is_false_positive=true 설정 완료", issue_id
    )

    return {"issue_id": issue_id, "is_false_positive": True}
