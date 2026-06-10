import asyncio
import logging
import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from backend.app.api.v1 import api_router
from backend.app.db.base import Base, async_session_factory, engine
from backend.app.middleware.error_handler import (
    http_exception_handler,
    unhandled_exception_handler,
)
from backend.app.services.ollama_client import is_ollama_available, warmup_model


def _configure_logging() -> None:
    """Set up application logging once, honouring the LOG_LEVEL env var.

    Agents and the orchestrator log warnings when an LLM/agent step fails; without
    this those records have no configured handler/level. Uses force=True so it wins
    over any handler uvicorn may have installed first.
    """
    level_name = os.getenv("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        force=True,
    )


_configure_logging()


_SAFE_MIGRATIONS = [
    "ALTER TABLE characters ADD COLUMN backstory TEXT DEFAULT ''",
    "ALTER TABLE turns ADD COLUMN attack_result TEXT",
]

# Default to the local dev frontend origins. Override with a comma-separated
# CORS_ORIGINS env var (use "*" to allow any origin — note that browsers reject
# wildcard origins on credentialed requests, so credentials are only enabled
# when an explicit origin list is configured).
_DEFAULT_CORS_ORIGINS = "http://localhost:3000,http://127.0.0.1:3000"


def _cors_settings() -> tuple[list[str], bool]:
    """Resolve allowed CORS origins and whether to allow credentials."""
    raw = os.getenv("CORS_ORIGINS", _DEFAULT_CORS_ORIGINS).strip()
    origins = [o.strip() for o in raw.split(",") if o.strip()]
    if "*" in origins:
        # Wildcard cannot be combined with credentials per the CORS spec.
        return ["*"], False
    return origins, True


def _bridge_app_logging() -> None:
    """Route the app's loggers (e.g. the M11 orchestrator's per-turn / fallback
    INFO lines) through uvicorn's console handler. Without this, app loggers
    have no handler under uvicorn and their output is silently dropped — so the
    server-side "what's happening" trace never appears."""
    uvicorn_logger = logging.getLogger("uvicorn")
    app_logger = logging.getLogger("backend.app")
    if uvicorn_logger.handlers and not app_logger.handlers:
        for h in uvicorn_logger.handlers:
            app_logger.addHandler(h)
    app_logger.setLevel(logging.INFO)
    app_logger.propagate = False


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Run DB schema creation and idempotent safe migrations on startup."""
    _bridge_app_logging()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        for stmt in _SAFE_MIGRATIONS:
            try:
                await conn.execute(text(stmt))
            except Exception:  # noqa: BLE001, S110
                pass  # column already exists — idempotent
    # Optionally preload the LLM so the first turn isn't cold (opt-in via OLLAMA_WARMUP=1).
    # Fire-and-forget: a reference is held on app.state so the task isn't garbage-collected.
    if os.getenv("OLLAMA_WARMUP", "0") == "1":
        app.state.warmup_task = asyncio.create_task(warmup_model())
    yield


app = FastAPI(
    title="D&D Multi-AI Agent Storytelling System API",
    description="A multi-agent LLM platform that runs Dungeons & Dragons sessions.",
    version="0.1.0",
    lifespan=lifespan,
)

_cors_origins, _cors_allow_credentials = _cors_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=_cors_allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_exception_handler(HTTPException, http_exception_handler)  # type: ignore[arg-type]
app.add_exception_handler(Exception, unhandled_exception_handler)

app.include_router(api_router)


async def _database_ok() -> bool:
    """Return True if a trivial query against the database succeeds."""
    try:
        async with async_session_factory() as session:
            await session.execute(text("SELECT 1"))
        return True
    except Exception:  # noqa: BLE001
        return False


@app.get("/health")
async def health() -> dict[str, str]:
    """Return service health including database and Ollama reachability."""
    # is_ollama_available makes a blocking HTTP call; offload it so a health
    # poll never freezes the event loop (and stalls in-flight turn streaming).
    ollama_ok = await asyncio.to_thread(is_ollama_available)
    db_ok = await _database_ok()
    return {
        "status": "ok" if db_ok else "degraded",
        "service": "dnd-multi-ai-agent-storytelling-system",
        "version": "0.1.0",
        "database": "ok" if db_ok else "unavailable",
        "ollama": "ok" if ollama_ok else "unavailable",
    }
