"""FastAPI application entry point."""

import os
from contextlib import asynccontextmanager

import asyncpg
from fastapi import FastAPI
from neo4j import AsyncGraphDatabase

from app.interfaces.api import staging as staging_mod
from app.interfaces.api.staging import router as staging_router
from app.interfaces.api.documents import router as documents_router
from app.interfaces.api.prescan import router as prescan_router
from app.interfaces.api.pipeline import router as pipeline_router
from app.interfaces.api.domains import (
    router as domains_router,
    staging_router as domain_staging_router,
)
from app.interfaces.api.graph import router as graph_router


def _pg_dsn() -> str:
    return (
        f"postgresql://{os.getenv('DB_USER', 'postgres')}:{os.getenv('DB_PASSWORD', 'postgres')}"
        f"@{os.getenv('DB_HOST', 'localhost')}:{os.getenv('DB_PORT', '5432')}"
        f"/{os.getenv('DB_NAME', 'postgres')}"
    )


def _neo4j_driver():
    uri = os.getenv("NEO4J_URI", "bolt://127.0.0.1:7688")
    auth = (os.getenv("NEO4J_USER", "neo4j"), os.getenv("NEO4J_PASSWORD", "pass1234!"))
    return AsyncGraphDatabase.driver(uri, auth=auth)


@asynccontextmanager
async def lifespan(app: FastAPI):
    pool = await asyncpg.create_pool(_pg_dsn(), min_size=2, max_size=10, ssl=False)
    app.state.pool = pool
    driver = _neo4j_driver()
    app.state.neo4j_driver = driver
    yield
    await pool.close()
    await driver.close()


app = FastAPI(title="Code Shepherd — Knowledge Graph Agent", lifespan=lifespan)

app.include_router(documents_router)
app.include_router(prescan_router)
app.include_router(pipeline_router)
app.include_router(domains_router)
app.include_router(domain_staging_router)
app.include_router(staging_router)
app.include_router(graph_router)


async def _get_conn_from_pool():
    async with app.state.pool.acquire() as conn:
        yield conn


app.dependency_overrides[staging_mod._get_conn] = _get_conn_from_pool


@app.get("/health")
async def health():
    return {"status": "ok"}
