"""TDD (RED): SearchResultItem + ChatSource — page_image_path 필드 검증.

테스트 대상:
    kms_routes.SearchResultItem  → page_image_path: Optional[str] 필드
    chat_routes.ChatSource       → page_image_path: Optional[str] 필드

User Journey:
    As a frontend consuming the KMS search API, I want each search result to include
    page_image_path so that I can render the original document page image
    alongside the matched text chunk for multimodal context.

ALL TESTS SHOULD FAIL UNTIL page_image_path is added to SearchResultItem and ChatSource.
"""

from __future__ import annotations


# ---------------------------------------------------------------------------
# User Journey 1: SearchResultItem — page_image_path 필드
# ---------------------------------------------------------------------------

class TestSearchResultItemSchema:

    def test_has_page_image_path_field(self):
        """SearchResultItem은 page_image_path 필드를 가져야 한다."""
        from app.routes.kms_routes import SearchResultItem

        fields = SearchResultItem.model_fields
        assert "page_image_path" in fields, (
            "SearchResultItem에 page_image_path 필드가 없습니다. "
            "kms_routes.py의 SearchResultItem에 page_image_path: str | None = None 을 추가하세요."
        )

    def test_page_image_path_is_optional(self):
        """page_image_path는 Optional(기본값 None)이어야 한다."""
        from app.routes.kms_routes import SearchResultItem

        # page_image_path 없이 인스턴스 생성 가능해야 함
        item = SearchResultItem(
            chunk_id="abc",
            content="내용",
            score=0.9,
        )
        assert item.page_image_path is None

    def test_page_image_path_accepts_string(self):
        """page_image_path에 문자열 경로를 설정할 수 있어야 한다."""
        from app.routes.kms_routes import SearchResultItem

        path = "images/doc-id/page_1.png"
        item = SearchResultItem(
            chunk_id="abc",
            content="내용",
            score=0.9,
            page_image_path=path,
        )
        assert item.page_image_path == path

    def test_page_image_path_serialized_in_json(self):
        """JSON 직렬화 결과에 page_image_path가 포함되어야 한다."""
        from app.routes.kms_routes import SearchResultItem

        item = SearchResultItem(
            chunk_id="abc",
            content="내용",
            score=0.9,
            page_image_path="images/doc-id/page_2.png",
        )
        data = item.model_dump()
        assert "page_image_path" in data
        assert data["page_image_path"] == "images/doc-id/page_2.png"

    def test_page_image_path_none_serialized_in_json(self):
        """page_image_path=None도 JSON에 포함되어야 한다."""
        from app.routes.kms_routes import SearchResultItem

        item = SearchResultItem(chunk_id="abc", content="내용", score=0.5)
        data = item.model_dump()
        assert "page_image_path" in data
        assert data["page_image_path"] is None


# ---------------------------------------------------------------------------
# User Journey 2: ChatSource — page_image_path 필드
# ---------------------------------------------------------------------------

class TestChatSourceSchema:

    def test_has_page_image_path_field(self):
        """ChatSource는 page_image_path 필드를 가져야 한다."""
        from app.routes.chat_routes import ChatSource

        fields = ChatSource.model_fields
        assert "page_image_path" in fields, (
            "ChatSource에 page_image_path 필드가 없습니다. "
            "chat_routes.py의 ChatSource에 page_image_path: str | None = None 을 추가하세요."
        )

    def test_page_image_path_is_optional(self):
        """page_image_path는 Optional(기본값 None)이어야 한다."""
        from app.routes.chat_routes import ChatSource

        source = ChatSource(chunk_id="abc", content="내용", score=0.8)
        assert source.page_image_path is None

    def test_page_image_path_accepts_string(self):
        """page_image_path에 문자열 경로를 설정할 수 있어야 한다."""
        from app.routes.chat_routes import ChatSource

        path = "images/doc-id/page_3.png"
        source = ChatSource(
            chunk_id="abc",
            content="내용",
            score=0.8,
            page_image_path=path,
        )
        assert source.page_image_path == path

    def test_page_image_path_serialized_in_json(self):
        """JSON 직렬화 결과에 page_image_path가 포함되어야 한다."""
        from app.routes.chat_routes import ChatSource

        source = ChatSource(
            chunk_id="abc",
            content="내용",
            score=0.8,
            page_image_path="images/doc-id/page_3.png",
        )
        data = source.model_dump()
        assert "page_image_path" in data
        assert data["page_image_path"] == "images/doc-id/page_3.png"
