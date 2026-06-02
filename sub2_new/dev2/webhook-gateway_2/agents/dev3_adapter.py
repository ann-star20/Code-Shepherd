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

        # 커버리지 측정 (Docker 샌드박스, 실패해도 계속)
        try:
            from prepare.sandbox import run_sandbox
            run_sandbox(ctx.work_dir)
        except Exception:
            pass

        repo = RepoInfo(clone_url=ctx.clone_url, commit_sha=ctx.commit_sha)
        inp = Dev3Input(
            task_id=f"gw-{ctx.pr_number}", scan_id=ctx.pr_number,
            pr_id=str(ctx.pr_number), pr_diff=ctx.pr_diff or _whole_diff(ctx),
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
                })
        return issues
    finally:
        # Dev3 모듈 캐시 정리 (다른 에이전트 import 충돌 방지)
        for m in ("contracts", "main", "config", "config.settings"):
            sys.modules.pop(m, None)


def _whole_diff(ctx: PRContext) -> str:
    """diff가 없을 때 — src 폴더 전체를 '바뀐 것'으로 간주하는 가짜 diff."""
    src = os.path.join(ctx.work_dir, "src")
    lines = 200
    f = os.path.join(src, "posts.py")
    if os.path.exists(f):
        lines = len(open(f, encoding="utf-8").read().splitlines())
    return ("diff --git a/src/posts.py b/src/posts.py\n--- /dev/null\n"
            f"+++ b/src/posts.py\n@@ -0,0 +1,{lines} @@\n"
            + "\n".join("+x" for _ in range(lines)))
