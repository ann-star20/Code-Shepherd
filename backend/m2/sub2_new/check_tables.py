import os
import asyncio
from dotenv import load_dotenv
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

load_dotenv()

async def main():
    url = os.getenv("DATABASE_URL")

    engine = create_async_engine(
        url,
        pool_pre_ping=True,
        pool_recycle=60,
        pool_size=1,
        max_overflow=0,
    )

    async with engine.begin() as conn:
        result = await conn.execute(text("""
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
            ORDER BY table_name
        """))

        tables = [row[0] for row in result.fetchall()]
        print("tables:")
        for t in tables:
            print("-", t)

    await engine.dispose()

asyncio.run(main())