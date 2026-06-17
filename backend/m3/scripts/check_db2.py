"""G3 DB 검증 — DB_HOST/PORT/NAME/USER/PASSWORD 조합으로 연결 시도."""
from __future__ import annotations
import os
import sys
from dotenv import load_dotenv

load_dotenv()

host = os.getenv("DB_HOST", "")
port = os.getenv("DB_PORT", "5432")
name = os.getenv("DB_NAME", "")
user = os.getenv("DB_USER", "")
password = os.getenv("DB_PASSWORD", "")
cloudsql = os.getenv("CLOUDSQL_INSTANCE_CONNECTION_NAME", "")

print("=== DB 환경변수 구조 ===")
print(f"DB_HOST: {'있음' if host else '없음'} | 값길이={len(host)}")
print(f"DB_PORT: {port}")
print(f"DB_NAME: {'있음' if name else '없음'}")
print(f"DB_USER: {'있음' if user else '없음'}")
print(f"DB_PASSWORD: {'있음' if password else '없음'}")
print(f"CLOUDSQL_INSTANCE_CONNECTION_NAME: {'있음' if cloudsql else '없음'}")

if not all([host, name, user, password]):
    print("\n필수 DB 변수 누락 — 연결 불가")
    sys.exit(1)

import psycopg2  # noqa: E402

# 직접 TCP 연결 시도
print("\n=== SELECT 1 (직접 TCP) ===")
try:
    conn = psycopg2.connect(
        host=host, port=int(port), dbname=name,
        user=user, password=password,
        connect_timeout=10, sslmode="require",
    )
    cur = conn.cursor()
    cur.execute("SELECT 1")
    print("SELECT 1:", cur.fetchone(), "— 연결 OK")

    # users 테이블
    print("\n=== users 테이블 스키마 ===")
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
        print("  users 테이블 없음 또는 권한 없음")

    # pull_requests 테이블
    print("\n=== pull_requests 테이블 스키마 ===")
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
        print("  pull_requests 테이블 없음 또는 권한 없음")

    # review_issues 테이블
    print("\n=== review_issues 테이블 스키마 ===")
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
        print("  review_issues 테이블 없음 또는 권한 없음")

    # 모든 테이블 목록
    print("\n=== 접근 가능한 모든 테이블 ===")
    cur.execute("""
        SELECT table_name FROM information_schema.tables
        WHERE table_schema = 'public'
        ORDER BY table_name
    """)
    tables = [r[0] for r in cur.fetchall()]
    print("  " + ", ".join(tables) if tables else "  없음")

    conn.close()
except Exception as exc:
    print(f"연결 실패: {type(exc).__name__}: {str(exc)[:300]}")
    sys.exit(1)
