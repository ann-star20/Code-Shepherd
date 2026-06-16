"""Celery 앱 인스턴스 — m6 지식 그래프 비동기 파이프라인."""

import os

from celery import Celery

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

celery_app = Celery(
    "m6_knowledge_graph",
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=["app.services.pipeline", "app.worker.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_queues={
        "m6_graph": {"exchange": "m6_graph", "routing_key": "m6_graph"},
    },
    task_default_queue="m6_graph",
)

if os.getenv("LOCAL_DEBUG") == "true":
    celery_app.conf.update(
        task_always_eager=True,       # 비동기 큐를 거치지 않고, 일반 함수처럼 즉시 실행
        task_eager_propagates=True    # 태스크 내부에서 에러 발생 시 디버거 콘솔에 바로 에러 전파
    )


from celery.signals import worker_ready  # noqa: E402


@worker_ready.connect
def _warmup_embedding_model(**kwargs):
    from app.infrastructure.embeddings import get_client
    get_client()