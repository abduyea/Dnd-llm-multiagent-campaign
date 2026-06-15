"""
Scheduler — pure functions over the event log.

Two modes:
  - exploration: only PCs act, cycling in `pc_order` (least-recently-
    acted goes next).
  - combat: all participants of the current combat act once per round,
    in initiative order (highest 1d20+dex_mod first; ties broken by
    entity_id alphabetical for replay-stability).

The scheduler holds NO MUTABLE STATE. Replay-correctness (M1 invariant
12) is automatic: same events in → same scheduler decisions out. The
brief calls this out as load-bearing — a mutable scheduler would lose
its place across a paused-and-resumed session.

The locked gate (S4) is "each NPC acts exactly once per round, no
matter how many times provoked." It is enforced by reading turn counts
from the log itself: `cause.player_id` identifies the acting entity,
`cause.turn_id` distinguishes turns. The scheduler counts distinct
turn_ids per actor since the most recent `combat_start`.
"""
from __future__ import annotations

from typing import Literal

import config
from models import (
    AttributeSet,
    CombatEnd,
    CombatParticipantsAdded,
    CombatStart,
    DiceRolled,
    Event,
)
from projection import project


Mode = Literal["exploration", "combat"]


# ---------------------------------------------------------------------------
# Mode
# ---------------------------------------------------------------------------


def current_mode(events: list[Event]) -> Mode:
    """The most recent CombatStart / CombatEnd determines mode.
    No CombatStart anywhere → exploration. Walks backward — the first
    combat-transition event found from the end IS the most recent one."""
    for e in reversed(events):
        if isinstance(e.payload, CombatStart):
            return "combat"
        if isinstance(e.payload, CombatEnd):
            return "exploration"
    return "exploration"


# ---------------------------------------------------------------------------
# Initiative
# ---------------------------------------------------------------------------


def initiative_order(events: list[Event]) -> list[tuple[str, int]]:
    """
    Read initiative DiceRolled events from the most recent CombatStart
    onward. Return (entity_id, initiative_value) sorted by initiative
    desc, ties broken by entity_id asc.

    The brief locks this format: each initiative roll is a DiceRolled
    event with `reason` starting "initiative: <entity_id>".
    """
    cs_idx = _last_combat_start_idx(events)
    if cs_idx is None:
        return []
    rolls: list[tuple[str, int]] = []
    for e in events[cs_idx + 1:]:
        p = e.payload
        if not isinstance(p, DiceRolled):
            continue
        if not p.reason.startswith("initiative:"):
            continue
        _, _, after = p.reason.partition(":")
        eid = after.strip()
        if eid:
            rolls.append((eid, p.result))
    rolls.sort(key=lambda pair: (-pair[1], pair[0]))
    return rolls


# ---------------------------------------------------------------------------
# next_actor
# ---------------------------------------------------------------------------


def next_actor(
    events: list[Event],
    pc_order: list[str],
    state=None,
) -> str | None:
    """
    Decide whose turn is next.

    In exploration:
      - B2: NPCs with a pending response marker
        (`config.PENDING_NPC_RESPONSE_ATTR` set more recently than
        their own last turn) are scheduled FIRST, in FIFO order by
        when the marker was set. The runner emits these markers when
        a PC talks to an NPC or moves into a hostile NPC's room.
      - Else: the PC in `pc_order` who has acted least recently (or
        `pc_order[0]` if nobody has acted yet). Ties broken by
        `pc_order` index.

    In combat: the participant with the fewest distinct turn_ids since
    the most recent `combat_start`. Ties broken by initiative order
    (highest first), then entity_id alphabetical.

    M9: Neutralized actors (status in `config.NEUTRALIZED_STATUSES`)
    are skipped in both modes. If every candidate is neutralized,
    returns None.

    Returns None when there is nobody to act.

    `state` (optional) — a pre-projected WorldState for these exact
    events. Pass it when the caller has already projected (the M11
    adapter/glue path projects several times per request); omitted, the
    function projects for itself, exactly as before.
    """
    if state is None:
        state = project(events)
    neutralized = _neutralized_set(state)
    if current_mode(events) == "combat":
        return _next_combat_actor(events, neutralized)
    return _next_exploration_actor(events, pc_order, neutralized)


def _neutralized_set(state) -> set[str]:
    """Entity ids that are explicitly neutralized (skip in scheduling).
    An id not in state is NOT considered neutralized — defensive default
    for test scaffolding that uses symbolic ids."""
    return {
        eid for eid, entity in state.entities.items()
        if entity.attributes.get("status") in config.NEUTRALIZED_STATUSES
    }


def _next_exploration_actor(
    events: list[Event],
    pc_order: list[str],
    neutralized: set[str],
) -> str | None:
    # B2: pending NPC responses are scheduled BEFORE the next PC. An NPC
    # has a pending response when an AttributeSet with the pending-attr
    # was emitted on them more recently than they themselves last acted
    # (or they have never acted). The runner emits these markers when a
    # PC talks to the NPC or a PC enters a location containing a hostile
    # NPC. Order: by oldest pending-marker seq, so triggers fire FIFO.
    pending_npc = _next_pending_npc(events, neutralized)
    if pending_npc is not None:
        return pending_npc

    candidates = [pid for pid in pc_order if pid not in neutralized]
    if not candidates:
        return None
    last_seq: dict[str, int] = {}
    for e in events:
        actor = e.cause.player_id
        if actor in candidates:
            if last_seq.get(actor, -1) < e.seq:
                last_seq[actor] = e.seq
    return min(
        candidates,
        key=lambda pid: (last_seq.get(pid, -1), pc_order.index(pid)),
    )


def _next_pending_npc(events: list[Event], neutralized: set[str]) -> str | None:
    """Find the NPC (if any) with an outstanding pending-response marker
    set more recently than their own last turn. Returns None when no NPC
    is pending. FIFO across multiple pending NPCs (oldest marker first).

    The marker is an `AttributeSet(npc_id, PENDING_NPC_RESPONSE_ATTR, ...)`
    emitted by the runner; a marker is "consumed" by the NPC acting (the
    next event whose `cause.player_id == npc_id`). Walking the log
    twice — once for pending markers, once for last-turn-seq — keeps the
    rule replay-safe (no mutable scheduler state)."""
    pending_seq: dict[str, int] = {}  # npc_id → most recent pending marker seq
    last_turn_seq: dict[str, int] = {}  # actor_id → most recent turn seq
    for e in events:
        p = e.payload
        if isinstance(p, AttributeSet) and p.attr == config.PENDING_NPC_RESPONSE_ATTR:
            if pending_seq.get(p.entity_id, -1) < e.seq:
                pending_seq[p.entity_id] = e.seq
        actor = e.cause.player_id
        if actor:
            if last_turn_seq.get(actor, -1) < e.seq:
                last_turn_seq[actor] = e.seq

    fresh: list[tuple[int, str]] = []
    for npc_id, seq in pending_seq.items():
        if npc_id in neutralized:
            continue
        if last_turn_seq.get(npc_id, -1) >= seq:
            continue  # NPC has acted since the marker was set
        fresh.append((seq, npc_id))
    if not fresh:
        return None
    fresh.sort()  # FIFO: oldest pending marker first; ties by entity_id
    return fresh[0][1]


def _next_combat_actor(events: list[Event], neutralized: set[str]) -> str | None:
    cs_idx = _last_combat_start_idx(events)
    if cs_idx is None:
        return None
    participants = _active_participants(events, cs_idx)
    live_participants = [p for p in participants if p not in neutralized]
    if not live_participants:
        return None

    turns_seen = _turns_since(events, cs_idx, participants)

    # Initiative order for tie-break (highest first ⇒ rank 0 is best).
    init_rank: dict[str, int] = {}
    for rank, (eid, _) in enumerate(initiative_order(events)):
        init_rank[eid] = rank

    def sort_key(pid: str) -> tuple[int, int, str]:
        return (
            len(turns_seen[pid]),
            init_rank.get(pid, len(participants)),  # unrolled actors sort last
            pid,
        )

    return min(live_participants, key=sort_key)


# ---------------------------------------------------------------------------
# Combat end + round counting
# ---------------------------------------------------------------------------


def should_end_combat(events: list[Event]) -> bool:
    """
    Combat ends if EITHER:
      (a) All hostile NPC participants are *neutralized*: status in
          `config.NEUTRALIZED_STATUSES` (dead, fled, knocked_out,
          surrender). [M9 extension of M5's "dead-only" rule.]
      (b) `config.DISENGAGE_TURN_WINDOW` consecutive turns pass at the
          end of the log with no two combat participants sharing a
          location. [M9 disengage rule.]
    """
    if current_mode(events) != "combat":
        return False
    cs_idx = _last_combat_start_idx(events)
    if cs_idx is None:
        return False
    participants = _active_participants(events, cs_idx)

    # Path (a) — all hostile NPCs neutralized
    state = project(events)
    any_live_hostile = False
    for pid in participants:
        entity = state.entities.get(pid)
        if entity is None:
            continue
        if entity.kind != "npc":
            continue
        if entity.attributes.get("status") in config.NEUTRALIZED_STATUSES:
            continue
        any_live_hostile = True
        break
    if not any_live_hostile:
        return True

    # Path (b) — disengage: count trailing turns where no two
    # participants share a location.
    run = _disengage_turn_run_length(
        events, cs_idx, participants, cap=config.DISENGAGE_TURN_WINDOW,
    )
    if run >= config.DISENGAGE_TURN_WINDOW:
        return True

    return False


def _disengage_turn_run_length(
    events: list[Event],
    cs_idx: int,
    participants: list[str],
    cap: int | None = None,
) -> int:
    """How many of the most recent turns (since combat_start) had no
    PC participant sharing a location with any non-neutralized hostile
    participant. The semantic is "the sides aren't seeing each other"
    — opposing factions separated, not just any-two-combatants-apart.
    NPC-vs-NPC co-location does NOT block disengage.

    Walks turns newest → oldest; stops counting at the first turn
    where any PC shares a location with any live hostile.

    `cap` — stop counting once the run reaches this length. Each turn
    counted costs a full projection of the log prefix, and the only
    caller asks "is the run >= DISENGAGE_TURN_WINDOW?" — counting past
    the window paid for projections whose answer changed nothing."""
    seen_turns: list[str] = []
    seen_set: set[str] = set()
    for e in reversed(events[cs_idx + 1:]):
        tid = e.cause.turn_id
        if tid and tid not in seen_set:
            seen_turns.append(tid)
            seen_set.add(tid)

    if not seen_turns:
        return 0

    last_idx_for_turn: dict[str, int] = {}
    for idx, e in enumerate(events):
        if e.cause.turn_id:
            last_idx_for_turn[e.cause.turn_id] = idx

    run = 0
    for tid in seen_turns:  # newest first
        if cap is not None and run >= cap:
            break
        idx = last_idx_for_turn[tid]
        state = project(events[: idx + 1])

        pc_locs: set[str] = set()
        hostile_locs: set[str] = set()
        for pid in participants:
            entity = state.entities.get(pid)
            if entity is None:
                continue
            if entity.attributes.get("status") in config.NEUTRALIZED_STATUSES:
                continue  # neutralized participants don't count as "engaged"
            if entity.kind == "pc":
                pc_locs.add(entity.location_id)
            elif entity.kind == "npc":
                hostile_locs.add(entity.location_id)

        any_overlap = bool(pc_locs & hostile_locs)
        if any_overlap:
            break
        run += 1
    return run


def combat_participants(events: list[Event]) -> list[str]:
    """The active participant set for the current combat (initial roster +
    every mid-combat joiner), in first-appearance order. Empty if not in
    combat. Public wrapper so callers (e.g. the M11 web adapter building a
    combat read-out) need not reach into the private helpers."""
    cs_idx = _last_combat_start_idx(events)
    if cs_idx is None:
        return []
    return _active_participants(events, cs_idx)


def current_round(events: list[Event]) -> int:
    """0 before combat; in combat, the number of FULL rounds completed
    (= the smallest turn count across participants)."""
    if current_mode(events) != "combat":
        return 0
    cs_idx = _last_combat_start_idx(events)
    if cs_idx is None:
        return 0
    participants = _active_participants(events, cs_idx)
    if not participants:
        return 0
    turns_seen = _turns_since(events, cs_idx, participants)
    return min(len(turns_seen[pid]) for pid in participants)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _last_combat_start_idx(events: list[Event]) -> int | None:
    for i in range(len(events) - 1, -1, -1):
        if isinstance(events[i].payload, CombatStart):
            return i
    return None


def _active_participants(events: list[Event], cs_idx: int) -> list[str]:
    """The participant set for the combat that started at `cs_idx`.

    Returns the union of:
      - CombatStart.participants (the initial roster)
      - Every CombatParticipantsAdded.participants emitted since cs_idx
        (mid-combat joiners — new hostiles encountered, PCs walking
        into the fight, etc.)

    Order is preserved by first-appearance so initiative tie-breaking
    remains deterministic. Duplicates are dropped silently — a join
    event re-naming an existing participant is a no-op."""
    cs_payload = events[cs_idx].payload
    if not isinstance(cs_payload, CombatStart):
        return []
    seen: set[str] = set()
    out: list[str] = []
    for pid in cs_payload.participants:
        if pid not in seen:
            seen.add(pid)
            out.append(pid)
    for e in events[cs_idx + 1:]:
        if isinstance(e.payload, CombatParticipantsAdded):
            for pid in e.payload.participants:
                if pid not in seen:
                    seen.add(pid)
                    out.append(pid)
    return out


def _turns_since(
    events: list[Event],
    cs_idx: int,
    actors: list[str],
) -> dict[str, set[str]]:
    """Distinct turn_ids per actor in events AFTER index cs_idx."""
    seen: dict[str, set[str]] = {a: set() for a in actors}
    for e in events[cs_idx + 1:]:
        actor = e.cause.player_id
        turn_id = e.cause.turn_id
        if actor in seen and turn_id:
            seen[actor].add(turn_id)
    return seen
