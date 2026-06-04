"""G3: Pre-scan Layer 테스트."""

import pytest
from app.usecases.prescan import PreScanResult, prescan_url, prescan_html, prescan


# T_prescan_django_url
def test_prescan_django_url():
    url = "https://docs.djangoproject.com/en/6.0/topics/security/"
    result = prescan_url(url)
    assert result.framework == "Django"
    assert result.version == "6.0"
    assert result.lang == "EN"


# T_prescan_html_title
def test_prescan_html_title():
    html = "<title>Spring Security 6.1 Reference</title>"
    result = prescan_html(html)
    assert result.framework == "Spring"


# T_prescan_html_lang
def test_prescan_html_lang():
    html = '<html lang="ko"><head></head><body></body></html>'
    result = prescan_html(html)
    assert result.lang == "KO"


# T_prescan_unknown_low
def test_prescan_unknown_low():
    url = "https://example.com/some/random/path"
    html = ""
    result = prescan(url, html)
    assert result.confidence < 0.3
