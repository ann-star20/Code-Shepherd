"""API 토큰 생성."""
from __future__ import annotations

import secrets

TOKEN_BYTES = 32


def generate_api_token() -> str:
    return secrets.token_hex(TOKEN_BYTES)


def generate_reset_token() -> str:
    return secrets.token_urlsafe(TOKEN_BYTES)
