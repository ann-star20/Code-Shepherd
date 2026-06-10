"""P1-T10 단위 테스트 — prescan v3 DB 주도형 추론 로직 (DB 미연결, fake conn)."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

import pytest

from app.interfaces.api.prescan import (
    _extract_doc_lang,
    _extract_title,
    _extract_version,
    _infer_via_db_patterns,
    _infer_via_title,
    _resolve_version,
)


class _FakeConn:
    """`framework_metadata` 조회만 흉내 내는 최소 fake asyncpg 커넥션."""

    def __init__(self, framework_rows):
        self._framework_rows = framework_rows

    async def fetch(self, query, *args):
        if "framework_metadata" in query:
            return self._framework_rows
        return []


# ── _extract_version ────────────────────────────────────────────────────────


def test_extract_version_from_url():
    """URL 경로의 버전 세그먼트를 추출한다."""
    v = _extract_version("https://docs.djangoproject.com/en/6.0/topics/security/")
    assert v == "6.0"


def test_extract_version_none_when_absent():
    """버전 세그먼트가 없으면 None."""
    v = _extract_version("https://unknown-docs.example.com/docs/")
    assert v is None


# ── _resolve_version ────────────────────────────────────────────────────────


def test_resolve_version_uses_url_segment_when_present():
    """URL에 버전 세그먼트가 있으면 그대로 사용한다."""
    v = _resolve_version("https://docs.djangoproject.com/en/6.0/topics/security/", "Django")
    assert v == "6.0"


def test_resolve_version_defaults_for_nestjs_without_url_version():
    """NestJS 문서는 URL에 버전이 없으므로 기본값(10.0)으로 보정한다."""
    v = _resolve_version("https://docs.nestjs.com/security/authorization", "NestJS")
    assert v == "10.0"


def test_resolve_version_none_for_unversioned_unknown_framework():
    """NestJS가 아닌 프레임워크는 URL에 버전이 없으면 None."""
    v = _resolve_version("https://docs.nestjs.com/security/authorization", "Django")
    assert v is None
    v2 = _resolve_version("https://unknown-docs.example.com/docs/", None)
    assert v2 is None


# ── _extract_doc_lang ───────────────────────────────────────────────────────


def test_extract_doc_lang_from_html():
    """`<html lang="...">`에서 대문자 언어 코드를 추출한다."""
    html = '<html lang="en"><head><title>Test</title></head></html>'
    assert _extract_doc_lang(html) == "EN"


def test_extract_doc_lang_strips_region_subtag():
    """`lang="ko-KR"`처럼 지역 서브태그가 있어도 기본 언어 코드만 반환한다."""
    html = '<html lang="ko-KR"><head></head></html>'
    assert _extract_doc_lang(html) == "KO"


def test_extract_doc_lang_none_when_absent():
    """`lang` 속성이 없으면 None."""
    html = "<html><head><title>Test</title></head></html>"
    assert _extract_doc_lang(html) is None


# ── _extract_title ──────────────────────────────────────────────────────────


def test_extract_title():
    html = "<html><head><title>Django Security Reference</title></head></html>"
    assert _extract_title(html) == "Django Security Reference"


def test_extract_title_none_when_absent():
    html = "<html><head></head></html>"
    assert _extract_title(html) is None


# ── _infer_via_db_patterns ───────────────────────────────────────────────────


@pytest.mark.anyio
async def test_infer_via_db_patterns_matches_registered_framework():
    """`framework_metadata.url_patterns` 정규식이 URL에 매칭되면 framework + base confidence 반환."""
    conn = _FakeConn([{"framework": "Django", "url_patterns": [r"djangoproject\.com"]}])

    framework, confidence = await _infer_via_db_patterns(
        conn, "https://docs.djangoproject.com/en/6.0/topics/security/"
    )

    assert framework == "Django"
    assert confidence == 0.5


@pytest.mark.anyio
async def test_infer_via_db_patterns_no_match_returns_none():
    """등록된 패턴 중 일치하는 것이 없으면 (None, 0.0)."""
    conn = _FakeConn([{"framework": "Django", "url_patterns": [r"djangoproject\.com"]}])

    framework, confidence = await _infer_via_db_patterns(
        conn, "https://unknown-docs.example.com/docs/"
    )

    assert framework is None
    assert confidence == 0.0


@pytest.mark.anyio
async def test_infer_via_db_patterns_skips_invalid_regex():
    """잘못된 정규식은 re.error로 건너뛰고 다음 패턴 매칭을 계속 시도한다."""
    conn = _FakeConn(
        [
            {"framework": "Broken", "url_patterns": ["(unclosed["]},
            {"framework": "Django", "url_patterns": [r"djangoproject\.com"]},
        ]
    )

    framework, confidence = await _infer_via_db_patterns(
        conn, "https://docs.djangoproject.com/en/6.0/topics/security/"
    )

    assert framework == "Django"
    assert confidence == 0.5


# ── _infer_via_title ─────────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_infer_via_title_matches_registered_framework():
    """URL 패턴 매칭 실패 시 `<title>`에 등록된 framework명이 있으면 추론."""
    conn = _FakeConn([{"framework": "Django"}])
    html = "<html><head><title>Django Security Reference</title></head></html>"

    framework = await _infer_via_title(conn, html)

    assert framework == "Django"


@pytest.mark.anyio
async def test_infer_via_title_no_title_returns_none():
    conn = _FakeConn([{"framework": "Django"}])
    html = "<html><head></head></html>"

    framework = await _infer_via_title(conn, html)

    assert framework is None


@pytest.mark.anyio
async def test_infer_via_title_no_match_returns_none():
    conn = _FakeConn([{"framework": "Django"}])
    html = "<html><head><title>Unrelated Page</title></head></html>"

    framework = await _infer_via_title(conn, html)

    assert framework is None
