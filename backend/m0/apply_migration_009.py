"""Apply migration 009 — add metadata_score column to documents table."""
import asyncio
import sys

sys.path.insert(0, "/app/_shared")
sys.path.insert(0, "/app/service")

async def main():
    from shared.config import get_settings
    from shared.db import _engine
    import sqlalchemy as sa

    settings = get_settings()
    print(f"DB URL: {str(settings.database_url)[:50]}...")

    async with _engine.begin() as conn:
        for col, col_type in [("metadata_score", "FLOAT"), ("error_message", "TEXT")]:
            result = await conn.execute(
                sa.text(f"""
                    SELECT column_name FROM information_schema.columns
                    WHERE table_name = 'documents' AND column_name = :col
                """),
                {"col": col},
            )
            if result.fetchone():
                print(f"Column '{col}' already exists. Skipping.")
            else:
                await conn.execute(
                    sa.text(f"ALTER TABLE documents ADD COLUMN {col} {col_type}")
                )
                print(f"Added column '{col}' to documents table.")

asyncio.run(main())
