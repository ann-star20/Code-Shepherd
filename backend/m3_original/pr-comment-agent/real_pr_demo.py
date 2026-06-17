"""실제 GitHub PR #1 라이브 데모 — 분석 → 코멘트 생성/등록.

흐름:
  1. 실제 레포 clone (prepare_repo)
  2. Docker 샌드박스에서 pytest --cov 실측 → coverage.json 생성 (Docker 없으면 폴백)
  3. Dev3 run()으로 검출 (N+1·O(n²)·테스트누락·커버리지)
  4. pr-comment-agent: aggregate → refine → post_comment
  5. GITHUB_TOKEN 있으면 PR #1에 진짜 등록, 없으면 dry-run

설정: pr-comment-agent/.env 의 GITHUB_TOKEN, GITHUB_REPO
"""
from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
TP = os.path.join(ROOT, "test-performance-agent")

# .env 로드
_envp = os.path.join(HERE, ".env")
if os.path.exists(_envp):
    for line in open(_envp, encoding="utf-8"):
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

REPO_URL = "https://github.com/kskt1234-netizen/-dev3-demo.git"
COMMIT_SHA = "d66400e667094a25788217a236f0daade4390955"
PR_NUM = 1


def banner(t):
    print(f"\n{'=' * 64}\n  {t}\n{'=' * 64}")


def main():
    banner("실제 GitHub PR #1 라이브 데모")

    # ── 1. clone ──
    sys.path.insert(0, TP)
    from contracts import Dev3Input, Developer, RepoInfo
    from prepare.repo import prepare_repo

    print("\n[1] 레포 clone")
    repo = RepoInfo(clone_url=REPO_URL, commit_sha=COMMIT_SHA)
    work = prepare_repo(repo)
    print(f"    → {work}")

    # 신입이 추가한 파일(posts.py) 줄 전체를 diff로 (필터 통과용)
    posts = os.path.join(work, "src", "posts.py")
    nlines = len(open(posts, encoding="utf-8").read().splitlines()) if os.path.exists(posts) else 25
    pr_diff = (
        "diff --git a/src/posts.py b/src/posts.py\n"
        "--- /dev/null\n+++ b/src/posts.py\n"
        f"@@ -0,0 +1,{nlines} @@\n" + "\n".join("+x" for _ in range(nlines))
    )

    # ── 2. Docker 샌드박스로 커버리지 측정 ──
    print("\n[2] Docker 샌드박스: pytest --cov 실측")
    try:
        from prepare.sandbox import run_sandbox
        res = run_sandbox(work)
        cov = res.get("coverage")
        if cov:
            pct = cov.get("totals", {}).get("percent_covered", 0)
            print(f"    → 커버리지 실측: {pct:.1f}%")
        else:
            print("    ⚠ coverage 회수 실패 → 커버리지 없이 진행")
    except Exception as e:
        print(f"    ⚠ Docker 실패({type(e).__name__}) → 정적 분석만 진행")

    # ── 3. Dev3 검출 ──
    print("\n[3] Dev3 검출 (탐지기)")
    import main as dev3_main
    inp = Dev3Input(
        task_id="real-demo-001", scan_id=1, pr_id=str(PR_NUM),
        pr_diff=pr_diff, repo=repo,
        developer=Developer(id="junior_dev_01", skill_level="junior"),
    )
    outputs = dev3_main.run(inp, work)
    n = sum(len(o.issues) for o in outputs)
    print(f"    → {n} 이슈 검출")
    for o in outputs:
        for i in o.issues:
            loc = f"{i.file}:{i.line}" if i.line else i.file
            print(f"       [{i.severity:6}] {i.rule_id:10} {loc}")

    # ── 4. 집계·코멘트 (pr-comment-agent) ──
    print("\n[4] 집계·판정·코멘트 (pr-comment-agent)")
    # 두 폴더에 동명 모듈(contracts/main)이 있어 import 충돌 → Dev3 모듈 캐시 제거 후
    # pr-comment 경로를 최우선으로
    for m in ("contracts", "main", "config", "config.settings"):
        sys.modules.pop(m, None)
    if TP in sys.path:
        sys.path.remove(TP)
    sys.path.insert(0, HERE)
    from aggregator import aggregate
    from llm_refiner import refine
    from github_poster import post_comment

    combined, verdict, summary = aggregate(outputs)
    print(f"    → 집계: C{summary.critical}/M{summary.major}/m{summary.minor}, 판정={verdict}")
    comment = refine(combined, verdict, "junior")
    print(f"    → 코멘트 생성 ({len(comment)} chars)")

    # ── 5. GitHub 등록 ──
    print("\n[5] GitHub PR #1 등록")
    repo_full = os.getenv("GITHUB_REPO", "kskt1234-netizen/-dev3-demo")
    owner, name = repo_full.split("/", 1)
    result = post_comment("", comment, owner=owner, repo=name, pr_num=PR_NUM)
    if result["mode"] == "github":
        print(f"    ✅ 진짜 등록 완료! comment_id={result['comment_id']}")
        print(f"    → https://github.com/{repo_full}/pull/{PR_NUM}")
    elif result["mode"] == "dry_run":
        print(f"    📄 dry-run (토큰 없음) → {result['path']}")
        print("    → .env에 GITHUB_TOKEN 넣으면 진짜 등록됩니다")

    banner("생성된 코멘트")
    print("\n" + comment)


if __name__ == "__main__":
    main()
