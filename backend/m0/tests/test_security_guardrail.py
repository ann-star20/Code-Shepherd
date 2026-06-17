"""
TDD: Security Guardrail — KMS 엔드포인트 인증 + 권한 필터링

RED 단계: 아직 구현 없음. 모든 테스트가 실패해야 한다.

검증 항목:
1. get_current_kms_user() — 유효 토큰 파싱, 401 처리
2. /kms/upload — 인증 없으면 401, 인증 시 current_user로 owner 주입
3. /kms/docs — 인증 없으면 401, permission WHERE 적용
4. /kms/docs/{id}/details — 인증 없으면 401, 접근 불가 문서 403
5. /kms/search — 인증 없으면 401, permission WHERE 적용
6. /ingest — 인증 없어도 정상 동작 (M1 내부 호출 유지)
"""
from __future__ import annotations

import inspect
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# 1. dependencies.py — get_current_kms_user
# ---------------------------------------------------------------------------

class TestGetCurrentKmsUser:
    def test_module_exists(self):
        """dependencies.py 파일이 존재해야 한다."""
        from app import dependencies  # noqa: F401

    def test_function_exists(self):
        """get_current_kms_user 함수가 있어야 한다."""
        from app.dependencies import get_current_kms_user  # noqa: F401

    def test_returns_user_id_role_team(self):
        """유효 토큰 → user_id, role, team을 포함한 dict 반환."""
        from app.dependencies import get_current_kms_user
        from fastapi.security import HTTPAuthorizationCredentials

        fake_payload = {
            "sub": "user-uuid-001",
            "role": "admin",
            "team": "backend",
            "type": "access",
        }
        creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials="faketoken")

        with patch("app.dependencies.decode_token", return_value=fake_payload):
            import asyncio
            result = asyncio.get_event_loop().run_until_complete(
                get_current_kms_user(credentials=creds)
            )

        assert result["user_id"] == "user-uuid-001"
        assert result["role"] == "admin"
        assert result["team"] == "backend"

    def test_no_token_raises_401(self):
        """토큰 없으면 HTTP 401."""
        from app.dependencies import get_current_kms_user
        from fastapi import HTTPException
        import asyncio

        with pytest.raises(HTTPException) as exc_info:
            asyncio.get_event_loop().run_until_complete(
                get_current_kms_user(credentials=None)
            )
        assert exc_info.value.status_code == 401

    def test_invalid_token_raises_401(self):
        """잘못된 토큰 → HTTP 401."""
        from app.dependencies import get_current_kms_user
        from fastapi import HTTPException
        from fastapi.security import HTTPAuthorizationCredentials
        import asyncio

        creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials="bad-token")
        with patch("app.dependencies.decode_token", side_effect=ValueError("Invalid token")):
            with pytest.raises(HTTPException) as exc_info:
                asyncio.get_event_loop().run_until_complete(
                    get_current_kms_user(credentials=creds)
                )
        assert exc_info.value.status_code == 401

    def test_missing_role_team_returns_none(self):
        """role/team이 없는 토큰 → None으로 채워서 반환 (하위 호환)."""
        from app.dependencies import get_current_kms_user
        from fastapi.security import HTTPAuthorizationCredentials
        import asyncio

        fake_payload = {"sub": "user-uuid-002", "type": "access"}
        creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials="faketoken")

        with patch("app.dependencies.decode_token", return_value=fake_payload):
            result = asyncio.get_event_loop().run_until_complete(
                get_current_kms_user(credentials=creds)
            )

        assert result["user_id"] == "user-uuid-002"
        assert result["role"] is None
        assert result["team"] is None


# ---------------------------------------------------------------------------
# 2. /kms/upload — current_user Depends + owner 자동 주입
# ---------------------------------------------------------------------------

class TestUploadEndpointAuth:
    def test_upload_has_current_user_param(self):
        """upload_document 시그니처에 current_user 파라미터가 있어야 한다."""
        from app.routes.kms_routes import upload_document
        sig = inspect.signature(upload_document)
        assert "current_user" in sig.parameters, (
            "upload_document must have current_user parameter (Depends)"
        )

    def test_upload_no_longer_accepts_user_id_from_form(self):
        """클라이언트가 user_id를 Form으로 지정 불가 — 파라미터에서 제거."""
        from app.routes.kms_routes import upload_document
        sig = inspect.signature(upload_document)
        # user_id는 Form 파라미터로 남으면 안 된다
        assert "user_id" not in sig.parameters, (
            "upload_document must NOT accept user_id as Form param (server injects from token)"
        )

    def test_upload_no_longer_accepts_department_id_from_form(self):
        """클라이언트가 department_id를 Form으로 지정 불가 — 파라미터에서 제거."""
        from app.routes.kms_routes import upload_document
        sig = inspect.signature(upload_document)
        assert "department_id" not in sig.parameters, (
            "upload_document must NOT accept department_id as Form param (server injects from token)"
        )


# ---------------------------------------------------------------------------
# 3. /kms/docs — permission WHERE 필터
# ---------------------------------------------------------------------------

class TestListDocumentsPermission:
    def test_list_docs_has_current_user_param(self):
        """list_documents 시그니처에 current_user 파라미터가 있어야 한다."""
        from app.routes.kms_routes import list_documents
        sig = inspect.signature(list_documents)
        assert "current_user" in sig.parameters

    @pytest.mark.asyncio
    async def test_list_docs_sql_includes_permission_filter(self):
        """list_documents SQL에 permission 필터 조건이 포함되어야 한다."""
        from app.routes.kms_routes import list_documents

        # Mock session_factory
        mock_count = MagicMock()
        mock_count.mappings.return_value.fetchone.return_value = {"count": 0}
        mock_list = MagicMock()
        mock_list.mappings.return_value.fetchall.return_value = []

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(side_effect=[mock_count, mock_list])
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        mock_factory = MagicMock(return_value=mock_session)

        current_user = {"user_id": "u-001", "role": "user", "team": "backend"}

        with patch("app.routes.kms_routes._get_session_factory", return_value=mock_factory):
            await list_documents(current_user=current_user)

        # 두 번째 execute 호출(LIST 쿼리)의 SQL에 permission 필터 확인
        calls = mock_session.execute.call_args_list
        list_sql = str(calls[1][0][0]).lower()
        assert "permission_level" in list_sql or "department_id" in list_sql, (
            "list_documents SQL must include permission filter"
        )


# ---------------------------------------------------------------------------
# 4. /kms/docs/{doc_id}/details — 접근 불가 문서 403
# ---------------------------------------------------------------------------

class TestDocDetailsPermission:
    def test_details_has_current_user_param(self):
        """get_doc_details 시그니처에 current_user 파라미터가 있어야 한다."""
        from app.routes.kms_routes import get_doc_details
        sig = inspect.signature(get_doc_details)
        assert "current_user" in sig.parameters

    @pytest.mark.asyncio
    async def test_details_returns_403_for_unauthorized_doc(self):
        """현재 사용자가 접근 불가한 문서(private, 다른 팀 소유) → 403."""
        from app.routes.kms_routes import get_doc_details
        from fastapi import HTTPException

        mock_doc_row = {
            "title": "비공개 문서",
            "file_type": "md",
            "upload_status": "stored",
            "created_at": None,
            "parser_used": None,
            "quality_score": None,
            "doc_complexity": None,
            "parsing_time_ms": None,
            # 다른 팀 소유, private
            "permission_level": "private",
            "department_id": "other_team",
            "user_id": "other-user-999",
        }

        mock_result = MagicMock()
        mock_result.mappings.return_value.fetchone.return_value = mock_doc_row

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_factory = MagicMock(return_value=mock_session)

        current_user = {"user_id": "u-001", "role": "user", "team": "backend"}

        with patch("app.routes.kms_routes._get_session_factory", return_value=mock_factory):
            with pytest.raises(HTTPException) as exc_info:
                await get_doc_details(
                    doc_id="aaaabbbb-0000-0000-0000-000000000001",
                    current_user=current_user,
                )
        assert exc_info.value.status_code == 403


# ---------------------------------------------------------------------------
# 5. /kms/search — permission WHERE 필터
# ---------------------------------------------------------------------------

class TestSearchPermission:
    def test_search_has_current_user_param(self):
        """search_kms 시그니처에 current_user 파라미터가 있어야 한다."""
        from app.routes.kms_routes import search_kms
        sig = inspect.signature(search_kms)
        assert "current_user" in sig.parameters

    @pytest.mark.asyncio
    async def test_search_sql_includes_permission_filter(self):
        """search SQL에 permission 필터가 포함되어야 한다."""
        from app.routes.kms_routes import search_kms

        mock_result = MagicMock()
        mock_result.mappings.return_value.fetchall.return_value = []
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_factory = MagicMock(return_value=mock_session)

        current_user = {"user_id": "u-001", "role": "user", "team": "backend"}

        with (
            patch("app.routes.kms_routes._get_session_factory", return_value=mock_factory),
            patch("app.routes.kms_routes._embed_query", new_callable=AsyncMock, return_value=[0.1] * 5),
        ):
            await search_kms(q="test", current_user=current_user)

        call_sql = str(mock_session.execute.call_args[0][0]).lower()
        assert "permission_level" in call_sql or "department_id" in call_sql, (
            "search SQL must include permission filter"
        )


# ---------------------------------------------------------------------------
# 6. /ingest — 인증 없이 동작 유지 (M1 내부 호출)
# ---------------------------------------------------------------------------

class TestIngestNoAuth:
    def test_ingest_has_no_auth_dependency(self):
        """/ingest 엔드포인트는 get_current_kms_user Depends 없이 동작해야 한다."""
        from app.main import app
        from fastapi.routing import APIRoute

        ingest_route = None
        for route in app.routes:
            if isinstance(route, APIRoute) and route.path == "/ingest":
                ingest_route = route
                break

        assert ingest_route is not None, "/ingest route must exist"

        # dependencies에 get_current_kms_user가 없어야 한다
        dep_callables = [d.dependency for d in ingest_route.dependencies]
        try:
            from app.dependencies import get_current_kms_user
            assert get_current_kms_user not in dep_callables, (
                "/ingest must NOT require get_current_kms_user (M1 internal call)"
            )
        except ImportError:
            pass  # dependencies.py 미생성 시 — /ingest는 안전


# ---------------------------------------------------------------------------
# 7. JWT Claim — issue_tokens에 role/team 포함
# ---------------------------------------------------------------------------

class TestJwtClaimExtension:
    def test_issue_tokens_source_includes_role_and_team(self):
        """api-core/auth_service.py의 issue_tokens()가 role, team을 extra_claims에 포함해야 한다.

        api-core는 패키지 내부 상대 임포트를 사용하므로 소스 코드 검사로 검증한다.
        """
        import pathlib

        service_path = (
            pathlib.Path(__file__).parent.parent.parent
            / "api-core" / "app" / "services" / "auth_service.py"
        )
        source = service_path.read_text(encoding="utf-8")

        assert '"role": user.role' in source or "'role': user.role" in source, (
            "issue_tokens() must include 'role': user.role in extra_claims"
        )
        assert '"team": user.team' in source or "'team': user.team" in source, (
            "issue_tokens() must include 'team': user.team in extra_claims"
        )

    def test_create_access_token_accepts_role_team_claims(self):
        """shared.auth.create_access_token이 role/team 클레임을 토큰에 포함시킨다."""
        import jwt as pyjwt
        from shared.auth import create_access_token

        with patch("shared.auth.get_settings") as mock_settings:
            mock_settings.return_value.jwt_secret = "test-secret"
            mock_settings.return_value.jwt_algorithm = "HS256"
            mock_settings.return_value.jwt_access_token_expire_minutes = 30

            token = create_access_token(
                subject="user-001",
                extra_claims={"role": "admin", "team": "backend"},
            )

        payload = pyjwt.decode(token, "test-secret", algorithms=["HS256"])
        assert payload["role"] == "admin"
        assert payload["team"] == "backend"
