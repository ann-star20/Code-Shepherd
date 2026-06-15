"""재고 확인 서비스."""
from __future__ import annotations

import httpx

INVENTORY_API = "https://inventory.internal"


async def check_stock(sku: str) -> dict:
    async with httpx.AsyncClient(timeout=5.0) as client:
        resp = await client.get(f"{INVENTORY_API}/stock", params={"sku": sku})
        resp.raise_for_status()
        return resp.json()
