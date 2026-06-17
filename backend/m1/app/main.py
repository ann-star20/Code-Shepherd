"""M1 오케스트레이터 FastAPI 진입점."""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from shared.logging import TraceIDMiddleware, configure_logging

from .routers import health, triggers


@asynccontextmanager
async def lifespan(_app: FastAPI):
    configure_logging()
    yield


app = FastAPI(
    title="code-shepherd m1-orchestrator",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(TraceIDMiddleware)
app.include_router(health.router, tags=["health"])
app.include_router(triggers.router, tags=["triggers"])
