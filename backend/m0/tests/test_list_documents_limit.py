"""
test_list_documents_limit.py — list_documents 엔드포인트 limit 경계값 테스트

검증 항목:
  - limit > 10000 → 422
  - limit <= 0    → 422
  - limit = 10000 → 정상 (422 아님)
  - approved status 필터 → 정상 (ALLOWED_DOC_STATUSES에 포함)
"""

from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

import app.routes.kms_routes as kms_routes


# ---------------------------------------------------------------------------
# 픽스처 — 최소한의 앱 + DB 목
# ---------------------------------------------------------------------------

@pytest.fixture()
def client():
    """kms_routes 라우터만 등록한 테스트 앱."""
    app = FastAPI()
    app.include_router(kms_routes.router)

    # DB 세션 팩토리 목
    mock_session = AsyncMock(spec=AsyncSession)
    mock_result = MagicMock()
    mock_result.mappings.return_value.fetchone.return_value = {"count": 0}
    mock_result.mappings.return_value.fetchall.return_value = []
    mock_session.execute = AsyncMock(return_value=mock_result)
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=None)

    mock_factory = MagicMock(spec=async_sessionmaker)
    mock_factory.return_value = mock_session
    kms_routes._db_session_factory = mock_factory

    # 인증 의존성 우회
    from app.dependencies import get_current_kms_user
    app.dependency_overrides[get_current_kms_user] = lambda: {
        "user_id": "test-user", "role": "lead", "team": "dev"
    }

    with TestClient(app) as c:
        yield c

    kms_routes._db_session_factory = None
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# limit 경계값 테스트
# ---------------------------------------------------------------------------

class TestListDocumentsLimit:
    def test_limit_10001_returns_422(self, client):
        resp = client.get("/kms/docs", params={"limit": 10001})
        assert resp.status_code == 422
        assert "10000" in resp.json()["detail"]

    def test_limit_0_returns_422(self, client):
        resp = client.get("/kms/docs", params={"limit": 0})
        assert resp.status_code == 422

    def test_limit_negative_returns_422(self, client):
        resp = client.get("/kms/docs", params={"limit": -1})
        assert resp.status_code == 422

    def test_limit_10000_returns_200(self, client):
        resp = client.get("/kms/docs", params={"limit": 10000})
        assert resp.status_code == 200

    def test_limit_100_returns_200(self, client):
        resp = client.get("/kms/docs", params={"limit": 100})
        assert resp.status_code == 200

    def test_approved_status_filter_returns_200(self, client):
        resp = client.get("/kms/docs", params={"status": "approved", "limit": 20})
        assert resp.status_code == 200

    def test_unknown_status_returns_422(self, client):
        resp = client.get("/kms/docs", params={"status": "unknown_xyz", "limit": 20})
        assert resp.status_code == 422
