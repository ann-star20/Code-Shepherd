"""내부 서비스(m1) 전용 인증."""

from __future__ import annotations

from fastapi import Header, HTTPException, status

from shared.config import get_settings


async def verify_internal_token(
    x_internal_token: str | None = Header(default=None, alias="X-Internal-Token"),
) -> None:
    expected = get_settings().internal_service_token
    if not expected or not x_internal_token or not (
        x_internal_token == expected
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid internal service token",
        )
