"""
카테고리 정의 공통 모듈

stage5_metadata_agent 와 stage5b_metadata_validate_agent 가 동일한
카테고리 기준을 사용하도록 단일 진실 공급원(Single Source of Truth) 역할을 한다.

VALID_CATEGORIES 는 stage5b 에서 rule-check 에 사용하고,
CATEGORY_DEFINITIONS 는 LLM 프롬프트에 삽입해 분류 정확도를 높인다.

카테고리 이름은 categories DB 테이블의 name 컬럼과 일치해야 한다.
lifespan 에서 get_valid_categories() 로 VALID_CATEGORIES 를 갱신한다.
"""

from __future__ import annotations

CATEGORY_DEFINITIONS: dict[str, str] = {
    "AI_ML": (
        "인공지능, 머신러닝, 딥러닝, LLM, RAG, RAG 시스템 설계, 임베딩, 벡터검색, "
        "MLOps, 모델 학습·배포·모니터링, 생성형 AI, 프롬프트 엔지니어링, "
        "검색 품질 평가(Precision@k, Recall@k, NDCG, MRR, SQM), "
        "파인튜닝, 검색 랭킹, 벡터 인덱스, pgvector, 임베딩 파이프라인"
    ),
    "온보딩": (
        "신입 교육, 온보딩, 입문 가이드, 개발 환경 설정, 취업규칙, "
        "인사 정책, 근로조건, 휴가, 복무, 채용, 커리어 성장"
    ),
    "코딩컨벤션": (
        "API 설계, REST, 코드 리뷰, 코딩 컨벤션, 개발 표준, SW 설계"
    ),
    "아키텍처": (
        "아키텍처 패턴, 마이크로서비스, 데이터 모델링, 시스템 설계, 기술 스택 결정"
    ),
    "보안": (
        "보안 정책, 보안 취약점, 인증·인가, 데이터 보호, 암호화, "
        "컴플라이언스, 개인정보보호, 데이터 거버넌스, ISMS, 감사"
    ),
    "프로젝트관리": (
        "프로젝트 관리, 스프린트, 회고, KPT, 일정, 이슈 관리, "
        "애자일, 스크럼, 마일스톤, 팀 협업, 의사결정"
    ),
    "배포": (
        "운영, 장애 보고, 인시던트, 모니터링, 배포, CI/CD, "
        "Docker, Kubernetes, 인프라, 포스트모텀, SLA, 온콜"
    ),
    "코드성능검증": (
        "성능 테스트, 부하 테스트, 코드 최적화, 쿼리 성능, "
        "응답 시간 측정, 병목 분석, 벤치마크, 캐시 전략, "
        "E-Commerce 성능, 트랜잭션 처리, 동시성, 스케일링"
    ),
    "기타": (
        "위 카테고리에 명확히 해당하지 않는 경우에만 선택. 마지막 수단."
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
