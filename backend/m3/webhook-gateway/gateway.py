"""게이트웨이 핵심 — PR 정보를 받아 clone하고, 등록된 에이전트를 모두 호출.

흐름:
  PRContext(repo·sha·pr_number)
    → git clone (코드 받아오기)
    → GitHub API로 diff 수집
    → 등록된 분석 에이전트 전부 호출 (부분 실패 허용)
    → 이슈 합치기 + 집계 + 코멘트 + GitHub 등록
"""
from __future__ import annotations

import os
import subprocess
import tempfile
import time
import urllib.request

from registry import PRContext, registered_agents


def clone_repo(ctx: PRContext) -> str:
    """레포를 shallow clone하고 PR 브랜치/커밋으로 checkout → 로컬 경로 반환.

    PR의 결함 코드는 feature 브랜치에만 있으므로, commit_sha 또는 branch를
    반드시 받아와야 한다 (기본 clone은 main만 받아 빈 결과가 됨).
    """
    work = tempfile.mkdtemp(prefix="gw_repo_")
    # PR 브랜치를 직접 clone (가능하면) — 결함 코드가 있는 브랜치 확보
    if ctx.branch:
        r = subprocess.run(
            ["git", "clone", "--depth", "1", "--branch", ctx.branch,
             ctx.clone_url, work],
            capture_output=True,
        )
        if r.returncode == 0:
            return work
    # fallback: 기본 clone 후 commit_sha로 checkout
    subprocess.run(
        ["git", "clone", "--depth", "1", ctx.clone_url, work],
        check=True, capture_output=True,
    )
    if ctx.commit_sha:
        subprocess.run(
            ["git", "-C", work, "fetch", "--depth", "1", "origin", ctx.commit_sha],
            check=True, capture_output=True,
        )
        subprocess.run(
            ["git", "-C", work, "checkout", ctx.commit_sha],
            check=True, capture_output=True,
        )
    return work


def fetch_pr_diff(ctx: PRContext, token: str = "") -> str:
    """GitHub API로 PR의 unified diff를 가져온다 (토큰 없으면 빈 문자열)."""
    token = token or os.getenv("GITHUB_TOKEN", "")
    url = f"https://api.github.com/repos/{ctx.repo_full_name}/pulls/{ctx.pr_number}"
    req = urllib.request.Request(url)
    req.add_header("Accept", "application/vnd.github.v3.diff")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except Exception:
        return ""


def run_all_agents(ctx: PRContext) -> dict[str, list[dict]]:
    """등록된 모든 분석 에이전트를 호출. 결과를 {agent_name: issues[]}로 반환.

    부분 실패 허용: 한 에이전트가 죽어도 나머지는 계속.
    """
    results: dict[str, list[dict]] = {}
    for agent in registered_agents():
        try:
            issues = agent.fn(ctx) or []
        except Exception as e:  # noqa: BLE001
            print(f"  [partial_fail] {agent.name}: {e}")
            issues = []
        results[agent.name] = issues
    return results


def process_pr(ctx: PRContext, *, do_comment: bool = True) -> dict:
    """PR 1건 전체 처리: clone → diff → 분석 → (집계·코멘트).

    Returns:
        {"context": ctx, "results": {...}, "verdict": str, "comment": str, "post": {...}}
    """
    # 1. clone + diff
    ctx.work_dir = clone_repo(ctx)
    if not ctx.pr_diff:
        ctx.pr_diff = fetch_pr_diff(ctx)

    # 2. 등록된 에이전트 전부 호출 (분석 소요시간 측정)
    t0 = time.perf_counter()
    results = run_all_agents(ctx)
    execution_ms = int((time.perf_counter() - t0) * 1000)
    all_issues = [i for issues in results.values() for i in issues]

    out: dict = {
        "context": ctx,
        "results": results,
        "issue_count": len(all_issues),
    }

    # 3. DB 적재 (Dev4가 scan_id로 읽어감) — scan_executions + scan_issues + scan_summaries
    try:
        scan_id = _persist_to_db(ctx, results, all_issues, execution_ms)
        out["scan_id"] = scan_id
        print(f"  [DB] scan_id={scan_id} 적재 완료 (Dev4가 읽을 수 있음)")
    except Exception as e:  # noqa: BLE001
        print(f"  [DB 적재 skipped] {type(e).__name__}: {e}")

    # 4. (선택) 집계·코멘트 — pr-comment-agent 연결
    if do_comment:
        try:
            verdict, comment, post = _aggregate_and_comment(ctx, all_issues)
            out.update(verdict=verdict, comment=comment, post=post)
        except Exception as e:  # noqa: BLE001
            print(f"  [comment skipped] {e}")

    return out


def _pg_url() -> str:
    """POSTGRES_URL을 env 또는 형제 .env에서 찾는다."""
    if os.getenv("POSTGRES_URL"):
        return os.environ["POSTGRES_URL"]
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for d in ("test-performance-agent", "pr-comment-agent", "webhook-gateway"):
        p = os.path.join(root, d, ".env")
        if os.path.exists(p):
            for ln in open(p, encoding="utf-8"):
                ln = ln.strip()
                if ln.startswith("POSTGRES_URL="):
                    return ln.split("=", 1)[1].strip()
    raise RuntimeError("POSTGRES_URL 없음")


def _persist_to_db(ctx: PRContext, results: dict, all_issues: list[dict],
                   execution_ms: int = 0, conn=None) -> int:
    """공유 DB에 적재. scan_executions 1행 생성 → scan_issues INSERT + scan_summaries UPSERT.

    user_id는 users 테이블에서 임의 1명을 서브쿼리로 자동 선택 (PII를 코드/로그에 노출 안 함).
    execution_ms = 분석 전체 소요시간(ms). conn 주입 시 커밋·close는 호출자가 제어(테스트 격리).
    """
    own = conn is None
    if own:
        import json as _json
        import psycopg2
        from psycopg2.extras import Json

        conn = psycopg2.connect(_pg_url(), connect_timeout=10)
    try:
        with conn.cursor() as cur:
            # (scan_summaries 테이블은 팀이 이미 생성함 — CREATE 안 함, INSERT만)
            # scan_executions 1행 (user_id는 데모 user 1명 자동 선택)
            cur.execute("""
                INSERT INTO scan_executions (task_id, pr_id, user_id, execution_ms)
                SELECT %s, %s, user_id, %s FROM users LIMIT 1
                RETURNING id
            """, (f"gw-{ctx.pr_number}", str(ctx.pr_number), execution_ms))
            row = cur.fetchone()
            if not row:
                raise RuntimeError("users 테이블이 비어 scan_executions 생성 불가")
            scan_id = row[0]

            # agent별로 그룹핑해서 적재
            for agent_name, issues in results.items():
                if not issues:
                    continue
                # agent 값 정규화 (CHECK 제약: test_verification/performance/...)
                for i in issues:
                    ag = _normalize_agent(i.get("_agent") or agent_name)
                    cur.execute("""
                        INSERT INTO scan_issues
                          (scan_id, agent, severity, rule_id, file, line, message, suggestion,
                           keyword, sub_keyword, metric_value, sub_category, code_context)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    """, (scan_id, ag, i["severity"], i.get("rule_id", ""),
                          i.get("file", ""), i.get("line"), i.get("message", ""),
                          i.get("suggestion", ""),
                          i.get("keyword", ""), i.get("sub_keyword", ""),
                          i.get("metric_value", ""), i.get("sub_category", ""),
                          i.get("code_context", "")))
                # 집계 + metrics
                grp: dict = {}
                for i in issues:
                    ag = _normalize_agent(i.get("_agent") or agent_name)
                    g = grp.setdefault(ag, {"critical": 0, "major": 0, "minor": 0})
                    g[i["severity"].lower()] += 1
                for ag, c in grp.items():
                    cur.execute("""
                        INSERT INTO scan_summaries (scan_id, agent, critical, major, minor, metrics)
                        VALUES (%s,%s,%s,%s,%s,%s)
                        ON CONFLICT (scan_id, agent) DO UPDATE SET
                          critical=excluded.critical, major=excluded.major,
                          minor=excluded.minor, metrics=excluded.metrics
                    """, (scan_id, ag, c["critical"], c["major"], c["minor"], None))
        if own:
            conn.commit()
        return scan_id
    finally:
        if own:
            conn.close()


def _normalize_agent(name: str) -> str:
    """scan_issues.agent CHECK 허용값으로 정규화."""
    allowed = {"static_analysis", "security_scan", "test_verification", "performance"}
    if name in allowed:
        return name
    # Dev3 어댑터는 'test_verification'/'performance'를 _agent로 넣음. 그 외는 performance 기본
    return name if name in allowed else "performance"


def _aggregate_and_comment(ctx: PRContext, issues: list[dict]):
    """pr-comment-agent의 집계·코멘트·등록을 호출 (지연 import)."""
    import sys
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    prc = os.path.join(root, "pr-comment-agent")
    sys.path.insert(0, prc)

    # pr-comment-agent/.env 의 GITHUB_TOKEN·GOOGLE_API_KEY 로드 (게이트웨이가 공유)
    prc_env = os.path.join(prc, ".env")
    if os.path.exists(prc_env):
        for ln in open(prc_env, encoding="utf-8"):
            ln = ln.strip()
            if ln and not ln.startswith("#") and "=" in ln:
                k, v = ln.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())

    from contracts import CombinedIssue  # type: ignore
    from llm_refiner import refine
    from github_poster import post_comment

    combined = [
        CombinedIssue(
            severity=i["severity"], file=i.get("file", ""), line=i.get("line"),
            message=i.get("message", ""), rule_id=i.get("rule_id", ""),
            suggestion=i.get("suggestion", ""), source_agent=i.get("_agent", ""),
            rag_context=i.get("rag_context", ""),  # 사내 가이드 인용 — RAG §6
        )
        for i in issues
    ]
    crit = sum(1 for i in combined if i.severity == "Critical")
    major = sum(1 for i in combined if i.severity == "Major")
    verdict = "escalate" if crit >= 1 else ("rework" if major >= 3 else "lgtm")

    comment = refine(combined, verdict, "junior")
    owner, name = ctx.repo_full_name.split("/", 1)
    post = post_comment("", comment, owner=owner, repo=name, pr_num=ctx.pr_number)
    return verdict, comment, post
