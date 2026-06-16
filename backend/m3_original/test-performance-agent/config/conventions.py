"""사내 코딩 컨벤션 — 정량 기준 (구조화 데이터, RAG 아님).

⚠️ 위험 3 (RAG 설계서 §5ⓐ): 커버리지% 같은 정량 룰을 자연어 문서에서 파싱하면
PR 합격/탈락 판정이 깨질 수 있음(재앙). 그래서 정량 기준은 RAG가 아니라
여기 구조화 dict로 관리한다. 팀이 기준을 바꾸면 이 파일만 수정하면 됨.

(정성 가이드·설명은 RAG로 코멘트에 인용 — augment.py 참고. 역할 분리.)
"""
from __future__ import annotations

# 모듈별 사내 라인 커버리지 기준 — **하드코딩 fallback**(DB 못 읽을 때만 사용).
# 평소 기준값의 정본은 GCP convention_policies('coverage'). policy_store가 읽음.
# 'default'는 그 외 전부의 기본값.
COVERAGE_RULES: dict[str, float] = {
    "default": 0.80,
    "payment": 0.90,   # 결제 모듈 — 더 엄격
    "auth": 0.90,      # 인증 모듈 — 더 엄격
    "legacy": 0.70,    # 레거시 — 완화
}


def coverage_rules() -> dict[str, float]:
    """커버리지 기준 dict. DB(convention_policies) 우선, 없으면 하드코딩 fallback.

    위험3: 숫자는 policy_store가 jsonb로 정확히 읽음(LLM 아님). DB params에
    'default'가 없으면 깨진 데이터로 보고 fallback(안전).
    """
    from config import policy_store  # 지연 import (모듈 로드 순서 안전)

    params = policy_store.get_params("coverage")
    if isinstance(params, dict) and "default" in params:
        return params
    return COVERAGE_RULES


def threshold_for(file_path: str) -> float:
    """파일 경로의 모듈을 보고 사내 커버리지 기준값을 반환.

    경로에 모듈 키워드(payment/auth/legacy 등)가 포함되면 해당 기준,
    없으면 default. 기준값은 coverage_rules()(DB→fallback)에서 옴.
    Windows 역슬래시 경로도 문자열 포함으로 처리됨.
    """
    rules = coverage_rules()
    for module, threshold in rules.items():
        if module == "default":
            continue
        if module in file_path:
            return threshold
    return rules["default"]


# 중첩 루프 깊이 기준 — **하드코딩 fallback**(DB 못 읽을 때만 사용).
# 평소 기준값의 정본은 GCP convention_policies('complexity'). policy_store가 읽음.
COMPLEXITY_RULES: dict[str, int] = {
    "minor_depth": 2,   # 2중 중첩 → Minor (O(n²))
    "major_depth": 3,   # 3중 이상 → Major (O(n³)+)
}


def complexity_rules() -> dict[str, int]:
    """복잡도 기준 dict. DB(convention_policies) 우선, 없으면 하드코딩 fallback.

    위험3: 숫자는 policy_store가 jsonb로 정확히 읽음(LLM 아님). DB params에
    'minor_depth'·'major_depth'가 모두 없으면 깨진 데이터로 보고 fallback(안전).
    """
    from config import policy_store  # 지연 import (모듈 로드 순서 안전)

    params = policy_store.get_params("complexity")
    if isinstance(params, dict) and "minor_depth" in params and "major_depth" in params:
        return params
    return COMPLEXITY_RULES
