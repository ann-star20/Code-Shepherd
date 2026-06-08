"""[Dev2 템플릿] 정적분석·보안 에이전트 어댑터.

★ 사용법:
   1. 이 파일을 dev2_adapter.py 로 복사
   2. 아래 analyze() 안의 TODO 부분을 Dev2 실제 분석으로 교체
   3. server.py 에 한 줄 추가:  import agents.dev2_adapter
   → 끝. PR 오면 자동으로 같이 실행됨.

규약 (이것만 지키면 됨):
   - 함수는 ctx(PRContext) 하나를 받는다
   - list[dict] 를 반환한다 (dict는 아래 표준 Issue 형식)
   - 게이트웨이 코드는 건드리지 않는다
"""
from __future__ import annotations

from registry import PRContext, register


@register("security_scan")          # ← 에이전트 이름 (자유롭게)
def analyze(ctx: PRContext) -> list[dict]:
    """clone된 레포를 Dev2 방식(정적분석·보안)으로 분석 → 이슈 목록 반환.

    ctx에서 쓸 수 있는 것:
        ctx.work_dir       # clone된 코드의 로컬 경로 (여기서 파일 읽으면 됨)
        ctx.repo_full_name # "owner/repo"
        ctx.pr_number      # PR 번호
        ctx.commit_sha     # 커밋 SHA
        ctx.pr_diff        # PR의 unified diff (신입이 바꾼 부분)
    """
    issues: list[dict] = []

    # ─────────────────────────────────────────────
    # TODO: Dev2의 실제 분석으로 교체
    #   예: ESLint/Pylint 실행, SQL 인젝션 탐지, OWASP 체크 등
    #   ctx.work_dir 안의 파일을 읽어서 분석하면 됨
    #
    # 예시) 보안 이슈 하나를 반환하는 형태:
    #
    # issues.append({
    #     "severity": "Critical",          # "Critical" | "Major" | "Minor"
    #     "file": "src/auth.py",           # 파일 경로
    #     "line": 23,                      # 줄 번호 (없으면 None)
    #     "message": "SQL 인젝션 가능성: 사용자 입력이 쿼리에 직접 삽입됨",
    #     "rule_id": "SEC-001",            # 보안=SEC-xxx, 정적분석=SA-xxx
    #     "suggestion": "파라미터 바인딩을 사용하세요",
    #     "_agent": "security_scan",       # 이 에이전트 이름 (위 @register와 동일)
    # })
    # ─────────────────────────────────────────────

    return issues


# 정적분석을 보안과 별도 에이전트로 두고 싶으면 함수 하나 더:
#
# @register("static_analysis")
# def analyze_static(ctx: PRContext) -> list[dict]:
#     ...
#     return issues
