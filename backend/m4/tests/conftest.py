import pytest
from langsmith.run_helpers import tracing_context


@pytest.fixture(autouse=True)
def _reset_skip_ragas_eval(monkeypatch):
    """.env의 SKIP_RAGAS_EVAL=true가 컨테이너 환경변수로 누수되어 RAGAS 평가 루프를 항상
    건너뛰게 만드는 것을 방지한다. 명시적으로 monkeypatch.setenv하는 테스트는 영향 없음."""
    monkeypatch.delenv("SKIP_RAGAS_EVAL", raising=False)


@pytest.fixture(autouse=True)
def _disable_langsmith_tracing():
    """T11~T14에서 추가된 @traceable 데코레이터(curator_agent/rag_search/build_card/
    ragas_eval/embed_query_fields/generate_card)가 테스트 중 실제 LangSmith로 네트워크
    요청을 보내지 않도록 기본적으로 tracing을 비활성화한다. 개별 테스트가 자체
    tracing_context(enabled=True, ...)로 이 블록 안에서 재정의할 수 있다."""
    with tracing_context(enabled=False):
        yield
