import pytest
from app.report_service import generate_report


def test_generate_report_returns_list():
    result = generate_report([1, 2])
    assert isinstance(result, list)
    assert len(result) == 2

# summarize, export_csv 테스트 없음 → TEST-001 (커버리지 미달)
