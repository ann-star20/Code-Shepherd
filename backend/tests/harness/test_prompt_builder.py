"""_build_prompt 단위 테스트 — 도메인 주입 및 프롬프트 구조 검증."""

from app.infrastructure.llm.gemini_client import _build_prompt, DEFAULT_DOMAINS

CHUNK = "Django uses CSRF tokens to protect against cross-site request forgery."
META_DJANGO = {"framework": "Django", "lang": "KO"}


# ── T1: 기본 도메인 포함 ──────────────────────────────────────────────────────

def test_default_domains_in_prompt():
    """allowed_domains 미전달 시 DEFAULT_DOMAINS가 프롬프트에 포함된다."""
    prompt = _build_prompt(CHUNK, META_DJANGO)
    for d in DEFAULT_DOMAINS:
        assert f'"{d}"' in prompt


# ── T2: 커스텀 도메인 주입 ────────────────────────────────────────────────────

def test_custom_domains_injected():
    """allowed_domains=['security','compliance'] → 두 값 반영, performance 제외."""
    prompt = _build_prompt(CHUNK, META_DJANGO, allowed_domains=["security", "compliance"])
    assert '"security"' in prompt
    assert '"compliance"' in prompt
    assert '"performance"' not in prompt


# ── T3: 신규 단일 도메인 ─────────────────────────────────────────────────────

def test_single_new_domain():
    """단일 신규 도메인도 프롬프트 구조를 깨지 않는다."""
    prompt = _build_prompt(CHUNK, META_DJANGO, allowed_domains=["reliability"])
    assert '"reliability"' in prompt
    assert "JSON 배열로만 응답" in prompt


# ── T4: framework/lang 반영 ──────────────────────────────────────────────────

def test_metadata_reflected():
    """framework, lang이 프롬프트에 포함된다."""
    prompt = _build_prompt(CHUNK, {"framework": "Spring", "lang": "EN"})
    assert "Spring" in prompt
    assert "EN" in prompt


# ── T5: 청크가 --- 구분선 사이에 위치 ────────────────────────────────────────

def test_chunk_wrapped_in_separator():
    """입력 청크가 --- 구분선 사이에 포함된다."""
    prompt = _build_prompt(CHUNK, META_DJANGO)
    assert f"---\n{CHUNK}\n---" in prompt


# ── T6: "both" 금지 문구 포함 ────────────────────────────────────────────────

def test_both_keyword_forbidden_instruction():
    """'both' 사용 금지 지시가 프롬프트에 포함된다."""
    prompt = _build_prompt(CHUNK, META_DJANGO)
    assert '"both" 사용 금지' in prompt


# ── T7: metadata['allowed_domains'] 자동 주입 경로 ───────────────────────────

def test_allowed_domains_via_metadata():
    """GeminiClient 내부 경로: metadata['allowed_domains'] → _build_prompt 전달."""
    meta = {**META_DJANGO, "allowed_domains": ["security", "reliability"]}
    prompt = _build_prompt(CHUNK, meta, meta.get("allowed_domains"))
    assert '"reliability"' in prompt
    assert '"security"' in prompt
