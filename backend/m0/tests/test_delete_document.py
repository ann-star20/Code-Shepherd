"""
TDD: DELETE /kms/docs/{doc_id} — 4개 저장소 동기화 삭제

RED 단계: 엔드포인트 없음. 모든 테스트가 실패해야 한다.

검증 항목:
1. 엔드포인트 존재 및 응답 모델 확인
2. 인증 없으면 401
3. 문서 없으면 404
4. 정상 삭제 시 sync_old_document_version 호출 확인
5. 본인 소유 또는 public 문서만 삭제 가능 (403)
6. sync 실패해도 PG는 삭제 완료 (부분 실패 허용)
"""
from __future__ import annotations

import inspect
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# 1. 엔드포인트 존재
# ---------------------------------------------------------------------------

class TestDeleteEndpointExists:
    def test_delete_doc_route_registered(self):
        """DELETE /kms/docs/{doc_id} 라우트가 등록되어 있어야 한다."""
        from fastapi.routing import APIRoute
        from app.routes.kms_routes import router

        delete_routes = [
            r for r in router.routes
            if isinstance(r, APIRoute)
            and "/docs/{doc_id}" in r.path
            and "DELETE" in r.methods
        ]
        assert len(delete_routes) == 1, (
            "DELETE /kms/docs/{doc_id} route must be registered"
        )

    def test_delete_response_model_has_doc_id(self):
        """delete_document 함수가 doc_id를 포함한 응답을 반환해야 한다."""
        from app.routes.kms_routes import delete_document
        assert callable(delete_document)

    def test_delete_endpoint_has_current_user_param(self):
        """delete_document는 current_user Depends를 가져야 한다 (인증 필수)."""
        from app.routes.kms_routes import delete_document
        sig = inspect.signature(delete_document)
        assert "current_user" in sig.parameters, (
            "delete_document must have current_user (JWT Depends)"
        )


# ---------------------------------------------------------------------------
# 2. 문서 없으면 404
# ---------------------------------------------------------------------------

class TestDeleteNotFound:
    @pytest.mark.asyncio
    async def test_delete_nonexistent_doc_returns_404(self):
        """존재하지 않는 doc_id → 404."""
        from app.routes.kms_routes import delete_document
        from fastapi import HTTPException

        mock_result = MagicMock()
        mock_result.mappings.return_value.fetchone.return_value = None

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_factory = MagicMock(return_value=mock_session)

        current_user = {"user_id": "u-001", "role": "user", "team": "backend"}

        with patch("app.routes.kms_routes._get_session_factory", return_value=mock_factory):
            with pytest.raises(HTTPException) as exc_info:
                await delete_document(
                    doc_id="aaaabbbb-0000-0000-0000-000000000001",
                    current_user=current_user,
                )
        assert exc_info.value.status_code == 404


# ---------------------------------------------------------------------------
# 3. 권한 없는 문서 403
# ---------------------------------------------------------------------------

class TestDeleteForbidden:
    @pytest.mark.asyncio
    async def test_delete_other_users_private_doc_returns_403(self):
        """다른 사용자 소유 + private 문서 → 403."""
        from app.routes.kms_routes import delete_document
        from fastapi import HTTPException

        mock_doc = {
            "title": "남의 문서",
            "upload_status": "stored",
            "permission_level": "private",
            "department_id": "other_team",
            "user_id": "other-user-999",
        }
        mock_result = MagicMock()
        mock_result.mappings.return_value.fetchone.return_value = mock_doc

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_factory = MagicMock(return_value=mock_session)

        current_user = {"user_id": "u-001", "role": "user", "team": "backend"}

        with patch("app.routes.kms_routes._get_session_factory", return_value=mock_factory):
            with pytest.raises(HTTPException) as exc_info:
                await delete_document(
                    doc_id="aaaabbbb-0000-0000-0000-000000000001",
                    current_user=current_user,
                )
        assert exc_info.value.status_code == 403


# ---------------------------------------------------------------------------
# 4. 정상 삭제 — sync_old_document_version 호출 확인
# ---------------------------------------------------------------------------

class TestDeleteSuccess:
    @pytest.mark.asyncio
    async def test_delete_own_doc_calls_graph_sync(self):
        """본인 소유 문서 삭제 시 sync_old_document_version이 호출되어야 한다."""
        from app.routes.kms_routes import delete_document

        mock_doc = {
            "title": "내 문서",
            "upload_status": "stored",
            "permission_level": "private",
            "department_id": "backend",
            "user_id": "u-001",
        }
        mock_result = MagicMock()
        mock_result.mappings.return_value.fetchone.return_value = mock_doc

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_factory = MagicMock(return_value=mock_session)

        current_user = {"user_id": "u-001", "role": "user", "team": "backend"}
        doc_id = "aaaabbbb-0000-0000-0000-000000000001"

        with (
            patch("app.routes.kms_routes._get_session_factory", return_value=mock_factory),
            patch(
                "app.routes.kms_routes.sync_old_document_version",
                new_callable=AsyncMock,
            ) as mock_sync,
        ):
            result = await delete_document(doc_id=doc_id, current_user=current_user)

        mock_sync.assert_called_once()
        call_kwargs = mock_sync.call_args
        assert call_kwargs[1].get("old_doc_id") == doc_id or call_kwargs[0][0] == doc_id

    @pytest.mark.asyncio
    async def test_delete_public_doc_allowed_for_any_user(self):
        """public 문서는 누구든 삭제 가능 (sync 호출 확인)."""
        from app.routes.kms_routes import delete_document

        mock_doc = {
            "title": "공개 문서",
            "upload_status": "stored",
            "permission_level": "public",
            "department_id": None,
            "user_id": "other-user-999",
        }
        mock_result = MagicMock()
        mock_result.mappings.return_value.fetchone.return_value = mock_doc

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_factory = MagicMock(return_value=mock_session)

        current_user = {"user_id": "u-001", "role": "user", "team": "backend"}

        with (
            patch("app.routes.kms_routes._get_session_factory", return_value=mock_factory),
            patch(
                "app.routes.kms_routes.sync_old_document_version",
                new_callable=AsyncMock,
            ) as mock_sync,
        ):
            result = await delete_document(
                doc_id="aaaabbbb-0000-0000-0000-000000000001",
                current_user=current_user,
            )

        mock_sync.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_returns_doc_id_and_status(self):
        """삭제 성공 응답에 doc_id와 status가 포함되어야 한다."""
        from app.routes.kms_routes import delete_document

        mock_doc = {
            "title": "내 문서",
            "upload_status": "stored",
            "permission_level": "private",
            "department_id": "backend",
            "user_id": "u-001",
        }
        mock_result = MagicMock()
        mock_result.mappings.return_value.fetchone.return_value = mock_doc

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_factory = MagicMock(return_value=mock_session)

        current_user = {"user_id": "u-001", "role": "user", "team": "backend"}
        doc_id = "aaaabbbb-0000-0000-0000-000000000001"

        with (
            patch("app.routes.kms_routes._get_session_factory", return_value=mock_factory),
            patch("app.routes.kms_routes.sync_old_document_version", new_callable=AsyncMock),
        ):
            result = await delete_document(doc_id=doc_id, current_user=current_user)

        assert result.doc_id == doc_id
        assert result.status == "deleted"


# ---------------------------------------------------------------------------
# 5. sync 실패해도 응답은 성공 (부분 실패 허용)
# ---------------------------------------------------------------------------

class TestDeleteSyncFailureTolerance:
    @pytest.mark.asyncio
    async def test_neo4j_failure_still_returns_deleted(self):
        """Neo4j / GCS 동기화 실패해도 PG 삭제 후 응답은 deleted."""
        from app.routes.kms_routes import delete_document

        mock_doc = {
            "title": "내 문서",
            "upload_status": "stored",
            "permission_level": "private",
            "department_id": "backend",
            "user_id": "u-001",
        }
        mock_result = MagicMock()
        mock_result.mappings.return_value.fetchone.return_value = mock_doc

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_factory = MagicMock(return_value=mock_session)

        current_user = {"user_id": "u-001", "role": "user", "team": "backend"}

        with (
            patch("app.routes.kms_routes._get_session_factory", return_value=mock_factory),
            patch(
                "app.routes.kms_routes.sync_old_document_version",
                new_callable=AsyncMock,
                side_effect=Exception("Neo4j 연결 실패"),
            ),
        ):
            result = await delete_document(
                doc_id="aaaabbbb-0000-0000-0000-000000000001",
                current_user=current_user,
            )

        assert result.status == "deleted"
        assert result.sync_warning is not None
