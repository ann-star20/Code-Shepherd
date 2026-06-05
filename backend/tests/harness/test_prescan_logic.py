"""P1-T10 단위 테스트 — prescan 추론 로직 (DB 불필요)."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from app.interfaces.api.prescan import _infer_from_url, _infer_from_html


def test_infer_django_url():
    """URL 패턴에서 Django + 버전 추론."""
    f, v, c = _infer_from_url("https://docs.djangoproject.com/en/6.0/topics/security/")
    assert f == "Django", f"framework 오류: {f}"
    assert v == "6.0", f"version 오류: {v}"
    assert c >= 0.5, f"confidence 낮음: {c}"


def test_infer_owasp_url():
    """OWASP URL에서 프레임워크 추론."""
    f, v, c = _infer_from_url("https://owasp.org/Top10/A03_2021-Injection/")
    assert f == "OWASP"


def test_infer_unknown_url():
    """알 수 없는 URL은 None + 낮은 confidence."""
    f, v, c = _infer_from_url("https://unknown-docs.example.com/docs/")
    assert f is None
    assert c < 0.5


def test_infer_html_lang():
    """HTML lang 태그에서 언어 추론."""
    html = '<html lang="en"><head><title>Test</title></head></html>'
    _, _, lang, c = _infer_from_html(html, "https://unknown.com/")
    assert lang == "EN"


def test_infer_html_django_title():
    """HTML title에서 Django 추론 (URL 패턴 없을 때)."""
    html = '<html><head><title>Django Security Reference</title></head></html>'
    f, _, _, c = _infer_from_html(html, "https://unknown-host.com/docs/")
    assert f == "Django"


def test_infer_confidence_capped():
    """confidence는 1.0을 초과하지 않음."""
    html = '<html lang="ko"><head><title>Django 6.0 Docs</title></head></html>'
    _, _, _, c = _infer_from_html(html, "https://docs.djangoproject.com/en/6.0/")
    assert c <= 1.0
