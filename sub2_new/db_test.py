import os
import sys
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text

if sys.platform.startswith("win"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

async def main():
    print("DATABASE_URL =", os.getenv("DATABASE_URL"))

    engine = create_async_engine(
        os.environ["DATABASE_URL"],
        echo=True,
        pool_pre_ping=True,
    )

    async with engine.connect() as conn:
        result = await conn.execute(text("SELECT 1"))
        print("RESULT =", result.scalar())

    await engine.dispose()

asyncio.run(main())