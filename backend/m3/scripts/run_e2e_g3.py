"""G3 E2E: 데모 PR scene1 → ENABLE_DB_WRITE=true → review_issue INSERT → row 덤프."""
from __future__ import annotations
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

os.environ["ENABLE_DB_WRITE"] = "true"

from dotenv import load_dotenv
load_dotenv()

from src.adapters.db_adapter import check_pg_connection, _pg_dsn_kwargs

print("=== G3 E2E (컬럼 매핑 검증) ===")
ok, msg = check_pg_connection()
print(f"연결: ok={ok} msg={msg}")
if not ok:
    print("ERROR: DB 연결 불가")
    sys.exit(1)

import psycopg2
kwargs = _pg_dsn_kwargs()
conn = psycopg2.connect(connect_timeout=10, **kwargs)
cur = conn.cursor()
cur.execute("SELECT count(*) FROM review_issue")
before = cur.fetchone()[0]
print(f"INSERT 전 행 수: {before}")
conn.close()

from contracts import ReviewInput
from src.graph import run_review_traced
from src.adapters.db_adapter import insert_review_issues

diff = Path("fixtures/demo/scene1_violation.txt").read_text(encoding="utf-8")
out, trace, _ragas = run_review_traced(ReviewInput(
    diff=diff,
    file_paths=["services/payment.py"],
    repo_meta={"repo": "kskt1234-netizen/-dev3-demo"},
))

violations = [f for f in (out.findings or []) if f.verdict == "violation"]
print(f"\nfindings: {len(out.findings or [])}, violation: {len(violations)}")
for f in violations:
    print(f"  [{f.rule_id}] {f.severity} | evidence[0]: {f.evidence_lines[0][:60] if f.evidence_lines else ''}")

insert_review_issues(
    out.findings or [],
    pr_number=4,
    repository="kskt1234-netizen/-dev3-demo",
    github_id="kskt1234-netizen",
    diff=diff,
)

conn = psycopg2.connect(connect_timeout=10, **kwargs)
cur = conn.cursor()
cur.execute("SELECT count(*) FROM review_issue")
after = cur.fetchone()[0]
print(f"\nINSERT 후 행 수: {after} (증가: +{after - before})")

print("\n=== 최신 삽입 row (dev3 에이전트, 전 컬럼) ===")
cur.execute("""
    SELECT id, pull_request_id, user_id, github_id, agent, severity,
           keyword, sub_category, code_context, code_snippet,
           suggestion, programming_language, framework, framework_version,
           name_of_function, created_at
    FROM review_issue
    WHERE agent = 'dev3'
    ORDER BY created_at DESC
    LIMIT 2
""")
cols = [d[0] for d in cur.description]
rows = cur.fetchall()
for row in rows:
    print()
    for col, val in zip(cols, row):
        display = str(val)[:80] if val is not None else "NULL"
        print(f"  {col:25s}: {display}")

print("\n=== 팀 샘플 비교 (performance 에이전트 최신 1행) ===")
cur.execute("""
    SELECT agent, severity, keyword, sub_category, code_snippet,
           suggestion, programming_language, name_of_function
    FROM review_issue
    WHERE agent != 'dev3'
    ORDER BY created_at DESC
    LIMIT 1
""")
team_row = cur.fetchone()
if team_row:
    team_cols = [d[0] for d in cur.description]
    for col, val in zip(team_cols, team_row):
        print(f"  팀   {col:20s}: {str(val)[:80] if val else 'NULL'}")
else:
    print("  팀 샘플 없음")

conn.close()
print("\n[완료] ENABLE_DB_WRITE=false로 복귀 필요")
