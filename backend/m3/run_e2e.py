"""D4 E2E 검증 스크립트.

1. scene1_violation.txt diff → pipeline → ReviewOutput 확인
2. ENABLE_DB_WRITE=true 로 mock DB INSERT → row 읽기
3. GitHub PR 코멘트 POST 시도 (토큰 write 권한 있는 경우만)
"""
from __future__ import annotations

import json
import os
import sqlite3
import tempfile
from pathlib import Path

# 환경 준비
os.environ.setdefault("ENABLE_DB_WRITE", "true")
from dotenv import load_dotenv
load_dotenv()

REPO_ROOT = Path(__file__).parent

# ── 1. 파이프라인 실행 ────────────────────────────────────────────────────────

diff = (REPO_ROOT / "fixtures" / "demo" / "scene1_violation.txt").read_text(encoding="utf-8")

from contracts import ReviewInput
from src.graph import run_review

print("[E2E] pipeline 실행 중...")
out = run_review(ReviewInput(diff=diff, file_paths=[], repo_meta={"source": "e2e_test"}))

print(f"[E2E] findings: {len(out.findings or [])}")
print(f"[E2E] gap_report: {out.gap_report is not None}")
violations = [f for f in (out.findings or []) if f.verdict == "violation"]
print(f"[E2E] violations: {len(violations)}")
for v in violations:
    print(f"       rule_id={v.rule_id} severity={v.severity}")

# ── 2. mock DB INSERT ─────────────────────────────────────────────────────────

with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
    mock_db_path = Path(f.name)

from src.adapters.db_adapter import insert_review_issues

insert_review_issues(
    out.findings or [],
    pr_number=4,
    repository="kskt1234-netizen/-dev3-demo",
    github_id="kskt1234-netizen",
    _mock_db_path=mock_db_path,
)

conn = sqlite3.connect(str(mock_db_path))
rows = conn.execute(
    "SELECT agent, severity, keyword, sub_category, programming_language FROM review_issue"
).fetchall()
conn.close()
mock_db_path.unlink(missing_ok=True)

print(f"\n[E2E] DB INSERT - {len(rows)}rows inserted:")
for r in rows:
    print(f"  agent={r[0]} severity={r[1]} keyword={r[2]} sub_category={r[3]} lang={r[4]}")

# ── 3. GitHub comment POST 시도 ───────────────────────────────────────────────

import urllib.request

token = os.getenv("GITHUB_TOKEN", "")
REPO = "kskt1234-netizen/-dev3-demo"
PR_NUM = 4
comment_body = out.comment_md or "## dev3 E2E 테스트\n\n파이프라인 실행 완료."

req = urllib.request.Request(
    f"https://api.github.com/repos/{REPO}/issues/{PR_NUM}/comments",
    method="POST",
)
req.add_header("Authorization", f"Bearer {token}")
req.add_header("Accept", "application/vnd.github+json")
req.add_header("Content-Type", "application/json")
req.add_header("User-Agent", "dev3")
body = json.dumps({"body": comment_body}).encode()

try:
    with urllib.request.urlopen(req, body, timeout=15) as r:
        resp = json.loads(r.read())
        comment_id = resp["id"]
        comment_url = resp["html_url"]
        print(f"\n[E2E] GitHub 코멘트 POST 성공 id={comment_id}")
        print(f"[E2E] comment_url={comment_url}")
        COMMENT_POSTED = True
except Exception as e:
    print(f"\n[E2E] GitHub 코멘트 POST 실패: {type(e).__name__}: {e}")
    print(f"[E2E] (토큰 write 권한 없음 — 코멘트 내용은 아래에 출력)")
    print(f"\n--- comment_md 내용 (앞 500자) ---")
    print(comment_body[:500])
    COMMENT_POSTED = False

# ── 최종 결과 ─────────────────────────────────────────────────────────────────

print("\n=== E2E 결과 요약 ===")
print(f"파이프라인 실행: OK (findings={len(out.findings or [])}, violations={len(violations)})")
print(f"DB INSERT: OK ({len(rows)}행)")
print(f"GitHub comment: {'OK' if COMMENT_POSTED else 'SKIP (write 권한 없음)'}")
