from app.invoice_service import load_invoice_totals
from app.db import FakeDB


def test_load_invoice_totals():
    result = load_invoice_totals([1, 2, 3], FakeDB())
    assert result == [100, 250, 50]
