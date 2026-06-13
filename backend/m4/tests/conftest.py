import pytest


@pytest.fixture(autouse=True)
def _reset_skip_ragas_eval(monkeypatch):
    """.env의 SKIP_RAGAS_EVAL=true가 컨테이너 환경변수로 누수되어 RAGAS 평가 루프를 항상
    건너뛰게 만드는 것을 방지한다. 명시적으로 monkeypatch.setenv하는 테스트는 영향 없음."""
    monkeypatch.delenv("SKIP_RAGAS_EVAL", raising=False)
