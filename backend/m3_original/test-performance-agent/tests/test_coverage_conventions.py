"""R4 — coverage.py × 사내 기준(conventions) 연동 TDD 테스트.

설계 의도(RAG 설계서 §5ⓐ): 바뀐 파일의 모듈을 판별해 사내 커버리지 기준 적용.
- payment/auth 등 기본(80%)보다 엄격한 모듈만 파일별 추가 판정 (중복 방지)
- changed 미제공 시 기존 전체-집계 동작 그대로 (하위호환)
"""
import json


def _write_cov(tmp_path, files: dict, totals_pct: float):
    cov = {
        "meta": {"format": 3, "branch_coverage": False},
        "files": files,
        "totals": {
            "covered_lines": int(totals_pct),
            "num_statements": 100,
            "percent_covered": totals_pct,
        },
    }
    (tmp_path / "coverage.json").write_text(json.dumps(cov), encoding="utf-8")


def _payment_file(pct: float):
    return {"executed_lines": [],
            "summary": {"num_statements": 20, "percent_covered": pct}}


def test_payment_file_below_90_flagged(tmp_path):
    """payment 파일 85% (< 사내 90%) → 파일별 TEST-001 1건 (전체는 90%라 무이슈)."""
    _write_cov(tmp_path, {"src/payment/billing.py": _payment_file(85.0)}, totals_pct=90.0)
    from test_verification.coverage import measure
    issues, _ = measure(str(tmp_path), {"src/payment/billing.py": {1, 2}})
    assert len(issues) == 1
    i = issues[0]
    assert i.rule_id == "TEST-001"
    assert i.file == "src/payment/billing.py"
    assert i.keyword == "커버리지 미충족"
    assert "85.0%" in i.message
    assert "90%" in i.message


def test_payment_file_at_95_not_flagged(tmp_path):
    """payment 파일 95% (≥ 90%) → 무이슈."""
    _write_cov(tmp_path, {"src/payment/billing.py": _payment_file(95.0)}, totals_pct=95.0)
    from test_verification.coverage import measure
    issues, _ = measure(str(tmp_path), {"src/payment/billing.py": {1}})
    assert issues == []


def test_default_module_not_individually_flagged(tmp_path):
    """일반 파일(기본 모듈)은 파일별 판정 안 함 (전체 집계가 담당 → 중복 방지)."""
    _write_cov(tmp_path, {"src/cart.py": _payment_file(50.0)}, totals_pct=90.0)
    from test_verification.coverage import measure
    issues, _ = measure(str(tmp_path), {"src/cart.py": {1}})
    assert issues == []


def test_backward_compatible_without_changed(tmp_path):
    """changed 미제공 → 파일별 판정 없음 (기존 동작 보존)."""
    _write_cov(tmp_path, {"src/payment/billing.py": _payment_file(85.0)}, totals_pct=90.0)
    from test_verification.coverage import measure
    issues, _ = measure(str(tmp_path))   # changed 없음
    assert issues == []


def test_whole_repo_and_payment_both_reported(tmp_path):
    """전체 80% 미달 + payment 90% 미달 → 두 이슈 (전체 1 + 파일별 1)."""
    _write_cov(tmp_path, {"src/payment/billing.py": _payment_file(85.0)}, totals_pct=50.0)
    from test_verification.coverage import measure
    issues, _ = measure(str(tmp_path), {"src/payment/billing.py": {1}})
    files = {i.file for i in issues}
    assert "(전체)" in files
    assert "src/payment/billing.py" in files
    assert len(issues) == 2
