"""api-core FastAPI 애플리케이션 진입점."""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from shared.logging import TraceIDMiddleware, configure_logging

from .routers import auth, health, teams, users


@asynccontextmanager
async def lifespan(_app: FastAPI):
    configure_logging()
    yield


app = FastAPI(title="code-shepherd api-core", version="0.1.0", lifespan=lifespan)

app.add_middleware(TraceIDMiddleware)

app.include_router(health.router, tags=["health"])
app.include_router(auth.router, prefix="/auth", tags=["auth"])
app.include_router(users.router, prefix="/users", tags=["users"])
app.include_router(teams.router, prefix="/teams", tags=["teams"])
