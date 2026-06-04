"""레이어 A — 결정론적 유틸 테스트 (T01, T02). PRD §10.2."""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parents[2]))

from app.domain.models import build_doc_id


# ── T01: doc_id 멱등성 ───────────────────────────────────────────────────────
def test_doc_id_idempotency():
    """동일 URL + 동일 content로 3회 호출 → 모두 동일한 doc_id."""
    # Arrange
    url     = "https://docs.djangoproject.com/en/6.0/topics/security/"
    content = "sample content"

    # Act
    ids = [build_doc_id("EXT", url, content) for _ in range(3)]

    # Assert
    assert ids[0] == ids[1] == ids[2]


# ── T02: 동일 URL + 콘텐츠 변경 → 해시만 다름 (rsplit 안전 버전) ────────────
def test_doc_id_content_change():
    """동일 URL, 다른 content → prefix(URL 파트) 동일, hash suffix 상이."""
    # Arrange
    url = "https://noru-sh.tistory.com/25"

    # Act
    id_v1 = build_doc_id("EXT", url, "version 1 content")
    id_v2 = build_doc_id("EXT", url, "version 2 content — updated")

    # Assert — rsplit("_", 1)로 해시만 분리 (URL에 _가 포함돼도 안전)
    prefix_v1, hash_v1 = id_v1.rsplit("_", 1)
    prefix_v2, hash_v2 = id_v2.rsplit("_", 1)

    assert prefix_v1 == prefix_v2, "URL 파트(prefix)는 동일해야 한다"
    assert hash_v1   != hash_v2,   "content가 다르면 hash suffix도 달라야 한다"


# ── T02-extra: 언더스코어 포함 URL 안전성 ────────────────────────────────────
def test_doc_id_url_with_underscore():
    """URL 경로에 '_'가 포함돼도 rsplit 기반 prefix 비교가 올바르게 동작한다."""
    # Arrange
    url = "https://docs.example.com/en/some_topic/security/"

    # Act
    id_v1 = build_doc_id("EXT", url, "content v1")
    id_v2 = build_doc_id("EXT", url, "content v2")

    # Assert
    prefix_v1, hash_v1 = id_v1.rsplit("_", 1)
    prefix_v2, hash_v2 = id_v2.rsplit("_", 1)
    assert prefix_v1 == prefix_v2
    assert hash_v1   != hash_v2


# ── 보너스: ETag 우선순위 ────────────────────────────────────────────────────
def test_doc_id_etag_takes_priority_over_content():
    """etag가 있으면 content가 달라도 etag 기준으로 해시 결정."""
    # Arrange
    url = "https://docs.djangoproject.com/en/6.0/topics/security/"

    # Act
    id_with_etag_a = build_doc_id("EXT", url, content="ignored", etag="abc123")
    id_with_etag_b = build_doc_id("EXT", url, content="different content", etag="abc123")

    # Assert — 동일 etag → 동일 hash
    assert id_with_etag_a == id_with_etag_b
