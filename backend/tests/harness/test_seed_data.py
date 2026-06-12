"""시드 데이터 검증 테스트 — DB 불필요.

커버:
  S01 JSON 파싱      — 모든 시드 항목이 ConceptExtractionSchema 오류 없이 파싱
  S02 필수 필드      — concept_name, domains, cwe_id, description_ko 존재
  S03 도메인 일관성  — security 시드는 domains에 'security', performance는 'performance'
  S04 severity       — 허용 범위 내 (critical/high/medium/low/info/None)
  S05 mechanism 정규화 — mechanism_name이 소문자 스네이크케이스
  S06 교차 도메인    — ConnPoolExhaustion·MemoryLeak이 두 도메인 모두 포함
  S07 OWASP/CWE 형식 — A##:20## / CWE-### 패턴
  S08 코드 예시 완결 — code 필드가 빈 문자열이 아님
  S09 개수 검증      — 보안 10개, 성능 4개
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from app.domain.models import ConceptExtractionSchema

# ── 경로 ─────────────────────────────────────────────────────────────────────

_SEED_DIR = Path(__file__).parent.parent.parent / "scripts" / "seed"
_SEC_JSON = _SEED_DIR / "security" / "security_concepts.json"
_PERF_JSON = _SEED_DIR / "performance" / "performance_concepts.json"

_VALID_SEVERITIES = {"critical", "high", "medium", "low", "info", None}
_OWASP_RE = re.compile(r"^A\d{2}:20\d{2}$")
_CWE_RE = re.compile(r"^CWE-\d+$")


def _load(path: Path) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8"))


def _all_concepts() -> list[tuple[str, dict]]:
    return [("security", c) for c in _load(_SEC_JSON)] + [
        ("performance", c) for c in _load(_PERF_JSON)
    ]


# ── S01: JSON 파싱 ────────────────────────────────────────────────────────────


@pytest.mark.parametrize("domain,raw", _all_concepts())
def test_S01_parses_without_error(domain: str, raw: dict):
    concept = ConceptExtractionSchema(**raw)
    assert concept.concept_name


# ── S02: 필수 필드 ────────────────────────────────────────────────────────────


@pytest.mark.parametrize("domain,raw", _all_concepts())
def test_S02_required_fields_present(domain: str, raw: dict):
    assert raw.get("concept_name"), "concept_name 누락"
    assert raw.get("domains"), "domains 누락"
    assert raw.get("cwe_id"), f"{raw.get('concept_name')}: cwe_id 누락"
    assert raw.get("description_ko"), f"{raw.get('concept_name')}: description_ko 누락"


# ── S03: 도메인 일관성 ────────────────────────────────────────────────────────


def test_S03_security_seed_has_security_domain():
    for raw in _load(_SEC_JSON):
        c = ConceptExtractionSchema(**raw)
        assert "security" in c.domains, f"{c.concept_name}: security 도메인 없음"


def test_S03_performance_seed_has_performance_domain():
    for raw in _load(_PERF_JSON):
        c = ConceptExtractionSchema(**raw)
        assert "performance" in c.domains, f"{c.concept_name}: performance 도메인 없음"


# ── S04: severity 허용 범위 ───────────────────────────────────────────────────


@pytest.mark.parametrize("domain,raw", _all_concepts())
def test_S04_severity_valid(domain: str, raw: dict):
    sev = raw.get("severity")
    assert (
        sev in _VALID_SEVERITIES
    ), f"{raw.get('concept_name')}: 비허용 severity '{sev}'"


# ── S05: mechanism_name 소문자 스네이크케이스 ─────────────────────────────────


@pytest.mark.parametrize("domain,raw", _all_concepts())
def test_S05_mechanism_names_normalized(domain: str, raw: dict):
    c = ConceptExtractionSchema(**raw)
    for mech in c.mechanisms:
        n = mech.mechanism_name
        assert n == n.lower(), f"{c.concept_name}/{n}: 소문자 아님"
        assert " " not in n, f"{c.concept_name}/{n}: 공백 포함"
        assert "-" not in n, f"{c.concept_name}/{n}: 하이픈 포함"


# ── S06: 교차 도메인 개념 검증 ────────────────────────────────────────────────


def test_S06_conn_pool_exhaustion_cross_domain():
    perf = _load(_PERF_JSON)
    conn = next((c for c in perf if c["concept_name"] == "ConnPoolExhaustion"), None)
    assert conn is not None, "ConnPoolExhaustion 시드 없음"
    assert set(conn["domains"]) >= {"performance", "security"}, "교차 도메인 아님"


def test_S06_memory_leak_cross_domain():
    perf = _load(_PERF_JSON)
    ml = next((c for c in perf if c["concept_name"] == "MemoryLeak"), None)
    assert ml is not None, "MemoryLeak 시드 없음"
    assert set(ml["domains"]) >= {"performance", "security"}, "교차 도메인 아님"


# ── S07: OWASP / CWE 형식 ─────────────────────────────────────────────────────


def test_S07_security_owasp_format():
    for raw in _load(_SEC_JSON):
        owasp = raw.get("owasp_id") or raw.get("owasp_category")
        if owasp:
            assert _OWASP_RE.match(
                owasp
            ), f"{raw.get('concept_name')}: owasp_id '{owasp}' 형식 오류 (A##:20## 기대)"


@pytest.mark.parametrize("domain,raw", _all_concepts())
def test_S07_cwe_format(domain: str, raw: dict):
    cwe = raw.get("cwe_id")
    if cwe:
        assert _CWE_RE.match(
            cwe
        ), f"{raw.get('concept_name')}: cwe_id '{cwe}' 형식 오류 (CWE-### 기대)"


# ── S08: 코드 예시 완결성 ─────────────────────────────────────────────────────


@pytest.mark.parametrize("domain,raw", _all_concepts())
def test_S08_code_examples_not_empty(domain: str, raw: dict):
    c = ConceptExtractionSchema(**raw)
    for mech in c.mechanisms:
        for ex in mech.code_examples:
            assert (
                ex.code.strip()
            ), f"{c.concept_name}/{mech.mechanism_name}: code 필드 비어 있음"


# ── S09: 개수 검증 ────────────────────────────────────────────────────────────


def test_S09_security_seed_count():
    assert len(_load(_SEC_JSON)) == 12, "보안 시드 개념 수 != 12"


def test_S09_performance_seed_count():
    assert len(_load(_PERF_JSON)) == 4, "성능 시드 개념 수 != 4"
