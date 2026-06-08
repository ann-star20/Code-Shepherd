import pytest
from app.pipeline_service import cross_join_records, normalize, filter_outliers


def test_cross_join_basic():
    a = [{"x": 1}, {"x": 2}]
    b = [{"y": "a"}]
    result = cross_join_records(a, b)
    assert len(result) == 2


def test_normalize_normal():
    assert normalize(5.0, 0.0, 10.0) == 0.5


def test_filter_outliers_normal():
    records = [{"val": 1}, {"val": 10}, {"val": 5}]
    result = filter_outliers(records, "val", 6)
    assert len(result) == 2

# normalize: min==max, 음수 범위 케이스 없음 → TEST-003
# filter_outliers: 빈 리스트, threshold=0 케이스 없음 → TEST-003
# export_csv, load_from_json 테스트 없음 → TEST-004
