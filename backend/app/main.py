from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from backend.app.api.v1 import api_router
from backend.app.db.base import Base, engine
from backend.app.middleware.error_handler import (
    http_exception_handler,
    unhandled_exception_handler,
)
from backend.app.services.ollama_client import is_ollama_available

_SAFE_MIGRATIONS = [
    "ALTER TABLE characters ADD COLUMN backstory TEXT DEFAULT ''",
    "ALTER TABLE turns ADD COLUMN attack_result TEXT",
]


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Run DB schema creation and idempotent safe migrations on startup."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        for stmt in _SAFE_MIGRATIONS:
            try:
                await conn.execute(text(stmt))
            except Exception:  # noqa: BLE001, S110
                pass  # column already exists — idempotent
    yield


app = FastAPI(
    title="D&D Storyteller API",
    description="Multi-AI Agent D&D Storytelling Platform",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_exception_handler(HTTPException, http_exception_handler)  # type: ignore[arg-type]
app.add_exception_handler(Exception, unhandled_exception_handler)

app.include_router(api_router)


@app.get("/health")
async def health() -> dict[str, str]:
    """Return service health including Ollama reachability."""
    ollama_ok = is_ollama_available()
    return {
        "status": "ok",
        "service": "dnd-storyteller",
        "version": "0.1.0",
        "ollama": "ok" if ollama_ok else "unavailable",
    }
