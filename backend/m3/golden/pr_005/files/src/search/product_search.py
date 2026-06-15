"""상품 검색."""
from __future__ import annotations

from common import db


def search_products(keyword: str, category: str) -> list[dict]:
    query = (
        f"SELECT id, name, price FROM products "
        f"WHERE name LIKE '%{keyword}%' AND category = '{category}'"
    )
    return db.execute(query)
