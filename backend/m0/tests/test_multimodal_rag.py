"""
TDD RED: 멀티모달 RAG — GCS 이미지 로드 + Gemini 멀티모달 답변 생성

C-1: _load_page_image()  — GCS에서 이미지 바이트 로드
C-2: _collect_page_images() — 청크에서 중복 제거 후 이미지 수집
C-3: _generate_answer() — page_images 파라미터 추가 + 멀티모달 Gemini 호출
C-4: chat endpoint — _collect_page_images → _generate_answer 연결
"""
from __future__ import annotations

import base64
import pytest
from unittest.mock import AsyncMock, MagicMock, patch, call


# ---------------------------------------------------------------------------
# C-1: _load_page_image
# ---------------------------------------------------------------------------

class TestLoadPageImage:
    """_load_page_image(path) — GCS에서 이미지 바이트 로드."""

    @pytest.mark.asyncio
    async def test_returns_bytes_for_valid_path(self):
        """유효한 GCS 경로면 bytes를 반환한다."""
        from app.routes.chat_routes import _load_page_image

        fake_bytes = b"\x89PNG\r\n\x1a\n" + b"\x00" * 20
        mock_storage = AsyncMock()
        mock_storage.load = AsyncMock(return_value=fake_bytes)

        with patch("app.routes.chat_routes._get_storage", return_value=mock_storage):
            result = await _load_page_image("images/doc-abc/page_1.png")

        assert result == fake_bytes

    @pytest.mark.asyncio
    async def test_returns_none_for_none_path(self):
        """path가 None이면 None을 반환한다."""
        from app.routes.chat_routes import _load_page_image

        result = await _load_page_image(None)
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_for_empty_path(self):
        """path가 빈 문자열이면 None을 반환한다."""
        from app.routes.chat_routes import _load_page_image

        result = await _load_page_image("")
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_on_gcs_error(self):
        """GCS 로드 실패 시 None을 반환한다 (graceful degradation)."""
        from app.routes.chat_routes import _load_page_image

        mock_storage = AsyncMock()
        mock_storage.load = AsyncMock(side_effect=FileNotFoundError("GCS 404"))

        with patch("app.routes.chat_routes._get_storage", return_value=mock_storage):
            result = await _load_page_image("images/doc-abc/page_1.png")

        assert result is None

    @pytest.mark.asyncio
    async def test_calls_storage_load_with_correct_path(self):
        """storage.load()를 정확한 경로로 호출한다."""
        from app.routes.chat_routes import _load_page_image

        mock_storage = AsyncMock()
        mock_storage.load = AsyncMock(return_value=b"PNG")

        with patch("app.routes.chat_routes._get_storage", return_value=mock_storage):
            await _load_page_image("images/doc-xyz/page_3.png")

        mock_storage.load.assert_called_once_with("images/doc-xyz/page_3.png")


# ---------------------------------------------------------------------------
# C-2: _collect_page_images
# ---------------------------------------------------------------------------

class TestCollectPageImages:
    """_collect_page_images(chunks) — 중복 제거 후 이미지 수집."""

    @pytest.mark.asyncio
    async def test_returns_list_of_bytes(self):
        """이미지가 있는 청크들에서 bytes 목록을 반환한다."""
        from app.routes.chat_routes import _collect_page_images

        chunks = [
            {"metadata": {"page_image_path": "images/doc/page_1.png"}},
            {"metadata": {"page_image_path": "images/doc/page_2.png"}},
        ]
        fake_img = b"PNG"

        with patch("app.routes.chat_routes._load_page_image", new=AsyncMock(return_value=fake_img)):
            result = await _collect_page_images(chunks)

        assert len(result) == 2
        assert all(r == fake_img for r in result)

    @pytest.mark.asyncio
    async def test_deduplicates_same_page_image_path(self):
        """같은 page_image_path가 여러 청크에 있으면 한 번만 로드한다."""
        from app.routes.chat_routes import _collect_page_images

        chunks = [
            {"metadata": {"page_image_path": "images/doc/page_1.png"}},
            {"metadata": {"page_image_path": "images/doc/page_1.png"}},  # 중복
            {"metadata": {"page_image_path": "images/doc/page_2.png"}},
        ]

        load_mock = AsyncMock(return_value=b"PNG")
        with patch("app.routes.chat_routes._load_page_image", new=load_mock):
            result = await _collect_page_images(chunks)

        assert len(result) == 2
        assert load_mock.call_count == 2

    @pytest.mark.asyncio
    async def test_skips_chunks_without_page_image_path(self):
        """metadata에 page_image_path가 없는 청크는 건너뛴다."""
        from app.routes.chat_routes import _collect_page_images

        chunks = [
            {"metadata": {"page_image_path": "images/doc/page_1.png"}},
            {"metadata": {}},
            {"source_type": "neo4j"},  # metadata 없음
        ]

        with patch("app.routes.chat_routes._load_page_image", new=AsyncMock(return_value=b"PNG")):
            result = await _collect_page_images(chunks)

        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_skips_failed_image_loads(self):
        """이미지 로드 실패(None 반환) 청크는 결과에서 제외한다."""
        from app.routes.chat_routes import _collect_page_images

        chunks = [
            {"metadata": {"page_image_path": "images/doc/page_1.png"}},
            {"metadata": {"page_image_path": "images/doc/page_2.png"}},
        ]

        async def mock_load(path):
            if "page_1" in path:
                return b"PNG"
            return None  # page_2 로드 실패

        with patch("app.routes.chat_routes._load_page_image", new=mock_load):
            result = await _collect_page_images(chunks)

        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_returns_empty_list_for_empty_chunks(self):
        """청크가 없으면 빈 리스트를 반환한다."""
        from app.routes.chat_routes import _collect_page_images

        result = await _collect_page_images([])
        assert result == []


# ---------------------------------------------------------------------------
# C-3: _generate_answer 멀티모달 확장
# ---------------------------------------------------------------------------

class TestGenerateAnswerMultimodal:
    """_generate_answer()가 page_images를 받아 Gemini 멀티모달로 호출한다."""

    @pytest.mark.asyncio
    async def test_signature_accepts_page_images_param(self):
        """_generate_answer가 page_images 파라미터를 받는다."""
        import inspect
        from app.routes.chat_routes import _generate_answer

        sig = inspect.signature(_generate_answer)
        assert "page_images" in sig.parameters, \
            "_generate_answer must accept page_images parameter"

    @pytest.mark.asyncio
    async def test_page_images_defaults_to_empty_list(self):
        """page_images 기본값은 빈 리스트다 (하위 호환)."""
        import inspect
        from app.routes.chat_routes import _generate_answer

        sig = inspect.signature(_generate_answer)
        default = sig.parameters["page_images"].default
        assert default == [] or default is inspect.Parameter.empty or default == None, \
            "page_images should have a default value"

    @pytest.mark.asyncio
    async def test_mock_llm_returns_string_with_images(self):
        """USE_MOCK_LLM=true이면 page_images가 있어도 문자열 반환."""
        from app.routes.chat_routes import _generate_answer

        with patch("app.routes.chat_routes._USE_MOCK_LLM", True):
            result = await _generate_answer(
                "질문",
                "컨텍스트",
                page_images=[b"PNG1", b"PNG2"],
            )

        assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_gemini_called_with_image_parts_when_images_provided(self):
        """page_images가 있으면 Gemini HumanMessage에 이미지 파트가 포함된다."""
        from app.routes.chat_routes import _generate_answer

        captured_messages = []

        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = "Gemini 멀티모달 답변"
        mock_llm.ainvoke = AsyncMock(return_value=mock_response)

        def capture_llm(*args, **kwargs):
            return mock_llm

        fake_png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 20

        with patch("app.routes.chat_routes._USE_MOCK_LLM", False):
            with patch("app.routes.chat_routes.ChatGoogleGenerativeAI", side_effect=capture_llm):
                result = await _generate_answer(
                    "표에서 합계를 알려줘",
                    "문서 컨텍스트",
                    page_images=[fake_png],
                )

        assert result == "Gemini 멀티모달 답변"
        call_args = mock_llm.ainvoke.call_args[0][0]
        human_message = call_args[-1]
        # HumanMessage content가 list (text + image_url 파트)여야 함
        assert isinstance(human_message.content, list), \
            "HumanMessage content must be a list when images are provided"

    @pytest.mark.asyncio
    async def test_gemini_called_text_only_when_no_images(self):
        """page_images가 없으면 기존 텍스트 전용 호출을 유지한다."""
        from app.routes.chat_routes import _generate_answer

        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = "텍스트 전용 답변"
        mock_llm.ainvoke = AsyncMock(return_value=mock_response)

        with patch("app.routes.chat_routes._USE_MOCK_LLM", False):
            with patch("app.routes.chat_routes.ChatGoogleGenerativeAI", return_value=mock_llm):
                result = await _generate_answer("질문", "컨텍스트", page_images=[])

        assert result == "텍스트 전용 답변"
        call_args = mock_llm.ainvoke.call_args[0][0]
        human_message = call_args[-1]
        # 이미지 없으면 content가 문자열
        assert isinstance(human_message.content, str), \
            "HumanMessage content must be str when no images"


# ---------------------------------------------------------------------------
# C-4: chat 엔드포인트 연결
# ---------------------------------------------------------------------------

class TestChatEndpointMultimodal:
    """chat 엔드포인트가 _collect_page_images → _generate_answer를 연결한다."""

    @pytest.mark.asyncio
    async def test_collect_page_images_called_with_raw_chunks(self):
        """chat 핸들러가 raw_chunks로 _collect_page_images를 호출한다."""
        from app.routes.chat_routes import chat, ChatRequest

        fake_chunks = [
            {
                "chunk_id": "c1",
                "content": "내용",
                "score": 0.9,
                "doc_title": "문서",
                "source_type": "pgvector",
                "metadata": {"page_image_path": "images/doc/page_1.png"},
            }
        ]

        collect_mock = AsyncMock(return_value=[b"PNG"])
        answer_mock = AsyncMock(return_value="멀티모달 답변")

        with patch("app.routes.chat_routes._classify_intent",
                   new=AsyncMock(return_value=MagicMock(intent="semantic", storages=["pgvector"]))):
            with patch("app.routes.chat_routes._query_pgvector",
                       new=AsyncMock(return_value=fake_chunks)):
                with patch("app.routes.chat_routes._collect_page_images", new=collect_mock):
                    with patch("app.routes.chat_routes._generate_answer", new=answer_mock):
                        with patch("app.routes.chat_routes._get_session_factory",
                                   return_value=MagicMock()):
                            req = ChatRequest(question="표를 설명해줘")
                            await chat(req)

        collect_mock.assert_called_once_with(fake_chunks)

    @pytest.mark.asyncio
    async def test_generate_answer_called_with_page_images(self):
        """chat 핸들러가 _generate_answer에 page_images를 전달한다."""
        from app.routes.chat_routes import chat, ChatRequest

        fake_chunks = [{"chunk_id": "c1", "content": "내용", "score": 0.9,
                        "doc_title": "문서", "source_type": "pgvector", "metadata": {}}]
        fake_images = [b"PNG1", b"PNG2"]

        answer_mock = AsyncMock(return_value="답변")

        with patch("app.routes.chat_routes._classify_intent",
                   new=AsyncMock(return_value=MagicMock(intent="semantic", storages=["pgvector"]))):
            with patch("app.routes.chat_routes._query_pgvector",
                       new=AsyncMock(return_value=fake_chunks)):
                with patch("app.routes.chat_routes._collect_page_images",
                           new=AsyncMock(return_value=fake_images)):
                    with patch("app.routes.chat_routes._generate_answer", new=answer_mock):
                        with patch("app.routes.chat_routes._get_session_factory",
                                   return_value=MagicMock()):
                            req = ChatRequest(question="질문")
                            await chat(req)

        call_kwargs = answer_mock.call_args
        passed_images = call_kwargs[1].get("page_images") or (
            call_kwargs[0][2] if len(call_kwargs[0]) > 2 else None
        )
        assert passed_images == fake_images, \
            "_generate_answer must receive page_images from _collect_page_images"
