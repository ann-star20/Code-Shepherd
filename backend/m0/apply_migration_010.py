"""Apply migration 010 — add stage5_latency_ms column to documents table.

Stage 5 (Gemini LLM 호출) latency를 documents 테이블에 저장해 /details API로 노출한다.
이 값은 파이프라인 성능 분석(T5 벤치마크)에 사용된다.
"""
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
        for col, col_type in [("stage5_latency_ms", "INTEGER")]:
            result = await conn.execute(
                sa.text("""
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
