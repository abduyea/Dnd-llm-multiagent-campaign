"""
Orchestrator — the integration seam.

M11 stage 1: `start_session`, `process_action`, and `process_action_stream`
now drive **our** event-sourced engine via `engine_glue` (which uses the pure
`m11_adapter`). The team's `engine/` and `agents/` modules are left in place
but no longer on the action path (retiring them is a later stage). `end_session`
keeps its original behaviour (mark completed + summary agent).
"""
from __future__ import annotations

import json
import logging
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.agents.summary_agent import summarise_session
from backend.app.db.models import EventLog, Session
from backend.app.engine.types import ActionInput
from backend.app.orchestrator import engine_glue

logger = logging.getLogger(__name__)


async def start_session(
    campaign_id: str,
    name: str,
    db: AsyncSession,
) -> dict[str, Any]:
    """Create a session; assemble + persist the engine seed for the demo
    campaign. Delegates to the M11 engine glue."""
    return await engine_glue.start_session_impl(campaign_id, name, db)


async def process_action(
    action_input: ActionInput,
    db: AsyncSession,
) -> dict[str, Any]:
    """Run one human action through our engine; return the frontend's result
    dict (or an ``{"error", "status"}`` dict)."""
    return await engine_glue.resolve_human_action(action_input, db)


async def process_action_stream(
    action_input: ActionInput,
    db: AsyncSession,
) -> AsyncGenerator[str, None]:
    """Run one human action and stream SSE chunks: result → token → done."""
    async for chunk in engine_glue.process_action_stream_impl(action_input, db):
        yield chunk


async def get_scene(
    session_id: str,
    character_id: str,
    db: AsyncSession,
) -> dict[str, Any]:
    """Scene read-out (location + exits + present entities) for a character."""
    return await engine_glue.get_scene(db, session_id, character_id)


async def advance_turn_stream(
    session_id: str,
    db: AsyncSession,
) -> AsyncGenerator[str, None]:
    """Run the next engine-driven turn (enemy/NPC) and stream it: result →
    token → done (with next_turn), or an ``idle`` event on a human's turn."""
    async for chunk in engine_glue.advance_stream_impl(session_id, db):
        yield chunk


async def set_seats(
    session_id: str,
    assignments: dict[str, str],
    db: AsyncSession,
) -> dict[str, Any]:
    """Assign per-seat controllers (AI vs human). Powers the AI-seat toggle and
    all-AI mode."""
    return await engine_glue.set_seats(db, session_id, assignments)


async def end_session(
    session_id: str,
    db: AsyncSession,
) -> dict[str, Any]:
    """Mark session completed, emit an audit event, and trigger the summary."""
    result = await db.execute(select(Session).where(Session.id == session_id))
    session = result.scalar_one_or_none()
    if session is None:
        return {"error": "Session not found", "status": 404}

    session.status = "completed"
    session.ended_at = datetime.now(UTC).isoformat()

    db.add(
        EventLog(
            event_type="session_end",
            entity_type="session",
            entity_id=session_id,
            data=json.dumps({"status": "completed"}),
            agent_id="orchestrator",
        )
    )

    try:
        await summarise_session(session_id=session_id, db=db)
    except Exception:  # noqa: BLE001
        logger.warning("Summary agent failed for session %s", session_id, exc_info=True)

    return {"id": session_id, "status": "completed", "status_code": 200}
