"""
Deterministic state projection.

    state = reduce(apply, sorted(events, key=seq), initial)

Pure function from events to WorldState (invariant 2 + 12). Same events in,
same state out. Always.

This module never:
  - removes an entity (invariant 5: death is a status)
  - applies a SummaryCreated to world state (invariant 7)
  - branches on game system (invariant 8)
"""
from __future__ import annotations

from typing import Iterable

from models import (
    AttributeDelta,
    AttributeSet,
    CombatEnd,
    CombatParticipantsAdded,
    CombatStart,
    DiceRolled,
    DMNarration,
    Entity,
    EntityCreated,
    EntityMoved,
    Event,
    InventoryAdded,
    InventoryRemoved,
    Item,
    ItemCreated,
    Location,
    LocationCreated,
    PlayerAction,
    SummaryCreated,
    WorldState,
)


def apply(state: WorldState, event: Event) -> WorldState:
    """
    Mutates `state` in place and returns it.

    Callers that need a pristine prior state must pass in a copy. `project`
    and `project_from` below own their state and do this correctly.
    """
    p = event.payload

    if isinstance(p, EntityCreated):
        if p.entity_id in state.entities:
            raise ValueError(f"entity {p.entity_id!r} already exists")
        state.entities[p.entity_id] = Entity(
            entity_id=p.entity_id,
            display_name=p.display_name,
            kind=p.kind,
            location_id=p.location_id,
            attributes=dict(p.attributes),
            inventory=list(p.inventory),
        )

    elif isinstance(p, LocationCreated):
        if p.location_id in state.locations:
            raise ValueError(f"location {p.location_id!r} already exists")
        state.locations[p.location_id] = Location(
            location_id=p.location_id,
            name=p.name,
            description=p.description,
            connections=list(p.connections),
            attributes=dict(p.attributes),
        )

    elif isinstance(p, ItemCreated):
        if p.item_id in state.items:
            raise ValueError(f"item {p.item_id!r} already exists")
        state.items[p.item_id] = Item(
            item_id=p.item_id,
            name=p.name,
            location_id=p.location_id,
            properties=dict(p.properties),
        )

    elif isinstance(p, EntityMoved):
        entity = state.entities[p.entity_id]
        entity.location_id = p.to_location

    elif isinstance(p, AttributeSet):
        entity = state.entities[p.entity_id]
        entity.attributes[p.attr] = p.value

    elif isinstance(p, AttributeDelta):
        entity = state.entities[p.entity_id]
        current = entity.attributes.get(p.attr, 0)
        entity.attributes[p.attr] = current + p.delta

    elif isinstance(p, InventoryAdded):
        entity = state.entities[p.entity_id]
        if p.item_id not in entity.inventory:
            entity.inventory.append(p.item_id)
        if p.item_id in state.items:
            state.items[p.item_id].location_id = None

    elif isinstance(p, InventoryRemoved):
        entity = state.entities[p.entity_id]
        if p.item_id in entity.inventory:
            entity.inventory.remove(p.item_id)

    elif isinstance(
        p,
        (DiceRolled, DMNarration, PlayerAction, CombatStart, CombatParticipantsAdded, CombatEnd),
    ):
        # Explicit no-op on world state. These events exist in the log for
        # replay reproducibility (dice) and for later layers (narration,
        # scheduler) but carry no mechanical world-state change.
        pass

    elif isinstance(p, SummaryCreated):
        # Invariant 7. Do NOT fold summaries into state — they are lossy
        # prompt-construction artifacts. This branch is here explicitly so
        # nobody later "helpfully" applies them.
        pass

    else:
        # The payload union is closed. Hitting this means a new variant was
        # added to models.py without updating the projection — fail loudly.
        raise NotImplementedError(f"no projection handler for payload type {p.type!r}")

    state.derived_through_seq = event.seq
    return state


def project(events: Iterable[Event]) -> WorldState:
    """Pure projection from a (sortable) iterable of events to WorldState."""
    state = WorldState()
    for event in sorted(events, key=lambda e: e.seq):
        apply(state, event)
    return state


def project_from(snapshot: WorldState, events: Iterable[Event]) -> WorldState:
    """
    Resume projection from a snapshot. Does not mutate the caller's snapshot.

    Snapshot equivalence is the contract: for any split N,
        project_from(project(events[:N+1]), events[N+1:]) == project(events)
    byte-for-byte.
    """
    state = snapshot.model_copy(deep=True)
    for event in sorted(events, key=lambda e: e.seq):
        if event.seq <= state.derived_through_seq:
            raise ValueError(
                f"event seq {event.seq} is not after snapshot's "
                f"derived_through_seq {state.derived_through_seq}"
            )
        apply(state, event)
    return state


def take_snapshot(state: WorldState) -> WorldState:
    """
    Freeze a snapshot of the current state. Snapshots are a cache, never
    truth (invariant 3) — the log can always rebuild state from seq 0.
    """
    return state.model_copy(deep=True)
