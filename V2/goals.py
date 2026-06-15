"""
Party goals — render-time navigation/objective config.

Goals are NOT part of the deterministic spine. They never become events,
never enter the projection, and never affect world state — invariants 1, 2,
7, and 12 are untouched. A goal is a *derived lens* over current state:
which objective is active, whether it is complete, and (via the view
builder) which direction points toward it. This mirrors how the ruleset id
is seed config that shapes behavior without itself being an event.

A dungeon — hand- or LLM-authored — declares its goals in the seed JSON
under a top-level `party_goals` array. Each goal:

    {
      "id": "escape",
      "text": "Escape with the Heartstone by reaching the surface.",
      "target_location": "loc_surface",          # optional: hint steers here
      "requires_item_held": "item_heartstone",    # optional activation gate
      "complete_when": {"kind": "location_reached", "location": "loc_surface"}
      #   or            {"kind": "item_held", "item": "item_heartstone"}
      #   or            {"kind": "item_held_at",                       # carry it OUT
      #                  "item": "item_heartstone", "location": "loc_surface"}
    }

  - `target_location` is what the navigation hint points toward. A goal
    without one (e.g. "retrieve the X") simply gets no directional hint.
  - `requires_item_held` gates *activation*: a goal whose gate is unmet is
    still listed, but is not yet the party's active objective. This is what
    keeps the escape route hidden until someone actually holds the macguffin.
  - `complete_when` is the predicate that retires the goal so the next one
    in declared order becomes active.

The condition vocabulary is deliberately small and closed (location_reached
/ item_held / item_held_at). `item_held_at` is the "carry it OUT" predicate:
it completes only when the SAME PC both holds the item and stands at the
location — distinct from a loose `location_reached` that any empty-handed PC
could satisfy while the relic sits in someone else's pocket elsewhere.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from models import WorldState


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class GoalCondition:
    """A completion predicate. `kind` selects which optional field applies."""
    kind: str                       # "location_reached" | "item_held" | "item_held_at"
    location: str | None = None     # for location_reached / item_held_at
    item: str | None = None         # for item_held / item_held_at


@dataclass(frozen=True)
class PartyGoal:
    id: str
    text: str
    target_location: str | None = None
    requires_item_held: str | None = None
    complete_when: GoalCondition | None = None


class GoalLoadError(ValueError):
    """Raised when a `party_goals` block is malformed. Like the seed loader,
    a bad goal block is a hard error — refuse to start rather than silently
    drop objectives the dungeon author intended."""


_VALID_CONDITION_KINDS = frozenset({"location_reached", "item_held", "item_held_at"})


# ---------------------------------------------------------------------------
# Parsing / loading
# ---------------------------------------------------------------------------


def _parse_condition(raw: Any, goal_id: str) -> GoalCondition | None:
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise GoalLoadError(f"goal {goal_id!r}: complete_when must be an object")
    kind = raw.get("kind")
    if kind not in _VALID_CONDITION_KINDS:
        raise GoalLoadError(
            f"goal {goal_id!r}: complete_when.kind must be one of "
            f"{sorted(_VALID_CONDITION_KINDS)}, got {kind!r}"
        )
    cond = GoalCondition(
        kind=kind, location=raw.get("location"), item=raw.get("item")
    )
    if kind == "location_reached" and not cond.location:
        raise GoalLoadError(
            f"goal {goal_id!r}: location_reached needs a 'location'"
        )
    if kind == "item_held" and not cond.item:
        raise GoalLoadError(f"goal {goal_id!r}: item_held needs an 'item'")
    if kind == "item_held_at" and not (cond.item and cond.location):
        raise GoalLoadError(
            f"goal {goal_id!r}: item_held_at needs both 'item' and 'location'"
        )
    return cond


def parse_party_goals(raw_list: Any) -> list[PartyGoal]:
    """Validate + build PartyGoal objects from the raw JSON list. Returns
    [] when the block is absent (a dungeon need not declare goals)."""
    if raw_list is None:
        return []
    if not isinstance(raw_list, list):
        raise GoalLoadError("party_goals must be a list")
    goals: list[PartyGoal] = []
    seen: set[str] = set()
    for raw in raw_list:
        if not isinstance(raw, dict):
            raise GoalLoadError("each party_goal must be an object")
        gid = raw.get("id")
        if not gid:
            raise GoalLoadError("each party_goal needs a non-empty 'id'")
        if gid in seen:
            raise GoalLoadError(f"duplicate party_goal id {gid!r}")
        seen.add(gid)
        text = raw.get("text")
        if not text:
            raise GoalLoadError(f"goal {gid!r}: needs a non-empty 'text'")
        goals.append(
            PartyGoal(
                id=gid,
                text=text,
                target_location=raw.get("target_location"),
                requires_item_held=raw.get("requires_item_held"),
                complete_when=_parse_condition(raw.get("complete_when"), gid),
            )
        )
    return goals


def read_party_goals(path: Path | str) -> list[PartyGoal]:
    """Read the `party_goals` array from a dungeon seed file. Kept separate
    from `seed.load_seed_file` on purpose: that loader's job is to emit
    events, and goals are explicitly NOT events."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return parse_party_goals(data.get("party_goals"))


# ---------------------------------------------------------------------------
# State-derived predicates
# ---------------------------------------------------------------------------


def _party_pcs(state: WorldState) -> list:
    return [e for e in state.entities.values() if e.kind == "pc"]


def party_holds_item(state: WorldState, item_id: str) -> bool:
    """True iff any PC currently carries `item_id` (party-wide, not per-PC)."""
    return any(item_id in (pc.inventory or []) for pc in _party_pcs(state))


def any_pc_at(state: WorldState, location_id: str) -> bool:
    return any(pc.location_id == location_id for pc in _party_pcs(state))


def item_held_at(state: WorldState, item_id: str, location_id: str) -> bool:
    """True iff a PC who is carrying `item_id` is currently at `location_id`.
    The item-BEARER must be the one standing at the spot — distinct from
    `any_pc_at`, which an empty-handed PC satisfies while the relic sits in a
    different PC's pocket somewhere else (the 'phantom carry-out' the escape
    goal hit in the 2026-06-13 web run)."""
    return any(
        item_id in (pc.inventory or []) and pc.location_id == location_id
        for pc in _party_pcs(state)
    )


def is_goal_complete(goal: PartyGoal, state: WorldState) -> bool:
    """True iff the goal's completion predicate holds. A goal with an
    activation gate (`requires_item_held`) cannot be complete while that
    gate is unmet — otherwise "escape to the surface" would read as already
    done at spawn, when the party stands on the surface but has not yet
    taken the macguffin. The gate is a precondition for completion, not just
    for activation."""
    cond = goal.complete_when
    if cond is None:
        return False
    if goal.requires_item_held and not party_holds_item(
        state, goal.requires_item_held
    ):
        return False
    if cond.kind == "location_reached":
        return any_pc_at(state, cond.location)
    if cond.kind == "item_held":
        return party_holds_item(state, cond.item)
    if cond.kind == "item_held_at":
        return item_held_at(state, cond.item, cond.location)
    return False


def completed_goal_ids(
    goals: list[PartyGoal], state: WorldState
) -> set[str]:
    """The set of goal ids that count as complete, with *forward latching*:
    a goal is complete if its own predicate holds OR any later goal in the
    declared sequence is complete. Objectives are a progression, so reaching
    a later one means the earlier ones were necessarily met — and, crucially,
    they STAY met even after the party moves on.

    Without this latch, an instantaneous "any PC at the vault" milestone
    un-completes the moment everyone leaves the vault, re-activating it as
    the current objective and pointing the navigation hint back down — which
    is exactly the bug that fights an escape.

    Progression is signalled two ways, both monotonic enough for the macguffin
    pattern and needing no event history:
      - a later goal is itself complete, or
      - a later goal's activation *gate* is satisfied (e.g. the party now
        holds the relic the escape goal needs — which they could only have
        gotten by reaching and taking it, so every earlier milestone is met).
    Either marks all *earlier* goals complete. This cannot falsely latch a
    gated terminal goal at spawn: its gate is unmet there, so nothing signals
    progression past the first objective."""
    latched = [is_goal_complete(g, state) for g in goals]
    gate_open = [
        g.requires_item_held is not None
        and party_holds_item(state, g.requires_item_held)
        for g in goals
    ]
    progressed = False
    for i in range(len(goals) - 1, -1, -1):
        if latched[i]:
            progressed = True
        elif progressed:
            latched[i] = True
        # A satisfied gate at i means everything BEFORE i is progressed past;
        # apply it after deciding latched[i] so it affects earlier indices.
        if gate_open[i]:
            progressed = True
    return {g.id for g, done in zip(goals, latched) if done}


def is_goal_active(
    goal: PartyGoal, goals: list[PartyGoal], state: WorldState
) -> bool:
    """A goal is active iff it is not (forward-latched) complete AND its
    activation gate (if any) is currently satisfied. Takes the full goal
    list so completion can latch across the sequence."""
    if goal.id in completed_goal_ids(goals, state):
        return False
    if goal.requires_item_held and not party_holds_item(
        state, goal.requires_item_held
    ):
        return False
    return True


def select_active_goal(
    goals: list[PartyGoal], state: WorldState
) -> PartyGoal | None:
    """The party's single current objective: the first goal in declared
    order that is not (forward-latched) complete and whose gate is
    satisfied. Returns None if every goal is complete or gated off."""
    done = completed_goal_ids(goals, state)
    for g in goals:
        if g.id in done:
            continue
        if g.requires_item_held and not party_holds_item(
            state, g.requires_item_held
        ):
            continue
        return g
    return None
