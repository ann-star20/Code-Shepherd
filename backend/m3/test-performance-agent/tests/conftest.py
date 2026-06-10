collect_ignore_glob = ["fixtures/*"]

import os

import pytest


@pytest.fixture(autouse=True)
def _rag_off(monkeypatch):
    """단위테스트가 BGE-M3·GCP 를 실제로 때리지 않도록 RAG_ENABLED 을 강제 unset.

    docker-compose 에 RAG_ENABLED=1 이 있어도 이 fixture 가 먼저 unset 한다.
    RAG 를 명시적으로 켜야 하는 테스트(test_main_rag_wiring.py 등)는
    monkeypatch.setenv("RAG_ENABLED", "1") 로 다시 활성화한다.
    """
    monkeypatch.delenv("RAG_ENABLED", raising=False)
