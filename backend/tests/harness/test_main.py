"""G1 테스트 — FastAPI main.py lifespan pool + /health 엔드포인트.

T_main_health:      GET /health → 200, {"status": "ok"}
T_main_pool_wired:  lifespan 이후 app.state.pool is not None
"""

from fastapi.testclient import TestClient


def test_T_main_health():
    """Arrange: TestClient(app).
    Act: GET /health.
    Assert: 200, {"status": "ok"}.
    """
    from app.main import app

    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_T_main_pool_wired():
    """Arrange: TestClient + lifespan.
    Act: lifespan startup 완료.
    Assert: app.state.pool is not None.
    """
    from app.main import app

    with TestClient(app) as client:
        _ = client.get("/health")

    assert app.state.pool is not None
