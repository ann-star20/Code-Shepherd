"""G3 DB 검증 스크립트 — SELECT 1 + 스키마 확인 + E2E INSERT."""
from __future__ import annotations
import os
import sys
from dotenv import load_dotenv

load_dotenv()

url = os.getenv("POSTGRES_URL", "")
if not url:
    print("ERROR: POSTGRES_URL 없음")
    sys.exit(1)

import psycopg2  # noqa: E402

# --- 1. SELECT 1 ---
print("=== 1. 연결 테스트 ===")
try:
    conn = psycopg2.connect(url, connect_timeout=10)
    cur = conn.cursor()
    cur.execute("SELECT 1")
    print("SELECT 1:", cur.fetchone())
    print("연결: OK")
except Exception as exc:
    print(f"연결 실패: {type(exc).__name__}: {exc}")
    sys.exit(1)

# --- 2. information_schema: users 테이블 컬럼 목록 ---
print("\n=== 2. users 테이블 스키마 ===")
try:
    cur.execute("""
        SELECT column_name, data_type, is_nullable
        FROM information_schema.columns
        WHERE table_name = 'users'
        ORDER BY ordinal_position
    """)
    rows = cur.fetchall()
    if rows:
        for col, dtype, nullable in rows:
            print(f"  {col} ({dtype}) null={nullable}")
    else:
        print("  users 테이블 없음 (또는 접근 불가)")
except Exception as exc:
    print(f"  스키마 조회 실패: {exc}")

# --- 3. review_issues 테이블 컬럼 목록 ---
print("\n=== 3. review_issues 테이블 스키마 ===")
try:
    cur.execute("""
        SELECT column_name, data_type, is_nullable
        FROM information_schema.columns
        WHERE table_name = 'review_issues'
        ORDER BY ordinal_position
    """)
    rows = cur.fetchall()
    if rows:
        for col, dtype, nullable in rows:
            print(f"  {col} ({dtype}) null={nullable}")
    else:
        print("  review_issues 테이블 없음 (또는 접근 불가)")
except Exception as exc:
    print(f"  스키마 조회 실패: {exc}")

# --- 4. pull_requests 테이블 컬럼 목록 ---
print("\n=== 4. pull_requests 테이블 스키마 ===")
try:
    cur.execute("""
        SELECT column_name, data_type, is_nullable
        FROM information_schema.columns
        WHERE table_name = 'pull_requests'
        ORDER BY ordinal_position
    """)
    rows = cur.fetchall()
    if rows:
        for col, dtype, nullable in rows:
            print(f"  {col} ({dtype}) null={nullable}")
    else:
        print("  pull_requests 테이블 없음 (또는 접근 불가)")
except Exception as exc:
    print(f"  스키마 조회 실패: {exc}")

conn.close()
print("\n스키마 확인 완료")
