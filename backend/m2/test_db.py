import os
import asyncio
import asyncpg
from dotenv import load_dotenv

load_dotenv()

async def main():
    url = os.getenv("DATABASE_URL")
    print("DATABASE_URL =", url)

    if not url:
        raise RuntimeError("DATABASE_URL is missing in .env")

    # SQLAlchemy용 URL이면 asyncpg 직접 연결용으로 변환
    url = url.replace("postgresql+asyncpg://", "postgresql://")

    conn = await asyncpg.connect(url)
    print("DB OK")
    await conn.close()

asyncio.run(main())