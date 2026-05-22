"""
Seed loader.

The seed file is human- or LLM-authored initial conditions consumed once
at startup. It is NOT a save file (invariant 11: the event log is the save
file). The loader converts the seed into a batch of seed_init events, after
which the log alone fully describes the starting world.

Loader responsibilities, in order:
  1. Validate (referential integrity, uniqueness, attribute schema)
  2. Enforce unique display names (numeric suffixing)
  3. Emit events with cause.kind="seed_init"

Validation failure is a hard error: refuse to start, do not partially load.
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any, Protocol

from eventlog import EventLog
from models import EntityCreated, EventCause, ItemCreated, LocationCreated


# ---------------------------------------------------------------------------
# Ruleset attribute schemas
# ---------------------------------------------------------------------------
#
# The only system-aware step in the spine (invariant 8). The loader looks up
# a schema by the seed's `ruleset` string and asks it to validate each
# entity's opaque `attributes` blob. The loader does not branch on the
# system itself.


class RulesetSchema(Protocol):
    name: str

    def validate_attributes(self, entity_kind: str, attrs: dict[str, Any]) -> None:
        """Raise SeedValidationError if `attrs` is invalid for an entity of `entity_kind`."""
        ...


class SeedValidationError(ValueError):
    """Raised when a seed fails validation. Refuse to start; do not partially load."""


class _DND5eLite:
    name = "dnd5e_lite"

    def validate_attributes(self, entity_kind: str, attrs: dict[str, Any]) -> None:
        for required in ("hp", "max_hp"):
            if required not in attrs:
                raise SeedValidationError(
                    f"missing required attribute {required!r} for {entity_kind}"
                )
            value = attrs[required]
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise SeedValidationError(
                    f"attribute {required!r} must be a non-negative int, got {value!r}"
                )
        if attrs["hp"] > attrs["max_hp"]:
            raise SeedValidationError(
                f"hp {attrs['hp']} exceeds max_hp {attrs['max_hp']}"
            )


_RULESETS: dict[str, RulesetSchema] = {
    "dnd5e_lite": _DND5eLite(),
}


def get_ruleset(name: str) -> RulesetSchema:
    if name not in _RULESETS:
        raise SeedValidationError(f"unknown ruleset {name!r}")
    return _RULESETS[name]


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------


def load_seed_file(path: Path | str, log: EventLog) -> None:
    """Load a seed from a JSON file into `log` as seed_init events."""
    path = Path(path)
    with path.open("r", encoding="utf-8") as fh:
        seed = json.load(fh)
    load_seed(seed, log)


def load_seed(seed: dict[str, Any], log: EventLog) -> None:
    """Load a seed dict into `log` as seed_init events."""
    ruleset_name = seed.get("ruleset")
    if not isinstance(ruleset_name, str):
        raise SeedValidationError("seed is missing top-level 'ruleset' string")
    schema = get_ruleset(ruleset_name)

    locations = seed.get("locations", []) or []
    entities = seed.get("entities", []) or []
    items = seed.get("items", []) or []

    _validate_seed(schema, locations, entities, items)
    display_names = _resolve_display_names(entities)

    cause = EventCause(kind="seed_init")
    timestamp = 0.0  # deterministic seed events

    for loc in locations:
        log.append(
            LocationCreated(
                location_id=loc["id"],
                name=loc["name"],
                description=loc["description"],
                connections=list(loc.get("connections", [])),
                attributes=dict(loc.get("attributes", {})),
            ),
            cause,
            timestamp=timestamp,
        )

    for item in items:
        log.append(
            ItemCreated(
                item_id=item["id"],
                name=item["name"],
                location_id=item.get("location_id"),
                properties=dict(item.get("properties", {})),
            ),
            cause,
            timestamp=timestamp,
        )

    for ent in entities:
        log.append(
            EntityCreated(
                entity_id=ent["id"],
                display_name=display_names[ent["id"]],
                kind=ent["kind"],
                location_id=ent["location_id"],
                attributes=dict(ent.get("attributes", {})),
                inventory=list(ent.get("inventory", [])),
            ),
            cause,
            timestamp=timestamp,
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _validate_seed(
    schema: RulesetSchema,
    locations: list[dict[str, Any]],
    entities: list[dict[str, Any]],
    items: list[dict[str, Any]],
) -> None:
    # All ids are unique across kinds. The brief: "No duplicate ids of any
    # kind across the whole seed."
    all_ids = (
        [loc["id"] for loc in locations]
        + [ent["id"] for ent in entities]
        + [item["id"] for item in items]
    )
    dupes = [i for i, n in Counter(all_ids).items() if n > 1]
    if dupes:
        raise SeedValidationError(f"duplicate ids in seed: {sorted(dupes)}")

    known_locations = {loc["id"] for loc in locations}

    # Every connection target exists.
    for loc in locations:
        for conn in loc.get("connections", []):
            if conn not in known_locations:
                raise SeedValidationError(
                    f"location {loc['id']!r} connects to unknown location {conn!r}"
                )

    # Every entity sits in a known location.
    for ent in entities:
        loc_id = ent.get("location_id")
        if loc_id not in known_locations:
            raise SeedValidationError(
                f"entity {ent['id']!r} placed in unknown location {loc_id!r}"
            )
        schema.validate_attributes(ent["kind"], ent.get("attributes", {}))

    # Items with a location_id reference a known location (None = unplaced).
    for item in items:
        loc_id = item.get("location_id")
        if loc_id is not None and loc_id not in known_locations:
            raise SeedValidationError(
                f"item {item['id']!r} placed in unknown location {loc_id!r}"
            )


def _resolve_display_names(entities: list[dict[str, Any]]) -> dict[str, str]:
    """
    Suffix duplicate display names deterministically: "Skeleton",
    "Skeleton 2", "Skeleton 3", ... in seed order. Internal ids are
    untouched.
    """
    seen: Counter[str] = Counter()
    resolved: dict[str, str] = {}
    for ent in entities:
        base = ent["display_name"]
        seen[base] += 1
        resolved[ent["id"]] = base if seen[base] == 1 else f"{base} {seen[base]}"
    return resolved
