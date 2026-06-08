"""
카테고리 정의 공통 모듈

stage5_metadata_agent 와 stage5b_metadata_validate_agent 가 동일한
카테고리 기준을 사용하도록 단일 진실 공급원(Single Source of Truth) 역할을 한다.

VALID_CATEGORIES 는 stage5b 에서 rule-check 에 사용하고,
CATEGORY_DEFINITIONS 는 LLM 프롬프트에 삽입해 분류 정확도를 높인다.
"""

from __future__ import annotations

CATEGORY_DEFINITIONS: dict[str, str] = {
    "코딩컨벤션": (
        "코딩 스타일, 네이밍 규칙, 코드 품질 가이드, 개발 표준, "
        "린트 설정, 포매터, 베스트 프랙티스, 코드 리뷰 기준"
    ),
    "아키텍처": (
        "SW 설계, 시스템 구조, 아키텍처 패턴, "
        "NCS SW아키텍처 수행관리, 기술 스택 설계, "
        "마이크로서비스, API 설계, 데이터 모델링, 인프라 설계"
    ),
    "온보딩": (
        "신입 교육, 입문 가이드, 개발 환경 설정, "
        "팀 규칙 안내, 신규 입사자 문서, 튜토리얼"
    ),
    "보안": (
        "보안 취약점, 인증·인가, 데이터 보호, "
        "보안 정책, SQL 인젝션 방지, XSS, CSRF, 암호화"
    ),
    "배포": (
        "CI/CD, 배포 프로세스, 릴리즈 가이드, "
        "Docker, Kubernetes, 인프라 운영, 모니터링"
    ),
    "기타": (
        "위 카테고리(코딩컨벤션·아키텍처·온보딩·보안·배포)에 "
        "명확히 해당하지 않는 경우에만 선택. 마지막 수단."
    ),
}

# stage5b rule-check 용 유효 카테고리 집합
VALID_CATEGORIES: frozenset[str] = frozenset(CATEGORY_DEFINITIONS.keys())


def build_category_prompt_snippet() -> str:
    """LLM 프롬프트에 삽입할 카테고리 정의 텍스트를 반환한다."""
    lines = ["카테고리 선택 기준:"]
    for name, definition in CATEGORY_DEFINITIONS.items():
        lines.append(f'- "{name}": {definition}')
    return "\n".join(lines)
