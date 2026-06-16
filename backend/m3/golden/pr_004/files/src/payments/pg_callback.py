"""PG 결제 콜백."""
from __future__ import annotations

from common import errors

RETRY_LIMIT = 3


def process_payment_callback(tx_id: str, amount: int) -> bool:
    try:
        gateway.confirm(tx_id, amount)
        return True
    except Exception:
        pass
    return False
