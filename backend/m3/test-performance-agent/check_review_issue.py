"""review_issue 적재 확인 — m3 분석 이슈(test_verification·performance)가
GCP review_issue 에 실제로 들어갔는지 본다.

실행(컨테이너 안):
  docker compose exec m3 sh -c 'cd /app/service/test-performance-agent && uv run python check_review_issue.py'
"""
import os
import sys

import psycopg2

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import persist  # noqa: E402


def _pg_url() -> str:
    """persist._pg_url 재사용 — placeholder(가짜 견본 URL) 걸러내는 로직 공유."""
    url = persist._pg_url()
    if not url:
        raise SystemExit("POSTGRES_URL 없음(또는 placeholder만 있음)")
    return url


def main() -> None:
    conn = psycopg2.connect(_pg_url(), connect_timeout=10)
    cur = conn.cursor()

    cur.execute(
        "SELECT agent, count(*) FROM review_issue GROUP BY agent ORDER BY agent"
    )
    print("=== agent별 행수 ===")
    for agent, n in cur.fetchall():
        print(f"  {agent:20} {n}")

    cur.execute(
        """
        SELECT ri.agent, ri.severity, ri.keyword, ri.name_of_function,
               pr.repository_full_name, pr.github_pr_number, ri.created_at
        FROM review_issue ri
        LEFT JOIN pull_requests pr ON pr.id = ri.pull_request_id
        WHERE ri.agent IN ('test_verification', 'performance')
        ORDER BY ri.created_at DESC
        LIMIT 10
        """
    )
    rows = cur.fetchall()
    print(f"\n=== m3 최근 이슈 {len(rows)}건 ===")
    if not rows:
        print("  (아직 m3 이슈 없음 — PR 쏘면 채워짐)")
    for r in rows:
        agent, sev, kw, fn, repo, pr_num, created = r
        print(f"  [{agent:17}] {sev:8} {kw or '-':8} fn={fn or '-':15} "
              f"{repo}#{pr_num}  {created}")

    # F5 빈칸 점검 — 최근 행의 github_id·언어·프레임워크·스니펫 채움 여부
    cur.execute(
        """
        SELECT ri.agent, ri.github_id, ri.programming_language, ri.framework,
               ri.framework_version,
               (ri.code_snippet IS NOT NULL AND ri.code_snippet <> '') AS has_snippet,
               (ri.code_context IS NOT NULL AND ri.code_context <> '') AS has_context
        FROM review_issue ri
        WHERE ri.agent IN ('test_verification', 'performance')
        ORDER BY ri.created_at DESC
        LIMIT 5
        """
    )
    print("\n=== F5 빈칸 점검 (최근 5건) ===")
    for r in cur.fetchall():
        agent, gid, lang, fw, fwv, snip, ctx = r
        print(f"  [{agent:17}] github_id={gid or '∅':20} lang={lang or '∅':8} "
              f"fw={fw or '∅':8} ver={fwv or '∅':8} snippet={'O' if snip else '∅'} "
              f"context={'O' if ctx else '∅'}")

    conn.close()


if __name__ == "__main__":
    main()
