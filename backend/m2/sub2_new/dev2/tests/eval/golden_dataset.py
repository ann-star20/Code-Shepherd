"""
golden_dataset.py — LLM severity 판단 평가용 골든 데이터셋

사람이 직접 "이 입력엔 이 정답"을 정해둔 기준 데이터셋이다.
LangSmith evaluate()가 이 정답과 LLM 출력을 비교해 정확도를 측정한다.

### 골든 데이터셋 설계 원칙
- CLAUDE.md §8 seed 시나리오 반영 (SQL 인젝션=Critical, N+1=Major)
- 3가지 등급(Critical/Major/Minor) 고르게 커버
- 모호한 경계 케이스(CVSS 9.1 → Critical 업그레이드) 포함
- 각 케이스마다 "왜 이 정답인가" 주석 필수 (채점 기준 명확화)

### LangSmith evaluate() data 형식
    [{"inputs": {...}, "outputs": {"expected": "..."}}, ...]
    - "inputs"  → target_function에 keyword arguments로 전달됨
    - "outputs" → example.outputs 로 evaluator에 전달됨

### 확장 방법
    Week 5 통합 시 실제 PR 데이터 기반으로 케이스 추가 권장 (최소 20개)
    케이스 추가는 이 파일에만 — evaluator/test 코드 수정 불필요
"""

# ── 골든 데이터셋 (5개: 3 Critical / 1 Major / 1 Minor) ───────────────────────
# CLAUDE.md §8: MVP P0 시나리오(SQL 인젝션, N+1, 코드 스멜)를 필수 포함
GOLDEN_DATASET: list[dict] = [
    # ─ 케이스 1: SQL 인젝션 → Critical (CLAUDE.md §8 seed 시나리오)
    # f-string으로 쿼리 조합 = 입력값이 직접 SQL에 삽입 → 무조건 Critical
    {
        "inputs": {
            "message": "SQL 파라미터 미처리 — f-string으로 쿼리 조합",
            "current_severity": "Major",  # CLI 도구는 Major로 판단했지만
            "developer_level": "junior",
            "similar_cases": [],
        },
        "outputs": {"expected": "Critical"},  # 사람 판단: SQL Injection은 무조건 Critical
    },

    # ─ 케이스 2: 하드코딩된 비밀번호 → Critical
    # 보안 자격증명 노출 = 인증 우회 가능 → 즉시 수정 필요
    {
        "inputs": {
            "message": "하드코딩된 비밀번호 발견: password='admin123'",
            "current_severity": "Major",  # CLI(bandit)는 Major로 판단했지만
            "developer_level": "junior",
            "similar_cases": [],
        },
        "outputs": {"expected": "Critical"},  # 사람 판단: 인증 자격증명 노출 = Critical
    },

    # ─ 케이스 3: CVE 고위험 → Critical (CVSS 9.1은 명확한 Critical 기준)
    # CVSS 9.x = Critical 등급 (공업 표준). 도구가 Major로 분류했어도 업그레이드 필요
    {
        "inputs": {
            "message": "pip-audit: CVE-2024-1234 (CVSS 9.1) — 의존성 취약점",
            "current_severity": "Major",  # pip-audit이 Major로 분류했지만
            "developer_level": "junior",
            "similar_cases": [],
        },
        "outputs": {"expected": "Critical"},  # 사람 판단: CVSS 9.1은 Critical
    },

    # ─ 케이스 4: 순환복잡도 높음 → Major (CLAUDE.md §8 seed 시나리오)
    # 복잡도 18 = 테스트 불가능 수준이지만, 즉각적인 보안 위험은 없음 → Major 유지
    {
        "inputs": {
            "message": "순환복잡도 18 감지 (함수: process_payment). 테스트 커버리지 불가.",
            "current_severity": "Major",  # CLI(radon)와 사람 판단 일치
            "developer_level": "mid",
            "similar_cases": [
                {"pr_id": "PR-001", "similarity": 0.88, "message": "순환복잡도 12 — 함수 분리 필요"},
            ],
        },
        "outputs": {"expected": "Major"},  # 사람 판단: 리팩토링 필요하지만 보안 위험은 아님
    },

    # ─ 케이스 5: 변수명 규칙 위반 → Minor (코드 스멜, 기능 영향 없음)
    # snake_case 위반은 PEP8 스타일 문제 → 기능 영향 없음 → Minor 유지
    {
        "inputs": {
            "message": "변수명 snake_case 위반: 'userID' → 'user_id' 사용 권장",
            "current_severity": "Minor",  # CLI(pylint)와 사람 판단 일치
            "developer_level": "senior",
            "similar_cases": [],
        },
        "outputs": {"expected": "Minor"},  # 사람 판단: 코드 스멜, 기능 영향 없음
    },
]

# ── 메타데이터 ────────────────────────────────────────────────────────────────
DATASET_VERSION = "1.0.0"
DATASET_DESCRIPTION = "Dev2 severity 판단 골든 데이터셋 — CLAUDE.md §8 MVP P0 시나리오 기반"

# 기대 정답 분포 (채점 기준 투명화)
EXPECTED_DISTRIBUTION = {
    "Critical": 3,   # SQL 인젝션, 하드코딩 비밀번호, CVE 9.1
    "Major": 1,      # 순환복잡도
    "Minor": 1,      # 변수명 규칙 위반
}
