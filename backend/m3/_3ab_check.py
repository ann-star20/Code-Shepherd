"""3-A: Finding 품질 확인 + 3-B: review_issue 적재 완전성 확인."""
import asyncio, sys, json
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, ".")
from dotenv import load_dotenv
load_dotenv("../../.env")
import os, httpx, psycopg2
from contracts import ReviewInput
from src.graph import run_review_traced
from src.adapters.db_adapter import _pg_dsn_kwargs, _RULE_MAP, _SEVERITY_MAP, _build_row

GITHUB_ID = "kskt1234-netizen"
REPO = "kskt1234-netizen/-dev3-demo"
PR11 = 11
TOKEN = os.getenv("GITHUB_TOKEN", "")

# ─── 3-A ──────────────────────────────────────────────────────────────────────
async def check_3a():
    print("=" * 60)
    print("3-A: PR #11 Finding 품질 확인")
    print("=" * 60)

    # 1) PR #11 diff 수신
    owner, repo = REPO.split("/", 1)
    headers = {"Accept": "application/vnd.github.v3.diff",
               "User-Agent": "dev3-code-review-agent"}
    if TOKEN:
        headers["Authorization"] = f"Bearer {TOKEN}"
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.get(
            f"https://api.github.com/repos/{owner}/{repo}/pulls/{PR11}",
            headers=headers)
        r.raise_for_status()
        diff = r.text
    print(f"diff: {len(diff)} chars")

    # 2) 파이프라인 실행
    inp = ReviewInput(diff=diff, file_paths=[],
                      repo_meta={"pr_number": PR11, "repository": REPO})
    output, _, _ragas = await asyncio.to_thread(run_review_traced, inp)

    violations = [f for f in (output.findings or []) if f.verdict == "violation"]
    print(f"findings: total={len(output.findings or [])} violations={len(violations)}")

    if not violations:
        print("[FAIL] violation 없음 — CONV-SQL-008 미발화")
        return False

    f = violations[0]

    # Finding 필드
    row = _build_row(f, PR11, REPO, GITHUB_ID, diff)
    keyword, sub_cat = _RULE_MAP.get(f.rule_id, (f.rule_id, f.rule_id))
    db_severity = _SEVERITY_MAP.get(f.severity, f.severity.lower())

    checks = {
        "rule_id":       (f.rule_id,           "CONV-SQL-008"),
        "keyword":       (keyword,              "security"),
        "sub_category":  (sub_cat,             "SQL Injection"),
        "severity(db)":  (db_severity,          lambda v: v in ("medium", "high")),
        "code_snippet":  (row["code_snippet"],  lambda v: bool(v and v.strip())),
        "evidence_lines":(f.evidence_lines,     lambda v: bool(v)),
    }

    all_pass = True
    for field, (actual, expected) in checks.items():
        if callable(expected):
            ok = expected(actual)
            exp_str = "(not null/empty)"
        else:
            ok = (actual == expected)
            exp_str = repr(expected)
        flag = "PASS" if ok else "FAIL"
        print(f"  [{flag}] {field}: {repr(actual)!s:<50} (expected {exp_str})")
        if not ok:
            all_pass = False

    print(f"\n  evidence_lines sample: {f.evidence_lines[:2]}")
    print(f"  code_snippet: {repr(row['code_snippet'])}")
    print(f"\n3-A 판정: {'PASS' if all_pass else 'FAIL'}")
    return all_pass

# ─── 3-B ──────────────────────────────────────────────────────────────────────
def check_3b():
    print()
    print("=" * 60)
    print("3-B: review_issue 적재 완전성 확인")
    print("=" * 60)

    conn = psycopg2.connect(**_pg_dsn_kwargs())
    cur = conn.cursor()
    cur.execute("""
        SELECT user_id, pull_request_id, keyword, sub_category, code_snippet, name_of_function
        FROM review_issue
        WHERE github_id = %s AND keyword = 'security'
        ORDER BY created_at DESC LIMIT 3
    """, (GITHUB_ID,))
    rows = cur.fetchall()
    conn.close()

    print(f"조회 행: {len(rows)}행")
    if len(rows) < 3:
        print(f"[FAIL] 3행 미만 ({len(rows)}행)")
        return False

    USER_UUID = "c4cdf4aa-9e02-408e-b990-e44c7ad1fb49"
    all_pass = True
    for i, r in enumerate(rows):
        user_id, pr_id, keyword, sub_cat, snippet, func = r
        checks = {
            "user_id":         (str(user_id) if user_id else None, USER_UUID),
            "pull_request_id": (pr_id,    lambda v: v is not None),
            "keyword":         (keyword,  "security"),
            "sub_category":    (sub_cat,  "SQL Injection"),
            "code_snippet":    (snippet,  lambda v: bool(v and v.strip())),
        }
        row_ok = True
        print(f"\n  행 [{i+1}] name_of_function={func}")
        for field, (actual, expected) in checks.items():
            if callable(expected):
                ok = expected(actual)
                exp_str = "(not null)"
            else:
                ok = (str(actual) == str(expected))
                exp_str = repr(expected)
            flag = "PASS" if ok else "FAIL"
            val_str = repr(actual)[:50] if actual else "NULL"
            print(f"    [{flag}] {field}: {val_str}")
            if not ok:
                row_ok = False
                all_pass = False

    print(f"\n3-B 판정: {'PASS' if all_pass else 'FAIL'}")
    return all_pass

async def main():
    ok_a = await check_3a()
    ok_b = check_3b()
    print()
    print("=" * 60)
    print(f"종합: 3-A={'PASS' if ok_a else 'FAIL'}  3-B={'PASS' if ok_b else 'FAIL'}")

asyncio.run(main())
