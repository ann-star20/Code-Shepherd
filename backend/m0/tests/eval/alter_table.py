import asyncio
import asyncpg

async def main():
    conn = await asyncpg.connect("postgresql://postgres:tasklink1!@34.22.101.111:5432/tasklink")
    await conn.execute(
        "ALTER TABLE documents ADD COLUMN IF NOT EXISTS quality_score FLOAT"
    )
    print("quality_score column added (or already exists)")
    await conn.close()

asyncio.run(main())
