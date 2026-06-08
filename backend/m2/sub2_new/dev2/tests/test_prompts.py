"""
Task 4-b 테스트 — 프롬프트 엔지니어링 (severity_judge)

순수 Python 로직이므로 LLM/DB 없이 통과한다.
"""

from dev2.prompts.severity_judge import build_severity_prompt


def test_prompt_includes_similar_cases():
    """RAG context: similar_cases가 프롬프트에 주입되는지 확인"""
    prompt = build_severity_prompt(
        message="SQL 파라미터 미처리",
        current_severity="Major",
        developer_level="junior",
        similar_cases=[{"pr_id": "98", "similarity": 0.94, "message": "SQL 인젝션"}],
    )
    # Few-shot 예시 포함 확인
    assert "SQL 파라미터 미처리" in prompt
    # RAG context 주입 확인 (PR ID가 포함되어야 함)
    assert "98" in prompt
    # CoT 단계 포함 확인
    assert "Chain-of-Thought" in prompt or "분석 단계" in prompt
    # Structured Output 형식 확인
    assert "severity" in prompt
    assert "suggestion" in prompt


def test_prompt_empty_similar_cases():
    """pgVector 0결과 시 '유사 사례 없음' 문구 포함 (CLAUDE.md §12)"""
    prompt = build_severity_prompt(
        message="변수명 위반",
        current_severity="Minor",
        developer_level="senior",
        similar_cases=[],
    )
    assert "유사 사례 없음" in prompt


def test_prompt_includes_developer_level():
    """developer_level이 프롬프트에 포함되는지 확인"""
    prompt = build_severity_prompt(
        message="N+1 쿼리 감지",
        current_severity="Major",
        developer_level="junior",
        similar_cases=[],
    )
    assert "junior" in prompt


def test_prompt_includes_few_shot_examples():
    """Few-shot 예시가 항상 포함되는지 확인"""
    prompt = build_severity_prompt(
        message="임의 이슈",
        current_severity="Minor",
        developer_level="mid",
        similar_cases=[],
    )
    # Few-shot 예시에 포함되는 severity 레이블 확인
    assert "Critical" in prompt
    assert "Major" in prompt
    assert "Minor" in prompt


def test_prompt_returns_string():
    """반환값이 str 타입인지 확인 (LLM 전달 전 타입 보장)"""
    prompt = build_severity_prompt(
        message="테스트 이슈", current_severity="Major",
        developer_level="junior", similar_cases=[]
    )
    assert isinstance(prompt, str)
    assert len(prompt) > 50  # 최소 길이 (의미있는 프롬프트)
