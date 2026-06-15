"""
Turn orchestration — M8 structured-turn-plan dispatch.

Per the M8 brief:
  - `run_turn` consumes a `PlayerTurnResult` (already validated by the
    PlayerAgent's retry loop) and walks the intent plan in order.
  - Each intent dispatches to a type-specific resolver. Earlier intents
    in the same turn can change the world state visible to later intents
    (e.g. a move shifts the actor's location; a subsequent attack
    validates against the new room).
  - All staged payloads commit atomically with the DM's narration. On
    narration failure, `buffer.discard()` drops everything — except the
    PlayerAction (the player's prose record), which commits up-front
    and survives.
  - `run_npc_turn` is symmetric for NPCs: `DMAgent.plan_npc_turn`
    produces the structured plan; runner dispatches the same way.

Combat_start is now runner-auto-emitted: when an attack intent lands a
hit on a hostile target while combat is not yet on, the runner stages
a `CombatStart` + initiative rolls. The M5 "DM emits redundant
combat_start" flag becomes moot — the runner deterministically decides.
"""
from __future__ import annotations

import random
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import config
import scheduler
from debug_log import write_fallback_record
from dice import roll as _dice_roll
from dice import roll_detailed
from dm import DMAgent, IntentOutcome, NarrationAttempt, gather_lore
from eventlog import EventLog
from llm import ChatResult
from mechanics import (
    INCAPACITATING_CONDITIONS,
    MechanicsError,
    MechanicsProvider,
    entity_condition_meta,
    entity_conditions,
    get_mechanics,
    is_incapacitated,
)
from models import (
    AttributeDelta,
    AttributeSet,
    CombatEnd,
    CombatParticipantsAdded,
    CombatStart,
    DiceRolled,
    DMNarration,
    Entity,
    EntityMoved,
    Event,
    EventCause,
    InventoryAdded,
    InventoryRemoved,
    Payload,
    PlayerAction,
    WorldState,
)
from player import PlayerAttempt, PlayerTurnResult
from projection import project
from tags import (
    AttackIntent,
    CheckIntent,
    ExamineIntent,
    GiveIntent,
    InspectIntent,
    IntentTag,
    LookIntent,
    MoveIntent,
    OpenIntent,
    PickupIntent,
    PuzzleAnswerIntent,
    TalkIntent,
    TradeIntent,
    UseItemIntent,
    WaitIntent,
)


# The ruleset whose mechanics provider the runner uses when a caller doesn't
# specify one. Everything ships dnd5e_lite today; a second system passes its
# own id to run_turn/run_npc_turn (invariant 8 — the runner never branches on
# system, it just looks the provider up).
_DEFAULT_RULESET = "dnd5e_lite"


# ---------------------------------------------------------------------------
# Measurement protocol
# ---------------------------------------------------------------------------


class MeasurementSink(Protocol):
    """One record per LLM call (player-planning + narration both flow here)."""

    def record(
        self,
        beat: str,
        chat: ChatResult,
        parse_status: str,
        error_message: str | None,
        attempt_idx: int,
    ) -> None: ...


# ---------------------------------------------------------------------------
# Result + buffer (unchanged from M3-M5 in shape)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TurnResult:
    turn_id: str
    succeeded: bool
    fallback_beat: str | None  # "intent" | "narration" | None


class TurnBuffer:
    """Stage payloads in memory; commit-or-discard atomically.

    `project()` returns the world state *as if* all staged payloads were
    appended after the committed log. This is what makes intra-turn
    multi-intent flow work: an earlier intent's mechanical effect is
    visible to the next intent's validation.
    """

    def __init__(self, log: EventLog) -> None:
        self._log = log
        self._staged: list[tuple[Payload, EventCause]] = []
        # Memoized projection. Valid until the next stage()/commit()/
        # discard() — projection is a pure function of (committed log,
        # staged list), so between mutations every call returns the same
        # state. A single attack resolution projects 4×; without the cache
        # each call re-folded the whole log. Callers treat the returned
        # WorldState as read-only (all world changes go through payloads —
        # nothing in the engine mutates a projected state).
        self._cached_state: WorldState | None = None

    def stage(self, payload: Payload, cause: EventCause) -> None:
        self._staged.append((payload, cause))
        self._cached_state = None

    def project(self) -> WorldState:
        if self._cached_state is not None:
            return self._cached_state
        committed = self._log.events()
        next_seq = len(committed)
        staged_events = [
            Event(
                seq=next_seq + i,
                timestamp=0.0,
                cause=cause,
                payload=payload,
            )
            for i, (payload, cause) in enumerate(self._staged)
        ]
        self._cached_state = project(committed + staged_events)
        return self._cached_state

    def commit(self) -> None:
        for payload, cause in self._staged:
            self._log.append(payload, cause)
        self._staged.clear()
        self._cached_state = None

    def discard(self) -> None:
        self._staged.clear()
        self._cached_state = None

    @property
    def is_empty(self) -> bool:
        return not self._staged

    def __len__(self) -> int:
        return len(self._staged)


# ---------------------------------------------------------------------------
# run_turn (PC)
# ---------------------------------------------------------------------------


def run_turn(
    log: EventLog,
    player_id: str,
    location_id: str,
    turn_result: PlayerTurnResult,
    dm: DMAgent,
    rng: random.Random,
    measurements: MeasurementSink | None = None,
    debug_log_path: Path | None = None,
    ruleset: str = _DEFAULT_RULESET,
) -> TurnResult:
    """
    Execute one PC turn. `turn_result` is what `PlayerAgent.act` produced
    — it has already been validated (or has parse_status indicating
    exhausted retries).
    """
    turn_id = uuid.uuid4().hex[:8]
    mechanics = get_mechanics(ruleset)

    # 0. M12 death saves — a dying PC (unconscious at 0 HP, still tallying
    #    death saves) cannot act. The runner rolls a death save for them and
    #    narrates it; the planned `turn_result` is ignored. This keeps the
    #    engine correct regardless of caller, though a caller that knows the
    #    PC is dying (see `is_dying_pc`) can skip planning to save an LLM call.
    pre_actor = project(log.events()).entities.get(player_id)
    if pre_actor is not None and is_dying_pc(pre_actor):
        return _run_death_save_turn(log, player_id, location_id, rng, mechanics, turn_id)

    # 1. Player's prose commits directly, outside the buffer.
    #    Even on a fallback path, the player's words survive.
    #    Empty text means the player LLM gave valid intents but no
    #    narration; we skip the PlayerAction so the player record does
    #    not contradict the intents that actually fire (the DM's
    #    narration of the intent outcomes carries the beat).
    if turn_result.narration_text:
        log.append(
            PlayerAction(
                player_id=player_id,
                location_id=location_id,
                text=turn_result.narration_text,
            ),
            EventCause(kind="player_action", turn_id=turn_id, player_id=player_id),
        )

    # 2. Record the player-planning LLM attempts.
    _record_player_attempts(measurements, "player_plan", turn_result.attempts)

    # 3. Player plan failed after retries → fallback path.
    if not turn_result.succeeded:
        _commit_fallback(log, turn_id, player_id, location_id, config.FALLBACK_INTENT_TEXT)
        _write_debug_for_player(
            debug_log_path, turn_id, "player_plan", player_id, location_id,
            turn_result.narration_text, dm.model, turn_result.attempts,
        )
        return TurnResult(turn_id=turn_id, succeeded=False, fallback_beat="intent")

    # 4. Walk the validated intent plan. Combat_start/join is staged
    #    *before* an attack rolls — any valid attack-attempt on an enemy
    #    flips the room to combat first, so the attack roll itself
    #    happens inside combat (no free pre-combat hits).
    current_mode = scheduler.current_mode(log.events())
    buffer = TurnBuffer(log)
    outcomes: list[IntentOutcome] = []

    for intent in turn_result.intents:
        if isinstance(intent, AttackIntent):
            pre_state = buffer.project()
            if (
                _attack_skip_reason(intent, pre_state, player_id) is None
                and _is_enemy(player_id, intent.target, pre_state)
            ):
                if current_mode == "exploration":
                    _stage_combat_start_auto(
                        buffer, player_id, intent.target, location_id, turn_id, rng,
                    )
                    current_mode = "combat"
                else:
                    _stage_combat_join_auto(
                        buffer, player_id, intent.target, location_id, turn_id, rng,
                    )

        outcome = _resolve_intent(intent, buffer, player_id, turn_id, rng, mechanics)
        outcomes.append(outcome)
        if isinstance(intent, WaitIntent):
            break

    # 6. Narrate the turn.
    state = buffer.project()
    narration_result = dm.narrate_turn_outcome(
        actor_id=player_id,
        outcomes=outcomes,
        state=state,
        location_id=location_id,
        player_text=turn_result.narration_text,
    )
    _record_narration_attempts(measurements, narration_result.attempts)

    if not narration_result.succeeded:
        # Atomic discard — drops every staged intent + combat_start + dice.
        buffer.discard()
        _commit_fallback(log, turn_id, player_id, location_id, config.FALLBACK_NARRATION_TEXT)
        _write_debug_for_narration(
            debug_log_path, turn_id, player_id, location_id,
            turn_result.narration_text, dm.model, narration_result.attempts,
        )
        return TurnResult(turn_id=turn_id, succeeded=False, fallback_beat="narration")

    # 7. Stage DMNarration + commit the whole buffer atomically.
    buffer.stage(
        DMNarration(
            audience=player_id,
            location_id=location_id,
            text=narration_result.narration.text,
        ),
        EventCause(kind="dm_action", turn_id=turn_id, player_id=player_id),
    )
    buffer.commit()

    # 8. Auto-emit combat_end (M5 behavior, unchanged).
    _maybe_emit_combat_end(log, turn_id, player_id)

    # 9. M9 countdown tick — decrement every `countdown_*` attribute by 1.
    _tick_countdowns(log, turn_id, player_id)

    # 10. M12 condition expiry — the actor's durationed/save-ends conditions
    #     tick (or are re-saved) at the end of their own turn.
    _tick_conditions(log, turn_id, player_id, rng, mechanics)

    return TurnResult(turn_id=turn_id, succeeded=True, fallback_beat=None)


# ---------------------------------------------------------------------------
# run_npc_turn (M5/M8)
# ---------------------------------------------------------------------------


def run_npc_turn(
    log: EventLog,
    npc_id: str,
    location_id: str,
    dm: DMAgent,
    rng: random.Random,
    measurements: MeasurementSink | None = None,
    debug_log_path: Path | None = None,
    ruleset: str = _DEFAULT_RULESET,
) -> TurnResult:
    """NPC turn — DM plans the structured plan via `plan_npc_turn`."""
    turn_id = uuid.uuid4().hex[:8]
    state = project(log.events())
    mechanics = get_mechanics(ruleset)

    recent_talks = _collect_recent_talks_to(log, npc_id, state, limit=5)
    npc_result = dm.plan_npc_turn(state, npc_id, location_id, recent_talks)
    _record_player_attempts(measurements, "npc_plan", npc_result.attempts)

    if not npc_result.succeeded:
        _commit_fallback(log, turn_id, npc_id, location_id, config.FALLBACK_INTENT_TEXT)
        _write_debug_for_player(
            debug_log_path, turn_id, "npc_plan", npc_id, location_id,
            npc_result.narration_text, dm.model, npc_result.attempts,
        )
        return TurnResult(turn_id=turn_id, succeeded=False, fallback_beat="intent")

    # NPCs do not commit a PlayerAction (no freeform input). The DM's
    # narration captures everything that happened.

    # Combat is triggered *before* the attack roll resolves — any valid
    # NPC attack on a PC flips the room to combat first. Symmetric with
    # the PC-attacks-hostile path in `run_turn`.
    current_mode = scheduler.current_mode(log.events())
    buffer = TurnBuffer(log)
    outcomes: list[IntentOutcome] = []

    for intent in npc_result.intents:
        if isinstance(intent, AttackIntent):
            pre_state = buffer.project()
            if (
                _attack_skip_reason(intent, pre_state, npc_id) is None
                and _is_enemy(npc_id, intent.target, pre_state)
            ):
                if current_mode == "exploration":
                    _stage_combat_start_auto(
                        buffer, npc_id, intent.target, location_id, turn_id, rng,
                    )
                    current_mode = "combat"
                else:
                    _stage_combat_join_auto(
                        buffer, npc_id, intent.target, location_id, turn_id, rng,
                    )

        outcome = _resolve_intent(intent, buffer, npc_id, turn_id, rng, mechanics)
        outcomes.append(outcome)
        if isinstance(intent, WaitIntent):
            break

    post_state = buffer.project()
    narration_result = dm.narrate_turn_outcome(
        actor_id=npc_id,
        outcomes=outcomes,
        state=post_state,
        location_id=location_id,
        player_text=npc_result.narration_text,
    )
    _record_narration_attempts(measurements, narration_result.attempts)

    if not narration_result.succeeded:
        buffer.discard()
        _commit_fallback(log, turn_id, npc_id, location_id, config.FALLBACK_NARRATION_TEXT)
        _write_debug_for_narration(
            debug_log_path, turn_id, npc_id, location_id,
            npc_result.narration_text, dm.model, narration_result.attempts,
        )
        return TurnResult(turn_id=turn_id, succeeded=False, fallback_beat="narration")

    buffer.stage(
        DMNarration(
            audience=npc_id,
            location_id=location_id,
            text=narration_result.narration.text,
        ),
        EventCause(kind="dm_action", turn_id=turn_id, player_id=npc_id),
    )
    buffer.commit()

    _maybe_emit_combat_end(log, turn_id, npc_id)
    _tick_countdowns(log, turn_id, npc_id)
    _tick_conditions(log, turn_id, npc_id, rng, mechanics)
    return TurnResult(turn_id=turn_id, succeeded=True, fallback_beat=None)


def run_death_save_turn(
    log: EventLog,
    pc_id: str,
    location_id: str,
    rng: random.Random,
    ruleset: str = _DEFAULT_RULESET,
) -> TurnResult:
    """Public entry point for a turn a *dying* PC spends rolling a death save.

    A caller that already knows the PC is dying (see `is_dying_pc`) uses this to
    skip building a view and planning with the LLM entirely — an unconscious
    hero has no decision to make, so there is nothing to "think" about. The
    `run_turn` path performs the same intercept defensively for any other caller
    (e.g. a human action submission for a downed PC)."""
    return _run_death_save_turn(
        log, pc_id, location_id, rng, get_mechanics(ruleset), uuid.uuid4().hex[:8],
    )


# ---------------------------------------------------------------------------
# Per-intent resolution
# ---------------------------------------------------------------------------


def _resolve_intent(
    intent: IntentTag,
    buffer: TurnBuffer,
    actor_id: str,
    turn_id: str,
    rng: random.Random,
    mechanics: MechanicsProvider,
) -> IntentOutcome:
    """Dispatch an intent against the buffer-projected state. Returns an
    IntentOutcome whose `summary` feeds the DM's narration prompt. `mechanics`
    is the ruleset's resolution provider — only the dice-resolving intents
    (attack/check, and the check-gated examine/use_item) need it."""
    if isinstance(intent, LookIntent):
        return _resolve_look(intent, buffer, actor_id)
    if isinstance(intent, ExamineIntent):
        return _resolve_examine(intent, buffer, actor_id, turn_id, rng, mechanics)
    if isinstance(intent, MoveIntent):
        return _resolve_move(intent, buffer, actor_id, turn_id)
    if isinstance(intent, AttackIntent):
        return _resolve_attack(intent, buffer, actor_id, turn_id, rng, mechanics)
    if isinstance(intent, TalkIntent):
        return _resolve_talk(intent, buffer, actor_id, turn_id)
    if isinstance(intent, WaitIntent):
        return IntentOutcome(intent=intent, resolved=True, summary="held action (waited)")
    if isinstance(intent, CheckIntent):
        return _resolve_check(intent, buffer, actor_id, turn_id, rng, mechanics)
    if isinstance(intent, UseItemIntent):
        return _resolve_use_item(intent, buffer, actor_id, turn_id, rng, mechanics)
    if isinstance(intent, PuzzleAnswerIntent):
        return _resolve_puzzle_answer(intent, buffer, actor_id, turn_id)
    if isinstance(intent, PickupIntent):
        return _resolve_pickup(intent, buffer, actor_id, turn_id)
    if isinstance(intent, GiveIntent):
        return _resolve_give(intent, buffer, actor_id, turn_id)
    if isinstance(intent, OpenIntent):
        return _resolve_open(intent, buffer, actor_id, turn_id)
    if isinstance(intent, TradeIntent):
        return _resolve_trade(intent, buffer, actor_id, turn_id)
    if isinstance(intent, InspectIntent):
        synthetic = ExamineIntent(type="examine", target=intent.target)
        return _resolve_examine(synthetic, buffer, actor_id, turn_id, rng, mechanics)
    return IntentOutcome(
        intent=intent, resolved=False,
        summary=f"unknown intent type {intent.type!r}",
    )


def _resolve_look(intent: LookIntent, buffer: TurnBuffer, actor_id: str) -> IntentOutcome:
    state = buffer.project()
    actor_loc = state.entities[actor_id].location_id
    if not _is_in_scope(intent.target, state, actor_id, actor_loc):
        return IntentOutcome(
            intent=intent, resolved=False,
            summary=f"SKIPPED: {intent.target!r} not in scene",
        )
    lore = gather_lore(intent.target, state, include_hidden=False)
    return IntentOutcome(
        intent=intent, resolved=True,
        summary=f"looked at {intent.target}: {lore}",
    )


def _resolve_examine(
    intent: ExamineIntent,
    buffer: TurnBuffer,
    actor_id: str,
    turn_id: str,
    rng: random.Random,
    mechanics: MechanicsProvider,
) -> IntentOutcome:
    state = buffer.project()
    actor_loc = state.entities[actor_id].location_id
    if not _is_in_scope(intent.target, state, actor_id, actor_loc):
        return IntentOutcome(
            intent=intent, resolved=False,
            summary=f"SKIPPED: {intent.target!r} not in scene",
        )

    # M9: search_dc gate. If the target has a search_dc, roll an
    # actor-stat check; success reveals hidden_text, failure does not.
    search_dc, search_stat = _lookup_search_dc(intent.target, state)
    if isinstance(search_dc, int) and not isinstance(search_dc, bool):
        actor = state.entities[actor_id]
        resolution, payloads = mechanics.resolve_check(
            actor, intent.target, search_stat, search_dc, rng, purpose="search",
        )
        for payload in payloads:
            cause_kind = "dice_resolution" if isinstance(payload, DiceRolled) else "dm_action"
            buffer.stage(payload, EventCause(kind=cause_kind, turn_id=turn_id, player_id=actor_id))
        lore = gather_lore(intent.target, state, include_hidden=resolution.success)
        result_str = "REVEALED" if resolution.success else "MISSED"
        roll_str = resolution.roll_text or (
            f"1d20{resolution.stat_mod:+d}={resolution.total} vs DC {search_dc}"
        )
        summary = (
            f"examined {intent.target} (search check {result_str}: {roll_str}): {lore}"
        )
        return IntentOutcome(intent=intent, resolved=True, summary=summary)

    lore = gather_lore(intent.target, state, include_hidden=True)
    return IntentOutcome(
        intent=intent, resolved=True,
        summary=f"examined {intent.target}: {lore}",
    )


def _lookup_search_dc(target_id: str, state: WorldState) -> tuple[int | None, str]:
    """Return (search_dc, search_stat) for a target. Stat defaults to
    'wis_mod'. Looks at item.properties first, then entity/location
    attributes."""
    item = state.items.get(target_id)
    if item is not None:
        dc = item.properties.get("search_dc")
        stat = item.properties.get("search_stat", "wis_mod")
        return (dc if isinstance(dc, int) and not isinstance(dc, bool) else None, stat)
    entity = state.entities.get(target_id)
    if entity is not None:
        dc = entity.attributes.get("search_dc")
        stat = entity.attributes.get("search_stat", "wis_mod")
        return (dc if isinstance(dc, int) and not isinstance(dc, bool) else None, stat)
    location = state.locations.get(target_id)
    if location is not None:
        dc = location.attributes.get("search_dc")
        stat = location.attributes.get("search_stat", "wis_mod")
        return (dc if isinstance(dc, int) and not isinstance(dc, bool) else None, stat)
    return (None, "wis_mod")


def _resolve_move(
    intent: MoveIntent,
    buffer: TurnBuffer,
    actor_id: str,
    turn_id: str,
) -> IntentOutcome:
    state = buffer.project()
    actor = state.entities[actor_id]

    # M9: movement_restricted attribute blocks the move. The value can
    # be `True` or a string describing the reason (surfaced in summary).
    restriction = actor.attributes.get("movement_restricted")
    if restriction:
        reason = restriction if isinstance(restriction, str) else "movement restricted"
        return IntentOutcome(
            intent=intent, resolved=False,
            summary=f"SKIPPED: {actor_id} cannot move ({reason})",
        )

    actor_loc = actor.location_id
    current = state.locations.get(actor_loc)
    if current is None:
        return IntentOutcome(
            intent=intent, resolved=False,
            summary=f"SKIPPED: actor's location {actor_loc!r} not found",
        )
    if intent.target not in current.connections:
        return IntentOutcome(
            intent=intent, resolved=False,
            summary=f"SKIPPED: {intent.target!r} is not connected to {actor_loc!r}",
        )

    # Gated exit (opt-in, authored): a location may seal a SPECIFIC outward exit
    # behind a solved puzzle via `gated_exits: {dest_location: solved_target}`.
    # The exit stays barred until ANY party member carries `solved_<target>` (a
    # door opened by one PC is open for all). This is the one hard movement gate
    # the engine enforces, and only where a seed declares it — narrating the door
    # open does nothing; only the puzzle_answer intent sets the marker.
    gated_exits = current.attributes.get("gated_exits")
    if isinstance(gated_exits, dict) and intent.target in gated_exits:
        required = gated_exits[intent.target]
        solved = any(
            e.attributes.get(f"solved_{required}") for e in state.entities.values()
        )
        if not solved:
            return IntentOutcome(
                intent=intent, resolved=False,
                summary=(
                    f"SKIPPED: the way to {intent.target} is SEALED — it will not "
                    f"open until someone answers the puzzle at {required} with "
                    f'<intent type="puzzle_answer" target="{required}" '
                    f'answer="..."/>. Narrating or pushing the door does nothing.'
                ),
            )

    buffer.stage(
        EntityMoved(entity_id=actor_id, to_location=intent.target),
        EventCause(kind="dm_action", turn_id=turn_id, player_id=actor_id),
    )

    # B2: hostile-on-entry. When a PC moves into a location containing
    # hostile NPC(s) who are not neutralized, mark each hostile with a
    # pending response so the scheduler queues their turn next. NPC-on-
    # NPC movement does NOT trigger this — only PCs entering rooms
    # rouse defenders.
    if actor.kind == "pc":
        for entity in state.entities.values():
            if entity.entity_id == actor_id:
                continue
            if entity.kind != "npc":
                continue
            if entity.location_id != intent.target:
                continue
            if entity.attributes.get("status") != "hostile":
                continue
            buffer.stage(
                AttributeSet(
                    entity_id=entity.entity_id,
                    attr=config.PENDING_NPC_RESPONSE_ATTR,
                    value=True,
                ),
                EventCause(kind="dm_action", turn_id=turn_id, player_id=actor_id),
            )

    # Use display NAMES (not raw ids) in the summary — this string feeds the
    # DM narration prompt, and the DM has been observed parroting a raw id
    # ("...the dimly lit chamber of loc_wicks_room"). Fall back to the id only
    # if a location somehow has no name.
    dest = state.locations.get(intent.target)
    dest_name = dest.name if dest is not None else intent.target
    from_name = current.name if current is not None else actor_loc
    return IntentOutcome(
        intent=intent, resolved=True,
        summary=f"moved from {from_name} to {dest_name}",
    )


def _attack_skip_reason(
    intent: AttackIntent,
    state: WorldState,
    actor_id: str,
) -> str | None:
    """Return the SKIP summary string if this attack would be rejected
    by `_resolve_attack`, else None. The runner calls this to decide
    whether to stage combat_start *before* the attack rolls — we don't
    want to flip the room to combat for an attack that's about to be
    discarded as invalid."""
    actor = state.entities.get(actor_id)
    if actor is None:
        return f"SKIPPED: attacker {actor_id!r} not found"
    # M12: an incapacitated actor (stunned/paralyzed/…) cannot take actions.
    if is_incapacitated(actor):
        conds = ", ".join(sorted(entity_conditions(actor) & INCAPACITATING_CONDITIONS))
        return f"SKIPPED: {actor_id} cannot act ({conds})"
    target = state.entities.get(intent.target)
    if target is None:
        return f"SKIPPED: target {intent.target!r} not found"
    if target.location_id != actor.location_id:
        return f"SKIPPED: target {intent.target!r} not in scene"
    if intent.target == actor_id:
        return "SKIPPED: cannot attack self"
    if target.attributes.get("status") == "dead":
        return f"SKIPPED: target {intent.target!r} is already dead"
    return None


def _is_enemy(actor_id: str, target_id: str, state: WorldState) -> bool:
    """Decide whether `target_id` counts as an enemy of `actor_id` for
    combat-trigger purposes. PCs treat hostile NPCs as enemies; NPCs
    treat PCs as enemies. Everything else (friendlies, NPC-on-NPC) is
    excluded so combat doesn't start from accidental swings at allies."""
    actor = state.entities.get(actor_id)
    target = state.entities.get(target_id)
    if actor is None or target is None:
        return False
    if actor.kind == "pc":
        return target.kind == "npc" and target.attributes.get("status") == "hostile"
    return target.kind == "pc"


def _resolve_attack(
    intent: AttackIntent,
    buffer: TurnBuffer,
    actor_id: str,
    turn_id: str,
    rng: random.Random,
    mechanics: MechanicsProvider,
) -> IntentOutcome:
    state = buffer.project()
    skip = _attack_skip_reason(intent, state, actor_id)
    if skip is not None:
        return IntentOutcome(intent=intent, resolved=False, summary=skip)
    actor = state.entities[actor_id]
    target = state.entities[intent.target]

    # M12 multi-target: an attacker authored with an `area_attack` spec
    # sweeps every opposing target in the room with one save-based effect
    # instead of striking the named target. The intent stays a plain
    # <attack> (closed vocabulary, zero prompt cost) — the named target
    # validated above is simply one of the swept targets.
    if mechanics.area_attack_spec(actor) is not None:
        return _resolve_area_attack_intent(
            intent, buffer, actor_id, turn_id, rng, mechanics,
        )

    try:
        resolution, payloads = mechanics.resolve_attack(actor, target, rng)
    except MechanicsError as e:
        return IntentOutcome(intent=intent, resolved=False, summary=f"SKIPPED: mechanics error: {e}")

    for payload in payloads:
        cause_kind = "dice_resolution" if isinstance(payload, DiceRolled) else "dm_action"
        buffer.stage(payload, EventCause(kind=cause_kind, turn_id=turn_id, player_id=actor_id))

    # Downed check post-staging. NPCs die at 0; PCs fall unconscious and make
    # death saves (M12). `_stage_downing` returns "dead" | "unconscious" | None.
    post_state = buffer.project()
    post_target = post_state.entities[target.entity_id]
    downed_state = _stage_downing(buffer, target, post_target, resolution, turn_id, actor_id)
    # Re-read hp after downing (a downed PC is clamped to 0) for the summary.
    hp_after = buffer.project().entities[target.entity_id].attributes.get("hp", 0)

    # M12: surface advantage/crit/inflicted-conditions so the DM narrates them.
    if resolution.crit:
        hit_str = "CRITICAL HIT"
    elif resolution.hit:
        hit_str = "HIT"
    elif resolution.fumble:
        hit_str = "MISS (natural 1 — fumble)"
    else:
        hit_str = "MISS"
    adv_str = "" if resolution.advantage == "none" else f" (with {resolution.advantage})"
    roll_str = resolution.roll_text or (
        f"1d20={resolution.attack_d20}{resolution.attack_mod:+d}"
        f" = {resolution.attack_total} vs AC {resolution.target_ac}"
    )
    summary = f"attacked {intent.target}{adv_str}: {roll_str} → {hit_str}"
    if resolution.hit:
        hp_after_int = int(hp_after) if isinstance(hp_after, (int, float)) else "?"
        crit_note = " (DOUBLED — critical hit)" if resolution.crit else ""
        # M12: damage type + resistance/vulnerability/immunity scaling.
        type_note = f" {resolution.damage_type}" if resolution.damage_type else ""
        applied = resolution.damage_applied
        applied = applied if applied is not None else resolution.damage_total
        effect = resolution.resistance_effect
        if effect == "immune":
            damage_clause = (
                f"; {target.display_name} is IMMUNE to {resolution.damage_type} damage"
                f" — 0 dealt (rolled {resolution.damage_total}){crit_note}"
            )
        elif effect in ("resisted", "vulnerable"):
            how = "halved by resistance" if effect == "resisted" else "doubled by vulnerability"
            damage_clause = (
                f"; damage {applied}{type_note} (rolled {resolution.damage_total}, {how}){crit_note}"
            )
        else:
            damage_clause = f"; damage {applied}{type_note} ({resolution.damage_formula}){crit_note}"
        summary += (
            damage_clause
            + f"; {target.display_name} hp BEFORE this hit: {resolution.target_hp_before}"
            f", AFTER this hit: {hp_after_int}"
            f" (use {hp_after_int} when describing current state)"
        )
        # M12: an on-hit rider may have forced a save to resist a condition.
        save = resolution.rider_save
        if save is not None:
            save_str = "SAVED" if save.success else "FAILED"
            save_roll = save.roll_text or (
                f"1d20{save.save_mod:+d}={save.total} vs DC {save.dc}"
            )
            summary += (
                f"; {target.display_name} {save.ability} save {save_roll} → {save_str}"
            )
            if save.success:
                summary += " (resisted — no condition)"
        if resolution.applied_conditions:
            summary += (
                f"; {target.display_name} is now "
                f"{', '.join(resolution.applied_conditions)}"
            )
    if downed_state == "dead":
        summary += f"; {target.display_name} is DOWNED (slain)"
    elif downed_state == "unconscious":
        succ, fail = _death_save_tally(buffer.project().entities[target.entity_id])
        summary += (
            f"; {target.display_name} drops to 0 HP and falls UNCONSCIOUS — dying"
            f" (death saves: {succ} successes / {fail} failures)"
        )
    return IntentOutcome(intent=intent, resolved=True, summary=summary)


def _area_targets(state: WorldState, actor: Entity) -> list[Entity]:
    """Every valid opposing target co-located with an area attacker, in
    entity_id order (deterministic for replay). Mirrors the single-target
    opposition rule: a PC sweeps hostile NPCs; an NPC sweeps PCs. Dead
    targets are excluded; a downed-but-not-dead PC is NOT (an area effect
    hitting a dying PC deals death-save failures, same as a direct hit)."""
    out: list[Entity] = []
    for entity in state.entities.values():
        if entity.entity_id == actor.entity_id:
            continue
        if entity.location_id != actor.location_id:
            continue
        if actor.kind == "pc":
            if entity.kind == "npc" and entity.attributes.get("status") == "hostile":
                out.append(entity)
        elif entity.kind == "pc" and entity.attributes.get("status") != "dead":
            out.append(entity)
    out.sort(key=lambda e: e.entity_id)
    return out


def _resolve_area_attack_intent(
    intent: AttackIntent,
    buffer: TurnBuffer,
    actor_id: str,
    turn_id: str,
    rng: random.Random,
    mechanics: MechanicsProvider,
) -> IntentOutcome:
    """Resolve an area attacker's <attack> as a room sweep: one damage roll,
    every opposing target saves (see `mechanics.resolve_area_attack`), then
    each target's downed state settles exactly like a single-target hit."""
    state = buffer.project()
    actor = state.entities[actor_id]
    targets = _area_targets(state, actor)
    if not targets:
        return IntentOutcome(
            intent=intent, resolved=False,
            summary="SKIPPED: no valid targets in the room for an area attack",
        )
    try:
        resolution, payloads = mechanics.resolve_area_attack(actor, targets, rng)
    except MechanicsError as e:
        return IntentOutcome(intent=intent, resolved=False, summary=f"SKIPPED: mechanics error: {e}")

    for payload in payloads:
        cause_kind = "dice_resolution" if isinstance(payload, DiceRolled) else "dm_action"
        buffer.stage(payload, EventCause(kind=cause_kind, turn_id=turn_id, player_id=actor_id))
    post_state = buffer.project()

    type_note = f" {resolution.damage_type}" if resolution.damage_type else ""
    parts = [
        f"area attack ({resolution.save_ability} save DC {resolution.dc}, "
        f"{len(targets)} targets): damage roll "
        f"{resolution.damage_formula}={resolution.damage_total}{type_note}"
    ]
    for out in resolution.targets:
        target = state.entities[out.target_id]
        post_target = post_state.entities[out.target_id]
        save_str = "SAVED" if out.save.success else "FAILED"
        seg = (
            f"{target.display_name}: {out.save.ability} save "
            f"1d20{out.save.save_mod:+d}={out.save.total} vs DC {out.save.dc}"
            f" → {save_str}"
        )
        if out.resistance_effect == "immune":
            seg += (
                f", IMMUNE to {resolution.damage_type} damage — 0 dealt"
                f" (rolled {out.damage_after_save})"
            )
        elif out.damage_applied > 0:
            notes = []
            if out.save.success:
                notes.append("halved by save")
            if out.resistance_effect == "resisted":
                notes.append("halved by resistance")
            elif out.resistance_effect == "vulnerable":
                notes.append("doubled by vulnerability")
            note_str = f" ({', '.join(notes)})" if notes else ""
            hp_after = post_target.attributes.get("hp", 0)
            seg += (
                f", takes {out.damage_applied}{type_note}{note_str}"
                f"; hp BEFORE this hit: {out.target_hp_before},"
                f" AFTER this hit: {hp_after}"
            )
        else:
            seg += ", takes 0 damage"
        if out.applied_conditions:
            seg += f"; {target.display_name} is now {', '.join(out.applied_conditions)}"

        downed_state = _stage_downing(buffer, target, post_target, resolution, turn_id, actor_id)
        if downed_state == "dead":
            seg += f"; {target.display_name} is DOWNED (slain)"
        elif downed_state == "unconscious":
            succ, fail = _death_save_tally(buffer.project().entities[out.target_id])
            seg += (
                f"; {target.display_name} drops to 0 HP and falls UNCONSCIOUS — dying"
                f" (death saves: {succ} successes / {fail} failures)"
            )
        parts.append(seg)

    summary = "; ".join(parts) + " (use each AFTER value when describing current state)"
    return IntentOutcome(intent=intent, resolved=True, summary=summary)


def _resolve_talk(
    intent: TalkIntent,
    buffer: TurnBuffer,
    actor_id: str,
    turn_id: str,
) -> IntentOutcome:
    state = buffer.project()
    actor_loc = state.entities[actor_id].location_id
    target = state.entities.get(intent.target)
    if target is None or target.location_id != actor_loc:
        return IntentOutcome(
            intent=intent, resolved=False,
            summary=f"SKIPPED: {intent.target!r} not in scene to talk to",
        )
    if intent.target == actor_id:
        return IntentOutcome(intent=intent, resolved=False, summary="SKIPPED: cannot talk to self")
    if target.attributes.get("status") in config.NEUTRALIZED_STATUSES:
        return IntentOutcome(
            intent=intent, resolved=False,
            summary=f"SKIPPED: {intent.target!r} cannot reply (status: "
                    f"{target.attributes.get('status')})",
        )

    # B2: mark the NPC as having a pending response turn. The scheduler
    # will pick them next tick instead of rotating to the next PC. The
    # value field is unused — the event's own seq is what the scheduler
    # compares against the NPC's last-turn seq.
    if target.kind == "npc":
        buffer.stage(
            AttributeSet(
                entity_id=target.entity_id,
                attr=config.PENDING_NPC_RESPONSE_ATTR,
                value=True,
            ),
            EventCause(kind="dm_action", turn_id=turn_id, player_id=actor_id),
        )

    return IntentOutcome(
        intent=intent, resolved=True,
        summary=f"spoke to {target.display_name}: \"{intent.speech}\"",
    )


# ---------------------------------------------------------------------------
# M9 resolvers — check, use_item, puzzle_answer
# ---------------------------------------------------------------------------


def _resolve_check(
    intent: CheckIntent,
    buffer: TurnBuffer,
    actor_id: str,
    turn_id: str,
    rng: random.Random,
    mechanics: MechanicsProvider,
) -> IntentOutcome:
    """Roll `1d20 + actor.attributes[stat]` against a DC derived from
    the target. DC lookup order (first match wins):
      1. target.attributes[f"{purpose}_dc"] (entities/locations)
      2. target.properties[f"{purpose}_dc"] (items)
      3. target.properties["lock_dc"] (items)
      4. target.properties["dc"]        (items)
      5. target.attributes["dc"]        (entities/locations)
    No DC → SKIPPED."""
    state = buffer.project()
    actor = state.entities.get(actor_id)
    if actor is None:
        return IntentOutcome(
            intent=intent, resolved=False,
            summary=f"SKIPPED: actor {actor_id!r} not found",
        )

    target_id = intent.target
    target_attrs: dict = {}
    target_props: dict = {}
    target_kind: str | None = None
    if target_id in state.entities:
        target_attrs = state.entities[target_id].attributes
        target_kind = "entity"
    elif target_id in state.items:
        target_props = state.items[target_id].properties
        target_kind = "item"
    elif target_id in state.locations:
        target_attrs = state.locations[target_id].attributes
        target_kind = "location"
    else:
        return IntentOutcome(
            intent=intent, resolved=False,
            summary=f"SKIPPED: target {target_id!r} not found",
        )

    dc = _derive_dc(intent.purpose, target_attrs, target_props)
    if dc is None:
        return IntentOutcome(
            intent=intent, resolved=False,
            summary=f"SKIPPED: no DC on target {target_id!r} for purpose {intent.purpose!r}",
        )

    resolution, payloads = mechanics.resolve_check(
        actor, target_id, intent.stat, dc, rng, purpose=intent.purpose,
    )
    for payload in payloads:
        cause_kind = "dice_resolution" if isinstance(payload, DiceRolled) else "dm_action"
        buffer.stage(payload, EventCause(kind=cause_kind, turn_id=turn_id, player_id=actor_id))

    result_str = "SUCCESS" if resolution.success else "FAILURE"
    roll_str = resolution.roll_text or (
        f"1d20{resolution.stat_mod:+d}={resolution.total} vs DC {dc}"
    )
    summary = (
        f"check {intent.purpose!r} ({intent.stat}) on {target_id} ({target_kind}): "
        f"{roll_str} → {result_str}"
    )
    return IntentOutcome(intent=intent, resolved=True, summary=summary)


def _derive_dc(
    purpose: str,
    target_attrs: dict,
    target_props: dict,
) -> int | None:
    candidates: list = []
    if purpose:
        candidates.append(target_attrs.get(f"{purpose}_dc"))
        candidates.append(target_props.get(f"{purpose}_dc"))
    candidates.append(target_props.get("lock_dc"))
    candidates.append(target_props.get("dc"))
    candidates.append(target_attrs.get("dc"))
    for v in candidates:
        if isinstance(v, int) and not isinstance(v, bool):
            return v
    return None


def _resolve_use_item(
    intent: UseItemIntent,
    buffer: TurnBuffer,
    actor_id: str,
    turn_id: str,
    rng: random.Random,
    mechanics: MechanicsProvider,
) -> IntentOutcome:
    """Dispatch on `item.properties["use"]`. Supported handlers:
      - "heal":   roll heal_formula, AttributeDelta(target, hp, +rolled);
                  optional InventoryRemoved if consumable.
      - "lockpicking": triggers an implicit check (dex_mod vs lock_dc);
                  success records AttributeSet(actor, f"unlocked_{tgt}", True).
    (Picking up items is now its own intent — see _resolve_pickup.)"""
    state = buffer.project()
    actor = state.entities.get(actor_id)
    if actor is None:
        return IntentOutcome(
            intent=intent, resolved=False,
            summary=f"SKIPPED: actor {actor_id!r} not found",
        )

    item = state.items.get(intent.item)
    if item is None:
        return IntentOutcome(
            intent=intent, resolved=False,
            summary=f"SKIPPED: item {intent.item!r} not found",
        )

    # Item must be either in actor's inventory OR on the ground in the
    # actor's room (for pickup-style uses like the Heartstone).
    from_ground = False
    if intent.item in actor.inventory:
        from_ground = False
    elif item.location_id == actor.location_id:
        from_ground = True
    else:
        return IntentOutcome(
            intent=intent, resolved=False,
            summary=f"SKIPPED: item {intent.item!r} not in inventory or scene",
        )

    target_id = intent.target if intent.target is not None else actor_id
    use_kind = item.properties.get("use")
    if not isinstance(use_kind, str) or not use_kind:
        return IntentOutcome(
            intent=intent, resolved=False,
            summary=f"SKIPPED: item {item.item_id!r} has no 'use' property",
        )

    if use_kind == "heal":
        return _use_item_heal(intent, item, actor_id, target_id, buffer, turn_id, rng, from_ground)
    if use_kind == "lockpicking":
        return _use_item_lockpicking(intent, item, actor_id, target_id, buffer, turn_id, rng, mechanics)

    return IntentOutcome(
        intent=intent, resolved=False,
        summary=f"SKIPPED: unknown use kind {use_kind!r} on item {item.item_id}",
    )


def _use_item_heal(
    intent: UseItemIntent,
    item,
    actor_id: str,
    target_id: str,
    buffer: TurnBuffer,
    turn_id: str,
    rng: random.Random,
    from_ground: bool,
) -> IntentOutcome:
    state = buffer.project()
    target = state.entities.get(target_id)
    if target is None:
        return IntentOutcome(
            intent=intent, resolved=False,
            summary=f"SKIPPED: heal target {target_id!r} not found",
        )
    actor_loc = state.entities[actor_id].location_id
    if target_id != actor_id and target.location_id != actor_loc:
        return IntentOutcome(
            intent=intent, resolved=False,
            summary=f"SKIPPED: heal target {target_id!r} not in scene",
        )

    formula = item.properties.get("heal_formula", "1d8")
    if not isinstance(formula, str):
        return IntentOutcome(
            intent=intent, resolved=False,
            summary=f"SKIPPED: item {item.item_id} has no valid heal_formula",
        )
    roll = roll_detailed(formula, rng)
    rolled = roll.total

    hp_current = target.attributes.get("hp", 0)
    max_hp = target.attributes.get("max_hp", hp_current)
    if isinstance(hp_current, (int, float)) and isinstance(max_hp, (int, float)):
        amount = max(0, min(rolled, int(max_hp) - int(hp_current)))
    else:
        amount = rolled

    buffer.stage(
        DiceRolled(
            formula=formula, result=rolled,
            reason=f"heal: {actor_id} uses {item.item_id} on {target_id}",
        ),
        EventCause(kind="dice_resolution", turn_id=turn_id, player_id=actor_id),
    )
    if amount > 0:
        buffer.stage(
            AttributeDelta(entity_id=target_id, attr="hp", delta=amount),
            EventCause(kind="dm_action", turn_id=turn_id, player_id=actor_id),
        )

    # Consume the item if it's a one-shot held in inventory. Two seed
    # idioms count as one-shot:
    #   - `consumable: true`            — explicit flag (shop potions etc.)
    #   - `uses_remaining: 1` (or 0)    — last charge; seed convention for
    #                                     PC-starter consumables like
    #                                     Brakka's healing potion.
    # uses_remaining > 1 is meant to indicate multi-use items (healer's
    # kit), but the closed M1 payload vocab has no way to mutate an
    # item's properties mid-flight. Today those items stay un-decremented
    # — a known limitation that needs a schema extension to fix
    # properly. For now they remain in inventory and can be used again
    # next turn, which is wrong but at least bounded.
    uses_remaining = item.properties.get("uses_remaining")
    one_shot_by_uses = (
        isinstance(uses_remaining, int)
        and not isinstance(uses_remaining, bool)
        and uses_remaining <= 1
    )
    is_one_shot = bool(item.properties.get("consumable", False)) or one_shot_by_uses
    if not from_ground and is_one_shot:
        buffer.stage(
            InventoryRemoved(entity_id=actor_id, item_id=item.item_id),
            EventCause(kind="dm_action", turn_id=turn_id, player_id=actor_id),
        )

    hp_after = (int(hp_current) + amount) if isinstance(hp_current, (int, float)) else "?"

    # M12: healing a downed PC above 0 revives them — clear the unconscious
    # condition + death-save tally and bring them back to "alive". (A dead PC
    # is NOT revived by a potion; only unconscious/stable.)
    revived = False
    if (
        target.attributes.get("status") in ("unconscious", "stable")
        and isinstance(hp_after, int) and hp_after > 0
    ):
        revive_cause = EventCause(kind="dm_action", turn_id=turn_id, player_id=actor_id)
        buffer.stage(AttributeSet(entity_id=target_id, attr="status", value="alive"), revive_cause)
        buffer.stage(
            AttributeSet(entity_id=target_id, attr="conditions",
                         value=sorted(entity_conditions(target) - {"unconscious"})),
            revive_cause,
        )
        buffer.stage(AttributeSet(entity_id=target_id, attr="death_save_successes", value=0), revive_cause)
        buffer.stage(AttributeSet(entity_id=target_id, attr="death_save_failures", value=0), revive_cause)
        revived = True

    summary = (
        f"used {item.name} on {target_id}: rolled {formula}={rolled}; "
        f"healed {amount}; {target.display_name} hp {hp_current} → {hp_after}"
    )
    if revived:
        summary += f"; {target.display_name} is revived (conscious again)"
    return IntentOutcome(intent=intent, resolved=True, summary=summary)


def _use_item_lockpicking(
    intent: UseItemIntent,
    item,
    actor_id: str,
    target_id: str,
    buffer: TurnBuffer,
    turn_id: str,
    rng: random.Random,
    mechanics: MechanicsProvider,
) -> IntentOutcome:
    state = buffer.project()
    target = state.items.get(target_id) or state.entities.get(target_id) or state.locations.get(target_id)
    if target is None:
        return IntentOutcome(
            intent=intent, resolved=False,
            summary=f"SKIPPED: lockpick target {target_id!r} not found",
        )

    target_props = getattr(target, "properties", {}) or {}
    target_attrs = getattr(target, "attributes", {}) or {}
    dc = _derive_dc("lock", target_attrs, target_props)
    if dc is None:
        return IntentOutcome(
            intent=intent, resolved=False,
            summary=f"SKIPPED: no lock_dc on {target_id!r}",
        )

    stat = item.properties.get("check_stat", "dex_mod")
    actor = state.entities[actor_id]
    resolution, payloads = mechanics.resolve_check(actor, target_id, stat, dc, rng, purpose="lockpicking")
    for payload in payloads:
        cause_kind = "dice_resolution" if isinstance(payload, DiceRolled) else "dm_action"
        buffer.stage(payload, EventCause(kind=cause_kind, turn_id=turn_id, player_id=actor_id))

    if resolution.success:
        buffer.stage(
            AttributeSet(entity_id=actor_id, attr=f"unlocked_{target_id}", value=True),
            EventCause(kind="dm_action", turn_id=turn_id, player_id=actor_id),
        )
        result_str = "UNLOCKED"
    else:
        result_str = "FAILED"

    roll_str = resolution.roll_text or (
        f"1d20{resolution.stat_mod:+d}={resolution.total} vs DC {dc}"
    )
    summary = f"used {item.name} on {target_id}: {roll_str} → {result_str}"
    return IntentOutcome(intent=intent, resolved=True, summary=summary)


def _resolve_puzzle_answer(
    intent: PuzzleAnswerIntent,
    buffer: TurnBuffer,
    actor_id: str,
    turn_id: str,
) -> IntentOutcome:
    """Compare the player's answer (case-insensitive) against the
    authored `puzzle_answer` on the target. Match → AttributeSet(
    actor, f"solved_{target_id}", True). Mismatch → SKIPPED."""
    state = buffer.project()
    target_id = intent.target

    authored: str | None = None
    target_kind: str | None = None
    if target_id in state.locations:
        candidate = state.locations[target_id].attributes.get("puzzle_answer")
        if isinstance(candidate, str):
            authored = candidate
            target_kind = "location"
    if authored is None and target_id in state.items:
        candidate = state.items[target_id].properties.get("puzzle_answer")
        if isinstance(candidate, str):
            authored = candidate
            target_kind = "item"

    if authored is None:
        return IntentOutcome(
            intent=intent, resolved=False,
            summary=f"SKIPPED: no puzzle_answer on {target_id!r}",
        )

    if _puzzle_answer_matches(intent.answer, authored):
        buffer.stage(
            AttributeSet(entity_id=actor_id, attr=f"solved_{target_id}", value=True),
            EventCause(kind="dm_action", turn_id=turn_id, player_id=actor_id),
        )
        return IntentOutcome(
            intent=intent, resolved=True,
            summary=f"answered puzzle on {target_id} ({target_kind}) correctly: {intent.answer!r}",
        )
    return IntentOutcome(
        intent=intent, resolved=False,
        summary=f"SKIPPED: wrong answer {intent.answer!r} for {target_id}",
    )


# ---------------------------------------------------------------------------
# pickup (M9 follow-up: generic pickup verb replacing the use_item
# "pickup_with_seal" special-case)
# ---------------------------------------------------------------------------


# Item `properties.type` values that represent fixtures or containers
# the player cannot lift and walk off with. Pickup is rejected for
# these. Everything else (weapon, armor, consumable, currency, gear,
# tool, lore, objective, light) is implicitly takeable.
_NON_PICKUPABLE_TYPES = frozenset({"container", "lock", "fixture"})


def _stage_currency_collection(
    buffer: TurnBuffer,
    actor_id: str,
    item,
    cause: EventCause,
) -> str:
    """Stage AttributeDelta for collecting a currency-type item (a pile
    of coin / silver ore / etc.). The item itself is not added to
    inventory — its value is absorbed into the actor's currency
    attribute. Returns a "+N currency" summary fragment for the
    caller's narration."""
    amount = item.properties.get("amount", 0)
    currency = item.properties.get("currency", "coin")
    if not (isinstance(currency, str) and currency):
        currency = "coin"
    if not (isinstance(amount, int) and not isinstance(amount, bool) and amount > 0):
        return f"(0 {currency} — empty pile)"
    buffer.stage(
        AttributeDelta(entity_id=actor_id, attr=currency, delta=amount),
        cause,
    )
    return f"+{amount} {currency}"


def _resolve_pickup(
    intent: PickupIntent,
    buffer: TurnBuffer,
    actor_id: str,
    turn_id: str,
) -> IntentOutcome:
    """Generic pickup: add an item from the actor's current room to
    inventory. Optional side-effects authored on `item.properties.on_pickup`:
      - `start_countdown: {"attribute": <attr>, "turns": <int>}`
        → AttributeSet(actor, attr, turns)
      - `seal_location: <loc_id>`
        → AttributeSet(actor, f"sealed_{loc_id}", True) (recorded on
          actor because the closed payload vocab can't mutate locations)
    """
    state = buffer.project()
    actor = state.entities.get(actor_id)
    if actor is None:
        return IntentOutcome(
            intent=intent, resolved=False,
            summary=f"SKIPPED: actor {actor_id!r} not found",
        )

    item = state.items.get(intent.target)
    if item is None:
        return IntentOutcome(
            intent=intent, resolved=False,
            summary=f"SKIPPED: item {intent.target!r} not found",
        )

    if intent.target in actor.inventory:
        return IntentOutcome(
            intent=intent, resolved=False,
            summary=f"SKIPPED: {intent.target!r} is already in your inventory",
        )

    if item.location_id != actor.location_id:
        return IntentOutcome(
            intent=intent, resolved=False,
            summary=f"SKIPPED: {intent.target!r} is not in this room",
        )

    item_type = item.properties.get("type")
    if isinstance(item_type, str) and item_type in _NON_PICKUPABLE_TYPES:
        return IntentOutcome(
            intent=intent, resolved=False,
            summary=f"SKIPPED: {intent.target!r} is a {item_type} — cannot be picked up",
        )

    cause = EventCause(kind="dm_action", turn_id=turn_id, player_id=actor_id)

    # Currency-type items are not inventory objects — they're piles of
    # money you collect. Convert their `amount` into AttributeDelta on
    # the actor's currency balance and skip the InventoryAdded.
    if item.properties.get("type") == "currency":
        currency_summary = _stage_currency_collection(buffer, actor_id, item, cause)
        summary = f"collected {item.name} ({item.item_id}): {currency_summary}"
        return IntentOutcome(intent=intent, resolved=True, summary=summary)

    buffer.stage(InventoryAdded(entity_id=actor_id, item_id=item.item_id), cause)

    side_effects: list[str] = []
    on_pickup = item.properties.get("on_pickup")
    if isinstance(on_pickup, dict):
        countdown = on_pickup.get("start_countdown")
        if isinstance(countdown, dict):
            attr_name = countdown.get("attribute")
            turns = countdown.get("turns")
            if (
                isinstance(attr_name, str) and attr_name
                and isinstance(turns, int) and not isinstance(turns, bool)
            ):
                buffer.stage(
                    AttributeSet(entity_id=actor_id, attr=attr_name, value=turns),
                    cause,
                )
                side_effects.append(f"started countdown {attr_name}={turns}")
        seal_loc = on_pickup.get("seal_location")
        if isinstance(seal_loc, str) and seal_loc:
            buffer.stage(
                AttributeSet(entity_id=actor_id, attr=f"sealed_{seal_loc}", value=True),
                cause,
            )
            side_effects.append(f"sealed {seal_loc}")

    summary = f"picked up {item.name} ({item.item_id})"
    if side_effects:
        summary += "; " + "; ".join(side_effects)
    return IntentOutcome(intent=intent, resolved=True, summary=summary)


# ---------------------------------------------------------------------------
# give (M9 follow-up: atomic one-way item transfer)
# ---------------------------------------------------------------------------


def _resolve_give(
    intent: GiveIntent,
    buffer: TurnBuffer,
    actor_id: str,
    turn_id: str,
) -> IntentOutcome:
    """Transfer an item from the actor's inventory to another entity in
    the same room. Stages InventoryRemoved + InventoryAdded atomically.
    Marks the recipient with a pending-response marker if they are an
    NPC, so the scheduler queues them for a reaction turn."""
    state = buffer.project()
    actor = state.entities.get(actor_id)
    target = state.entities.get(intent.target)
    item = state.items.get(intent.item)

    if actor is None:
        return IntentOutcome(intent=intent, resolved=False,
                             summary=f"SKIPPED: actor {actor_id!r} not found")
    if target is None:
        return IntentOutcome(intent=intent, resolved=False,
                             summary=f"SKIPPED: recipient {intent.target!r} not found")
    if item is None:
        return IntentOutcome(intent=intent, resolved=False,
                             summary=f"SKIPPED: item {intent.item!r} not found")
    if intent.target == actor_id:
        return IntentOutcome(intent=intent, resolved=False,
                             summary="SKIPPED: cannot give to self")
    if intent.item not in actor.inventory:
        return IntentOutcome(intent=intent, resolved=False,
                             summary=f"SKIPPED: {intent.item!r} not in your inventory")
    if target.location_id != actor.location_id:
        return IntentOutcome(intent=intent, resolved=False,
                             summary=f"SKIPPED: {intent.target!r} not in this room")
    if target.attributes.get("status") in config.NEUTRALIZED_STATUSES:
        return IntentOutcome(
            intent=intent, resolved=False,
            summary=f"SKIPPED: {intent.target!r} cannot receive (status: "
                    f"{target.attributes.get('status')})",
        )

    cause = EventCause(kind="dm_action", turn_id=turn_id, player_id=actor_id)
    buffer.stage(InventoryRemoved(entity_id=actor_id, item_id=intent.item), cause)
    buffer.stage(InventoryAdded(entity_id=intent.target, item_id=intent.item), cause)

    # If the recipient is an NPC, queue them for a response (same
    # mechanism as <talk>). Merchants need this to react with their
    # own give; conversational NPCs to acknowledge the gift in
    # character.
    if target.kind == "npc":
        buffer.stage(
            AttributeSet(
                entity_id=target.entity_id,
                attr=config.PENDING_NPC_RESPONSE_ATTR,
                value=True,
            ),
            cause,
        )

    return IntentOutcome(
        intent=intent, resolved=True,
        summary=f"gave {item.name} ({intent.item}) to {target.display_name}",
    )


# ---------------------------------------------------------------------------
# open (M9 follow-up: container access)
# ---------------------------------------------------------------------------


def _resolve_open(
    intent: OpenIntent,
    buffer: TurnBuffer,
    actor_id: str,
    turn_id: str,
) -> IntentOutcome:
    """Open a container in the actor's room and transfer its contents
    into the actor's inventory. Containers must have `properties.type
    == "container"`. If `properties.locked == True`, the actor needs a
    prior `unlocked_<container_id>` attribute from a successful
    lockpicking check."""
    state = buffer.project()
    actor = state.entities.get(actor_id)
    target = state.items.get(intent.target)

    if actor is None:
        return IntentOutcome(intent=intent, resolved=False,
                             summary=f"SKIPPED: actor {actor_id!r} not found")
    if target is None:
        return IntentOutcome(intent=intent, resolved=False,
                             summary=f"SKIPPED: container {intent.target!r} not found")
    if target.location_id != actor.location_id:
        return IntentOutcome(intent=intent, resolved=False,
                             summary=f"SKIPPED: {intent.target!r} not in this room")
    if target.properties.get("type") != "container":
        return IntentOutcome(
            intent=intent, resolved=False,
            summary=f"SKIPPED: {intent.target!r} is not a container",
        )
    if target.properties.get("locked"):
        unlocked = actor.attributes.get(f"unlocked_{target.item_id}")
        if not unlocked:
            return IntentOutcome(
                intent=intent, resolved=False,
                summary=f"SKIPPED: {target.name} is locked (pick the lock first)",
            )

    cause = EventCause(kind="dm_action", turn_id=turn_id, player_id=actor_id)

    # Mark the container as opened by this actor — replay-stable record.
    buffer.stage(
        AttributeSet(
            entity_id=actor_id, attr=f"opened_{target.item_id}", value=True,
        ),
        cause,
    )

    contents = target.properties.get("contents", [])
    if not isinstance(contents, list):
        return IntentOutcome(
            intent=intent, resolved=True,
            summary=f"opened {target.name} — but contents list is malformed",
        )

    transferred: list[str] = []
    for content_id in contents:
        if not isinstance(content_id, str):
            continue
        content_item = state.items.get(content_id)
        if content_item is None:
            continue
        # Currency-type contents (gold piles inside a chest) absorb into
        # the actor's currency attribute, not inventory.
        if content_item.properties.get("type") == "currency":
            currency_note = _stage_currency_collection(
                buffer, actor_id, content_item, cause,
            )
            transferred.append(f"{content_id} ({currency_note})")
            continue
        buffer.stage(
            InventoryAdded(entity_id=actor_id, item_id=content_id), cause,
        )
        transferred.append(content_id)

    if transferred:
        summary = (
            f"opened {target.name} ({intent.target}); collected: "
            f"{', '.join(transferred)}"
        )
    else:
        summary = f"opened {target.name} ({intent.target}); it was empty"
    return IntentOutcome(intent=intent, resolved=True, summary=summary)


# ---------------------------------------------------------------------------
# trade (M9 follow-up: NPC-mediated atomic exchange)
# ---------------------------------------------------------------------------


def _resolve_trade(
    intent: TradeIntent,
    buffer: TurnBuffer,
    actor_id: str,
    turn_id: str,
) -> IntentOutcome:
    """Buy a priced item from a merchant. Reads price+currency off the
    target item's properties. Validates the actor's currency-attribute
    balance, then atomically stages the AttributeDelta payments + the
    item transfer."""
    state = buffer.project()
    actor = state.entities.get(actor_id)
    target = state.entities.get(intent.target)
    want_item = state.items.get(intent.want)

    if actor is None:
        return IntentOutcome(intent=intent, resolved=False,
                             summary=f"SKIPPED: actor {actor_id!r} not found")
    if target is None:
        return IntentOutcome(intent=intent, resolved=False,
                             summary=f"SKIPPED: trader {intent.target!r} not found")
    if want_item is None:
        return IntentOutcome(intent=intent, resolved=False,
                             summary=f"SKIPPED: item {intent.want!r} not found")
    if intent.target == actor_id:
        return IntentOutcome(intent=intent, resolved=False,
                             summary="SKIPPED: cannot trade with self")
    if target.location_id != actor.location_id:
        return IntentOutcome(intent=intent, resolved=False,
                             summary=f"SKIPPED: {intent.target!r} not in this room")
    if intent.want not in target.inventory:
        return IntentOutcome(
            intent=intent, resolved=False,
            summary=f"SKIPPED: {target.display_name} does not have {intent.want!r}",
        )
    if target.attributes.get("status") in config.NEUTRALIZED_STATUSES:
        return IntentOutcome(
            intent=intent, resolved=False,
            summary=f"SKIPPED: {intent.target!r} cannot trade (status: "
                    f"{target.attributes.get('status')})",
        )

    price = want_item.properties.get("price")
    if not (isinstance(price, int) and not isinstance(price, bool) and price >= 0):
        return IntentOutcome(
            intent=intent, resolved=False,
            summary=f"SKIPPED: {intent.want!r} is not for sale (no price)",
        )
    currency = want_item.properties.get("currency", "coin")
    if not isinstance(currency, str) or not currency:
        currency = "coin"

    balance = actor.attributes.get(currency, 0)
    if not (isinstance(balance, int) and not isinstance(balance, bool)):
        balance = 0
    if balance < price:
        return IntentOutcome(
            intent=intent, resolved=False,
            summary=f"SKIPPED: need {price} {currency}; you have {balance}",
        )

    cause = EventCause(kind="dm_action", turn_id=turn_id, player_id=actor_id)
    # Atomic 4-event purchase. All ride the same buffer commit — if
    # narration later fails, the whole purchase rolls back.
    buffer.stage(AttributeDelta(entity_id=actor_id, attr=currency, delta=-price), cause)
    buffer.stage(AttributeDelta(entity_id=intent.target, attr=currency, delta=price), cause)
    buffer.stage(InventoryRemoved(entity_id=intent.target, item_id=intent.want), cause)
    buffer.stage(InventoryAdded(entity_id=actor_id, item_id=intent.want), cause)

    return IntentOutcome(
        intent=intent, resolved=True,
        summary=f"bought {want_item.name} ({intent.want}) from "
                f"{target.display_name} for {price} {currency}",
    )


def _puzzle_answer_matches(submitted: str, authored: str) -> bool:
    """Case-insensitive puzzle-answer match tolerant of leading English
    articles. Returns True if `authored` (normalized) appears anywhere
    in `submitted` (normalized) as a substring. This handles natural
    English answering: "An echo" matches authored "echo", "the truth"
    matches authored "truth", "I think it's an echo" matches "echo".

    Conservative — only matches the authored answer as a substring, so
    a player saying "fish" doesn't accidentally solve a riddle whose
    answer is "fishhook" the other way around."""
    def _normalize(s: str) -> str:
        s = s.strip().lower()
        for article in ("the ", "an ", "a "):
            if s.startswith(article):
                s = s[len(article):]
                break
        return s

    return _normalize(authored) in _normalize(submitted)


def _is_in_scope(target_id: str, state: WorldState, actor_id: str, location_id: str) -> bool:
    """Look/Examine target must be: the current location, an entity in
    this location, an item in this location, or an item in inventory."""
    if target_id == location_id:
        return True
    entity = state.entities.get(target_id)
    if entity is not None and entity.location_id == location_id:
        return True
    item = state.items.get(target_id)
    if item is not None and item.location_id == location_id:
        return True
    actor = state.entities.get(actor_id)
    if actor is not None and target_id in actor.inventory:
        return True
    return False


# ---------------------------------------------------------------------------
# Auto combat_start (M8 — runner-decided)
# ---------------------------------------------------------------------------


def _stage_combat_start_auto(
    buffer: TurnBuffer,
    actor_id: str,
    target_id: str,
    location_id: str,
    turn_id: str,
    rng: random.Random,
) -> None:
    """Auto-stage CombatStart + initiative dice when an attack just
    landed a hit while combat was not yet on. Called only when
    pre_mode == "exploration" — once combat is active, new joiners
    flow through `_stage_combat_join_auto` instead so the existing
    fight isn't restarted.

    Initial participant set is the union of:
      - the attacking actor
      - the explicit target (the hostile they just hit)
      - every PC in the world (regardless of location) — they are all
        "in the fight" abstractly; ones in other rooms simply act in
        their own scenes during their initiative slots. This means a
        PC who walks into the combat room later is already in
        initiative order, not bolted on as an afterthought.
      - every LIVE hostile NPC in the actor's room
    Friendly NPCs (Aldous, Hessa) are deliberately excluded. Dead
    entities are also excluded — once combat begins, dead participants
    serve no purpose in the order. (Pre-fix, a freshly-killed hostile
    in the same room got added with status='dead'; that was rolled
    forward into wasted initiative slots and confused tie-break.)"""
    state = buffer.project()
    participants: list[str] = [actor_id]
    if target_id != actor_id and target_id in state.entities:
        if target_id not in participants:
            participants.append(target_id)
    # All PCs join from the start, even ones not in the room.
    for eid, entity in state.entities.items():
        if entity.kind != "pc":
            continue
        if eid in participants:
            continue
        participants.append(eid)
    # Live hostiles in the room round out the opposing side.
    for eid, entity in state.entities.items():
        if eid in participants:
            continue
        if entity.location_id != location_id:
            continue
        if entity.kind != "npc":
            continue
        if entity.attributes.get("status") != "hostile":
            continue
        participants.append(eid)

    transition_cause = EventCause(kind="combat_transition", turn_id=turn_id, player_id=actor_id)
    dice_cause = EventCause(kind="dice_resolution", turn_id=turn_id, player_id=actor_id)
    buffer.stage(CombatStart(participants=list(participants)), transition_cause)

    for pid in participants:
        _stage_initiative_roll(buffer, state, pid, rng, dice_cause)


def _stage_combat_join_auto(
    buffer: TurnBuffer,
    actor_id: str,
    target_id: str,
    location_id: str,
    turn_id: str,
    rng: random.Random,
) -> None:
    """Mid-combat join. Called when an attack lands during an active
    combat. Adds the actor and the explicit target to the combat's
    participant roster via CombatParticipantsAdded, plus rolls
    initiative for whichever ones were not already participants.

    Existing participants are unaffected — no fresh CombatStart, no
    reset of round counting, no re-roll of existing initiative.
    Friendly NPCs in the room are still excluded. Dead entities are
    not added.

    This is the path that breaks the M9 "two simultaneous fights"
    failure mode where killing one hostile prematurely ended combat
    and a subsequent attack on a different hostile incorrectly fired
    a fresh CombatStart (which re-included dead participants in
    initiative and made round counting inconsistent)."""
    state = buffer.project()
    existing = _current_participants_with_staged(buffer)

    new_participants: list[str] = []
    for pid in (actor_id, target_id):
        if pid in existing or pid in new_participants:
            continue
        entity = state.entities.get(pid)
        if entity is None:
            continue
        # Don't add the dead — they have nothing to do in combat.
        if entity.attributes.get("status") in config.NEUTRALIZED_STATUSES:
            continue
        new_participants.append(pid)

    if not new_participants:
        return

    transition_cause = EventCause(kind="combat_transition", turn_id=turn_id, player_id=actor_id)
    dice_cause = EventCause(kind="dice_resolution", turn_id=turn_id, player_id=actor_id)
    buffer.stage(CombatParticipantsAdded(participants=list(new_participants)), transition_cause)
    for pid in new_participants:
        _stage_initiative_roll(buffer, state, pid, rng, dice_cause)


def _stage_initiative_roll(
    buffer: TurnBuffer,
    state: WorldState,
    pid: str,
    rng: random.Random,
    cause: EventCause,
) -> None:
    """Roll 1d20+dex_mod for `pid`; stage the DiceRolled event with
    the scheduler-required `initiative: <id>` reason format."""
    entity = state.entities.get(pid)
    dex_mod = 0
    if entity is not None:
        raw = entity.attributes.get("dex_mod", 0)
        if isinstance(raw, int) and not isinstance(raw, bool):
            dex_mod = raw
    formula = _format_d20_formula(dex_mod)
    result = _dice_roll(formula, rng)
    buffer.stage(
        DiceRolled(
            formula=formula,
            result=result,
            reason=f"initiative: {pid}",
        ),
        cause,
    )


def _current_participants_with_staged(buffer: TurnBuffer) -> set[str]:
    """Return the active combat participants, accounting for any
    CombatStart / CombatParticipantsAdded already staged in this turn
    (so a turn that fires multiple joins doesn't re-add the same id)."""
    events = list(buffer._log.events())
    # Project the buffer's staged payloads onto a synthetic event list
    # the scheduler can read.
    next_seq = len(events)
    for i, (payload, cause) in enumerate(buffer._staged):
        events.append(Event(
            seq=next_seq + i, timestamp=0.0, cause=cause, payload=payload,
        ))
    cs_idx = scheduler._last_combat_start_idx(events)
    if cs_idx is None:
        return set()
    return set(scheduler._active_participants(events, cs_idx))


def _format_d20_formula(mod: int) -> str:
    if mod == 0:
        return "1d20"
    return f"1d20{mod:+d}"


# ---------------------------------------------------------------------------
# Combat end (unchanged from M5)
# ---------------------------------------------------------------------------


def _maybe_emit_combat_end(log: EventLog, turn_id: str, actor_id: str) -> None:
    if scheduler.should_end_combat(log.events()):
        log.append(
            CombatEnd(),
            EventCause(kind="combat_transition", turn_id=turn_id, player_id=actor_id),
        )


def _collect_recent_talks_to(
    log: EventLog,
    npc_id: str,
    state: WorldState,
    limit: int = 5,
) -> list[tuple[str, str]]:
    """M9: walk the log for recent PlayerAction events in the NPC's
    current location. Returns (speaker_display_name, text) pairs — the
    conversational context surfaced to the NPC prompt. The TalkIntent
    payload class doesn't exist in the closed vocab; co-located prose
    is the next-best signal."""
    npc = state.entities.get(npc_id)
    if npc is None:
        return []
    target_loc = npc.location_id
    # Only the LAST `limit` matches are wanted — walk backward and stop
    # as soon as we have them, instead of scanning the whole log forward.
    out: list[tuple[str, str]] = []
    for e in reversed(log.events()):
        if not isinstance(e.payload, PlayerAction):
            continue
        if e.payload.location_id != target_loc:
            continue
        speaker = state.entities.get(e.payload.player_id)
        name = speaker.display_name if speaker else e.payload.player_id
        out.append((name, e.payload.text))
        if len(out) >= limit:
            break
    out.reverse()  # restore chronological order
    return out


def _tick_countdowns(log: EventLog, turn_id: str, actor_id: str) -> None:
    """M9: after each committed turn, walk every entity and decrement
    every `countdown_*` attribute by 1. When a countdown reaches 0,
    set the matching `countdown_..._expired` companion to True. The
    countdown itself stays at 0 (no silent erasure — replay-safe)."""
    state = project(log.events())
    cause = EventCause(kind="dm_action", turn_id=turn_id, player_id=actor_id)
    for eid, entity in state.entities.items():
        for attr_name, value in list(entity.attributes.items()):
            if not attr_name.startswith("countdown_"):
                continue
            if attr_name.endswith("_expired"):
                continue
            if not isinstance(value, int) or isinstance(value, bool):
                continue
            if value <= 0:
                continue
            new_value = value - 1
            log.append(
                AttributeSet(entity_id=eid, attr=attr_name, value=new_value),
                cause,
            )
            if new_value == 0:
                log.append(
                    AttributeSet(
                        entity_id=eid, attr=f"{attr_name}_expired", value=True,
                    ),
                    cause,
                )


def _tick_conditions(
    log: EventLog,
    turn_id: str,
    actor_id: str,
    rng: random.Random,
    mechanics: MechanicsProvider,
) -> None:
    """M12: at the end of the acting entity's own turn, resolve expiry on each
    of ITS conditions that carries a `condition_meta` spec. Two forms:

      - `{"save": {"ability", "dc"}}` (save-ends) → roll the save; on success
        the condition (and its meta) is removed. The DiceRolled is logged so
        replay is deterministic.
      - `{"duration": int}` → decrement; at <=1 the condition (and meta) is
        removed. A duration with no save just counts down.

    Conditions with NO meta entry are permanent and untouched. Ticking only the
    *actor's* conditions (not the whole world) gives the 5e cadence: a poison
    inflicted on a defender ticks down on the defender's later turns, not the
    attacker's. Mirrors `_tick_countdowns` — post-commit, appends directly."""
    state = project(log.events())
    entity = state.entities.get(actor_id)
    if entity is None:
        return
    conditions = entity_conditions(entity)
    meta = entity_condition_meta(entity)
    if not conditions or not meta:
        return

    cause = EventCause(kind="dm_action", turn_id=turn_id, player_id=actor_id)
    dice_cause = EventCause(kind="dice_resolution", turn_id=turn_id, player_id=actor_id)
    remaining = set(conditions)
    new_meta = dict(meta)

    for cond in sorted(conditions):
        spec = meta.get(cond)
        if not isinstance(spec, dict):
            continue  # permanent — no expiry

        save_spec = spec.get("save")
        if isinstance(save_spec, dict):
            ability = save_spec.get("ability")
            dc = save_spec.get("dc")
            if isinstance(ability, str) and ability and isinstance(dc, int) and not isinstance(dc, bool):
                resolution, payloads = mechanics.resolve_save(entity, ability, dc, rng)
                for payload in payloads:
                    log.append(payload, dice_cause)
                if resolution.success:
                    remaining.discard(cond)
                    new_meta.pop(cond, None)
                continue

        duration = spec.get("duration")
        if isinstance(duration, int) and not isinstance(duration, bool):
            if duration <= 1:
                remaining.discard(cond)
                new_meta.pop(cond, None)
            else:
                new_meta[cond] = {**spec, "duration": duration - 1}

    if remaining != conditions:
        log.append(AttributeSet(entity_id=actor_id, attr="conditions", value=sorted(remaining)), cause)
    if new_meta != meta:
        log.append(AttributeSet(entity_id=actor_id, attr="condition_meta", value=new_meta), cause)


# ---------------------------------------------------------------------------
# M12 death saves — downed-PC state machine
# ---------------------------------------------------------------------------
#
# An NPC dies outright at 0 HP (status="dead"). A PC instead falls
# *unconscious* and makes a death saving throw on each of its turns: 3
# successes → "stable" (out of the fight), 3 failures → "dead". Massive damage
# (overkill >= max_hp) kills a PC outright, and a hit on an already-downed PC
# is an automatic failure (two on a crit). Healing above 0, or a natural-20
# death save, revives. The unconscious *condition* (existing machinery) makes
# the PC incapacitated and grants attackers advantage for free.


def _int_attr(entity: Entity, name: str, default: int = 0) -> int:
    raw = entity.attributes.get(name, default)
    if isinstance(raw, int) and not isinstance(raw, bool):
        return raw
    return default


def _death_save_tally(entity: Entity) -> tuple[int, int]:
    """(successes, failures) on a downed entity."""
    return _int_attr(entity, "death_save_successes"), _int_attr(entity, "death_save_failures")


def is_dying_pc(entity: Entity) -> bool:
    """A PC that is unconscious at 0 HP and still resolving death saves (< 3
    successes AND < 3 failures). Exposed so a caller (the web advance loop) can
    skip LLM planning for a turn the runner will spend rolling a death save."""
    if entity.kind != "pc":
        return False
    if entity.attributes.get("status") != "unconscious":
        return False
    succ, fail = _death_save_tally(entity)
    return succ < 3 and fail < 3


def _stage_downing(
    buffer: TurnBuffer,
    target: Entity,
    post_target: Entity,
    resolution,
    turn_id: str,
    actor_id: str,
) -> str | None:
    """After damage is staged, settle the target's downed state. Returns
    "dead" | "unconscious" | None (still standing). NPCs die at 0; PCs fall
    unconscious and roll death saves."""
    cause = EventCause(kind="dm_action", turn_id=turn_id, player_id=actor_id)
    hp_after = post_target.attributes.get("hp", 0)
    if not isinstance(hp_after, (int, float)) or isinstance(hp_after, bool):
        return None
    pre_status = target.attributes.get("status")

    # A DAMAGING hit on an already-downed PC is an automatic death-save
    # failure (5e). A miss — or a hit fully soaked to 0 (immune/armor) —
    # changes nothing. Without this gate every whiffed swing at a dying PC
    # added a phantom failure (observed live: coc run 20260612, turn 28).
    if target.kind == "pc" and pre_status in ("unconscious", "stable"):
        dealt = getattr(resolution, "damage_applied", None)
        if dealt is None:
            dealt = getattr(resolution, "damage_total", None)
        if not isinstance(dealt, int) or dealt <= 0:
            return None
        return _stage_hit_while_downed(buffer, target, post_target, resolution, cause)

    if hp_after > 0:
        return None

    # NPCs just die.
    if target.kind != "pc":
        if pre_status != "dead":
            buffer.stage(AttributeSet(entity_id=target.entity_id, attr="status", value="dead"), cause)
        return "dead"

    # PC dropped to 0. Massive damage (overkill >= max_hp) = instant death.
    max_hp = post_target.attributes.get("max_hp")
    overkill = -int(hp_after)
    if isinstance(max_hp, int) and not isinstance(max_hp, bool) and overkill >= max_hp:
        buffer.stage(AttributeSet(entity_id=target.entity_id, attr="status", value="dead"), cause)
        return "dead"

    # Fall unconscious; begin death saves (and clamp hp to 0).
    buffer.stage(AttributeSet(entity_id=target.entity_id, attr="status", value="unconscious"), cause)
    buffer.stage(AttributeSet(entity_id=target.entity_id, attr="hp", value=0), cause)
    new_conditions = sorted(entity_conditions(post_target) | {"unconscious"})
    buffer.stage(AttributeSet(entity_id=target.entity_id, attr="conditions", value=new_conditions), cause)
    buffer.stage(AttributeSet(entity_id=target.entity_id, attr="death_save_successes", value=0), cause)
    buffer.stage(AttributeSet(entity_id=target.entity_id, attr="death_save_failures", value=0), cause)
    return "unconscious"


def _stage_hit_while_downed(
    buffer: TurnBuffer, target: Entity, post_target: Entity, resolution, cause: EventCause,
) -> str:
    """A downed PC taking a hit: +1 death-save failure (+2 on a crit); 3 fails →
    dead. A 'stable' PC is knocked back into 'unconscious' (dying)."""
    fails_added = 2 if getattr(resolution, "crit", False) else 1
    _, current_fail = _death_save_tally(post_target)
    new_fail = current_fail + fails_added
    buffer.stage(AttributeSet(entity_id=target.entity_id, attr="hp", value=0), cause)  # clamp
    if target.attributes.get("status") == "stable":
        buffer.stage(AttributeSet(entity_id=target.entity_id, attr="status", value="unconscious"), cause)
    if new_fail >= 3:
        buffer.stage(AttributeSet(entity_id=target.entity_id, attr="death_save_failures", value=3), cause)
        buffer.stage(AttributeSet(entity_id=target.entity_id, attr="status", value="dead"), cause)
        return "dead"
    buffer.stage(AttributeSet(entity_id=target.entity_id, attr="death_save_failures", value=new_fail), cause)
    return "unconscious"


def _run_death_save_turn(
    log: EventLog,
    pc_id: str,
    location_id: str,
    rng: random.Random,
    mechanics: MechanicsProvider,
    turn_id: str,
) -> TurnResult:
    """Spend a dying PC's turn on one death saving throw and apply the result.
    Narration is templated (no LLM call) — these beats are mechanical and we do
    not want to plan/narrate via the model for an unconscious character."""
    state = project(log.events())
    actor = state.entities[pc_id]
    name = actor.display_name
    resolution, payloads = mechanics.resolve_death_save(actor, rng)
    for payload in payloads:
        log.append(payload, EventCause(kind="dice_resolution", turn_id=turn_id, player_id=pc_id))

    cause = EventCause(kind="dm_action", turn_id=turn_id, player_id=pc_id)
    succ, fail = _death_save_tally(actor)
    roll_label = resolution.roll_text or f"d20={resolution.d20}"

    if resolution.outcome == "revive":
        log.append(AttributeSet(entity_id=pc_id, attr="hp", value=1), cause)
        log.append(AttributeSet(entity_id=pc_id, attr="status", value="alive"), cause)
        log.append(
            AttributeSet(entity_id=pc_id, attr="conditions",
                         value=sorted(entity_conditions(actor) - {"unconscious"})),
            cause,
        )
        log.append(AttributeSet(entity_id=pc_id, attr="death_save_successes", value=0), cause)
        log.append(AttributeSet(entity_id=pc_id, attr="death_save_failures", value=0), cause)
        text = (
            f"({name} makes a death saving throw: a natural 20! They surge back to "
            f"consciousness at 1 HP and can act again.)"
        )
    else:
        if resolution.outcome == "success":
            succ += 1
        elif resolution.outcome == "failure":
            fail += 1
        elif resolution.outcome == "double_failure":
            fail += 2

        if succ >= 3:
            log.append(AttributeSet(entity_id=pc_id, attr="death_save_successes", value=3), cause)
            log.append(AttributeSet(entity_id=pc_id, attr="status", value="stable"), cause)
            text = (
                f"({name} makes a death saving throw ({roll_label}): success — a third "
                f"success. {name} is STABLE, unconscious but no longer dying.)"
            )
        elif fail >= 3:
            log.append(AttributeSet(entity_id=pc_id, attr="death_save_failures", value=3), cause)
            log.append(AttributeSet(entity_id=pc_id, attr="status", value="dead"), cause)
            crit_note = "a natural 1 — two failures, and " if resolution.outcome == "double_failure" else ""
            text = (
                f"({name} makes a death saving throw ({roll_label}): {crit_note}a third "
                f"failure. {name} has died.)"
            )
        else:
            log.append(AttributeSet(entity_id=pc_id, attr="death_save_successes", value=succ), cause)
            log.append(AttributeSet(entity_id=pc_id, attr="death_save_failures", value=fail), cause)
            label = {
                "success": "success",
                "failure": "failure",
                "double_failure": "natural 1 — counts as two failures",
            }[resolution.outcome]
            text = (
                f"({name} makes a death saving throw ({roll_label}): {label}. "
                f"Death saves now {succ} successes / {fail} failures.)"
            )

    log.append(DMNarration(audience=pc_id, location_id=location_id, text=text), cause)
    _maybe_emit_combat_end(log, turn_id, pc_id)
    _tick_countdowns(log, turn_id, pc_id)
    _tick_conditions(log, turn_id, pc_id, rng, mechanics)
    return TurnResult(turn_id=turn_id, succeeded=True, fallback_beat=None)


# ---------------------------------------------------------------------------
# Helpers — fallback + measurements + debug
# ---------------------------------------------------------------------------


def _commit_fallback(
    log: EventLog,
    turn_id: str,
    actor_id: str,
    location_id: str,
    text: str,
) -> None:
    log.append(
        DMNarration(audience=actor_id, location_id=location_id, text=text),
        EventCause(kind="dm_action", turn_id=turn_id, player_id=actor_id),
    )


def _record_player_attempts(
    measurements: MeasurementSink | None,
    beat: str,
    attempts: list[PlayerAttempt],
) -> None:
    if measurements is None:
        return
    for idx, attempt in enumerate(attempts):
        measurements.record(
            beat=beat,
            chat=attempt.chat,
            parse_status=attempt.parse_status,
            error_message=attempt.error_message,
            attempt_idx=idx,
        )


def _record_narration_attempts(
    measurements: MeasurementSink | None,
    attempts: list[NarrationAttempt],
) -> None:
    if measurements is None:
        return
    for idx, attempt in enumerate(attempts):
        measurements.record(
            beat="narration",
            chat=attempt.chat,
            parse_status=attempt.parse_status,
            error_message=attempt.error_message,
            attempt_idx=idx,
        )


def _write_debug_for_player(
    path: Path | None,
    turn_id: str,
    beat: str,
    actor_id: str,
    location_id: str,
    player_text: str,
    model: str,
    attempts: list[PlayerAttempt],
) -> None:
    if path is None:
        return
    records = [
        {
            "parse_status": a.parse_status,
            "error_message": a.error_message,
            "raw_completion": a.chat.raw,
        }
        for a in attempts
    ]
    write_fallback_record(
        path,
        turn_id=turn_id, beat=beat, player_id=actor_id, location_id=location_id,
        player_text=player_text, model=model, attempts=records,
    )


def _write_debug_for_narration(
    path: Path | None,
    turn_id: str,
    actor_id: str,
    location_id: str,
    player_text: str,
    model: str,
    attempts: list[NarrationAttempt],
) -> None:
    if path is None:
        return
    records = [
        {
            "parse_status": a.parse_status,
            "error_message": a.error_message,
            "raw_completion": a.chat.raw,
        }
        for a in attempts
    ]
    write_fallback_record(
        path,
        turn_id=turn_id, beat="narration", player_id=actor_id, location_id=location_id,
        player_text=player_text, model=model, attempts=records,
    )
