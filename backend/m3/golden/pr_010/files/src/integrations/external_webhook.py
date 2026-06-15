"""외부 웹훅 연동."""
from __future__ import annotations

from common import config


def get_webhook_settings() -> dict:
    settings = config.from_env()
    return {
        "endpoint": settings.webhook_endpoint,
        "secret": settings.webhook_secret,
    }
