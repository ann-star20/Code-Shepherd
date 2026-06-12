"""Celery 앱 설정."""

import logging
import os
from celery import Celery
from celery.signals import worker_process_init

logging.basicConfig(level=logging.INFO, format="%(name)s | %(levelname)s | %(message)s")

broker = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0")
backend = os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/1")

celery_app = Celery(
    "code_shepherd",
    broker=broker,
    backend=backend,
    include=["app.worker.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Seoul",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,  # worker 장애 시 재처리 보장
    worker_prefetch_multiplier=1,  # 태스크 하나씩 처리 (긴 태스크 공정 분배)
)


@worker_process_init.connect
def warm_up_embedding(**kwargs):
    # 각 ForkPoolWorker 시작 시 BGE-M3를 미리 로드해 첫 태스크 2분 지연 제거
    from app.infrastructure.llm.factory import create_embedding_client

    create_embedding_client(model=os.getenv("EMBEDDING_MODEL", "BAAI/bge-m3"))
