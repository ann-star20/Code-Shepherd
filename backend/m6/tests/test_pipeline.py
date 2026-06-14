"""tests/test_pipeline.py — Celery 파이프라인 태스크 단위 테스트 (mock 기반)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestPrescanTask:
    @patch("app.worker.tasks.asyncio.run")
    @patch("app.worker.tasks._emit")
    def test_prescan_emits_running_then_done_event(self, mock_emit, mock_run):
        """prescan 시작 시 Input/RUNNING, 성공 시 Input/DONE step_update 이벤트 발행."""
        mock_run.return_value = {
            "skip": False, "doc_id": "doc_abc123", "url": "https://nestjs.com",
            "session_id": "test-session-id",
        }

        from app.worker.tasks import prescan_task
        ctx = prescan_task.run("test-session-id", "https://nestjs.com")

        assert mock_emit.call_count == 2

        running_event = mock_emit.call_args_list[0][0][1]
        assert running_event["type"] == "step_update"
        assert running_event["step"] == "Input"
        assert running_event["status"] == "RUNNING"

        done_event = mock_emit.call_args_list[1][0][1]
        assert done_event["type"] == "step_update"
        assert done_event["step"] == "Input"
        assert done_event["status"] == "DONE"

    @patch("app.worker.tasks.asyncio.run")
    @patch("app.worker.tasks._set_failed_sync")
    @patch("app.worker.tasks._emit")
    def test_prescan_sets_failed_on_exception(self, mock_emit, mock_set_failed, mock_run):
        """prescan 예외 발생 시 _set_failed_sync 호출."""
        mock_run.side_effect = RuntimeError("connection refused")

        from app.worker.tasks import prescan_task
        with pytest.raises(Exception):
            prescan_task.run("test-session-id", "https://example.com")

        mock_set_failed.assert_called_once_with("test-session-id")

    @patch("app.worker.tasks.asyncio.run")
    @patch("app.worker.tasks._emit")
    def test_prescan_emits_skipped_and_finished_on_duplicate(self, mock_emit, mock_run):
        """중복 문서 감지 시 SKIPPED + finished 이벤트를 순서대로 발행."""
        mock_run.return_value = {
            "skip": True, "doc_id": "doc_dup123", "session_id": "test-session-id",
            "skip_reason": "이미 처리된 문서입니다 (doc_id=doc_dup123, state=COMMITTED) - 파이프라인을 건너뜁니다.",
        }

        from app.worker.tasks import prescan_task
        ctx = prescan_task.run("test-session-id", "https://nestjs.com")

        assert ctx["skip"] is True
        assert mock_emit.call_count == 3

        running_event = mock_emit.call_args_list[0][0][1]
        assert running_event["type"] == "step_update"
        assert running_event["step"] == "Input"
        assert running_event["status"] == "RUNNING"

        skipped_event = mock_emit.call_args_list[1][0][1]
        assert skipped_event["type"] == "step_update"
        assert skipped_event["step"] == "Input"
        assert skipped_event["status"] == "SKIPPED"
        assert "doc_dup123" in skipped_event["reason"]

        finished_event = mock_emit.call_args_list[2][0][1]
        assert finished_event["type"] == "finished"

    @patch("app.worker.tasks.asyncio.run")
    @patch("app.worker.tasks._emit")
    def test_prescan_emits_metadata_required_without_finished_when_framework_unmatched(
        self, mock_emit, mock_run
    ):
        """프레임워크 미인식 시 metadata_required 이벤트만 발행하고 finished는 보내지 않음."""
        mock_run.return_value = {
            "skip": False, "awaiting_metadata": True,
            "doc_id": "doc_new123", "url": "https://docs.astro.build/",
            "session_id": "test-session-id",
            "suggestions": ["Astro", "NestJS"],
            "source_prefix": "external", "framework": None, "lang": None, "version": None,
        }

        from app.worker.tasks import prescan_task
        ctx = prescan_task.run("test-session-id", "https://docs.astro.build/")

        assert ctx["awaiting_metadata"] is True
        assert mock_emit.call_count == 2

        running_event = mock_emit.call_args_list[0][0][1]
        assert running_event["type"] == "step_update"
        assert running_event["step"] == "Input"
        assert running_event["status"] == "RUNNING"

        event = mock_emit.call_args_list[1][0][1]
        assert event["type"] == "metadata_required"
        assert event["doc_id"] == "doc_new123"
        assert event["url"] == "https://docs.astro.build/"
        assert event["suggestions"] == ["Astro", "NestJS"]


class TestCrawlTask:
    @patch("app.worker.tasks.asyncio.run")
    @patch("app.worker.tasks._emit")
    def test_crawl_skips_when_flag_set(self, mock_emit, mock_run):
        """skip=True 컨텍스트는 crawl을 건너뜀."""
        from app.worker.tasks import crawl_task
        ctx = {"skip": True, "doc_id": "doc_abc", "session_id": "sid"}
        result = crawl_task.run(ctx)
        mock_run.assert_not_called()
        assert result == ctx

    @patch("app.worker.tasks.asyncio.run")
    @patch("app.worker.tasks._emit")
    def test_crawl_skips_when_awaiting_metadata(self, mock_emit, mock_run):
        """awaiting_metadata=True 컨텍스트는 crawl을 건너뜀 (HITL 대기)."""
        from app.worker.tasks import crawl_task
        ctx = {"skip": False, "awaiting_metadata": True, "doc_id": "doc_abc", "session_id": "sid"}
        result = crawl_task.run(ctx)
        mock_run.assert_not_called()
        mock_emit.assert_not_called()
        assert result == ctx

    @patch("app.worker.tasks.asyncio.run")
    @patch("app.worker.tasks._emit")
    def test_crawl_emits_running_then_done_event(self, mock_emit, mock_run):
        """crawl 시작 시 Crawler/RUNNING, 성공 시 Crawler/DONE step_update 이벤트."""
        ctx = {"skip": False, "doc_id": "doc_abc", "url": "https://x.com", "session_id": "sid"}
        mock_run.return_value = {**ctx, "chunks": ["chunk1"]}

        from app.worker.tasks import crawl_task
        crawl_task.run(ctx)

        assert mock_emit.call_count == 2

        running_event = mock_emit.call_args_list[0][0][1]
        assert running_event["type"] == "step_update"
        assert running_event["step"] == "Crawler"
        assert running_event["status"] == "RUNNING"

        done_event = mock_emit.call_args_list[1][0][1]
        assert done_event["type"] == "step_update"
        assert done_event["step"] == "Crawler"
        assert done_event["status"] == "DONE"


class TestExtractTextNoiseStripping:
    @pytest.mark.asyncio
    async def test_strips_banner_menu_and_version_noise_outside_main(self):
        """nav/header 밖의 배너·메뉴·버전 안내(예: nextjs.org)도 본문(main) 추출 시 제거됨."""
        from app.worker.tasks import _extract_text

        html = """
        <html>
          <body>
            <header>
              <div class="announcement-banner">
                NEXT.JS NIGHTS SF JUN 9 - AMS JUN 11 - LDN JUN 18
                <a href="/events">VIEW EVENTS</a>
              </div>
              <button class="menu-toggle">Menu</button>
              <div class="version-selector">Latest Version 16.2.9</div>
            </header>
            <main>
              <h1>Getting Started: Proxy</h1>
              <p>Next.js proxy lets you intercept requests before they reach your app.</p>
            </main>
            <footer>copyright notice</footer>
          </body>
        </html>
        """
        mock_resp = MagicMock()
        mock_resp.text = html
        mock_resp.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("app.worker.tasks.httpx.AsyncClient", return_value=mock_client):
            text = await _extract_text("https://nextjs.org/docs/app/getting-started/proxy")

        assert "Menu" not in text
        assert "VIEW EVENTS" not in text
        assert "Latest Version" not in text
        assert "NEXT.JS NIGHTS" not in text
        assert "# Getting Started: Proxy" in text
        assert "Next.js proxy lets you intercept requests" in text


class TestExtractTask:
    @patch("app.worker.tasks.asyncio.run")
    @patch("app.worker.tasks._emit")
    def test_extract_skips_when_flag_set(self, mock_emit, mock_run):
        """skip=True 컨텍스트는 extract를 건너뜀."""
        from app.worker.tasks import extract_task
        ctx = {"skip": True, "session_id": "sid"}
        result = extract_task.run(ctx)
        mock_run.assert_not_called()

    @patch("app.worker.tasks.asyncio.run")
    @patch("app.worker.tasks._emit")
    def test_extract_skips_when_awaiting_metadata(self, mock_emit, mock_run):
        """awaiting_metadata=True 컨텍스트는 extract를 건너뜀 (HITL 대기)."""
        from app.worker.tasks import extract_task
        ctx = {"skip": False, "awaiting_metadata": True, "doc_id": "doc_abc", "session_id": "sid"}
        result = extract_task.run(ctx)
        mock_run.assert_not_called()
        mock_emit.assert_not_called()
        assert result == ctx

    @patch("app.worker.tasks.asyncio.run")
    @patch("app.worker.tasks._emit")
    def test_extract_emits_running_done_and_finished(self, mock_emit, mock_run):
        """extract 시작 시 Extractor/RUNNING, 성공 시 Extractor/DONE + finished 이벤트 순서대로."""
        ctx = {
            "skip": False, "doc_id": "doc_abc",
            "chunks": ["text"], "session_id": "sid",
            "source_prefix": "external",
        }
        mock_run.return_value = {**ctx, "staged": 1}

        from app.worker.tasks import extract_task
        extract_task.run(ctx)

        calls = [c[0][1] for c in mock_emit.call_args_list]
        assert calls[0]["type"] == "step_update"
        assert calls[0]["step"] == "Extractor"
        assert calls[0]["status"] == "RUNNING"

        assert calls[1]["type"] == "step_update"
        assert calls[1]["step"] == "Extractor"
        assert calls[1]["status"] == "DONE"

        assert calls[2]["type"] == "finished"

    @patch("app.worker.tasks.asyncio.run")
    @patch("app.worker.tasks._emit")
    def test_extract_emits_failed_with_reason_when_no_concepts_found(self, mock_emit, mock_run):
        """문서 전체가 노이즈로 판정되어 적재 가능한 개념이 없으면 Extractor/FAILED + 안내
        문구(reason)를 emit하고, 재시도 없이 finished를 emit한다 (crawling-chunking-guide §2)."""
        ctx = {
            "skip": False, "doc_id": "doc_abc",
            "chunks": ["text"], "session_id": "sid",
            "source_prefix": "external",
        }
        mock_run.return_value = {**ctx, "staged": 0, "no_concepts_found": True}

        from app.worker.tasks import extract_task, _NO_CONCEPTS_FOUND_MESSAGE
        extract_task.run(ctx)

        calls = [c[0][1] for c in mock_emit.call_args_list]
        assert calls[0]["type"] == "step_update"
        assert calls[0]["step"] == "Extractor"
        assert calls[0]["status"] == "RUNNING"

        assert calls[1]["type"] == "step_update"
        assert calls[1]["step"] == "Extractor"
        assert calls[1]["status"] == "FAILED"
        assert calls[1]["reason"] == _NO_CONCEPTS_FOUND_MESSAGE

        assert calls[2]["type"] == "finished"


class TestFetchMeta:
    @pytest.mark.asyncio
    async def test_returns_default_lang_when_head_request_fails(self):
        """HEAD 요청 실패 시에도 content_lang이 'ko' 기본값을 유지하고 예외 없이 반환됨."""
        from app.worker.tasks import _fetch_meta

        mock_get_resp = MagicMock()
        mock_get_resp.content = b"<html></html>"

        mock_client = AsyncMock()
        mock_client.head = AsyncMock(side_effect=RuntimeError("HEAD failed"))
        mock_client.get = AsyncMock(return_value=mock_get_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("app.worker.tasks.httpx.AsyncClient", return_value=mock_client):
            etag, content_hash, content_lang = await _fetch_meta("https://example.com")

        assert etag is None
        assert content_lang == "ko"
        assert len(content_hash) == 8

    @pytest.mark.asyncio
    async def test_detects_english_lang_from_content_language_header(self):
        """HEAD 응답의 Content-Language가 en이면 content_lang='en'으로 설정됨."""
        from app.worker.tasks import _fetch_meta

        mock_head_resp = MagicMock()
        mock_head_resp.headers = {"etag": '"abc123"', "Content-Language": "en-US"}
        mock_get_resp = MagicMock()
        mock_get_resp.content = b"<html></html>"

        mock_client = AsyncMock()
        mock_client.head = AsyncMock(return_value=mock_head_resp)
        mock_client.get = AsyncMock(return_value=mock_get_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("app.worker.tasks.httpx.AsyncClient", return_value=mock_client):
            etag, _, content_lang = await _fetch_meta("https://example.com")

        assert etag == "abc123"
        assert content_lang == "en"

    @pytest.mark.asyncio
    async def test_falls_back_to_get_response_etag_when_head_omits_it(self):
        """HEAD 응답에 etag가 없으면 GET 응답 헤더의 etag로 보강한다 (knowledge_documents.etag 누락 방지)."""
        from app.worker.tasks import _fetch_meta

        mock_head_resp = MagicMock()
        mock_head_resp.headers = {}
        mock_get_resp = MagicMock()
        mock_get_resp.headers = {"etag": 'W/"get-etag-456"'}
        mock_get_resp.content = b"<html></html>"

        mock_client = AsyncMock()
        mock_client.head = AsyncMock(return_value=mock_head_resp)
        mock_client.get = AsyncMock(return_value=mock_get_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("app.worker.tasks.httpx.AsyncClient", return_value=mock_client):
            etag, _, _ = await _fetch_meta("https://example.com")

        assert etag == "get-etag-456"

    @pytest.mark.asyncio
    async def test_head_etag_takes_precedence_over_get_etag(self):
        """HEAD 응답에 etag가 있으면 GET 응답의 etag로 덮어쓰지 않는다."""
        from app.worker.tasks import _fetch_meta

        mock_head_resp = MagicMock()
        mock_head_resp.headers = {"etag": '"head-etag-123"'}
        mock_get_resp = MagicMock()
        mock_get_resp.headers = {"etag": '"get-etag-456"'}
        mock_get_resp.content = b"<html></html>"

        mock_client = AsyncMock()
        mock_client.head = AsyncMock(return_value=mock_head_resp)
        mock_client.get = AsyncMock(return_value=mock_get_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("app.worker.tasks.httpx.AsyncClient", return_value=mock_client):
            etag, _, _ = await _fetch_meta("https://example.com")

        assert etag == "head-etag-123"


class TestNormalizeEtag:
    def test_strips_weak_prefix_and_quotes(self):
        from app.worker.tasks import _normalize_etag
        assert _normalize_etag('W/"abc123"') == "abc123"

    def test_strips_quotes_only(self):
        from app.worker.tasks import _normalize_etag
        assert _normalize_etag('"abc123"') == "abc123"

    def test_returns_none_for_missing_header(self):
        from app.worker.tasks import _normalize_etag
        assert _normalize_etag(None) is None
        assert _normalize_etag("") is None


class TestChunkText:
    def test_short_text_single_chunk(self):
        from app.worker.tasks import _chunk_text
        chunks = _chunk_text("hello world", max_len=4000)
        assert len(chunks) == 1
        assert chunks[0] == "hello world"

    def test_long_text_multiple_chunks(self):
        from app.worker.tasks import _chunk_text
        text = "\n\n".join(["paragraph"] * 100)
        chunks = _chunk_text(text, max_len=50)
        assert len(chunks) > 1

    def test_empty_text_returns_single_empty(self):
        from app.worker.tasks import _chunk_text
        chunks = _chunk_text("", max_len=4000)
        assert chunks == [""]

    def test_snaps_to_markdown_header_within_window(self):
        """30000~40000자 윈도우 내에서 가장 가까운 마크다운 헤더 직전에서 청크를 마감한다."""
        from app.worker.tasks import _chunk_text
        text = "A" * 25 + "\n\n## Section\n" + "B" * 25
        chunks = _chunk_text(text, min_len=20, max_len=45, overlap=0)
        assert chunks[0] == "A" * 25
        assert chunks[1].startswith("## Section")

    def test_falls_back_to_paragraph_break_without_header(self):
        """헤더가 없으면 빈 줄(문단 경계)에서 청크를 마감한다."""
        from app.worker.tasks import _chunk_text
        text = "A" * 25 + "\n\n" + "B" * 25
        chunks = _chunk_text(text, min_len=20, max_len=45, overlap=0)
        assert chunks[0] == "A" * 25
        assert chunks[1] == "B" * 25

    def test_overlap_duplicates_trailing_context_into_next_chunk(self):
        """청크 경계의 마지막 overlap자를 다음 청크 상단에 중복 적재한다."""
        from app.worker.tasks import _chunk_text
        text = "A" * 25 + "\n\n" + "B" * 25
        chunks = _chunk_text(text, min_len=20, max_len=45, overlap=5)
        assert chunks[0].endswith("AAAAA")
        assert chunks[1].startswith("AAAAA")


class TestMockExtract:
    def test_returns_list_with_one_concept(self):
        from app.worker.tasks import _mock_extract
        result = _mock_extract("some text about security", {"framework": "Django", "source_prefix": "django"})
        assert len(result) == 1
        assert result[0]["concept_name"].startswith("DjangoConcept")
        assert "Django" in result[0]["domains"] or "django" in result[0]["domains"]

    def test_concept_name_matches_pascal_case_pattern(self):
        """crawling-chunking-guide-v3.md §2 — concept_name은 concept_ 접두사/해시 접미사/
        프레임워크 원형(예: 'Next.js') 없이 ^[A-Z][a-zA-Z0-9]+$ PascalCase여야 한다."""
        import re

        from app.domain.models import ConceptExtractionSchema
        from app.worker.tasks import _mock_extract

        result = _mock_extract("chunk", {"framework": "Next.js", "source_prefix": "nextjs"})

        assert re.match(r"^[A-Z][a-zA-Z0-9]+$", result[0]["concept_name"])
        # ConceptExtractionSchema 검증을 통과해야 한다 (디스크 적재 차단 방지)
        ConceptExtractionSchema(**result[0])

    def test_concept_name_deterministic(self):
        from app.worker.tasks import _mock_extract
        chunk = "same chunk"
        ctx = {"framework": "NestJS", "source_prefix": "nestjs"}
        r1 = _mock_extract(chunk, ctx)
        r2 = _mock_extract(chunk, ctx)
        assert r1[0]["concept_name"] == r2[0]["concept_name"]

    def test_domains_classified_from_allowed_domains_metadata(self):
        """Layer 0 - allowed_domains가 주입되면 domains를 그 중에서 선택한다."""
        from app.worker.tasks import _mock_extract
        result = _mock_extract(
            "chunk", {"framework": "Django", "source_prefix": "django"},
            metadata={"allowed_domains": ["performance", "security"]},
        )
        assert result[0]["domains"] == ["performance"]


class TestEnsureDomains:
    def test_filters_domains_to_allowed_list(self):
        """허용 도메인 목록 밖의 값은 제거한다."""
        from app.worker.tasks import _ensure_domains
        concept = {"domains": ["django", "security"]}
        _ensure_domains(concept, {"source_prefix": "django"}, ["security", "performance"])
        assert concept["domains"] == ["security"]

    def test_falls_back_to_first_allowed_domain_when_empty(self):
        """domains가 비어있으면 [Checkpoint] 허용 도메인의 첫 항목으로 보정한다."""
        from app.worker.tasks import _ensure_domains
        concept = {"domains": []}
        _ensure_domains(concept, {"source_prefix": "django"}, ["security", "performance"])
        assert concept["domains"] == ["security"]

    def test_keeps_source_prefix_when_no_allowed_domains_registered(self):
        """허용 도메인 레지스트리가 비어있으면 source_prefix로 폴백한다."""
        from app.worker.tasks import _ensure_domains
        concept = {"domains": []}
        _ensure_domains(concept, {"source_prefix": "django"}, [])
        assert concept["domains"] == ["django"]


class TestValidateConcepts:
    """_validate_concepts — Pydantic 강제 파싱 + 논리 무결성 검증 (crawling-chunking-guide-v2.md §1, §2)."""

    def test_normalizes_valid_concepts_via_model_dump(self):
        """유효한 개념은 ConceptExtractionSchema.model_dump() 결과로 정규화되어 반환된다."""
        from app.worker.tasks import _validate_concepts

        concepts = [{
            "concept_name": "CsrfProtection",
            "concept_type": "mechanism",
            "domains": ["security"],
            "description_ko": "CSRF 공격을 방지하기 위한 토큰 기반 검증 메커니즘입니다.",
        }]

        result = _validate_concepts(concepts, "sid", "doc_abc")

        assert result[0]["concept_name"] == "CsrfProtection"
        assert result[0]["description_ko"] == "CSRF 공격을 방지하기 위한 토큰 기반 검증 메커니즘입니다."
        assert result[0]["mechanism"] == []

    def test_skips_concept_with_description_noise_without_raising(self):
        """description_ko에 웹사이트 메뉴 노이즈가 섞이면 해당 개념만 건너뛰고
        ValidationError를 전파하지 않는다 (비관련 페이지에서 파이프라인이 멈추지 않도록)."""
        from app.worker.tasks import _validate_concepts

        concepts = [{
            "concept_name": "CsrfProtection",
            "concept_type": "mechanism",
            "domains": ["security"],
            "description_ko": "Menu View Events Latest Version 안내",
        }]

        result = _validate_concepts(concepts, "sid", "doc_abc")

        assert result == []

    def test_raises_validation_error_on_concept_without_mechanism(self):
        """concept_type='concept'인데 mechanism이 비어있으면 ValidationError를 전파한다."""
        from app.worker.tasks import _validate_concepts
        from pydantic import ValidationError

        concepts = [{
            "concept_name": "CsrfProtection",
            "concept_type": "concept",
            "domains": ["security"],
            "description_ko": "CSRF 보호 개념",
            "mechanism": [],
        }]

        with pytest.raises(ValidationError, match="mechanism"):
            _validate_concepts(concepts, "sid", "doc_abc")

    def test_logs_debug_for_each_validated_concept(self):
        """검증을 통과한 각 개념에 대해 디버그 로그를 남긴다 (백엔드 결과 확인용)."""
        from app.worker.tasks import _validate_concepts

        concepts = [{
            "concept_name": "CsrfProtection",
            "concept_type": "mechanism",
            "domains": ["security"],
            "description_ko": "CSRF 공격을 방지하기 위한 토큰 기반 검증 메커니즘입니다.",
        }]

        with patch("app.worker.tasks.logger") as mock_logger:
            _validate_concepts(concepts, "sid", "doc_abc")

        assert mock_logger.debug.called


class TestListAllowedDomains:
    @pytest.mark.asyncio
    async def test_returns_active_domain_names(self):
        from app.worker.tasks import _list_allowed_domains
        mock_conn = AsyncMock()
        mock_conn.fetch = AsyncMock(return_value=[{"name": "security"}, {"name": "performance"}])
        result = await _list_allowed_domains(mock_conn)
        assert result == ["security", "performance"]


class TestGeminiExtract:
    @pytest.mark.asyncio
    async def test_prompt_includes_4layer_ontology_context(self):
        """4-Layer 온톨로지 프롬프트에 framework/language/allowed_domains 컨텍스트가 주입된다."""
        from app.worker.tasks import _gemini_extract

        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {"candidates": [{"content": {"parts": [{"text": "[]"}]}}]}

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        ctx = {"framework": "Django", "lang": "python"}
        metadata = {"framework": "Django", "language": "python", "allowed_domains": ["security", "performance"]}

        with patch("app.worker.tasks.httpx.AsyncClient", return_value=mock_client):
            result = await _gemini_extract("some chunk text", ctx, metadata)

        assert result == []
        sent_prompt = mock_client.post.call_args.kwargs["json"]["contents"][0]["parts"][0]["text"]
        assert "security" in sent_prompt
        assert "performance" in sent_prompt
        assert "Django" in sent_prompt

    @pytest.mark.asyncio
    async def test_prompt_includes_pydantic_format_instructions(self):
        """ConceptExtractionSchema 스키마 기반 포맷 지시문을 프롬프트에 주입해 구조적 뇌절을 차단한다."""
        from app.worker.tasks import _gemini_extract

        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {"candidates": [{"content": {"parts": [{"text": "[]"}]}}]}

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        ctx = {"framework": "Django", "lang": "python"}
        metadata = {"framework": "Django", "language": "python", "allowed_domains": ["security"]}

        with patch("app.worker.tasks.httpx.AsyncClient", return_value=mock_client):
            await _gemini_extract("some chunk text", ctx, metadata)

        sent_prompt = mock_client.post.call_args.kwargs["json"]["contents"][0]["parts"][0]["text"]
        assert "concept_type" in sent_prompt
        assert "description_ko" in sent_prompt

    @pytest.mark.asyncio
    async def test_prompt_includes_few_shot_and_negative_instructions(self):
        """crawling-chunking-guide-v3.md §3 — Few-Shot 예시 + 명명 규칙 부정 지시어가 주입된다."""
        from app.worker.tasks import _gemini_extract

        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {"candidates": [{"content": {"parts": [{"text": "[]"}]}}]}

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        ctx = {"framework": "Django", "lang": "python"}
        metadata = {"framework": "Django", "language": "python", "allowed_domains": ["security"]}

        with patch("app.worker.tasks.httpx.AsyncClient", return_value=mock_client):
            await _gemini_extract("some chunk text", ctx, metadata)

        sent_prompt = mock_client.post.call_args.kwargs["json"]["contents"][0]["parts"][0]["text"]
        assert "concept_Next.js_b6ce44" in sent_prompt  # 잘못된 명명 규칙 부정 예시
        assert "MemoryLeak" in sent_prompt  # Few-Shot 모범 출력 예시
        assert "PascalCase" in sent_prompt
        assert "Was this helpful?" in sent_prompt

    @pytest.mark.asyncio
    async def test_logs_raw_gemini_response_at_debug_level(self):
        """Gemini 원본 응답을 디버그 로그로 남겨 백엔드에서 결과를 확인할 수 있게 한다."""
        from app.worker.tasks import _gemini_extract

        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {"candidates": [{"content": {"parts": [{"text": "[]"}]}}]}

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        ctx = {"framework": "Django", "lang": "python"}
        metadata = {"framework": "Django", "language": "python", "allowed_domains": ["security"]}

        with patch("app.worker.tasks.httpx.AsyncClient", return_value=mock_client), \
             patch("app.worker.tasks.logger") as mock_logger:
            await _gemini_extract("some chunk text", ctx, metadata)

        assert mock_logger.debug.called


class TestExtractAsync:
    @pytest.mark.asyncio
    async def test_mock_mode_processes_only_first_chunk(self):
        """USE_REAL_LLM=False(MOCK)이면 두 번째 청크부터는 건너뛰어 중복 적재를 방지한다."""
        from app.worker.tasks import _extract_async

        mock_conn = AsyncMock()
        mock_conn.fetch = AsyncMock(return_value=[{"name": "security"}, {"name": "performance"}])
        mock_conn.execute = AsyncMock()
        mock_conn.close = AsyncMock()

        mock_resolve_result = MagicMock(
            action=MagicMock(value="NEW"), score=0.0, target_concept_name=None,
            score_jaro_winkler=0.0, score_name_vector=0.0, score_desc_vector=0.0,
        )
        mock_resolver = AsyncMock()
        mock_resolver.resolve = AsyncMock(return_value=mock_resolve_result)

        ctx = {
            "session_id": "11111111-1111-1111-1111-111111111111", "doc_id": "doc_abc",
            "chunks": ["chunk one", "chunk two", "chunk three"],
            "framework": "Django", "source_prefix": "django",
        }

        with patch("app.worker.tasks.asyncpg.connect", AsyncMock(return_value=mock_conn)), \
             patch("app.worker.tasks._update_doc_state", AsyncMock()), \
             patch("app.worker.tasks._update_doc_state_conn", AsyncMock()), \
             patch("app.worker.tasks.USE_REAL_LLM", False), \
             patch("app.infrastructure.graph.hybrid_resolver.HybridResolver", return_value=mock_resolver), \
             patch("app.infrastructure.graph.hybrid_resolver._embed_async", AsyncMock(return_value=[0.1])):
            result = await _extract_async(ctx)

        assert result["staged"] == 1

    @pytest.mark.asyncio
    async def test_emits_resolver_running_and_done_around_resolve_loop(self):
        """개념 해석(HybridResolver) 단계 전후로 Resolver/RUNNING, Resolver/DONE step_update를 발행한다."""
        from app.worker.tasks import _extract_async

        mock_conn = AsyncMock()
        mock_conn.fetch = AsyncMock(return_value=[{"name": "security"}, {"name": "performance"}])
        mock_conn.execute = AsyncMock()
        mock_conn.close = AsyncMock()

        mock_resolve_result = MagicMock(
            action=MagicMock(value="NEW"), score=0.0, target_concept_name=None,
            score_jaro_winkler=0.0, score_name_vector=0.0, score_desc_vector=0.0,
        )
        mock_resolver = AsyncMock()
        mock_resolver.resolve = AsyncMock(return_value=mock_resolve_result)

        ctx = {
            "session_id": "11111111-1111-1111-1111-111111111111", "doc_id": "doc_abc",
            "chunks": ["chunk one"],
            "framework": "Django", "source_prefix": "django",
        }

        with patch("app.worker.tasks.asyncpg.connect", AsyncMock(return_value=mock_conn)), \
             patch("app.worker.tasks._update_doc_state", AsyncMock()), \
             patch("app.worker.tasks._update_doc_state_conn", AsyncMock()), \
             patch("app.worker.tasks.USE_REAL_LLM", False), \
             patch("app.infrastructure.graph.hybrid_resolver.HybridResolver", return_value=mock_resolver), \
             patch("app.infrastructure.graph.hybrid_resolver._embed_async", AsyncMock(return_value=[0.1])), \
             patch("app.worker.tasks._emit") as mock_emit:
            await _extract_async(ctx)

        events = [c[0][1] for c in mock_emit.call_args_list]
        resolver_events = [e for e in events if e.get("step") == "Resolver"]
        assert resolver_events[0]["status"] == "RUNNING"
        assert resolver_events[-1]["status"] == "DONE"

    @pytest.mark.asyncio
    async def test_production_mode_sleeps_between_chunks_to_respect_rate_limit(self):
        """USE_REAL_LLM=True(PRODUCTION)이면 두 번째 청크부터 Gemini 20RPM 방지용 4초 대기를 건다."""
        from app.worker.tasks import _extract_async

        mock_conn = AsyncMock()
        mock_conn.fetch = AsyncMock(return_value=[])
        mock_conn.execute = AsyncMock()
        mock_conn.close = AsyncMock()

        mock_resolve_result = MagicMock(
            action=MagicMock(value="NEW"), score=0.0, target_concept_name=None,
            score_jaro_winkler=0.0, score_name_vector=0.0, score_desc_vector=0.0,
        )
        mock_resolver = AsyncMock()
        mock_resolver.resolve = AsyncMock(return_value=mock_resolve_result)

        ctx = {
            "session_id": "sid", "doc_id": "doc_abc",
            "chunks": ["chunk one", "chunk two"],
            "framework": "Django", "source_prefix": "django",
        }

        with patch("app.worker.tasks.asyncpg.connect", AsyncMock(return_value=mock_conn)), \
             patch("app.worker.tasks._update_doc_state", AsyncMock()), \
             patch("app.worker.tasks._update_doc_state_conn", AsyncMock()), \
             patch("app.worker.tasks.USE_REAL_LLM", True), \
             patch("app.worker.tasks.GEMINI_API_KEY", "fake-key"), \
             patch("app.worker.tasks._gemini_extract", AsyncMock(return_value=[])), \
             patch("app.infrastructure.graph.hybrid_resolver.HybridResolver", return_value=mock_resolver), \
             patch("app.infrastructure.graph.hybrid_resolver._embed_async", AsyncMock(return_value=[0.1])), \
             patch("app.worker.tasks.asyncio.sleep", AsyncMock()) as mock_sleep:
            await _extract_async(ctx)

        mock_sleep.assert_awaited_once_with(4)

    @pytest.mark.asyncio
    async def test_returns_no_concepts_found_when_all_concepts_filtered_as_noise(self):
        """추출된 개념이 모두 description_ko 노이즈로 필터링되면 staged=0,
        no_concepts_found=True를 반환하고 문서 상태를 EXTRACTED로 갱신한다
        (취약점/안티패턴과 무관한 페이지 - 파이프라인은 멈추지 않음)."""
        from app.worker.tasks import _extract_async

        mock_conn = AsyncMock()
        mock_conn.fetch = AsyncMock(return_value=[{"name": "security"}, {"name": "performance"}])
        mock_conn.execute = AsyncMock()
        mock_conn.close = AsyncMock()

        noisy_concept = {
            "concept_name": "CsrfProtection",
            "concept_type": "mechanism",
            "domains": ["security"],
            "description_ko": "Menu View Events Latest Version 안내",
        }

        ctx = {
            "session_id": "11111111-1111-1111-1111-111111111111", "doc_id": "doc_abc",
            "chunks": ["chunk one"],
            "framework": "Django", "source_prefix": "django",
        }

        with patch("app.worker.tasks.asyncpg.connect", AsyncMock(return_value=mock_conn)), \
             patch("app.worker.tasks._update_doc_state", AsyncMock()), \
             patch("app.worker.tasks._update_doc_state_conn", AsyncMock()) as mock_update_conn, \
             patch("app.worker.tasks.USE_REAL_LLM", False), \
             patch("app.worker.tasks._mock_extract", return_value=[noisy_concept]):
            result = await _extract_async(ctx)

        assert result["staged"] == 0
        assert result["no_concepts_found"] is True
        mock_update_conn.assert_awaited_once_with(mock_conn, "doc_abc", "EXTRACTED")


class TestWriteGraphTask:
    @patch("app.worker.tasks.asyncio.run")
    @patch("app.worker.tasks._emit")
    def test_write_graph_emits_finished(self, mock_emit, mock_run):
        """write_graph 성공 시 GraphWriter + finished 이벤트."""
        mock_run.return_value = {
            "session_id": "test-sid",
            "summary": {"MERGE": 1, "RELATED_TO": 0, "NEW": 0},
        }

        from app.worker.tasks import write_graph_task
        write_graph_task.run("test-sid")

        events = [c[0][1]["type"] for c in mock_emit.call_args_list]
        assert "step_update" in events
        assert "finished" in events
