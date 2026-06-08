"""로더 확장 — 문서 프론트매터(숫자) → convention_policies UPSERT,
   산문 본문만 임베딩(프론트매터는 벡터에서 제외). 외부 의존은 monkeypatch 고립.
"""
import textwrap
from pathlib import Path

import pytest

from rag import load_conventions

CONV_DIR = Path(__file__).resolve().parents[1] / "conventions"


# ─── 1) _split_frontmatter: 메타(dict) + 본문 분리 ────────────────────────────
def test_split_frontmatter_parses_meta_and_body():
    content = textwrap.dedent("""\
        ---
        policy_key: coverage
        rule_id: TEST-001
        params:
          default: 0.80
          payment: 0.90
        ---
        # 테스트 커버리지 가이드
        본문 산문입니다.
    """)
    meta, body = load_conventions._split_frontmatter(content)
    assert meta["policy_key"] == "coverage"
    assert meta["params"]["payment"] == 0.90
    assert body.startswith("# 테스트 커버리지 가이드")
    assert "---" not in body
    assert "policy_key" not in body          # 프론트매터는 본문에서 제거됨


# ─── 2) 프론트매터 없는 문서 → (None, 원문 그대로) ───────────────────────────
def test_split_frontmatter_none_when_absent():
    content = "# 그냥 문서\n본문만 있음.\n"
    meta, body = load_conventions._split_frontmatter(content)
    assert meta is None
    assert body == content


# ─── 3) load_from_dir: 정책 UPSERT + 본문만 임베딩 ───────────────────────────
def test_load_from_dir_upserts_policy_and_embeds_body(tmp_path, monkeypatch):
    # 문서 2개: 하나는 프론트매터 有(coverage), 하나는 無(산문만)
    (tmp_path / "01_cov.md").write_text(textwrap.dedent("""\
        ---
        policy_key: coverage
        rule_id: TEST-001
        params:
          default: 0.80
          payment: 0.90
        ---
        # 커버리지 가이드
        테스트는 변경의 일부입니다.
    """), encoding="utf-8")
    (tmp_path / "02_edge.md").write_text(
        "# 엣지케이스 가이드\nnull을 항상 처리하세요.\n", encoding="utf-8")

    from config import policy_store
    upserts = []
    monkeypatch.setattr(policy_store, "ensure_table", lambda conn: None)
    monkeypatch.setattr(policy_store, "upsert_policy",
                        lambda conn, k, r, p: upserts.append((k, r, p)))

    captured = {}

    def fake_embed_and_store(records, conn, embed=None):
        captured["records"] = records
        return len(records)
    monkeypatch.setattr(load_conventions, "embed_and_store", fake_embed_and_store)

    n = load_conventions.load_from_dir(str(tmp_path), conn=object())

    # 정책 1건만 UPSERT (coverage), 값 정확
    assert len(upserts) == 1
    key, rule_id, params = upserts[0]
    assert key == "coverage"
    assert rule_id == "TEST-001"
    assert params == {"default": 0.80, "payment": 0.90}

    # 임베딩 레코드 2건, 본문에 프론트매터(---, policy_key) 없음
    assert n == 2
    contents = [r["content"] for r in captured["records"]]
    assert all("policy_key" not in c and "params:" not in c for c in contents)
    assert any("커버리지 가이드" in c for c in contents)


# ─── 4) 실제 conventions/ 문서의 정책 수집 (커버리지+복잡도 둘 다) ────────────
def test_real_docs_collect_coverage_and_complexity(monkeypatch):
    from config import policy_store
    upserts = {}
    monkeypatch.setattr(policy_store, "ensure_table", lambda conn: None)
    monkeypatch.setattr(policy_store, "upsert_policy",
                        lambda conn, k, r, p: upserts.__setitem__(k, (r, p)))
    monkeypatch.setattr(load_conventions, "embed_and_store",
                        lambda records, conn, embed=None: len(records))

    load_conventions.load_from_dir(str(CONV_DIR), conn=object())

    # 복잡도 정책이 실제 문서에서 수집됐는지
    assert "complexity" in upserts
    rule_id, params = upserts["complexity"]
    assert rule_id == "PERF-001"
    assert params == {"minor_depth": 2, "major_depth": 3}
    # 커버리지 정책도 그대로 (회귀 없음)
    assert "coverage" in upserts
    assert upserts["coverage"][1]["default"] == 0.80
