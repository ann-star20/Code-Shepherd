"""Dev3(test-performance-agent) 어댑터 — 게이트웨이에 분석 함수를 등록.

★ Dev2도 이 파일을 본떠 자기 어댑터(dev2_adapter.py)를 만들면 끝.
   규약: analyze(ctx) -> list[dict]  (dict는 표준 Issue 형식)
"""
from __future__ import annotations

import os
import sys

from registry import PRContext, register

# test-performance-agent 경로 추가
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_TP = os.path.join(_ROOT, "test-performance-agent")


@register("test_verification_and_performance")
def analyze(ctx: PRContext) -> list[dict]:
    """clone된 레포를 Dev3로 분석 → 이슈 목록(dict) 반환."""
    # Dev3 모듈 격리 import (동명 모듈 충돌 방지)
    saved = {m: sys.modules.pop(m, None)
             for m in ("contracts", "main", "config", "config.settings")}
    if _TP not in sys.path:
        sys.path.insert(0, _TP)
    try:
        from contracts import Dev3Input, Developer, RepoInfo
        import main as dev3_main

        # 커버리지 측정 (Docker 샌드박스). 컨테이너가 만든 coverage.json은
        # 호스트가 못 읽을 수 있으므로, 반환된 coverage dict를 받아 호스트가 직접 기록.
        try:
            import json as _json
            from prepare.sandbox import run_sandbox
            res = run_sandbox(ctx.work_dir)
            cov = res.get("coverage")
            if cov:
                cov_path = os.path.join(ctx.work_dir, "coverage.json")
                try:
                    if os.path.exists(cov_path):
                        os.remove(cov_path)          # 컨테이너 잔여물 제거
                except OSError:
                    pass
                with open(cov_path, "w", encoding="utf-8") as f:
                    _json.dump(cov, f)
                print(f"  [dev3] 커버리지 측정됨: "
                      f"{cov.get('totals',{}).get('percent_covered',0):.1f}%")
            else:
                print("  [dev3] 커버리지 회수 실패 (test_verification 일부 누락 가능)")
        except Exception as e:  # noqa: BLE001
            print(f"  [dev3] 커버리지 측정 skip: {type(e).__name__}: {e}")

        # 진짜 PR diff만 사용 (신입이 바꾼 부분만 지적하는 핵심 기능).
        # diff를 못 가져오면 가짜를 만들지 않고 정직하게 빈 결과 반환.
        if not ctx.pr_diff:
            print("  [dev3] PR diff 없음 → 분석 불가 (가짜 diff 만들지 않음)")
            return []

        repo = RepoInfo(clone_url=ctx.clone_url, commit_sha=ctx.commit_sha)
        inp = Dev3Input(
            task_id=f"gw-{ctx.pr_number}", scan_id=ctx.pr_number,
            pr_id=str(ctx.pr_number), pr_diff=ctx.pr_diff,
            repo=repo,
            developer=Developer(id=ctx.author or "junior", skill_level="junior"),
        )
        outputs = dev3_main.run(inp, ctx.work_dir)

        issues: list[dict] = []
        for o in outputs:
            for i in o.issues:
                issues.append({
                    "severity": i.severity, "file": i.file, "line": i.line,
                    "message": i.message, "rule_id": i.rule_id,
                    "suggestion": i.suggestion, "_agent": o.agent,
                    "keyword": i.keyword, "sub_category": i.sub_category,
                    "code_context": i.code_context, "rag_context": i.rag_context,
                    # ── Dev2 통일 신규 컬럼 (GCP ALTER ADD 후 gateway INSERT에 연결) ──
                    "github_id": i.github_id, "code_snippet": i.code_snippet,
                    "programming_language": i.programming_language,
                    "framework": i.framework, "framework_version": i.framework_version,
                    # review_issue.name_of_function (AST 함수명) — gateway 적재가 사용
                    "name_of_function": i.name_of_function,
                })
        return issues
    finally:
        # Dev3 모듈 캐시 정리 (다른 에이전트 import 충돌 방지)
        for m in ("contracts", "main", "config", "config.settings"):
            sys.modules.pop(m, None)


# (가짜 diff 생성 함수 제거됨 — 진짜 PR diff만 사용한다)
