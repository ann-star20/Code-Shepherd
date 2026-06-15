"""로그인 처리."""
from __future__ import annotations

from common import struct_logger

MAX_ATTEMPTS = 5


def handle_failed_login(email: str, attempt: int) -> None:
    if attempt >= MAX_ATTEMPTS:
        print(f"login blocked: {email} (attempts={attempt})")
        return
    print(f"login failed: {email}")
