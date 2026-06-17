"""
TDD Cycle: chat_routes — else 브랜치 권한 필터 누락 버그

버그:
  chat() 엔드포인트의 storage 분기에서 알 수 없는 storage 타입이 들어오면
  else 브랜치가 실행되는데, 이때 _query_pgvector()를 user_team/user_id 없이 호출한다.
  → 권한 필터 없이 전체 DB 청크가 RAG 컨텍스트에 포함될 수 있음.

목표:
  else 브랜치도 user_team, user_id를 _query_pgvector에 전달해야 한다.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


FAKE_USER = {"user_id": "user-123", "team": "team-alpha", "role": "member"}
FAKE_QUESTION = "테스트 질문입니다"


def _make_intent_mock(storages: list[str]):
    """_classify_intent를 mock하여 지정 storages를 반환한다."""
    result = MagicMock()
    result.storages = storages
    result.intent = "semantic"
    return AsyncMock(return_value=result)


class TestChatElseBranchPermissionFilter:
    """storage 분기의 else 브랜치가 권한 파라미터를 전달하는지 검증."""

    @pytest.mark.asyncio
    async def test_unknown_storage_passes_user_team_to_pgvector(self):
        """알 수 없는 storage 타입 → else 브랜치 → _query_pgvector에 user_team 포함."""
        from app.routes.chat_routes import chat

        captured_kwargs: list[dict] = []

        async def mock_query_pgvector(*args, **kwargs):
            captured_kwargs.append(kwargs)
            return []

        mock_request = MagicMock()
        mock_request.question = FAKE_QUESTION
        mock_request.top_k = 5
        mock_request.storages = None

        with (
            patch("app.routes.chat_routes._classify_intent", _make_intent_mock(["unknown_storage"])),
            patch("app.routes.chat_routes._query_pgvector", side_effect=mock_query_pgvector),
            patch("app.routes.chat_routes._generate_answer", AsyncMock(return_value="답변")),
            patch("app.routes.chat_routes._collect_page_images", AsyncMock(return_value=[])),
            patch("app.routes.chat_routes._get_session_factory", return_value=MagicMock()),
        ):
            await chat(mock_request, MagicMock(), FAKE_USER)

        assert captured_kwargs, "_query_pgvector가 호출되지 않음"
        kwargs = captured_kwargs[0]
        assert "user_team" in kwargs, (
            f"else 브랜치에서 user_team 누락. 실제 kwargs: {list(kwargs.keys())}"
        )
        assert kwargs["user_team"] == "team-alpha", (
            f"user_team 값 불일치. 예상: 'team-alpha', 실제: {kwargs.get('user_team')}"
        )

    @pytest.mark.asyncio
    async def test_unknown_storage_passes_user_id_to_pgvector(self):
        """알 수 없는 storage 타입 → else 브랜치 → _query_pgvector에 user_id 포함."""
        from app.routes.chat_routes import chat

        captured_kwargs: list[dict] = []

        async def mock_query_pgvector(*args, **kwargs):
            captured_kwargs.append(kwargs)
            return []

        mock_request = MagicMock()
        mock_request.question = FAKE_QUESTION
        mock_request.top_k = 5
        mock_request.storages = None

        with (
            patch("app.routes.chat_routes._classify_intent", _make_intent_mock(["unknown_storage"])),
            patch("app.routes.chat_routes._query_pgvector", side_effect=mock_query_pgvector),
            patch("app.routes.chat_routes._generate_answer", AsyncMock(return_value="답변")),
            patch("app.routes.chat_routes._collect_page_images", AsyncMock(return_value=[])),
            patch("app.routes.chat_routes._get_session_factory", return_value=MagicMock()),
        ):
            await chat(mock_request, MagicMock(), FAKE_USER)

        kwargs = captured_kwargs[0]
        assert "user_id" in kwargs, (
            f"else 브랜치에서 user_id 누락. 실제 kwargs: {list(kwargs.keys())}"
        )
        assert kwargs["user_id"] == "user-123", (
            f"user_id 값 불일치. 예상: 'user-123', 실제: {kwargs.get('user_id')}"
        )

    @pytest.mark.asyncio
    async def test_pgvector_storage_still_passes_user_context(self):
        """정상 pgvector 브랜치도 권한 파라미터를 올바르게 전달한다 (회귀 방지)."""
        from app.routes.chat_routes import chat

        captured_kwargs: list[dict] = []

        async def mock_query_pgvector(*args, **kwargs):
            captured_kwargs.append(kwargs)
            return []

        mock_request = MagicMock()
        mock_request.question = FAKE_QUESTION
        mock_request.top_k = 5
        mock_request.storages = None

        with (
            patch("app.routes.chat_routes._classify_intent", _make_intent_mock(["pgvector"])),
            patch("app.routes.chat_routes._query_pgvector", side_effect=mock_query_pgvector),
            patch("app.routes.chat_routes._generate_answer", AsyncMock(return_value="답변")),
            patch("app.routes.chat_routes._collect_page_images", AsyncMock(return_value=[])),
            patch("app.routes.chat_routes._get_session_factory", return_value=MagicMock()),
        ):
            await chat(mock_request, MagicMock(), FAKE_USER)

        assert captured_kwargs, "_query_pgvector가 호출되지 않음"
        kwargs = captured_kwargs[0]
        assert kwargs.get("user_team") == "team-alpha"
        assert kwargs.get("user_id") == "user-123"
