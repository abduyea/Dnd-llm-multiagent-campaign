"""
XML tag protocol — the DM ↔ runner contract.

The DM emits XML tags; the runner converts them into events. This module
is the validation boundary: every tag the runner ever wraps in an event
went through one of `extract_intent` / `extract_narration` first
(invariant 9 — no model output reaches state without going through here).

Design split:
- **Forgiving extraction.** Local models routinely wrap tags in prose,
  apologies, code fences, or repeated attempts. The extractor's job is to
  *locate* the first well-formed tag of the expected kind. Surrounding
  prose is discarded.
- **Strict validation.** Once a tag is located, its attributes (or body)
  are validated by a Pydantic model. Unknown attributes, wrong values,
  missing required fields, empty body — all raise `MalformedTagError`.

The error type is the signal M3's retry layer will catch. M2 just raises.

`<think>...</think>` reasoning blocks (qwen3) are stripped upstream in
`llm.py`; this module does not concern itself with them.
"""
from __future__ import annotations

import re
from typing import Annotated, ClassVar, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError


class MalformedTagError(ValueError):
    """
    The DM's output does not contain a valid tag of the expected kind.

    `category` is one of: "no_tag_found", "wrong_attribute", "empty_body".
    M2's measurement layer reads it directly as `parse_status` for M3's
    failure-mode breakdown. The taxonomy may grow as M3's brief is written
    against observed failures — additions are non-breaking.
    """

    def __init__(self, message: str, category: str = "no_tag_found") -> None:
        super().__init__(message)
        self.category = category


class AttackIntent(BaseModel):
    """M2: hostile action against a present target. `cost = "action"`."""

    model_config = ConfigDict(extra="forbid")
    cost: ClassVar[str] = "action"

    type: Literal["attack"]
    target: str


class MoveIntent(BaseModel):
    """
    M7/M8: move to a connected location. `cost = "move"` (consumes the
    turn's move slot). The runner enforces 1 move per turn via the
    ruleset action-economy validator.
    """

    model_config = ConfigDict(extra="forbid")
    cost: ClassVar[str] = "move"

    type: Literal["move"]
    target: str


class InspectIntent(BaseModel):
    """
    M7-legacy: combined "look at + examine carefully" intent. Kept for
    backward compatibility with M7 tests; M8 splits this into
    `LookIntent` (free) and `ExamineIntent` (action). New code should
    use those instead.
    """

    model_config = ConfigDict(extra="forbid")
    cost: ClassVar[str] = "action"  # treated as the conservative case

    type: Literal["inspect"]
    target: str


class LookIntent(BaseModel):
    """
    M8: casual observation. `cost = "free"` — the player can `<look/>`
    at multiple things in a single turn. No state change; the narration
    prompt receives the target's standard description.

    `target` may be a location_id (the room), an item_id, or an
    entity_id, all in the actor's scene. Same validity rule as
    InspectIntent's target.
    """

    model_config = ConfigDict(extra="forbid")
    cost: ClassVar[str] = "free"

    type: Literal["look"]
    target: str


class ExamineIntent(BaseModel):
    """
    M8: deliberate inspection. `cost = "action"` — uses the turn's
    action slot. Reveals standard description plus any `hidden_text`
    attached to the target. M9 may gate hidden_text behind a check
    when `target.search_dc` is set.

    Same target validity rule as `look`.
    """

    model_config = ConfigDict(extra="forbid")
    cost: ClassVar[str] = "action"

    type: Literal["examine"]
    target: str


class TalkIntent(BaseModel):
    """
    M8: speak to a present entity. `cost = "free"` — players can
    converse without consuming their action. The NPC's reaction is
    M9's work; in M8 the speech is recorded as narration context.

    Tag uses wrapping form, with the speech as the body:
        <intent type="talk" target="ent_npc_aldous">What's your name?</intent>
    """

    model_config = ConfigDict(extra="forbid")
    cost: ClassVar[str] = "free"

    type: Literal["talk"]
    target: str
    speech: str  # populated from the tag body, not an attribute


class WaitIntent(BaseModel):
    """
    M8: the character explicitly holds. `cost = "turn"` — must be the
    final intent in a turn plan; consumes all remaining slots. Useful
    when the player wants to do nothing this turn.
    """

    model_config = ConfigDict(extra="forbid")
    cost: ClassVar[str] = "turn"

    type: Literal["wait"]


class CheckIntent(BaseModel):
    """
    M9: skill check. Rolls `1d20 + actor.attributes[stat]` against a
    DC derived from `target`'s attributes/properties (see runner's
    `_resolve_check` for the lookup order). `cost = "action"`.

    `purpose` is a free-form short string ("pick the lock", "search
    for traps") used by the runner's DC lookup (it looks for
    `target.attributes.get(f"{purpose}_dc")` first) and the narration
    prompt.
    """

    model_config = ConfigDict(extra="forbid")
    cost: ClassVar[str] = "action"

    type: Literal["check"]
    stat: str
    target: str
    purpose: str


class UseItemIntent(BaseModel):
    """
    M9: use an item from the actor's inventory. `target` defaults to
    the actor (self-use; e.g. drinking a potion); otherwise another
    entity in the scene (e.g. healing an ally). The runner dispatches
    on the item's `properties.use` field. `cost = "action"`.

    For lockpicks: `target` is the locked item; runner triggers an
    implicit check (Dexterity vs lock_dc) and unlocks on success.
    """

    model_config = ConfigDict(extra="forbid")
    cost: ClassVar[str] = "action"

    type: Literal["use_item"]
    item: str
    target: str | None = None


class PuzzleAnswerIntent(BaseModel):
    """
    M9: declare an answer to a puzzle. `target` is the puzzle-bearing
    location or item; `answer` is the player's submitted string.
    Runner compares case-insensitively against the authored
    `puzzle_answer`. On match, records the solution on the actor.
    `cost = "action"`.
    """

    model_config = ConfigDict(extra="forbid")
    cost: ClassVar[str] = "action"

    type: Literal["puzzle_answer"]
    target: str
    answer: str


class PickupIntent(BaseModel):
    """
    M9 follow-up: pick up an item from the floor of the actor's current
    location. `cost = "action"` (a single object interaction per turn
    matches the 5e "free interaction" budget; treating it as an action
    keeps the action economy simple — multi-pickup turns are bonus
    actions we don't model yet).

    Side-effects are authored on the item's `properties.on_pickup`
    dict: `start_countdown: {attribute, turns}` for time-pressure
    items (Heartstone), `seal_location: <loc_id>` for sealing the
    room. Runner reads on_pickup and stages the appropriate
    AttributeSet payloads alongside the InventoryAdded.
    """

    model_config = ConfigDict(extra="forbid")
    cost: ClassVar[str] = "action"

    type: Literal["pickup"]
    target: str  # item_id


class GiveIntent(BaseModel):
    """
    M9 follow-up: atomic one-way item transfer from the actor's
    inventory to another entity in the same room. Used for handing
    items to allies, payment to merchants, surrendering goods, etc.
    `cost = "action"`.

    Giving to an NPC also queues that NPC for a response turn (same
    machinery as <talk>) so merchants can react with a counter-give
    and conversational NPCs can acknowledge gifts in character.
    """

    model_config = ConfigDict(extra="forbid")
    cost: ClassVar[str] = "action"

    type: Literal["give"]
    item: str  # item_id from actor's inventory
    target: str  # recipient entity_id


class OpenIntent(BaseModel):
    """
    M9 follow-up: open a container item in the actor's room. Targets
    must have `properties.type == "container"`. If the container is
    locked, the actor must have a prior `unlocked_<container_id>`
    attribute (from lockpicking or another mechanism). On success, the
    container's `properties.contents` (list of item ids) is transferred
    into the actor's inventory and an `opened_<container_id>` marker
    is set on the actor. `cost = "action"`.
    """

    model_config = ConfigDict(extra="forbid")
    cost: ClassVar[str] = "action"

    type: Literal["open"]
    target: str  # container item_id


class TradeIntent(BaseModel):
    """
    M9 follow-up: buy an item from a merchant at the authored fixed
    price. The runner reads `want_item.properties.price` (int) and
    `want_item.properties.currency` (str, default "coin"), validates
    that the actor's `attributes[currency]` covers the price, then
    stages AttributeDelta(actor, currency, -price) + AttributeDelta
    (npc, currency, +price) + InventoryRemoved(npc, want) +
    InventoryAdded(actor, want) atomically.

    Currency is an entity attribute (numeric), not an item — this is
    what allows partial payment / change without needing to mutate
    item properties. Items without a `price` cannot be traded for
    via this intent.

    Haggling is intentionally out of scope here: NPCs may negotiate
    in their conversational prose (via persona / goals), but the
    structural trade pays the listed price. `cost = "action"`.
    """

    model_config = ConfigDict(extra="forbid")
    cost: ClassVar[str] = "action"

    type: Literal["trade"]
    want: str   # item id in the target's inventory
    target: str  # trading partner entity_id


# M9 discriminated union — fourteen types. AttackIntent + MoveIntent +
# InspectIntent carry from M5/M7; Look/Examine/Talk/Wait from M8;
# Check/UseItem/PuzzleAnswer added in M9; Pickup/Give/Open/Trade in
# M9 follow-up (verb-discoverability fixes).
IntentTag = Annotated[
    Union[
        AttackIntent,
        MoveIntent,
        InspectIntent,  # M7-legacy; kept for backward compat
        LookIntent,
        ExamineIntent,
        TalkIntent,
        WaitIntent,
        CheckIntent,
        UseItemIntent,
        PuzzleAnswerIntent,
        PickupIntent,
        GiveIntent,
        OpenIntent,
        TradeIntent,
    ],
    Field(discriminator="type"),
]

_INTENT_ADAPTER: TypeAdapter[IntentTag] = TypeAdapter(IntentTag)


class Narration(BaseModel):
    """
    Beat-2 tag body. No attributes — the runner sets audience / location
    on the resulting `dm_narration` event from values it already knows.
    """

    model_config = ConfigDict(extra="forbid")

    text: str


class CombatStartTag(BaseModel):
    """
    M5 tag emitted by the DM in beat 1 (alongside `<intent/>`) when the
    player's action initiates combat. Runner validates that every
    participant is present in the scene + alive; classification
    failures route into M3's retry loop under `hallucinated_id`.
    """

    model_config = ConfigDict(extra="forbid")

    participants: list[str]


# Self-closing intent: <intent ... />. Excludes '/' and '>' inside the
# attribute span — entity ids do not contain those characters. Used by
# the M2-M7 single-intent `extract_intent` entry point.
_INTENT_RE = re.compile(r"<intent\b([^/>]*?)/\s*>", re.DOTALL)

# M8: matches both self-closing AND wrapping intent forms.
# - Self-closing: <intent attrs/>  (group 1 = attrs, group 2 = None)
# - Wrapping:     <intent attrs>body</intent>  (group 1 = attrs, group 2 = body)
# The wrapping form is required for <intent type="talk">speech</intent>.
_INTENT_TAG_RE = re.compile(
    r"<intent\b([^>]*?)(?:/\s*>|>(.*?)</intent\s*>)",
    re.DOTALL,
)

# Wrapping narration: <narration [attrs]>body</narration>. Forgiving on
# attributes (we ignore them — the prompt instructs none); the body is
# the load-bearing thing.
_NARRATION_RE = re.compile(r"<narration\b[^>]*>(.*?)</narration>", re.DOTALL)

# Self-closing combat_start: <combat_start participants="a,b,c"/>.
_COMBAT_START_RE = re.compile(r"<combat_start\b([^/>]*?)/\s*>", re.DOTALL)

# Attributes inside the tag span. Requires quoted values (single or double).
# Unquoted attributes are treated as not-present and the strict Pydantic
# layer catches the resulting missing-field error.
_ATTR_RE = re.compile(r"""(\w+)\s*=\s*(?:"([^"]*)"|'([^']*)')""")


def extract_intent(text: str) -> IntentTag:
    """
    M2-M7 single-intent entry point. Locate and validate the first
    `<intent .../>` (self-closing) in `text`.

    Returns one of the IntentTag union variants — discriminated by
    `type`. M8 callers should use `extract_intents` for the multi-
    intent turn protocol; this function remains for the legacy
    single-tag tests and is unchanged in behavior.
    """
    m = _INTENT_RE.search(text)
    if m is None:
        raise MalformedTagError(
            f"no valid <intent .../> tag in DM output: {text!r}",
            category="no_tag_found",
        )
    attrs = _parse_attrs(m.group(1))
    try:
        return _INTENT_ADAPTER.validate_python(attrs)
    except ValidationError as e:
        raise MalformedTagError(
            f"<intent/> attributes {attrs!r} failed validation: {e}",
            category="wrong_attribute",
        ) from e


def extract_intents(text: str) -> list[IntentTag]:
    """
    M8 multi-intent entry point. Locate all `<intent .../>` tags in
    `text` (self-closing OR wrapping) in document order. Returns the
    list of parsed intents.

    Empty list if no intents are present (a player's turn with only
    a `<narration>` and no intents is valid — equivalent to
    `<intent type="wait"/>`; the ruleset validator handles that).

    Raises `MalformedTagError` if any individual tag fails parsing
    or validation. Per-tag failures are surfaced eagerly so the
    retry loop can correct them.
    """
    intents: list[IntentTag] = []
    for match in _INTENT_TAG_RE.finditer(text):
        attrs = _parse_attrs(match.group(1))
        body = match.group(2)
        if body is not None:
            stripped = body.strip()
            if stripped:
                # Wrapping form supplies the body as the `speech` field
                # for talk intents; other types reject it via extra="forbid".
                attrs["speech"] = stripped
        try:
            intent = _INTENT_ADAPTER.validate_python(attrs)
        except ValidationError as e:
            raise MalformedTagError(
                f"<intent/> attributes {attrs!r} failed validation: {e}",
                category="wrong_attribute",
            ) from e
        intents.append(intent)
    return intents


def extract_narration(text: str) -> Narration:
    """Locate and validate the first `<narration>...</narration>` in `text`."""
    m = _NARRATION_RE.search(text)
    if m is None:
        raise MalformedTagError(
            f"no <narration>...</narration> tag in DM output: {text!r}",
            category="no_tag_found",
        )
    body = m.group(1).strip()
    if not body:
        raise MalformedTagError("<narration> body is empty", category="empty_body")
    return Narration(text=body)


def extract_combat_start(text: str) -> CombatStartTag | None:
    """
    Locate and validate `<combat_start participants="..."/>` in `text`.

    Returns None if the tag is not present (combat_start is optional in
    a DM response — most turns don't initiate combat). Raises
    MalformedTagError ONLY when the tag is present but malformed, so
    the M3 retry loop can re-prompt for a fix.
    """
    m = _COMBAT_START_RE.search(text)
    if m is None:
        return None

    attrs = _parse_attrs(m.group(1))
    extra = set(attrs) - {"participants"}
    if extra:
        raise MalformedTagError(
            f"<combat_start/> has unexpected attributes: {sorted(extra)}",
            category="wrong_attribute",
        )
    raw = attrs.get("participants")
    if raw is None:
        raise MalformedTagError(
            "<combat_start/> missing 'participants' attribute",
            category="wrong_attribute",
        )
    participants = [p.strip() for p in raw.split(",") if p.strip()]
    if not participants:
        raise MalformedTagError(
            "<combat_start/> 'participants' is empty",
            category="wrong_attribute",
        )
    try:
        return CombatStartTag(participants=participants)
    except ValidationError as e:
        raise MalformedTagError(
            f"<combat_start/> participants failed validation: {e}",
            category="wrong_attribute",
        ) from e


def _parse_attrs(attr_span: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for match in _ATTR_RE.finditer(attr_span):
        name = match.group(1)
        value = match.group(2) if match.group(2) is not None else match.group(3)
        out[name] = value
    return out
