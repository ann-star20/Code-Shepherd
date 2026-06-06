import sys
import asyncio
import asyncpg

if sys.platform.startswith("win"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

async def main():
    conn = await asyncpg.connect(
        user="postgres",
        password="1234",
        database="dev2_db",
        host="127.0.0.1",
        port=55432,
        ssl=False,
    )

    value = await conn.fetchval("SELECT 1")
    print("RESULT =", value)

    await conn.close()

asyncio.run(main())