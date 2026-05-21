"""
Pydantic models for the deterministic spine.

The payload vocabulary below is closed (invariant 6). There is no freeform
set(path, value). Adding a new kind of change means adding a new payload
variant here AND a handler in projection.apply — never an escape hatch.
"""
from __future__ import annotations

from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Cause
# ---------------------------------------------------------------------------

CauseKind = Literal[
    "seed_init",
    "dm_action",
    "dice_resolution",
    "player_action",
    "summarizer",
    "combat_transition",
]


class EventCause(BaseModel):
    """Why an event exists. Non-optional on every event (invariant: traceability)."""

    model_config = ConfigDict(extra="forbid")

    kind: CauseKind
    turn_id: str | None = None
    player_id: str | None = None


# ---------------------------------------------------------------------------
# Payload variants (the entire closed vocabulary of what can happen)
# ---------------------------------------------------------------------------


class _PayloadBase(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EntityCreated(_PayloadBase):
    type: Literal["entity_created"] = "entity_created"
    entity_id: str
    display_name: str
    kind: Literal["pc", "npc"]
    location_id: str
    attributes: dict[str, Any] = Field(default_factory=dict)
    inventory: list[str] = Field(default_factory=list)


class LocationCreated(_PayloadBase):
    type: Literal["location_created"] = "location_created"
    location_id: str
    name: str
    description: str
    connections: list[str] = Field(default_factory=list)
    # M9: optional ruleset-aware data on the location (puzzle answers,
    # gated-connection metadata, etc.). Default empty; existing seeds
    # unchanged. Mirrors Entity.attributes — opaque to the spine.
    attributes: dict[str, Any] = Field(default_factory=dict)


class ItemCreated(_PayloadBase):
    type: Literal["item_created"] = "item_created"
    item_id: str
    name: str
    location_id: str | None = None
    properties: dict[str, Any] = Field(default_factory=dict)


class EntityMoved(_PayloadBase):
    type: Literal["entity_moved"] = "entity_moved"
    entity_id: str
    to_location: str


class AttributeSet(_PayloadBase):
    """Replacement semantics: overwrite whatever is there (order-sensitive)."""

    type: Literal["attribute_set"] = "attribute_set"
    entity_id: str
    attr: str
    value: Any


class AttributeDelta(_PayloadBase):
    """
    Accumulation semantics: add to current value. Numeric only.

    Deltas compose and are order-independent under replay; this is the property
    that makes combat math correct. The emitter must never compute the
    resulting absolute value — emit the delta, let the projection sum.
    """

    type: Literal["attribute_delta"] = "attribute_delta"
    entity_id: str
    attr: str
    delta: int | float


class InventoryAdded(_PayloadBase):
    type: Literal["inventory_added"] = "inventory_added"
    entity_id: str
    item_id: str


class InventoryRemoved(_PayloadBase):
    type: Literal["inventory_removed"] = "inventory_removed"
    entity_id: str
    item_id: str


class DiceRolled(_PayloadBase):
    """No-op on world state. Logged so a replay does not re-randomize."""

    type: Literal["dice_rolled"] = "dice_rolled"
    formula: str
    result: int
    reason: str


class DMNarration(_PayloadBase):
    """No-op on world state. Carries scoping metadata for view filtering (M4)."""

    type: Literal["dm_narration"] = "dm_narration"
    audience: str
    location_id: str
    text: str


class PlayerAction(_PayloadBase):
    """No-op on world state. Freeform player text."""

    type: Literal["player_action"] = "player_action"
    player_id: str
    location_id: str
    text: str


class SummaryCreated(_PayloadBase):
    """
    Invariant 7: the projection MUST ignore this entirely. Summaries are lossy
    prompt-construction artifacts. Feeding one into world state is a
    correctness bug. `scope` is locked to "world" — per-player summarization
    is a deferred future implementation behind an interface.
    """

    type: Literal["summary_created"] = "summary_created"
    scope: Literal["world"] = "world"
    covers_through: int
    text: str


class CombatStart(_PayloadBase):
    """No-op on world state. Scheduler (M5) consumes it later."""

    type: Literal["combat_start"] = "combat_start"
    participants: list[str]


class CombatEnd(_PayloadBase):
    """No-op on world state. Scheduler (M5) consumes it later."""

    type: Literal["combat_end"] = "combat_end"


Payload = Annotated[
    Union[
        EntityCreated,
        LocationCreated,
        ItemCreated,
        EntityMoved,
        AttributeSet,
        AttributeDelta,
        InventoryAdded,
        InventoryRemoved,
        DiceRolled,
        DMNarration,
        PlayerAction,
        SummaryCreated,
        CombatStart,
        CombatEnd,
    ],
    Field(discriminator="type"),
]

NOOP_PAYLOAD_TYPES: frozenset[str] = frozenset(
    {
        "dice_rolled",
        "dm_narration",
        "player_action",
        "summary_created",
        "combat_start",
        "combat_end",
    }
)


# ---------------------------------------------------------------------------
# Event envelope
# ---------------------------------------------------------------------------


class Event(BaseModel):
    """
    Thin envelope. No domain logic.

    `seq` is the total order (invariant 4). `timestamp` is informational and
    must never be used for ordering.
    """

    model_config = ConfigDict(extra="forbid")

    seq: int
    timestamp: float
    cause: EventCause
    payload: Payload

    @property
    def type(self) -> str:
        return self.payload.type


# ---------------------------------------------------------------------------
# World state (the projection result)
# ---------------------------------------------------------------------------


class Entity(BaseModel):
    """
    PCs and NPCs use the same model; `kind` discriminates. A PC's full
    character sheet IS its `attributes` blob (locked decision: sheets live in
    the seed's attributes, not a separate file).
    """

    model_config = ConfigDict(extra="forbid")

    entity_id: str
    display_name: str
    kind: Literal["pc", "npc"]
    location_id: str
    attributes: dict[str, Any] = Field(default_factory=dict)
    inventory: list[str] = Field(default_factory=list)


class Location(BaseModel):
    model_config = ConfigDict(extra="forbid")

    location_id: str
    name: str
    description: str
    connections: list[str] = Field(default_factory=list)
    # M9: ruleset-aware data on the location. Spine treats it as opaque
    # (same convention as Entity.attributes). Used by M9 for puzzle-
    # gating data — but the M1 projection never reads this field.
    attributes: dict[str, Any] = Field(default_factory=dict)


class Item(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item_id: str
    name: str
    location_id: str | None = None  # None when held in an entity's inventory
    properties: dict[str, Any] = Field(default_factory=dict)


class WorldState(BaseModel):
    """
    Strictly mechanical projection of the event log.

    Carries NO narration, summaries, player memory, or scheduler state —
    those are not world state.
    """

    model_config = ConfigDict(extra="forbid")

    derived_through_seq: int = -1
    entities: dict[str, Entity] = Field(default_factory=dict)
    locations: dict[str, Location] = Field(default_factory=dict)
    items: dict[str, Item] = Field(default_factory=dict)
