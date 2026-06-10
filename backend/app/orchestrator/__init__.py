"""
Orchestrator — the integration seam.

M11 stage 1: `start_session`, `process_action`, and `process_action_stream`
now drive **our** event-sourced engine via `engine_glue` (which uses the pure
`m11_adapter`). The team's `engine/` and `agents/` modules are left in place
but no longer on the action path (retiring them is a later stage). `end_session`
keeps its original behaviour (mark completed + summary agent).
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import uuid
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.agents.context_builder import build_dm_context
from backend.app.agents.dm_agent import build_narration_prompt, narrate
from backend.app.agents.memory_agent import extract_and_store
from backend.app.agents.npc_agent import get_npc_responses
from backend.app.agents.summary_agent import summarise_session
from backend.app.db.models import EventLog, Session, Turn
from backend.app.db.models.character import Character as CharacterModel
from backend.app.engine.combat import process_attack
from backend.app.engine.dice import roll_dice
from backend.app.engine.types import (
    ActionEconomy,
    ActionInput,
    AttackResult,
    CharacterState,
    GameState,
    TurnDelta,
)
from backend.app.engine.validation import validate_action
from backend.app.orchestrator import engine_glue
from backend.app.services.ollama_client import _static_fallback, generate_stream

logger = logging.getLogger(__name__)

_DC_RE = re.compile(r"\b(?:DC|difficulty)\s*(\d+)", re.IGNORECASE)
_DEFAULT_SKILL_DC = 15


def _parse_skill_dc(description: str) -> int:
    """Extract DC from player description text; fall back to DC 15."""
    match = _DC_RE.search(description)
    return int(match.group(1)) if match else _DEFAULT_SKILL_DC


# D&D 5e XP thresholds by level (index = current level, value = XP needed to reach next level).
_XP_THRESHOLDS: tuple[int, ...] = (
    0, 300, 900, 2700, 6500, 14000, 23000, 34000, 48000,
    64000, 85000, 100000, 120000, 140000, 165000, 195000,
    225000, 265000, 305000, 355000,
)
_XP_PER_KILL = 25


async def _award_xp_for_kill(
    attacker_id: str,
    db: AsyncSession,
    xp: int = _XP_PER_KILL,
) -> dict[str, int]:
    """Award XP to the attacker character and level up if threshold crossed.

    Returns a dict with keys ``xp_gained``, ``new_xp``, ``new_level``
    (the last two reflect state after the award). Pure DB operation — no
    engine state involved.
    """
    db_char = await db.get(CharacterModel, attacker_id)
    if db_char is None:
        return {"xp_gained": 0, "new_xp": 0, "new_level": 1}

    old_xp: int = db_char.experience or 0
    new_xp = old_xp + xp
    db_char.experience = new_xp

    # Bump level while threshold for next level is met and level < 20
    current_level: int = db_char.level or 1
    while current_level < 20 and new_xp >= _XP_THRESHOLDS[current_level]:
        current_level += 1
    db_char.level = current_level

    return {"xp_gained": xp, "new_xp": new_xp, "new_level": current_level}


async def _get_recent_npc_talks(
    session_id: str,
    db: AsyncSession,
    limit: int = 3,
) -> list[dict[str, str]]:
    """Fetch the most recent NPC dialogue lines for this session from the event log."""
    # Single query: join the event log to this session's turns instead of pulling
    # every turn id into Python and passing them back as an IN (...) list.
    session_turn_ids = select(Turn.id).where(Turn.session_id == session_id)
    log_result = await db.execute(
        select(EventLog)
        .where(EventLog.event_type == "npc_dialogue")
        .where(EventLog.entity_id.in_(session_turn_ids))
        .order_by(EventLog.created_at.desc())
        .limit(limit)
    )
    rows = list(log_result.scalars().all())
    talks: list[dict[str, str]] = []
    for row in reversed(rows):
        try:
            data = json.loads(row.data)
            npc_name = data.get("npc_name", "NPC")
            dialogue = data.get("dialogue", "")
            if npc_name and dialogue:
                talks.append({"npc_name": npc_name, "dialogue": dialogue})
        except (json.JSONDecodeError, TypeError):
            pass
    return talks


async def get_game_state(
    session_id: str,
    db: AsyncSession,
) -> GameState | None:
    """Build a GameState snapshot from DB for the given session; None if not found."""
    result = await db.execute(select(Session).where(Session.id == session_id))
    db_session = result.scalar_one_or_none()
    if db_session is None:
        return None

    chars_result = await db.execute(
        select(CharacterModel).where(CharacterModel.campaign_id == db_session.campaign_id)
    )
    characters = chars_result.scalars().all()

    char_states: dict[str, Any] = {}
    for char in characters:
        char_states[char.id] = CharacterState(
            id=char.id,
            name=char.character_name,
            hp_current=char.hp_current,
            hp_max=char.hp_max,
            strength=char.strength,
            dexterity=char.dexterity,
            constitution=char.constitution,
            intelligence=char.intelligence,
            wisdom=char.wisdom,
            charisma=char.charisma,
            armor_class=char.armor_class,
            initiative_bonus=char.initiative,
            speed=char.speed,
            conditions=(),
            action_economy=ActionEconomy(movement_remaining=char.speed),
        )

    return GameState(
        session_id=session_id,
        campaign_id=db_session.campaign_id,
        turn_number=db_session.turn_count,
        current_character_id=None,
        characters=char_states,
    )


@dataclass
class _TurnError:
    """A pre-execution failure (missing/ended session, validation) to surface to the caller."""

    message: str
    status: int
    violations: list[dict[str, str]] | None = None


@dataclass
class _PreparedTurn:
    """Game-logic outcome of a turn, ready for narration.

    Holds the engine result plus the already-persisted ``Turn`` record and
    event log so that the narration half of a turn only has to deal with the
    LLM agents.
    """

    state: GameState
    new_state: GameState
    attack_result: AttackResult | None
    delta: TurnDelta
    turn_id: str
    turn_record: Turn
    state_changes: dict[str, Any]
    dm_dice_context: dict[str, Any] | None
    damage_dealt: int


async def _prepare_turn(
    action_input: ActionInput,
    db: AsyncSession,
) -> _PreparedTurn | _TurnError:
    """Validate, resolve dice/combat, and persist the turn record + event log.

    Shared by both the buffered (:func:`process_action`) and streaming
    (:func:`process_action_stream`) entry points so the game-logic half of a
    turn lives in exactly one place. Returns a :class:`_TurnError` for
    pre-execution failures (missing/ended session, validation) or a
    :class:`_PreparedTurn` snapshot ready for narration.
    """
    session_check = await db.execute(select(Session).where(Session.id == action_input.session_id))
    db_session_check = session_check.scalar_one_or_none()
    if db_session_check is None:
        return _TurnError("Session not found", 404)
    if db_session_check.status == "completed":
        return _TurnError("Session has already ended", 409)

    state = await get_game_state(action_input.session_id, db)
    if state is None:
        return _TurnError("Session not found", 404)

    state_violations = validate_action(state, action_input)
    if state_violations:
        return _TurnError(
            "Action validation failed",
            400,
            [
                {"field": v.field, "message": v.message, "code": v.code}
                for v in state_violations
            ],
        )

    if action_input.action_type in ("attack_melee", "attack_ranged"):
        new_state, attack_result = process_attack(state, action_input, seed=action_input.seed)
        extra_dice: list[Any] = []
    else:
        new_state = state
        attack_result = None
        extra_dice = []
        if action_input.dice_expression:
            try:
                extra_dice = [roll_dice(action_input.dice_expression, seed=action_input.seed)]
            except ValueError:
                extra_dice = []

    delta = TurnDelta(
        turn_number=state.turn_number,
        character_id=action_input.character_id,
        action_type=action_input.action_type,
        action_description=action_input.description,
        dice_results=extra_dice,
        attack_results=[attack_result] if attack_result else [],
        state_changes={},
        initiative_order=new_state.initiative_order,
    )

    turn_id = str(uuid.uuid4())
    turn_record = Turn(
        id=turn_id,
        session_id=action_input.session_id,
        character_id=action_input.character_id,
        turn_number=delta.turn_number,
        action_type=action_input.action_type,
        action_text=action_input.description,
        dice_results=json.dumps(
            [{"expression": dr.expression, "total": dr.total} for dr in delta.dice_results]
        ),
        attack_result=json.dumps(
            {
                "is_hit": attack_result.is_hit,
                "is_critical": attack_result.is_critical,
                "natural_roll": attack_result.natural_roll,
                "total_roll": attack_result.attack_roll,
                "damage": attack_result.damage,
            }
        ) if attack_result else None,
        narration="",
    )
    db.add(turn_record)

    xp_award: dict[str, int] = {}
    for char_id, updated in new_state.characters.items():
        old_char = state.characters.get(char_id)
        if old_char and updated.hp_current != old_char.hp_current:
            db_char = await db.get(CharacterModel, char_id)
            if db_char:
                db_char.hp_current = updated.hp_current
            if updated.hp_current == 0 and old_char.hp_current > 0:
                xp_award = await _award_xp_for_kill(action_input.character_id, db)

    db_session = await db.get(Session, action_input.session_id)
    if db_session:
        db_session.turn_count = db_session.turn_count + 1

    log = EventLog(
        event_type="action",
        entity_type="turn",
        entity_id=turn_id,
        data=json.dumps(
            {
                "action_type": action_input.action_type,
                "character_id": action_input.character_id,
                "description": action_input.description,
                **({"xp_award": xp_award} if xp_award else {}),
            }
        ),
        agent_id="orchestrator",
    )
    db.add(log)

    damage_dealt = attack_result.damage if attack_result else 0

    state_changes: dict[str, Any] = {}
    for char_id, updated in new_state.characters.items():
        old_char = state.characters.get(char_id)
        if old_char and (
            updated.hp_current != old_char.hp_current
            or set(updated.conditions) != set(old_char.conditions)
        ):
            state_changes[char_id] = {
                "hp_current": updated.hp_current,
                "hp_max": updated.hp_max,
                "conditions": list(updated.conditions),
            }

    dm_dice_context: dict[str, Any] | None = None
    if attack_result:
        dm_dice_context = {
            "expression": "1d20 attack",
            "total": attack_result.attack_roll,
            "rolls": [attack_result.natural_roll],
            "is_hit": attack_result.is_hit,
            "is_critical": attack_result.is_critical,
            "damage": attack_result.damage,
        }
    elif action_input.action_type == "skill_check":
        dc = _parse_skill_dc(action_input.description)
        if extra_dice:
            dr = extra_dice[0]
            dm_dice_context = {"total": dr.total, "dc": dc, "rolls": list(dr.rolls)}
        else:
            try:
                auto_roll = roll_dice("1d20", seed=action_input.seed)
                extra_dice = [auto_roll]
                dm_dice_context = {
                    "total": auto_roll.total,
                    "dc": dc,
                    "rolls": list(auto_roll.rolls),
                }
            except ValueError:
                dm_dice_context = {"dc": dc}
    elif extra_dice:
        dr = extra_dice[0]
        dm_dice_context = {
            "expression": dr.expression,
            "total": dr.total,
            "rolls": list(dr.rolls),
        }

    return _PreparedTurn(
        state=state,
        new_state=new_state,
        attack_result=attack_result,
        delta=delta,
        turn_id=turn_id,
        turn_record=turn_record,
        state_changes=state_changes,
        dm_dice_context=dm_dice_context,
        damage_dealt=damage_dealt,
    )


async def _legacy_process_action(
    action_input: ActionInput,
    db: AsyncSession,
) -> dict[str, Any]:
    """Validate, execute, persist, and narrate a player action; returns result dict."""
    prep = await _prepare_turn(action_input, db)
    if isinstance(prep, _TurnError):
        error: dict[str, Any] = {"error": prep.message, "status": prep.status}
        if prep.violations is not None:
            error["violations"] = prep.violations
        return error

    attack_result = prep.attack_result
    turn_record = prep.turn_record
    turn_id = prep.turn_id

    narration = ""
    npc_responses: list[dict[str, str]] = []
    try:
        context = await build_dm_context(
            session_id=action_input.session_id,
            campaign_id=prep.state.campaign_id,
            character_id=action_input.character_id,
            action_text=action_input.description,
            dice_result=prep.dm_dice_context,
            db=db,
            action_type=action_input.action_type,
            enemies=action_input.enemies,
            location=action_input.location,
        )
        # Offload the blocking LLM call so the event loop stays responsive for
        # other requests while this turn's narration is generated.
        narration = await asyncio.to_thread(narrate, messages=context)
        turn_record.narration = narration
    except Exception:  # noqa: BLE001
        logger.warning("DM narration failed for turn %s", turn_id, exc_info=True)
        narration = _static_fallback(action_input.description)
        turn_record.narration = narration

    try:
        if narration:
            recent_talks = await _get_recent_npc_talks(action_input.session_id, db)
            # Offload the blocking LLM call so the event loop stays responsive.
            npc_responses = await asyncio.to_thread(
                get_npc_responses,
                campaign_id=prep.state.campaign_id,
                dm_narration=narration,
                action_text=action_input.description,
                action_type=action_input.action_type,
                enemies=action_input.enemies,
                recent_talks=recent_talks,
            )
            for npc in npc_responses:
                npc_log = EventLog(
                    event_type="npc_dialogue",
                    entity_type="turn",
                    entity_id=turn_id,
                    data=json.dumps(npc),
                    agent_id="npc_agent",
                )
                db.add(npc_log)
    except Exception:  # noqa: BLE001
        logger.warning("NPC agent failed for turn %s", turn_id, exc_info=True)

    try:
        await extract_and_store(
            session_id=action_input.session_id,
            campaign_id=prep.state.campaign_id,
            action_text=action_input.description,
            narration=narration,
            db=db,
        )
    except Exception:  # noqa: BLE001
        logger.warning("Memory extraction failed for turn %s", turn_id, exc_info=True)

    return {
        "turn_number": prep.delta.turn_number,
        "character_id": action_input.character_id,
        "action_type": action_input.action_type,
        "description": action_input.description,
        "dice_results": [
            {
                "expression": dr.expression,
                "rolls": list(dr.rolls),
                "modifier": dr.modifier,
                "total": dr.total,
            }
            for dr in prep.delta.dice_results
        ],
        "attack_result": {
            "is_hit": attack_result.is_hit if attack_result else False,
            "is_critical": attack_result.is_critical if attack_result else False,
            "damage": prep.damage_dealt,
            "natural_roll": attack_result.natural_roll if attack_result else 0,
            "total_roll": attack_result.attack_roll if attack_result else 0,
        }
        if attack_result
        else None,
        "narration": narration,
        "npc_responses": npc_responses,
        "state_changes": prep.state_changes,
        "errors": [],
        "status": 200,
    }


async def _legacy_process_action_stream(
    action_input: ActionInput,
    db: AsyncSession,
) -> AsyncGenerator[str, None]:
    """Run game logic then stream SSE chunks: result → narration tokens → done."""

    def _sse(data: dict[str, Any]) -> str:
        return f"data: {json.dumps(data)}\n\n"

    prep = await _prepare_turn(action_input, db)
    if isinstance(prep, _TurnError):
        payload: dict[str, Any] = {
            "type": "error",
            "message": prep.message,
            "status": prep.status,
        }
        if prep.violations is not None:
            payload["violations"] = prep.violations
        yield _sse(payload)
        return

    attack_result = prep.attack_result
    turn_record = prep.turn_record
    turn_id = prep.turn_id

    errors: list[str] = []
    if attack_result and not attack_result.is_hit:
        errors = [f"Attack missed (rolled {attack_result.natural_roll})"]

    dm_context: list[dict[str, str]] = []
    try:
        dm_context = await build_dm_context(
            session_id=action_input.session_id,
            campaign_id=prep.state.campaign_id,
            character_id=action_input.character_id,
            action_text=action_input.description,
            dice_result=prep.dm_dice_context,
            db=db,
            action_type=action_input.action_type,
            enemies=action_input.enemies,
            location=action_input.location,
        )
    except Exception:  # noqa: BLE001
        logger.warning("Context build failed for turn %s", turn_id, exc_info=True)

    await db.flush()

    yield _sse({
        "type": "result",
        "turn_number": prep.delta.turn_number,
        "character_id": action_input.character_id,
        "action_type": action_input.action_type,
        "description": action_input.description,
        "dice_results": [
            {
                "expression": dr.expression, "rolls": list(dr.rolls),
                "modifier": dr.modifier, "total": dr.total,
            }
            for dr in prep.delta.dice_results
        ],
        "attack_result": {
            "is_hit": attack_result.is_hit,
            "is_critical": attack_result.is_critical,
            "damage": prep.damage_dealt,
            "natural_roll": attack_result.natural_roll,
            "total_roll": attack_result.attack_roll,
        } if attack_result else None,
        "state_changes": prep.state_changes,
        "errors": errors,
    })

    narration = ""
    if dm_context:
        try:
            prompt, system_prompt, action_text = build_narration_prompt(dm_context)
            async for token in generate_stream(
                prompt=prompt, system_prompt=system_prompt, action_text=action_text
            ):
                narration += token
                yield _sse({"type": "token", "text": token})
        except Exception:  # noqa: BLE001
            logger.warning("Streaming narration failed for turn %s", turn_id, exc_info=True)

    if not narration.strip():
        narration = _static_fallback(action_input.description)
        yield _sse({"type": "token", "text": narration})

    turn_record.narration = narration

    npc_responses: list[dict[str, str]] = []
    try:
        if narration:
            recent_talks = await _get_recent_npc_talks(action_input.session_id, db)
            # Offload the blocking LLM call to a worker thread so the event loop
            # stays responsive (health checks, other requests) during the turn.
            npc_responses = await asyncio.to_thread(
                get_npc_responses,
                campaign_id=prep.state.campaign_id,
                dm_narration=narration,
                action_text=action_input.description,
                action_type=action_input.action_type,
                enemies=action_input.enemies,
                recent_talks=recent_talks,
            )
            for npc in npc_responses:
                npc_log = EventLog(
                    event_type="npc_dialogue",
                    entity_type="turn",
                    entity_id=turn_id,
                    data=json.dumps(npc),
                    agent_id="npc_agent",
                )
                db.add(npc_log)
    except Exception:  # noqa: BLE001
        logger.warning("NPC agent failed for turn %s", turn_id, exc_info=True)

    # Surface the finished turn to the player now. Memory extraction is a third
    # LLM call needed only for future-turn context, so run it afterwards instead
    # of making the player wait on it before the result appears.
    yield _sse({"type": "done", "narration": narration, "npc_responses": npc_responses})

    try:
        await extract_and_store(
            session_id=action_input.session_id,
            campaign_id=prep.state.campaign_id,
            action_text=action_input.description,
            narration=narration,
            db=db,
        )
    except Exception:  # noqa: BLE001
        logger.warning("Memory extraction failed for turn %s", turn_id, exc_info=True)

async def _session_has_engine_world(session_id: str, db: AsyncSession) -> bool:
    """Return whether this session is backed by the M11 event-sourced engine."""
    return await engine_glue.load_session_engine(db, session_id) is not None


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
    """Run one human action, using M11 engine sessions and legacy sessions."""
    if not await _session_has_engine_world(action_input.session_id, db):
        return await _legacy_process_action(action_input, db)
    return await engine_glue.resolve_human_action(action_input, db)


async def process_action_stream(
    action_input: ActionInput,
    db: AsyncSession,
) -> AsyncGenerator[str, None]:
    """Run one human action and stream SSE chunks: result -> token -> done."""
    if not await _session_has_engine_world(action_input.session_id, db):
        async for chunk in _legacy_process_action_stream(action_input, db):
            yield chunk
        return
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
