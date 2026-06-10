"""
M11 Stage-1 engine adapter — the pure, DB-free half of the seam.

This module is the translation layer between the team's web app and our
event-sourced engine, holding ONLY logic that depends on our engine (no
SQLAlchemy, no async, no team models). The DB-coupled glue (the
``session_events`` table, HP/Turn cache sync, rebuild-from-table) lives in
the team backend's orchestrator and calls into the helpers here.

Stage-1 scope (see ``m11_stage1_build_brief.md``):
  - assemble a session seed for the demo campaign from ``demo_dungeon_m95.json``
  - translate one human action (attack / talk) into a validated
    ``PlayerTurnResult`` — the **Human controller** (the 2nd producer of that
    struct; ``PlayerAgent.act`` is the 1st). No LLM call.
  - run one turn through our runner and project the new events into the
    frontend's existing response shape.

Vendoring note: for stage 1 this imports our engine by bare module name
(``runner``, ``scheduler``, ...). The team orchestrator puts the engine root
on ``sys.path`` before importing this module. Proper packaging is stage 6.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Iterable

import config
import scheduler
from eventlog import EventLog
from llm import ChatResult
from models import DiceRolled, DMNarration, Event, PlayerAction
from player import PlayerTurnResult
from projection import project
from ruleset import get_action_economy
from runner import _derive_dc, run_turn
from seed import load_seed
from tags import AttackIntent, CheckIntent, MoveIntent, PuzzleAnswerIntent, TalkIntent
from view_builder import strip_demo_annotations

# ---------------------------------------------------------------------------
# Stage-1 constants
# ---------------------------------------------------------------------------

HERE = Path(__file__).resolve().parent
DEMO_CAMPAIGN_NAME = "The Sunken Vault"
DEMO_DUNGEON = HERE / "demo_dungeon_m95.json"
RULESET = "dnd5e_lite"

# Action types the Human controller can translate. attack/talk (stage 1),
# movement (stage 2), roleplay (stage 2b), skill_check (1d20+stat vs a derived
# DC), and puzzle_answer (speak the answer to a room/item puzzle — the human
# counterpart of the AI's PuzzleAnswerIntent; needed so a human seat can clear a
# hard-gated threshold). Still unsupported → clean 422: cast_spell (M12 spell
# mechanics), use_item, etc.
SUPPORTED_ACTIONS = frozenset(
    {"roleplay", "attack_melee", "attack_ranged", "talk", "movement", "move",
     "skill_check", "puzzle_answer"}
)

# Ability modifiers a skill check may roll. Guards against a bad `stat` from the
# request resolving to 0 silently (resolve_check defaults a missing attr to 0).
SKILL_CHECK_STATS = frozenset(
    {"str_mod", "dex_mod", "con_mod", "int_mod", "wis_mod", "cha_mod"}
)

# DC kinds that are NOT pure ability checks — they belong to other verbs
# (lock/force a container is open/use_item, not a free-standing skill_check), so
# they are excluded from the scene's offered check targets.
_NON_CHECK_DC_PURPOSES = frozenset({"lock", "force"})

# Demo PC mapping: a campaign character's FIRST name → the dungeon's authored
# pc entity id. First-name keyed so it survives the "Ironjaw"/"Ironhide"
# surname mismatch between the team demo and our seed.
DEMO_PC_ALIASES: dict[str, str] = {
    "brakka": "ent_pc_brakka",
    "sylvi": "ent_pc_sylvi",
}


class TranslationError(Exception):
    """A human submission that can't be turned into a legal engine turn.
    Carries an HTTP-ish ``status`` so the orchestrator can surface it in the
    response shape the frontend already understands."""

    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = message


# ---------------------------------------------------------------------------
# Seed assembly (demo path)
# ---------------------------------------------------------------------------


def dungeon_path_for_campaign(campaign_name: str | None) -> Path | None:
    """Stage-1 dungeon binding: the demo campaign (by name) → the demo
    dungeon. Any other campaign → None (not playable yet)."""
    if (campaign_name or "").strip().lower() == DEMO_CAMPAIGN_NAME.lower():
        return DEMO_DUNGEON
    return None


def load_seed_dict(path: Path | str) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def fresh_log_from_seed(seed: dict[str, Any]) -> EventLog:
    """A new in-memory event log seeded with ``seed_init`` events. The strict
    loader validates ids / referential integrity / attribute schema and
    refuses to start on any error."""
    log = EventLog()  # in-memory; the orchestrator persists to the DB
    load_seed(seed, log)
    return log


def map_characters_to_pcs(
    characters: Iterable[tuple[str, str]],
    seed: dict[str, Any],
) -> dict[str, str]:
    """Map campaign characters onto the dungeon's authored pc entities.

    ``characters`` is an iterable of ``(character_id, character_name)``.
    Returns ``{character_id: engine_entity_id}`` for the ones that match a
    known demo PC. Unmatched characters are dropped (stage 1 plays the two
    authored demo PCs only).
    """
    pc_ids = {
        e["id"] for e in seed.get("entities", []) if e.get("kind") == "pc"
    }
    id_map: dict[str, str] = {}
    for char_id, char_name in characters:
        tokens = (char_name or "").strip().split()
        first = tokens[0].lower() if tokens else ""
        entity_id = DEMO_PC_ALIASES.get(first)
        if entity_id is not None and entity_id in pc_ids:
            id_map[char_id] = entity_id
    return id_map


# ---------------------------------------------------------------------------
# Per-session log (de)serialization — used by the DB glue
# ---------------------------------------------------------------------------


def serialize_new_events(log: EventLog, since_seq: int) -> list[tuple[int, str, str]]:
    """Serialize events appended at/after ``since_seq`` for DB persistence.
    Returns ``[(seq, kind, event_json), ...]`` in seq order."""
    return [
        (ev.seq, ev.type, ev.model_dump_json())
        for ev in log.events()[since_seq:]
    ]


def eventlog_from_serialized(event_jsons: Iterable[str]) -> EventLog:
    """Rebuild an in-memory event log from stored ``Event`` JSON rows (in seq
    order). This is how "resume a session" works — replay the rows."""
    log = EventLog()  # in-memory
    events: list[Event] = []
    for i, raw in enumerate(event_jsons):
        ev = Event.model_validate_json(raw)
        if ev.seq != i:
            raise ValueError(
                f"event seq {ev.seq} out of order at index {i} (expected {i})"
            )
        events.append(ev)
    log._events = events  # faithful rebuild (same as EventLog.load does)
    return log


# ---------------------------------------------------------------------------
# The Human controller — submission → PlayerTurnResult (no LLM call)
# ---------------------------------------------------------------------------


def _human_chat_stub() -> ChatResult:
    """A human turn makes no LLM call; PlayerTurnResult.chat still wants a
    ChatResult. A zero-cost stub keeps the engine untouched."""
    return ChatResult(
        text="", raw="", model="human",
        prompt_chars=0, completion_chars=0, latency_s=0.0,
    )


def _resolve_check_target(target_id: str, state: Any):
    """A skill-check target may be an entity, an item, or a location. Returns
    ``(target_obj, attrs, props, kind)`` — ``(None, {}, {}, None)`` if not found.
    The DC lookup reads attrs for entities/locations, props for items."""
    ent = state.entities.get(target_id)
    if ent is not None:
        return ent, ent.attributes, {}, "entity"
    item = state.items.get(target_id)
    if item is not None:
        return item, {}, item.properties, "item"
    loc = state.locations.get(target_id)
    if loc is not None:
        return loc, loc.attributes, {}, "location"
    return None, {}, {}, None


def _check_target_in_scene(target_id: str, target_obj: Any, kind: str, actor: Any) -> bool:
    if kind == "location":
        return target_id == actor.location_id
    if kind == "entity":
        return target_obj.location_id == actor.location_id
    if kind == "item":
        return target_obj.location_id == actor.location_id or target_id in actor.inventory
    return False


def _dc_purposes(attrs: dict, props: dict) -> list[str]:
    """Pure-ability-check purposes a target offers = its ``{purpose}_dc`` keys,
    minus the non-check ones (lock/force belong to open/use_item)."""
    out: list[str] = []
    for src in (attrs, props):
        for key, val in src.items():
            if not key.endswith("_dc"):
                continue
            if not (isinstance(val, int) and not isinstance(val, bool)):
                continue
            purpose = key[:-3]
            if not purpose or purpose in _NON_CHECK_DC_PURPOSES or purpose in out:
                continue
            out.append(purpose)
    return out


def human_submission_to_turn(
    action_type: str,
    description: str,
    actor_engine_id: str,
    target_engine_id: str | None,
    state: Any,
    ruleset: str = RULESET,
    stat: str | None = None,
    purpose: str | None = None,
) -> PlayerTurnResult:
    """Translate one human submission into a validated turn plan.

    ``actor_engine_id`` / ``target_engine_id`` are ENGINE entity ids (the
    orchestrator maps the frontend's character/target ids first). Raises
    ``TranslationError`` (with a status) on anything the engine can't legally
    do — nothing commits.
    """
    if action_type not in SUPPORTED_ACTIONS:
        raise TranslationError(
            422, f"action type {action_type!r} is not supported yet"
        )

    actor = state.entities.get(actor_engine_id)
    if actor is None:
        raise TranslationError(400, f"actor {actor_engine_id!r} is not in the world")

    intents: list[Any] = []
    if action_type == "roleplay":
        # Narration-only beat — a valid empty turn plan (= pass). The player's
        # prose commits as the PlayerAction; the DM narrates around it. No
        # target, no mechanical state change.
        pass
    elif action_type in ("movement", "move"):
        # The target is a DESTINATION LOCATION (a connected exit), not an
        # entity. Validate connectivity here for an immediate, clean 400.
        if not target_engine_id:
            raise TranslationError(400, "move requires a destination location")
        here = state.locations.get(actor.location_id)
        if here is None or target_engine_id not in here.connections:
            raise TranslationError(
                400,
                f"{target_engine_id!r} is not a connected exit from "
                f"{actor.location_id!r}",
            )
        intents = [MoveIntent(type="move", target=target_engine_id)]
    elif action_type == "skill_check":
        # Roll 1d20 + actor.<stat> vs a DC the engine derives from the target's
        # `{purpose}_dc`. The target may be an entity, item, or location in the
        # scene. Validate everything up-front so an invalid check 400s instead
        # of burning a turn on a SKIPPED beat.
        if not target_engine_id:
            raise TranslationError(400, "a skill check requires a target")
        target_obj, t_attrs, t_props, t_kind = _resolve_check_target(
            target_engine_id, state
        )
        if target_obj is None:
            raise TranslationError(
                400, f"check target {target_engine_id!r} is not in the world"
            )
        if not _check_target_in_scene(target_engine_id, target_obj, t_kind, actor):
            raise TranslationError(
                400, f"check target {target_engine_id!r} is not in your current scene"
            )
        chk_stat = stat or "wis_mod"
        if chk_stat not in SKILL_CHECK_STATS:
            raise TranslationError(400, f"unknown ability {chk_stat!r}")
        offered = _dc_purposes(t_attrs, t_props)
        chk_purpose = purpose or (offered[0] if offered else None)
        if not chk_purpose:
            raise TranslationError(
                400, f"{target_engine_id!r} offers no skill check"
            )
        if _derive_dc(chk_purpose, t_attrs, t_props) is None:
            raise TranslationError(
                400, f"no {chk_purpose!r} DC on {target_engine_id!r}"
            )
        intents = [CheckIntent(
            type="check", stat=chk_stat, target=target_engine_id, purpose=chk_purpose
        )]
    elif action_type == "puzzle_answer":
        # Speak the answer to a puzzle. The answer is the player's prose; the
        # target is the puzzle's location/item — defaults to the room they're
        # standing in (most puzzles, incl. the gated thresholds, are room-level).
        target_id = target_engine_id or actor.location_id
        loc = state.locations.get(target_id)
        itm = state.items.get(target_id)
        has_puzzle = (
            (loc is not None and isinstance(loc.attributes.get("puzzle_answer"), str))
            or (itm is not None and isinstance(itm.properties.get("puzzle_answer"), str))
        )
        if not has_puzzle:
            raise TranslationError(
                400, f"there is no puzzle to answer at {target_id!r}"
            )
        answer = description.strip()
        if not answer:
            raise TranslationError(
                400, "a puzzle answer needs the answer text in the description"
            )
        intents = [PuzzleAnswerIntent(
            type="puzzle_answer", target=target_id, answer=answer
        )]
    else:
        # attack / talk — the target is an ENTITY in the actor's scene.
        if not target_engine_id:
            raise TranslationError(400, f"{action_type} requires a target")
        target = state.entities.get(target_engine_id)
        if target is None:
            raise TranslationError(
                400, f"target {target_engine_id!r} is not in the world"
            )
        if target.location_id != actor.location_id:
            raise TranslationError(
                400, f"target {target_engine_id!r} is not in your current scene"
            )
        if action_type in ("attack_melee", "attack_ranged"):
            intents = [AttackIntent(type="attack", target=target_engine_id)]
        else:  # talk
            speech = description.strip() or "..."
            intents = [TalkIntent(type="talk", target=target_engine_id, speech=speech)]

    ok, err = get_action_economy(ruleset).validate(intents)
    if not ok:
        raise TranslationError(400, f"illegal turn plan: {err}")

    text = description.strip() or config.PLAYER_FALLBACK_TEXT
    return PlayerTurnResult(
        chat=_human_chat_stub(),
        intents=intents,
        narration_text=text,
        raw_text=text,
        parse_status="ok",
        error_message=None,
    )


def run_human_turn(
    log: EventLog,
    actor_engine_id: str,
    location_id: str,
    turn_result: PlayerTurnResult,
    dm: Any,
    rng: Any,
    measurements: Any = None,
    debug_log_path: Any = None,
) -> tuple[int, int]:
    """Run one validated human turn through our runner. Returns
    ``(seq_before, seq_after)`` delimiting the events this turn appended.

    ``measurements`` / ``debug_log_path`` are forwarded to the runner so a
    human turn's narration LLM calls land in the same per-session dev logs as
    the AI/NPC turns (the human controller makes no plan call, but the DM's
    narration of the turn is still an LLM beat worth recording)."""
    seq_before = len(log)
    run_turn(log, actor_engine_id, location_id, turn_result, dm, rng,
             measurements, debug_log_path=debug_log_path)
    return seq_before, len(log)


# ---------------------------------------------------------------------------
# Events → response (the frontend's existing shape)
# ---------------------------------------------------------------------------


_D20_MOD_RE = re.compile(r"1d20\s*([+-]\s*\d+)?")


def _parse_d20_mod(formula: str | None) -> int:
    """Recover the +N modifier from an attack formula like '1d20+5'."""
    if not formula:
        return 0
    m = _D20_MOD_RE.search(formula)
    if not m or not m.group(1):
        return 0
    return int(m.group(1).replace(" ", ""))


def events_to_response(
    log: EventLog,
    seq_before: int,
    seq_after: int,
    entity_to_char: dict[str, str],
    action_meta: dict[str, Any],
) -> dict[str, Any]:
    """Project the turn's new events into the team's response dict.

    ``entity_to_char`` maps engine entity id → frontend character id (so
    ``state_changes`` is keyed the way the SPA expects). ``action_meta`` carries
    ``turn_number`` / ``character_id`` / ``action_type`` / ``description``.
    """
    events = log.events()
    turn_slice = events[seq_before:seq_after]
    before = project(events[:seq_before])
    after = project(events[:seq_after])

    # state_changes — only roster PCs whose hp/status changed (the only thing
    # the unchanged frontend renders from this field).
    state_changes: dict[str, Any] = {}
    for engine_id, char_id in entity_to_char.items():
        a = after.entities.get(engine_id)
        if a is None:
            continue
        b = before.entities.get(engine_id)
        hp_after = a.attributes.get("hp")
        hp_before = b.attributes.get("hp") if b is not None else None
        status_after = a.attributes.get("status")
        status_before = b.attributes.get("status") if b is not None else None
        if b is None or hp_after != hp_before or status_after != status_before:
            state_changes[char_id] = {
                "hp_current": hp_after,
                "hp_max": a.attributes.get("max_hp", hp_after),
                "conditions": [],
            }

    # dice_results + attack_result, reconstructed from the slice.
    dice_results: list[dict[str, Any]] = []
    attack_total: int | None = None
    attack_formula: str | None = None
    damage_total: int | None = None
    for e in turn_slice:
        p = e.payload
        if isinstance(p, DiceRolled):
            dice_results.append(
                {
                    "expression": p.formula,
                    "rolls": [p.result],
                    "modifier": 0,
                    "total": p.result,
                }
            )
            if p.reason.startswith("attack:"):
                attack_total = p.result
                attack_formula = p.formula
            elif p.reason.startswith("damage:"):
                damage_total = p.result

    attack_result: dict[str, Any] | None = None
    if attack_total is not None:
        mod = _parse_d20_mod(attack_formula)
        is_hit = damage_total is not None
        attack_result = {
            "is_hit": is_hit,
            "is_critical": False,
            "damage": damage_total or 0,
            "natural_roll": attack_total - mod,
            "total_roll": attack_total,
        }

    # narration — the last DM narration committed this turn.
    narration = ""
    for e in reversed(turn_slice):
        if isinstance(e.payload, DMNarration):
            narration = e.payload.text
            break

    # actor_prose — the actor's own in-character declaration (the PlayerAction
    # the PC committed this turn). For a HUMAN seat this echoes what they typed
    # (`description`); for an AI seat it's the PlayerAgent's generated prose,
    # which would otherwise be invisible — only the DM's narration reaches the
    # UI. Surfacing it is what makes an AI hero's turn read like a real player
    # speaking at the table, not anonymous DM voice. NPC turns commit no
    # PlayerAction, so this stays "" for them (their voice rides the narration).
    actor_prose = ""
    for e in turn_slice:
        if isinstance(e.payload, PlayerAction):
            actor_prose = e.payload.text
            break

    return {
        "turn_number": action_meta["turn_number"],
        "character_id": action_meta["character_id"],
        "action_type": action_meta["action_type"],
        "description": action_meta.get("description", ""),
        "dice_results": dice_results,
        "attack_result": attack_result,
        "narration": narration,
        "actor_prose": actor_prose,
        "npc_responses": [],
        "state_changes": state_changes,
        "errors": [],
        "status": 200,
    }


# ---------------------------------------------------------------------------
# Combat read-out (engine-backed enemy HP + initiative + round)
# ---------------------------------------------------------------------------


def build_combat_state(
    events: Iterable[Any],
    pc_order: list[str],
    entity_to_char: dict[str, str],
) -> dict[str, Any]:
    """Project the engine's combat state into the shape the frontend's
    encounter/initiative panels render — so enemy HP, death, the initiative
    order and the round counter reflect engine truth instead of the team's old
    client-side tracker.

    ``pc_order`` is the engine pc-entity order (for the scheduler's whose-turn
    decision); ``entity_to_char`` maps engine entity ids back to roster
    character ids (PCs render under their character id; NPCs pass through).

    Returns ``{active, round, active_id, order, enemies}``:
      - ``active``    — True iff combat is currently on.
      - ``round``     — 1-based round number for display (0 when not in combat).
      - ``active_id`` — frontend id of whoever acts next (highlights the row).
      - ``order``     — every combatant in initiative order, each with
                        hp/max_hp/status/ac/attack_mod/initiative/is_active/dead.
      - ``enemies``   — the NPC subset (the encounter panel's enemy cards).
    """
    events = list(events)
    mode = scheduler.current_mode(events)
    active_engine = scheduler.next_actor(events, pc_order)
    active_id = entity_to_char.get(active_engine, active_engine) if active_engine else None

    if mode != "combat":
        return {"active": False, "round": 0, "active_id": active_id,
                "order": [], "enemies": []}

    state = project(events)
    initiative = dict(scheduler.initiative_order(events))  # engine_id -> value
    # initiative_order is already sorted (init desc, id asc); any participant
    # without a roll (shouldn't happen — combat_start rolls for all) sorts last.
    ordered_ids = [eid for eid, _ in scheduler.initiative_order(events)]
    for eid in scheduler.combat_participants(events):
        if eid not in initiative:
            ordered_ids.append(eid)

    order: list[dict[str, Any]] = []
    for eid in ordered_ids:
        ent = state.entities.get(eid)
        if ent is None:
            continue
        status = ent.attributes.get("status")
        order.append({
            "id": entity_to_char.get(eid, eid),
            "name": ent.display_name,
            "kind": ent.kind,
            "hp": ent.attributes.get("hp"),
            "max_hp": ent.attributes.get("max_hp"),
            "status": status,
            "ac": ent.attributes.get("ac"),
            "attack_mod": ent.attributes.get("attack_mod"),
            "initiative": initiative.get(eid),
            "is_active": eid == active_engine,
            "dead": status in config.NEUTRALIZED_STATUSES,
        })

    enemies = [o for o in order if o["kind"] == "npc"]
    return {
        "active": True,
        "round": scheduler.current_round(events) + 1,  # 1-based for display
        "active_id": active_id,
        "order": order,
        "enemies": enemies,
    }


# A check's DiceRolled reason encodes everything we need to reconstruct the
# outcome — `check 'search' (int_mod): ent_pc_brakka -> item_gallery_effigies`
# (purpose may be absent: `check (dex_mod): a -> b`). Parsing it means
# `extract_check_result` is caller-agnostic: it works for a HUMAN submission and
# for an AI PlayerAgent's CheckIntent identically (the event log is the same).
_CHECK_REASON_RE = re.compile(
    r"check\s+(?:'([^']*)'\s+)?\(([^)]+)\):\s*\S+\s*->\s*(\S+)"
)


def extract_check_result(
    log: EventLog,
    seq_before: int,
    seq_after: int,
) -> dict[str, Any] | None:
    """Recover a skill check's outcome (roll total vs DC, pass/fail) for the UI,
    from the committed events alone. The engine logs the d20 roll but NOT the DC
    (it lives only in the internal CheckResolution), so re-derive the DC from
    the target's post-turn attributes/properties — the same lookup the runner
    used. Returns None if no check rolled this turn or the target has no DC.

    Works for any actor (human or AI), since it reads the check's `reason`
    rather than an in-hand intent. Surfaces the FIRST check in the slice."""
    events = log.events()
    after = project(events[:seq_after])
    for e in events[seq_before:seq_after]:
        p = e.payload
        if not (isinstance(p, DiceRolled) and p.reason.startswith("check")):
            continue
        m = _CHECK_REASON_RE.match(p.reason)
        if m is None:
            continue
        purpose, stat, target_id = (m.group(1) or ""), m.group(2), m.group(3)
        _, attrs, props, _ = _resolve_check_target(target_id, after)
        dc = _derive_dc(purpose, attrs, props)
        if dc is None:
            return None
        return {"stat": stat, "purpose": purpose, "total": p.result,
                "dc": dc, "success": p.result >= dc}
    return None


# ---------------------------------------------------------------------------
# Scene read-out (the location badge + exits + targets the frontend renders)
# ---------------------------------------------------------------------------


def build_scene(state: Any, actor_engine_id: str) -> dict[str, Any]:
    """Structured snapshot of the actor's current scene: where they are, the
    connected exits (the move options), and the entities present (attack/talk
    targets). This is what replaces the frontend's free-text location label —
    the badge becomes a read-out of `location.name`, and movement picks from
    `exits`.
    """
    actor = state.entities.get(actor_engine_id)
    if actor is None:
        raise TranslationError(400, f"actor {actor_engine_id!r} is not in the world")

    here = state.locations.get(actor.location_id)
    exits: list[dict[str, str]] = []
    for conn_id in here.connections if here is not None else []:
        cloc = state.locations.get(conn_id)
        exits.append({"id": conn_id, "name": cloc.name if cloc is not None else conn_id})
    exits.sort(key=lambda e: e["id"])

    entities_here: list[dict[str, Any]] = []
    for e in state.entities.values():
        if e.location_id != actor.location_id or e.entity_id == actor_engine_id:
            continue
        entities_here.append(
            {
                "id": e.entity_id,
                "name": e.display_name,
                "kind": e.kind,
                "status": e.attributes.get("status"),
                "hp": e.attributes.get("hp"),
                "max_hp": e.attributes.get("max_hp"),
            }
        )

    # Skill-check targets: anything in the scene carrying a `{purpose}_dc` (the
    # room itself, items on the ground / in inventory, entities present). One
    # entry per offered purpose, so the frontend presents a target and supplies
    # the matching purpose automatically (the engine derives the DC).
    check_targets: list[dict[str, Any]] = []

    def _add_checks(tid: str, name: str, kind: str, attrs: dict, props: dict) -> None:
        for p in _dc_purposes(attrs, props):
            check_targets.append({"id": tid, "name": name, "kind": kind, "purpose": p})

    if here is not None:
        _add_checks(actor.location_id, here.name, "location", here.attributes, {})
    for e in state.entities.values():
        if e.location_id == actor.location_id and e.entity_id != actor_engine_id:
            _add_checks(e.entity_id, e.display_name, "entity", e.attributes, {})
    for it in state.items.values():
        if it.location_id == actor.location_id or it.item_id in actor.inventory:
            _add_checks(it.item_id, it.name, "item", {}, it.properties)

    return {
        "character_id": actor_engine_id,  # engine id; orchestrator maps back
        "location": {
            "id": actor.location_id,
            "name": here.name if here is not None else actor.location_id,
            "description": strip_demo_annotations(here.description) if here is not None else "",
        },
        "exits": exits,
        "entities_here": entities_here,
        "check_targets": check_targets,
    }
