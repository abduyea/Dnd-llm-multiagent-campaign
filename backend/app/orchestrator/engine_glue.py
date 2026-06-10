"""
M11 Stage-1 DB glue — wires the team's async backend to our event-sourced
engine via the pure adapter (`m11_adapter`).

Responsibilities (the DB-coupled half of the seam):
  - put the vendored engine on sys.path and import the pure adapter
  - hold a per-session `EngineHandle` (in-process cache, rebuildable from the
    `session_events` table — "resume = replay")
  - persist the engine log to `session_events`, sync projected HP into the
    `characters` rows and write a `Turn` row (both are derived caches the
    unchanged frontend reads — never independent writers of truth)
  - implement `start_session`, `process_action`, `process_action_stream` on
    top of the adapter

Engine-authoritative: the per-session event log is the only source of game
truth. The DB rows it writes are a cache; if they disagree, the log wins.
"""
from __future__ import annotations

import asyncio
import json
import logging
import random
import sys
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# --- put our engine on sys.path. Two supported layouts, auto-detected:
#   * SHIPPED: the engine is vendored into the repo at <repo_root>/V2 (stage 6).
#   * DEV:     the engine lives one dir above the repo (the working checkout),
#              and <repo_root>/V2 is the team's stale snapshot.
# Sentinel = V2/m11_adapter.py: present only in the vendored (shipped) engine,
# absent from the stale dev V2 — so dev keeps using the parent checkout and the
# shipped repo uses its own V2, from the same file. ---
_VENDORED_ENGINE = Path(__file__).resolve().parents[3] / "V2"
_DEV_ENGINE_ROOT = Path(__file__).resolve().parents[4]
_ENGINE_ROOT = (
    _VENDORED_ENGINE
    if (_VENDORED_ENGINE / "m11_adapter.py").exists()
    else _DEV_ENGINE_ROOT
)
if str(_ENGINE_ROOT) not in sys.path:
    sys.path.insert(0, str(_ENGINE_ROOT))

import config  # noqa: E402
import m11_adapter as adapter  # noqa: E402
import scheduler  # noqa: E402
from m2_inspect import MeasurementSink  # noqa: E402
from projection import project  # noqa: E402
from runner import run_npc_turn, run_turn  # noqa: E402
from summarizer import GlobalSummaryFilter, maybe_summarize  # noqa: E402
from view_builder import build_view  # noqa: E402

from backend.app.db.models import (  # noqa: E402
    Campaign,
    Character,
    Session,
    SessionEvent,
    Turn,
)
from backend.app.db.models import EventLog as AuditEventLog  # noqa: E402

logger = logging.getLogger(__name__)

# Per-session developer logs (fallback traces + per-LLM-call telemetry) live
# alongside the team app's DB, one directory per session. The canonical game
# record is still the `session_events` table (replayable); these are the
# dev-facing "what did the models do / where did one fall back" logs that the
# offline demos write to their run dir — restored for the web path so a session
# can be inspected after the fact.
_SESSION_LOG_ROOT = Path(__file__).resolve().parents[3] / "data" / "session_logs"


# ---------------------------------------------------------------------------
# Per-session engine handle + in-process cache
# ---------------------------------------------------------------------------


@dataclass
class EngineHandle:
    session_id: str
    log: Any  # eventlog.EventLog
    id_map: dict[str, str]  # character_id -> engine entity_id
    entity_to_char: dict[str, str]  # engine entity_id -> character_id
    dm: Any
    rng: random.Random
    # PC entity ids controlled by a human. A PC NOT in this set is AI-driven
    # (the advance loop plays it with a PlayerAgent). All-human = stage 3
    # default; emptying it = all-AI spectator/auto-play.
    human_seats: set[str] = field(default_factory=set)
    # Lazily-built PlayerAgents for AI seats, keyed by entity id.
    player_agents: dict[str, Any] = field(default_factory=dict)
    # Party goals (for AI player prompts); loaded from the bound dungeon.
    goals: list = field(default_factory=list)
    # Global summarizer: collapses old narrative beats into a SummaryCreated
    # when a PC's prompt grows over budget, so long sessions don't bloat the
    # prompt (which was causing narration truncation). None until built.
    summary_provider: Any = None
    # Per-session developer logs (None until set up). debug_log_path collects
    # exhausted-retry / fallback traces; measurements collects one record per
    # LLM call (latency, parse status, raw completion).
    log_dir: Any = None
    debug_log_path: Any = None
    measurements: Any = None


# Rebuildable from session_events, so this is purely a hot cache.
_HANDLES: dict[str, EngineHandle] = {}


def _session_logging(session_id: str) -> tuple[Path, Path, MeasurementSink]:
    """Create (or reuse) this session's developer-log directory and return
    ``(log_dir, debug_log_path, measurements)``. Best-effort: if the directory
    can't be made we log a warning and fall back to no file logging."""
    log_dir = _SESSION_LOG_ROOT / session_id
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir, log_dir / config.DEBUG_LOG_FILENAME, MeasurementSink(
        log_dir / "measurements.json"
    )


def _attach_logging(handle: EngineHandle) -> EngineHandle:
    """Best-effort: give a handle its per-session dev logs."""
    try:
        handle.log_dir, handle.debug_log_path, handle.measurements = _session_logging(
            handle.session_id
        )
    except Exception:  # noqa: BLE001
        logger.warning("Could not set up session logs for %s", handle.session_id,
                       exc_info=True)
    return handle


def _dump_measurements(handle: EngineHandle) -> None:
    """Flush the in-memory measurement records to disk (best-effort)."""
    if handle.measurements is None:
        return
    try:
        handle.measurements.dump()
    except Exception:  # noqa: BLE001
        logger.warning("Could not write measurements for %s", handle.session_id,
                       exc_info=True)


async def _summarize_before_turn(
    db: AsyncSession, session_id: str, handle: EngineHandle, actor_engine_id: str
) -> None:
    """Cap the prompt before a PC turn. If the actor is a PC whose prompt has
    grown over budget, the global summarizer collapses old narrative beats into
    a `SummaryCreated` (the view builder then renders from the summary instead of
    the raw history) — this is what keeps long web sessions from bloating the
    prompt and truncating narration. No-op for NPC turns (small prompts) and when
    under budget. The new summary is persisted so resume/replay includes it.

    Runs the (blocking) summary LLM call in a thread, like the turn itself.
    Best-effort: a summarizer failure must not abort the turn."""
    if handle.summary_provider is None:
        return
    pc_ids = set(handle.id_map.values())
    seq_before = len(handle.log)
    try:
        appended = await asyncio.to_thread(
            maybe_summarize, handle.log, actor_engine_id, pc_ids,
            handle.summary_provider,
        )
    except Exception:  # noqa: BLE001
        logger.warning("session %s: summarizer failed (continuing)", session_id,
                       exc_info=True)
        return
    if appended:
        await _persist_events(db, session_id, handle.log, seq_before)
        logger.info("session %s: summarized old beats (prompt was over budget)",
                    session_id)


def _make_dm() -> Any:
    """DM factory. Overridden in tests to avoid real LLM calls."""
    from dm import DMAgent

    return DMAgent()


def _make_summary_provider() -> Any:
    """Summary-provider factory. Overridden in tests. Constructing it is cheap
    (no LLM call until `summarize` runs)."""
    return GlobalSummaryFilter()


def _inverse(id_map: dict[str, str]) -> dict[str, str]:
    return {v: k for k, v in id_map.items()}


def _goals_for(campaign_name: str | None) -> list:
    """Party goals for AI player prompts, loaded from the bound dungeon."""
    dungeon = adapter.dungeon_path_for_campaign(campaign_name)
    if dungeon is None:
        return []
    try:
        from goals import read_party_goals

        return read_party_goals(dungeon)
    except Exception:  # noqa: BLE001
        return []


def _get_player_agent(handle: EngineHandle, entity_id: str, state: Any) -> Any:
    """Lazily build (and cache) a PlayerAgent for an AI-controlled PC seat,
    voiced by that PC's persona + the party goals."""
    agent = handle.player_agents.get(entity_id)
    if agent is not None:
        return agent
    from llm import DEFAULT_MODEL
    from player import PlayerAgent

    ent = state.entities.get(entity_id)
    persona = ent.attributes.get("persona", "") if ent is not None else ""
    name = ent.display_name if ent is not None else entity_id
    role = (
        f"You are {name}. {persona} You and your party are exploring a "
        f"dungeon. Speak and act in character."
    )
    agent = PlayerAgent(
        player_id=entity_id, role_description=role,
        model=DEFAULT_MODEL, goals=handle.goals,
    )
    handle.player_agents[entity_id] = agent
    return agent


def _objective_complete(handle: EngineHandle) -> bool:
    """True once EVERY party goal is (forward-latched) complete — the adventure
    is won. Used to auto-stop the all-AI advance loop so it stops generating
    aimless turns after the objective is met. Note: a goal list with a gated
    terminal goal can make `select_active_goal` return None before completion,
    so we check the completed set directly, not the active goal."""
    if not handle.goals:
        return False
    from goals import completed_goal_ids

    state = project(handle.log.events())
    return len(completed_goal_ids(handle.goals, state)) == len(handle.goals)


def _combat_state(handle: EngineHandle) -> dict[str, Any]:
    """Engine-backed combat read-out (enemy HP + initiative + round) for the
    frontend's encounter/initiative panels — replaces the old client-side
    tracker so combat reflects engine truth on every turn."""
    return adapter.build_combat_state(
        handle.log.events(), list(handle.id_map.values()), handle.entity_to_char
    )


def _seat_config(handle: EngineHandle, state: Any) -> list[dict[str, Any]]:
    """Per-PC controller assignment for the frontend toggles."""
    out: list[dict[str, Any]] = []
    for char_id, entity_id in handle.id_map.items():
        ent = state.entities.get(entity_id)
        out.append({
            "character_id": char_id,
            "name": ent.display_name if ent is not None else char_id,
            "controller": "human" if entity_id in handle.human_seats else "ai",
        })
    return out


async def _campaign_characters(db: AsyncSession, campaign_id: str) -> list[Character]:
    result = await db.execute(
        select(Character).where(Character.campaign_id == campaign_id)
    )
    return list(result.scalars().all())


async def _id_map_for(db: AsyncSession, campaign_id: str, log: Any) -> dict[str, str]:
    """Recompute character_id -> entity_id from the campaign roster + the
    log's projected pc entities (so resume needs no stored mapping)."""
    chars = await _campaign_characters(db, campaign_id)
    state = project(log.events())
    seed_like = {
        "entities": [
            {"id": e.entity_id, "kind": e.kind} for e in state.entities.values()
        ]
    }
    return adapter.map_characters_to_pcs(
        [(c.id, c.character_name) for c in chars], seed_like
    )


# ---------------------------------------------------------------------------
# Persistence (the session_events table is the save file)
# ---------------------------------------------------------------------------


async def _persist_events(
    db: AsyncSession, session_id: str, log: Any, since_seq: int
) -> None:
    for seq, kind, event_json in adapter.serialize_new_events(log, since_seq):
        db.add(
            SessionEvent(
                session_id=session_id, seq=seq, kind=kind, event_json=event_json
            )
        )
    await db.flush()


async def _load_event_jsons(db: AsyncSession, session_id: str) -> list[str]:
    result = await db.execute(
        select(SessionEvent)
        .where(SessionEvent.session_id == session_id)
        .order_by(SessionEvent.seq)
    )
    return [row.event_json for row in result.scalars().all()]


async def _sync_hp(db: AsyncSession, log: Any, id_map: dict[str, str]) -> None:
    """Write each roster PC's projected HP into its characters row (cache)."""
    state = project(log.events())
    for char_id, entity_id in id_map.items():
        ent = state.entities.get(entity_id)
        if ent is None:
            continue
        hp = ent.attributes.get("hp")
        if isinstance(hp, (int, float)) and not isinstance(hp, bool):
            ch = await db.get(Character, char_id)
            if ch is not None:
                ch.hp_current = int(hp)


# ---------------------------------------------------------------------------
# Engine handle loading (new at start, replayed on resume)
# ---------------------------------------------------------------------------


async def load_session_engine(
    db: AsyncSession, session_id: str
) -> EngineHandle | None:
    """Return the session's engine handle, rebuilding it from session_events
    if it isn't cached. None if the session has no engine (e.g. a campaign
    with no bound dungeon)."""
    cached = _HANDLES.get(session_id)
    if cached is not None:
        return cached

    event_jsons = await _load_event_jsons(db, session_id)
    if not event_jsons:
        return None

    log = adapter.eventlog_from_serialized(event_jsons)
    session = (
        await db.execute(select(Session).where(Session.id == session_id))
    ).scalar_one_or_none()
    if session is None:
        return None
    id_map = await _id_map_for(db, session.campaign_id, log)
    campaign = (
        await db.execute(select(Campaign).where(Campaign.id == session.campaign_id))
    ).scalar_one_or_none()
    handle = EngineHandle(
        session_id=session_id,
        log=log,
        id_map=id_map,
        entity_to_char=_inverse(id_map),
        dm=_make_dm(),
        rng=random.Random(),  # noqa: S311 - game simulation RNG, not security-sensitive
        human_seats=set(id_map.values()),
        goals=_goals_for(campaign.name if campaign is not None else None),
        summary_provider=_make_summary_provider(),
    )
    _attach_logging(handle)
    _HANDLES[session_id] = handle
    return handle


# ---------------------------------------------------------------------------
# start_session
# ---------------------------------------------------------------------------


async def start_session_impl(
    campaign_id: str, name: str, db: AsyncSession
) -> dict[str, Any]:
    """Create the session, and — for the demo campaign — assemble the engine
    seed, persist it, and cache the handle. Non-demo campaigns get a session
    with no engine (stage 1 supports the demo campaign only); actions on them
    return a clean error."""
    session_id = str(uuid.uuid4())
    started_at = datetime.now(UTC).isoformat()
    db.add(
        Session(
            id=session_id,
            campaign_id=campaign_id,
            name=name,
            status="active",
            turn_count=0,
            started_at=started_at,
        )
    )
    db.add(
        AuditEventLog(
            event_type="session_start",
            entity_type="session",
            entity_id=session_id,
            data=json.dumps({"campaign_id": campaign_id, "name": name}),
            agent_id="orchestrator",
        )
    )

    campaign = (
        await db.execute(select(Campaign).where(Campaign.id == campaign_id))
    ).scalar_one_or_none()
    dungeon = adapter.dungeon_path_for_campaign(
        campaign.name if campaign is not None else None
    )

    if dungeon is not None:
        seed = adapter.load_seed_dict(dungeon)
        log = adapter.fresh_log_from_seed(seed)
        id_map = adapter.map_characters_to_pcs(
            [(c.id, c.character_name) for c in await _campaign_characters(db, campaign_id)],
            seed,
        )
        await _persist_events(db, session_id, log, 0)
        await _sync_hp(db, log, id_map)
        handle = EngineHandle(
            session_id=session_id,
            log=log,
            id_map=id_map,
            entity_to_char=_inverse(id_map),
            dm=_make_dm(),
            rng=random.Random(),  # noqa: S311 - game simulation RNG, not security-sensitive
            human_seats=set(id_map.values()),
            goals=_goals_for(campaign.name if campaign is not None else None),
            summary_provider=_make_summary_provider(),
        )
        _attach_logging(handle)
        _HANDLES[session_id] = handle
        logger.info("session %s engine ready; dev logs → %s",
                    session_id, handle.log_dir)
    else:
        logger.warning(
            "Campaign %s has no bound dungeon; session %s created without an "
            "engine world (stage 1 supports the demo campaign only).",
            campaign_id,
            session_id,
        )

    await db.flush()
    return {
        "id": session_id,
        "campaign_id": campaign_id,
        "name": name,
        "status": "active",
        "started_at": started_at,
        "turn_count": 0,
        "status_code": 201,
    }


# ---------------------------------------------------------------------------
# process_action (shared core for stream + non-stream)
# ---------------------------------------------------------------------------


async def resolve_human_action(
    action_input: Any, db: AsyncSession
) -> dict[str, Any]:
    """Run one human action through the engine and return the frontend's
    response dict (or an ``{"error", "status"}`` dict on any rejection)."""
    session = (
        await db.execute(
            select(Session).where(Session.id == action_input.session_id)
        )
    ).scalar_one_or_none()
    if session is None:
        return {"error": "Session not found", "status": 404}
    if session.status == "completed":
        return {"error": "Session has already ended", "status": 409}

    handle = await load_session_engine(db, action_input.session_id)
    if handle is None:
        return {
            "error": "This session has no engine world "
            "(stage 1 supports the demo campaign only).",
            "status": 422,
        }

    actor_engine = handle.id_map.get(action_input.character_id)
    if actor_engine is None:
        return {
            "error": f"character {action_input.character_id!r} is not in this "
            "session's party",
            "status": 400,
        }
    target_engine: str | None = None
    if action_input.target_id:
        # frontend target ids are character ids for PCs; fall through to a raw
        # engine id otherwise (validated in-scene by the translator).
        target_engine = handle.id_map.get(
            action_input.target_id, action_input.target_id
        )

    state = project(handle.log.events())
    try:
        turn_result = adapter.human_submission_to_turn(
            action_input.action_type,
            action_input.description,
            actor_engine,
            target_engine,
            state,
            stat=getattr(action_input, "stat", None),
            purpose=getattr(action_input, "purpose", None),
        )
    except adapter.TranslationError as e:
        return {"error": e.message, "status": e.status}

    location_id = state.entities[actor_engine].location_id
    # Cap the prompt before the DM narrates this turn (the narration prompt grows
    # with history too; summarizing keeps it from truncating on long sessions).
    await _summarize_before_turn(
        db, action_input.session_id, handle, actor_engine
    )
    seq_before, seq_after = await asyncio.to_thread(
        adapter.run_human_turn,
        handle.log,
        actor_engine,
        location_id,
        turn_result,
        handle.dm,
        handle.rng,
        handle.measurements,
        handle.debug_log_path,
    )
    _dump_measurements(handle)

    # Persist the committed slice + sync the caches the UI reads.
    await _persist_events(db, action_input.session_id, handle.log, seq_before)
    await _sync_hp(db, handle.log, handle.id_map)
    session.turn_count = (session.turn_count or 0) + 1
    logger.info("session %s turn %s: %s [%s] (human)", action_input.session_id,
                session.turn_count, action_input.character_id,
                action_input.action_type)

    response = adapter.events_to_response(
        handle.log,
        seq_before,
        seq_after,
        handle.entity_to_char,
        {
            "turn_number": session.turn_count,
            "character_id": action_input.character_id,
            "action_type": action_input.action_type,
            "description": action_input.description,
        },
    )

    db.add(
        Turn(
            session_id=action_input.session_id,
            character_id=action_input.character_id,
            turn_number=session.turn_count,
            action_type=action_input.action_type,
            action_text=action_input.description,
            dice_results=json.dumps(response["dice_results"]),
            attack_result=(
                json.dumps(response["attack_result"])
                if response["attack_result"]
                else None
            ),
            narration=response["narration"],
        )
    )
    await db.flush()
    # Whose turn is next — tells the frontend whether to wait for a human or
    # drive engine turns (enemy/NPC reactions) via /advance.
    response["next_turn"] = _next_turn_info(handle)
    response["combat"] = _combat_state(handle)
    # Skill-check outcome (roll vs DC, pass/fail) for the UI's result chip.
    # Parsed from the committed events, so the same call serves the AI path.
    response["check_result"] = adapter.extract_check_result(
        handle.log, seq_before, seq_after
    )
    # Did this human action complete the adventure? (Surfaces the victory banner
    # the same way the all-AI loop's stop does.)
    response["objective_complete"] = _objective_complete(handle)
    return response


async def get_scene(
    db: AsyncSession, session_id: str, character_id: str
) -> dict[str, Any]:
    """Structured scene read-out for a character: current location, connected
    exits (move options), and entities present (attack/talk targets). Drives
    the frontend's location badge + exit picker (replacing free-text)."""
    handle = await load_session_engine(db, session_id)
    if handle is None:
        return {
            "error": "This session has no engine world "
            "(stage 1 supports the demo campaign only).",
            "status": 422,
        }
    entity_id = handle.id_map.get(character_id)
    if entity_id is None:
        return {
            "error": f"character {character_id!r} is not in this session's party",
            "status": 400,
        }
    state = project(handle.log.events())
    scene = adapter.build_scene(state, entity_id)
    # Map engine ids back to frontend ids: the scene's character + any PC
    # targets become character ids (so the frontend submits them as target_id
    # and the glue maps them back). NPC ids pass through unchanged.
    scene["character_id"] = character_id
    for ent in scene["entities_here"]:
        ent["id"] = handle.entity_to_char.get(ent["id"], ent["id"])
    # Map any PC-entity check targets back to character ids too (NPC/item/
    # location ids pass through unchanged).
    for ct in scene.get("check_targets", []):
        ct["id"] = handle.entity_to_char.get(ct["id"], ct["id"])
    # Stage 3.5: whose turn is next + the per-seat controller config (so the
    # frontend can render AI/Human toggles and bootstrap auto-advance).
    scene["next_turn"] = _next_turn_info(handle)
    scene["seats"] = _seat_config(handle, state)
    # Engine-backed combat read-out (enemy HP / initiative / round).
    scene["combat"] = _combat_state(handle)
    return scene


async def set_seats(
    db: AsyncSession, session_id: str, assignments: dict[str, str]
) -> dict[str, Any]:
    """Set per-seat controllers. ``assignments`` maps character_id ->
    "ai"|"human". Returns the updated seat config + whose turn is next."""
    handle = await load_session_engine(db, session_id)
    if handle is None:
        return {"error": "This session has no engine world.", "status": 422}
    for char_id, controller in (assignments or {}).items():
        entity_id = handle.id_map.get(char_id)
        if entity_id is None:
            continue
        if controller == "human":
            handle.human_seats.add(entity_id)
        elif controller == "ai":
            handle.human_seats.discard(entity_id)
    state = project(handle.log.events())
    return {
        "seats": _seat_config(handle, state),
        "next_turn": _next_turn_info(handle),
    }


# ---------------------------------------------------------------------------
# Turn scheduling — whose turn is next, and running engine-driven turns
# ---------------------------------------------------------------------------


def _next_turn_info(handle: EngineHandle) -> dict[str, Any]:
    """Who acts next, per the engine scheduler. ``is_human`` is True when the
    next actor is a human-controlled PC seat (the frontend should wait for
    input); False for an NPC or an AI-controlled PC seat (the advance loop
    runs it). ``mode`` is exploration|combat."""
    events = handle.log.events()
    pc_order = list(handle.id_map.values())
    actor = scheduler.next_actor(events, pc_order)
    mode = scheduler.current_mode(events)
    if actor is None:
        return {"actor_id": None, "engine_id": None, "is_human": True,
                "kind": None, "mode": mode, "actor_name": None}
    is_pc = actor in handle.entity_to_char
    is_human = is_pc and actor in handle.human_seats
    ent = project(events).entities.get(actor)
    return {
        "actor_id": handle.entity_to_char.get(actor, actor),
        "engine_id": actor,
        "is_human": is_human,
        "kind": "pc" if is_pc else "npc",
        "mode": mode,
        # Display name of whoever acts next — lets the UI say "X is composing…".
        "actor_name": ent.display_name if ent is not None else actor,
    }


async def advance_one_turn(db: AsyncSession, session_id: str) -> dict[str, Any]:
    """Run the single next engine-driven turn (an NPC, or later an AI PC seat),
    if it's not a human's turn. Returns ``{ran, turn?, next_turn}`` — ``ran`` is
    False when the next actor is a human (or nobody is left to act)."""
    handle = await load_session_engine(db, session_id)
    if handle is None:
        return {"error": "This session has no engine world.", "status": 422}

    # A completed session must not advance — the all-AI loop would otherwise
    # keep producing engine turns after the player hit "End Session" (the log
    # is closed; advancing it would mutate a finished save). `ended` tells the
    # frontend to stop its auto-advance loop.
    session = (
        await db.execute(select(Session).where(Session.id == session_id))
    ).scalar_one_or_none()
    if session is not None and session.status == "completed":
        return {"ran": False, "ended": True, "next_turn": _next_turn_info(handle)}

    # Objective met → stop the all-AI loop instead of padding the run with
    # aimless wandering. The completing turn itself still ran on the prior
    # advance; this is the first call after, so we halt cleanly.
    if _objective_complete(handle):
        return {"ran": False, "objective_complete": True,
                "next_turn": _next_turn_info(handle)}

    info = _next_turn_info(handle)
    if info["engine_id"] is None or info["is_human"]:
        return {"ran": False, "next_turn": info}

    actor = info["engine_id"]
    state = project(handle.log.events())
    ent = state.entities.get(actor)
    if ent is None:
        return {"ran": False, "next_turn": info}
    loc = ent.location_id

    # Cap the prompt before an AI PC plans (no-op for NPCs / under budget).
    await _summarize_before_turn(db, session_id, handle, actor)

    seq_before = len(handle.log)
    if info["kind"] == "npc":
        tr = await asyncio.to_thread(
            run_npc_turn, handle.log, actor, loc, handle.dm, handle.rng,
            handle.measurements, debug_log_path=handle.debug_log_path,
        )
        turn_char_id = None  # NPC: not a roster character
        action_label = "npc_turn"
    else:
        # AI-controlled PC seat: the engine plays the hero via a PlayerAgent
        # (the same agent that drives our autonomous demos).
        agent = _get_player_agent(handle, actor, state)

        def _run_ai_pc() -> Any:
            view = build_view(handle.log.events(), actor)
            st = project(handle.log.events())
            turn_result = agent.act(view, st)
            return run_turn(
                handle.log, actor, loc, turn_result, handle.dm, handle.rng,
                handle.measurements, debug_log_path=handle.debug_log_path,
            )

        tr = await asyncio.to_thread(_run_ai_pc)
        turn_char_id = info["actor_id"]  # a real roster character id
        action_label = "ai_turn"

    _dump_measurements(handle)
    if tr is not None and not tr.succeeded:
        logger.info("session %s: %s engine turn FELL BACK (%s beat) — see %s",
                    session_id, info["actor_id"], tr.fallback_beat,
                    handle.debug_log_path)

    await _persist_events(db, session_id, handle.log, seq_before)
    await _sync_hp(db, handle.log, handle.id_map)

    # `session` was loaded above for the completed-status guard.
    turn_no = ((session.turn_count or 0) + 1) if session is not None else 0
    if session is not None:
        session.turn_count = turn_no

    response = adapter.events_to_response(
        handle.log, seq_before, len(handle.log), handle.entity_to_char,
        {"turn_number": turn_no, "character_id": info["actor_id"],
         "action_type": action_label, "description": ""},
    )
    # Attribute the engine turn to its actor so the UI can surface "who" —
    # an NPC's dialogue/beat or an AI hero's turn, not anonymous narration.
    response["actor_name"] = ent.display_name
    response["actor_kind"] = info["kind"]  # "npc" | "pc"
    # Hostile flag so the UI can tint a hostile actor's beat red (vs gold for a
    # friendly NPC, blue for an AI hero).
    response["actor_hostile"] = ent.attributes.get("status") == "hostile"
    response["combat"] = _combat_state(handle)
    # An AI hero (or NPC) may make a skill check too — surface its verdict the
    # same way the human path does, so the chip isn't human-only.
    response["check_result"] = adapter.extract_check_result(
        handle.log, seq_before, len(handle.log)
    )
    # Did this engine turn complete the adventure? (Surface the win on the
    # completing turn itself, not just on the next advance's idle.)
    response["objective_complete"] = _objective_complete(handle)
    logger.info("session %s turn %s: %s acted [%s] — %.80s",
                session_id, turn_no, ent.display_name, action_label,
                (response.get("narration") or "").replace("\n", " "))
    db.add(
        Turn(
            session_id=session_id, character_id=turn_char_id, turn_number=turn_no,
            action_type=action_label, action_text=str(info["actor_id"]),
            dice_results=json.dumps(response["dice_results"]),
            attack_result=(json.dumps(response["attack_result"])
                           if response["attack_result"] else None),
            narration=response["narration"],
        )
    )
    await db.flush()
    return {"ran": True, "turn": response, "next_turn": _next_turn_info(handle)}


async def advance_stream_impl(session_id: str, db: AsyncSession):
    """SSE for one engine-driven turn: result → token → done (with next_turn),
    or an ``idle`` event when it's a human's turn / nobody is left."""

    def _sse(data: dict[str, Any]) -> str:
        return f"data: {json.dumps(data)}\n\n"

    result = await advance_one_turn(db, session_id)
    if "error" in result:
        yield _sse({"type": "error", "message": result["error"],
                    "status": result.get("status", 400)})
        return
    if not result["ran"]:
        yield _sse({"type": "idle", "ended": result.get("ended", False),
                    "objective_complete": result.get("objective_complete", False),
                    "next_turn": result["next_turn"]})
        return

    turn = result["turn"]
    yield _sse({
        "type": "result",
        "turn_number": turn["turn_number"],
        "character_id": turn["character_id"],
        "actor_name": turn.get("actor_name"),
        "actor_kind": turn.get("actor_kind"),
        "actor_hostile": turn.get("actor_hostile", False),
        # The AI hero's own in-character prose for this turn (empty for NPCs,
        # whose voice rides the DM narration). Surfaced so an AI PC's turn shows
        # what the hero "said/did" at the table, not just the DM's outcome.
        "actor_prose": turn.get("actor_prose", ""),
        "action_type": turn["action_type"],
        "description": turn["description"],
        "dice_results": turn["dice_results"],
        "attack_result": turn["attack_result"],
        "check_result": turn.get("check_result"),
        "state_changes": turn["state_changes"],
        "errors": turn["errors"],
    })
    yield _sse({"type": "token", "text": turn["narration"]})
    yield _sse({"type": "done", "narration": turn["narration"],
                "npc_responses": [], "next_turn": result["next_turn"],
                "combat": turn.get("combat"),
                "objective_complete": turn.get("objective_complete", False)})


async def process_action_stream_impl(action_input: Any, db: AsyncSession):
    """SSE wrapper: resolve the turn, then emit result → token → done.

    Stage 1 emits the whole narration as a single token (no token-by-token
    streaming yet — that is stage 5); the envelope the frontend expects is
    preserved."""

    def _sse(data: dict[str, Any]) -> str:
        return f"data: {json.dumps(data)}\n\n"

    response = await resolve_human_action(action_input, db)
    if "error" in response:
        yield _sse(
            {
                "type": "error",
                "message": response["error"],
                "status": response.get("status", 400),
            }
        )
        return

    yield _sse(
        {
            "type": "result",
            "turn_number": response["turn_number"],
            "character_id": response["character_id"],
            "action_type": response["action_type"],
            "description": response["description"],
            "dice_results": response["dice_results"],
            "attack_result": response["attack_result"],
            "check_result": response.get("check_result"),
            "state_changes": response["state_changes"],
            "errors": response["errors"],
        }
    )
    yield _sse({"type": "token", "text": response["narration"]})
    yield _sse(
        {
            "type": "done",
            "narration": response["narration"],
            "npc_responses": response["npc_responses"],
            "next_turn": response.get("next_turn"),
            "combat": response.get("combat"),
            "objective_complete": response.get("objective_complete", False),
        }
    )
