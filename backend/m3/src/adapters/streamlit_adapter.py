"""Streamlit 어댑터 — app/streamlit_app.py(세션 B 소유)와 파이프라인 사이 경계.

세션 B는 이 모듈의 review() 만 호출한다 (src 내부 구조에 의존 금지).
"""
from __future__ import annotations

from contracts import ReviewInput, ReviewOutput


def review(diff: str, file_paths: list[str], repo_meta: dict | None = None) -> ReviewOutput:
    """UI 입력 → 파이프라인 1회 실행. D2 구현 (메인 세션)."""
    from src.graph import run_review

    return run_review(ReviewInput(diff=diff, file_paths=file_paths, repo_meta=repo_meta or {}))


def review_traced(
    diff: str, file_paths: list[str], repo_meta: dict | None = None,
) -> tuple[ReviewOutput, list[dict]]:
    """review() + 노드 실행 trace — D5 타임라인 표시용. review() 계약은 불변."""
    from src.graph import run_review_traced

    return run_review_traced(
        ReviewInput(diff=diff, file_paths=file_paths, repo_meta=repo_meta or {})
    )
