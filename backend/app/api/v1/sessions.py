from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.base import get_db
from backend.app.db.models import Campaign, Session
from backend.app.db.models.character import Character
from backend.app.db.models.event_log import EventLog
from backend.app.db.models.memory import Memory, Summary
from backend.app.db.models.session import Turn
from backend.app.models.session import SessionCreate, SessionEnd, SessionResponse
from backend.app.orchestrator import advance_turn_stream as orchestrator_advance
from backend.app.orchestrator import end_session as orchestrator_end_session
from backend.app.orchestrator import get_scene as orchestrator_get_scene
from backend.app.orchestrator import set_seats as orchestrator_set_seats
from backend.app.orchestrator import start_session as orchestrator_start_session

router = APIRouter(prefix="/sessions", tags=["sessions"])


@router.get("/{session_id}/scene")
async def get_scene(
    session_id: str,
    character_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """M11 stage 2: the character's current scene — location (read-out),
    connected exits (move options), and present entities (targets)."""
    result = await orchestrator_get_scene(session_id, character_id, db)
    if "error" in result:
        raise HTTPException(status_code=result["status"], detail=result["error"])
    return result


@router.post("/{session_id}/advance")
async def advance_turn(
    session_id: str,
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    """M11 stage 3: run the next engine-driven turn (enemy/NPC reaction) and
    stream it. Events: ``result`` → ``token`` → ``done`` (with ``next_turn``),
    or a single ``idle`` event when it's a human's turn / nobody is left."""
    return StreamingResponse(
        orchestrator_advance(session_id, db),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/{session_id}/seats")
async def set_seats(
    session_id: str,
    assignments: dict[str, str],
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """M11 stage 3.5: assign per-seat controllers — body is
    ``{character_id: "ai"|"human"}``. Returns seat config + next_turn."""
    result = await orchestrator_set_seats(session_id, assignments, db)
    if "error" in result:
        raise HTTPException(status_code=result["status"], detail=result["error"])
    return result


async def _get_session_summary(session_id: str, db: AsyncSession) -> str | None:
    """Fetch the latest summary text for a session, or None."""
    result = await db.execute(
        select(Summary)
        .where(Summary.session_id == session_id)
        .order_by(Summary.created_at.desc())
        .limit(1)
    )
    summary = result.scalar_one_or_none()
    return str(summary.summary_text) if summary and summary.summary_text else None


@router.get("", response_model=list[SessionResponse])
async def list_sessions(
    db: AsyncSession = Depends(get_db),
) -> list[SessionResponse]:
    """List all sessions ordered newest-first."""
    result = await db.execute(select(Session).order_by(Session.started_at.desc()))
    sessions = result.scalars().all()
    return [
        SessionResponse(
            id=s.id,
            campaign_id=s.campaign_id,
            name=s.name,
            status=s.status,
            started_at=s.started_at,
            ended_at=s.ended_at,
            turn_count=s.turn_count,
        )
        for s in sessions
    ]


@router.get("/{session_id}", response_model=SessionResponse)
async def get_session(
    session_id: str,
    db: AsyncSession = Depends(get_db),
) -> SessionResponse:
    """Fetch a single session by ID; returns 404 if not found."""
    result = await db.execute(select(Session).where(Session.id == session_id))
    session = result.scalar_one_or_none()
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return SessionResponse(
        id=session.id,
        campaign_id=session.campaign_id,
        name=session.name,
        status=session.status,
        started_at=session.started_at,
        ended_at=session.ended_at,
        turn_count=session.turn_count,
        summary=await _get_session_summary(session_id, db),
    )


@router.post("", response_model=SessionResponse, status_code=status.HTTP_201_CREATED)
async def create_session(
    body: SessionCreate,
    db: AsyncSession = Depends(get_db),
) -> SessionResponse:
    """Start a new session for a campaign via the orchestrator."""
    campaign_result = await db.execute(select(Campaign).where(Campaign.id == body.campaign_id))
    if campaign_result.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Campaign not found")

    result = await orchestrator_start_session(campaign_id=body.campaign_id, name=body.name, db=db)
    return SessionResponse(
        id=result["id"],
        campaign_id=result["campaign_id"],
        name=result["name"],
        status=result["status"],
        started_at=result["started_at"],
        ended_at=None,
        turn_count=result["turn_count"],
    )


@router.get("/{session_id}/turns")
async def list_session_turns(
    session_id: str,
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    """Return all turns for a session, each with NPC dialogues from the event log."""
    session_check = await db.execute(select(Session).where(Session.id == session_id))
    if session_check.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Session not found")

    turns_result = await db.execute(
        select(Turn)
        .where(Turn.session_id == session_id)
        .order_by(Turn.turn_number)
    )
    turns = turns_result.scalars().all()

    char_ids = {t.character_id for t in turns if t.character_id}
    char_names: dict[str, str] = {}
    if char_ids:
        names_result = await db.execute(
            select(Character.id, Character.character_name).where(Character.id.in_(char_ids))
        )
        char_names = {row[0]: row[1] for row in names_result}

    output = []
    for t in turns:
        npc_result = await db.execute(
            select(EventLog)
            .where(
                EventLog.entity_id == t.id,
                EventLog.event_type == "npc_dialogue",
            )
            .order_by(EventLog.created_at)
        )
        npc_events = npc_result.scalars().all()
        npc_responses = []
        for ev in npc_events:
            try:
                npc_responses.append(json.loads(ev.data))
            except (json.JSONDecodeError, TypeError):
                pass

        try:
            dice_results = json.loads(t.dice_results) if t.dice_results else []
            if not isinstance(dice_results, list):
                dice_results = []
        except (json.JSONDecodeError, TypeError):
            dice_results = []

        try:
            attack_result = json.loads(t.attack_result) if t.attack_result else None
        except (json.JSONDecodeError, TypeError):
            attack_result = None

        output.append(
            {
                "id": t.id,
                "turn_number": t.turn_number,
                "character_id": t.character_id,
                "character_name": char_names.get(str(t.character_id), "") if t.character_id else "",
                "action_type": t.action_type,
                "action_text": t.action_text or "",
                "dice_results": dice_results,
                "attack_result": attack_result,
                "narration": t.narration or "",
                "npc_responses": npc_responses,
                "created_at": (
                    t.created_at.isoformat()
                    if hasattr(t.created_at, "isoformat")
                    else t.created_at
                ),
            }
        )
    return output


@router.post("/{session_id}/end", response_model=SessionResponse)
async def end_session(
    session_id: str,
    body: SessionEnd | None = None,
    db: AsyncSession = Depends(get_db),
) -> SessionResponse:
    """End a session and trigger the summary agent; returns 404/409 on error."""
    result = await orchestrator_end_session(session_id=session_id, db=db)
    if "error" in result:
        raise HTTPException(status_code=result["status"], detail=result["error"])

    session_result = await db.execute(select(Session).where(Session.id == session_id))
    session = session_result.scalar_one()
    return SessionResponse(
        id=session.id,
        campaign_id=session.campaign_id,
        name=session.name,
        status=session.status,
        started_at=session.started_at,
        ended_at=session.ended_at,
        turn_count=session.turn_count,
        summary=await _get_session_summary(session_id, db),
    )


@router.get("/{session_id}/memories")
async def list_session_memories(
    session_id: str,
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    """Return AI-extracted story facts for a session, ordered by importance then recency."""
    session_check = await db.execute(select(Session).where(Session.id == session_id))
    if session_check.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Session not found")

    result = await db.execute(
        select(Memory)
        .where(Memory.session_id == session_id)
        .order_by(Memory.importance.desc(), Memory.created_at.desc())
        .limit(20)
    )
    memories = result.scalars().all()
    return [
        {
            "id": m.id,
            "fact_text": m.fact_text,
            "fact_type": m.fact_type,
            "importance": m.importance,
            "created_at": m.created_at,
        }
        for m in memories
        if m.fact_text and m.fact_text.strip()
    ]


@router.delete("/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_session(
    session_id: str,
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete a completed session. Returns 404 if not found, 409 if session is still active."""
    result = await db.execute(select(Session).where(Session.id == session_id))
    session = result.scalar_one_or_none()
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    if session.status == "active":
        raise HTTPException(
            status_code=409,
            detail="Cannot delete an active session — end it first",
        )
    await db.delete(session)
    await db.flush()
