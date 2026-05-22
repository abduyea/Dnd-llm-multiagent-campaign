"""
Ruleset-driven mechanics for dnd5e_lite.

Pure functions. Mechanics **never** appends to the event log — it returns
the payloads the runner should append, in order. This is the M2 expression
of invariant 9 (LLMs propose, runner disposes) extended to mechanics: the
LLM proposes intent, mechanics computes outcomes, the runner is the only
thing that calls `log.append`.

M2 only resolves a single rule: a melee/ranged attack of the dnd5e_lite
shape. Crits / advantage / saves / multi-target / second weapon are
deliberately out of scope (see m2_build_brief.md).
"""
from __future__ import annotations

import random
from dataclasses import dataclass

from dice import roll_detailed
from models import AttributeDelta, DiceRolled, Entity, Payload


class MechanicsError(ValueError):
    """Raised when a resolution cannot be computed from the given entities."""


@dataclass(frozen=True)
class AttackResolution:
    """
    Structured outcome of an attack. The beat-2 narration prompt is built
    from this — the LLM never sees a die roll the runner didn't compute,
    and never has to do arithmetic on its own.

    `damage_*` fields are None on a miss.
    """

    attacker_id: str
    target_id: str
    attack_d20: int  # raw d20 (1..20)
    attack_mod: int
    attack_total: int  # d20 + mod
    target_ac: int
    hit: bool
    damage_formula: str | None
    damage_dice: int | None  # sum of dice, no mod
    damage_mod: int | None
    damage_total: int | None
    target_hp_before: int


def resolve_attack(
    attacker: Entity,
    target: Entity,
    rng: random.Random,
) -> tuple[AttackResolution, list[Payload]]:
    """
    Roll an attack against `target`. On hit, roll damage and emit an HP
    delta payload. Returns (resolution, payloads-to-append-in-order).

    The runner appends the payloads, re-projects, and then — if the
    target's hp has dropped to <= 0 — appends `AttributeSet(status="dead")`
    on its own. Mechanics does not touch status: hp_after is the
    projection's truth, not mechanics' guess.
    """
    attack_mod = _require_int(attacker, "attack_mod")
    target_ac = _require_int(target, "ac")
    hp_before = _require_int(target, "hp")

    attack_formula = _format_d20_formula(attack_mod)
    attack_roll = roll_detailed(attack_formula, rng)
    attack_total = attack_roll.total
    d20 = attack_roll.dice_total
    hit = attack_total >= target_ac  # ties hit (5e standard)

    payloads: list[Payload] = [
        DiceRolled(
            formula=attack_formula,
            result=attack_total,
            reason=f"attack: {attacker.entity_id} -> {target.entity_id}",
        )
    ]

    if not hit:
        return (
            AttackResolution(
                attacker_id=attacker.entity_id,
                target_id=target.entity_id,
                attack_d20=d20,
                attack_mod=attack_mod,
                attack_total=attack_total,
                target_ac=target_ac,
                hit=False,
                damage_formula=None,
                damage_dice=None,
                damage_mod=None,
                damage_total=None,
                target_hp_before=hp_before,
            ),
            payloads,
        )

    damage_formula = attacker.attributes.get("weapon_damage")
    if not isinstance(damage_formula, str) or not damage_formula:
        raise MechanicsError(
            f"attacker {attacker.entity_id!r} hit but has no 'weapon_damage' attribute"
        )
    damage_roll = roll_detailed(damage_formula, rng)
    damage_total = damage_roll.total

    payloads.append(
        DiceRolled(
            formula=damage_formula,
            result=damage_total,
            reason=f"damage: {attacker.entity_id} -> {target.entity_id}",
        )
    )
    payloads.append(
        AttributeDelta(
            entity_id=target.entity_id,
            attr="hp",
            delta=-damage_total,
        )
    )

    return (
        AttackResolution(
            attacker_id=attacker.entity_id,
            target_id=target.entity_id,
            attack_d20=d20,
            attack_mod=attack_mod,
            attack_total=attack_total,
            target_ac=target_ac,
            hit=True,
            damage_formula=damage_formula,
            damage_dice=damage_roll.dice_total,
            damage_mod=damage_roll.mod,
            damage_total=damage_total,
            target_hp_before=hp_before,
        ),
        payloads,
    )


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _require_int(entity: Entity, attr: str) -> int:
    value = entity.attributes.get(attr)
    # bool is a subclass of int in Python — exclude it explicitly so a
    # rogue boolean attribute doesn't silently coerce into 0 or 1.
    if not isinstance(value, int) or isinstance(value, bool):
        raise MechanicsError(
            f"entity {entity.entity_id!r} missing required int attribute {attr!r}"
        )
    return value


def _format_d20_formula(mod: int) -> str:
    """'1d20+5', '1d20-3', '1d20' (when mod=0)."""
    if mod == 0:
        return "1d20"
    return f"1d20{mod:+d}"


# ---------------------------------------------------------------------------
# M9: skill check resolution
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CheckResolution:
    """Structured outcome of a skill check. The narration prompt is
    built from this — the LLM sees only resolved numbers, not a raw
    dice expression."""

    actor_id: str
    target_id: str
    stat: str
    stat_mod: int
    dc: int
    d20: int          # raw 1d20 (1..20)
    total: int        # d20 + stat_mod
    success: bool
    purpose: str


def resolve_check(
    actor: Entity,
    target_id: str,
    stat: str,
    dc: int,
    rng: random.Random,
    purpose: str = "",
) -> tuple[CheckResolution, list[Payload]]:
    """
    Roll `1d20 + actor.attributes[stat]` against `dc`. Returns the
    resolution + the DiceRolled payload the runner should append.

    Missing stat attribute defaults to 0 (matches dex_mod fallback for
    initiative — older seeds that lack `int_mod` etc. still resolve
    cleanly).
    """
    raw = actor.attributes.get(stat, 0)
    # Exclude bool (Python's bool is an int subclass — same defensive
    # check as elsewhere in mechanics).
    if isinstance(raw, int) and not isinstance(raw, bool):
        stat_mod = raw
    else:
        stat_mod = 0

    formula = _format_d20_formula(stat_mod)
    roll = roll_detailed(formula, rng)
    d20 = roll.dice_total
    total = roll.total
    success = total >= dc  # ties succeed (5e standard)

    reason = (
        f"check {purpose!r} ({stat}): {actor.entity_id} -> {target_id}"
        if purpose
        else f"check ({stat}): {actor.entity_id} -> {target_id}"
    )
    payloads: list[Payload] = [
        DiceRolled(formula=formula, result=total, reason=reason),
    ]

    return (
        CheckResolution(
            actor_id=actor.entity_id,
            target_id=target_id,
            stat=stat,
            stat_mod=stat_mod,
            dc=dc,
            d20=d20,
            total=total,
            success=success,
            purpose=purpose,
        ),
        payloads,
    )
