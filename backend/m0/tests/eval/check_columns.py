import asyncio
import asyncpg

async def check():
    conn = await asyncpg.connect("postgresql://postgres:tasklink1!@34.22.101.111:5432/tasklink")
    rows = await conn.fetch(
        "SELECT column_name, data_type FROM information_schema.columns "
        "WHERE table_name='documents' ORDER BY ordinal_position"
    )
    for r in rows:
        print(r["column_name"], r["data_type"])
    await conn.close()

asyncio.run(check())
