"""M6 외부 문서 지식 그래프 서비스."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router as graph_router
from shared.logging import TraceIDMiddleware, configure_logging


@asynccontextmanager
async def lifespan(_app: FastAPI):
    configure_logging()
    yield


app = FastAPI(
    title="code-shepherd m6-knowledge-graph",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(TraceIDMiddleware)
app.include_router(graph_router, prefix="/graph")


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "service": "m6-knowledge-graph"}
