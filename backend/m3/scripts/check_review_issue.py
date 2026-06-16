"""review_issue 테이블 스키마 확인."""
from __future__ import annotations
import os
from dotenv import load_dotenv

load_dotenv()

import psycopg2  # noqa: E402

conn = psycopg2.connect(
    host=os.getenv("DB_HOST"), port=int(os.getenv("DB_PORT", "5432")),
    dbname=os.getenv("DB_NAME"), user=os.getenv("DB_USER"),
    password=os.getenv("DB_PASSWORD"), connect_timeout=10, sslmode="require",
)
cur = conn.cursor()

print("=== review_issue 테이블 스키마 ===")
cur.execute("""
    SELECT column_name, data_type, is_nullable, column_default
    FROM information_schema.columns
    WHERE table_name = 'review_issue'
    ORDER BY ordinal_position
""")
for col, dtype, nullable, default in cur.fetchall():
    print(f"  {col} ({dtype}) null={nullable} default={default}")

print("\n=== pr_reviews 테이블 스키마 ===")
cur.execute("""
    SELECT column_name, data_type, is_nullable, column_default
    FROM information_schema.columns
    WHERE table_name = 'pr_reviews'
    ORDER BY ordinal_position
""")
for col, dtype, nullable, default in cur.fetchall():
    print(f"  {col} ({dtype}) null={nullable} default={default}")

print("\n=== pull_requests 샘플 1행 (컬럼명만) ===")
cur.execute("SELECT * FROM pull_requests LIMIT 1")
if cur.description:
    print("  컬럼:", [d[0] for d in cur.description])
    row = cur.fetchone()
    if row:
        print("  github_pr_number:", row[cur.description.index(next(d for d in cur.description if d[0]=='github_pr_number'))])

conn.close()
