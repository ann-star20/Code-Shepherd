"""PostgreSQL 스키마 적용 스크립트.

Usage: python backend/scripts/seed_postgres.py
"""

import os
import sys
from pathlib import Path
import psycopg2

SCHEMA_FILE = Path(__file__).parent / "seed" / "security" / "schema.sql"


def main():
    conn = psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", "5433")),
        user=os.getenv("DB_USER", "postgres"),
        password=os.getenv("DB_PASSWORD", "postgres"),
        dbname=os.getenv("DB_NAME", "postgres"),
    )
    try:
        with conn.cursor() as cur:
            sql = SCHEMA_FILE.read_text(encoding="utf-8")
            cur.execute(sql)
        conn.commit()
        print("schema applied OK")
    except Exception as e:
        conn.rollback()
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
