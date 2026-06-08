from app.product_service import get_product_names
from app.fake_session import FakeSession


def test_get_product_names():
    result = get_product_names([1, 2, 3], FakeSession())
    assert result == ["Keyboard", "Mouse", "Monitor"]
