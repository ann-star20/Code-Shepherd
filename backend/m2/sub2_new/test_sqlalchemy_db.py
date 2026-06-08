import os
import sys
import asyncio

if sys.platform.startswith("win"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from dotenv import load_dotenv
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

load_dotenv()

async def main():
    url = os.getenv("DATABASE_URL")
    print("DB host =", url.split("@")[-1] if url else None)

    engine = create_async_engine(
        url,
        pool_pre_ping=True,
        pool_recycle=60,
        pool_size=1,
        max_overflow=0,
    )

    async with engine.begin() as conn:
        result = await conn.execute(text("SELECT 1"))
        print("SELECT result =", result.scalar())

    await engine.dispose()
    print("SQLAlchemy DB OK")

asyncio.run(main())