"""Alembic env.py 골격 — m0 담당자가 모델 추가 후 채운다."""

import asyncio
import sys
import os
from logging.config import fileConfig
from pathlib import Path

from dotenv import load_dotenv
# 프로젝트 루트 .env 로드 (shared.config가 DB 환경변수를 읽을 수 있도록)
load_dotenv(Path(__file__).parent.parent.parent.parent / ".env")

from alembic import context
from sqlalchemy.ext.asyncio import create_async_engine

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from shared.config import get_settings
from shared.db import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=get_settings().database_url,
        target_metadata=target_metadata,
        literal_binds=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection):
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        version_table="alembic_version_m4",  # api-core 버전 테이블과 분리
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    engine = create_async_engine(get_settings().database_url)
    async with engine.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
