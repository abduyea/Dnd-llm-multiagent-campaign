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
from typing import Any, Protocol

from dice import roll_detailed
from models import AttributeDelta, AttributeSet, DiceRolled, Entity, Payload


class MechanicsError(ValueError):
    """Raised when a resolution cannot be computed from the given entities."""


# ---------------------------------------------------------------------------
# M12 conditions (dnd5e_lite, simplified)
# ---------------------------------------------------------------------------
#
# Conditions are stored as a plain `conditions: list[str]` on an entity's
# attributes (rides the existing AttributeSet payload — invariant 6, no spine
# change). The mechanical effect of each is a *derived* advantage/disadvantage
# or a can't-act gate — the player never chooses advantage; the rules grant it
# from the conditions already shown in the scene. Kept as module helpers
# (shared by the provider + the runner's can-act gate); for a second system
# these would move behind the provider.

# Being one of these gives the BEARER disadvantage on its own attacks/checks.
SELF_DISADVANTAGE_CONDITIONS = frozenset(
    {"poisoned", "frightened", "prone", "blinded", "restrained", "exhausted"}
)
# Being one of these gives ATTACKERS advantage against the bearer.
ATTACKERS_ADVANTAGE_CONDITIONS = frozenset(
    {"prone", "blinded", "stunned", "paralyzed", "restrained", "unconscious"}
)
# Being one of these means the bearer cannot take actions at all.
INCAPACITATING_CONDITIONS = frozenset(
    {"stunned", "paralyzed", "unconscious", "incapacitated"}
)


def entity_conditions(entity: Entity) -> set[str]:
    """The set of conditions on an entity (empty if none / malformed)."""
    raw = entity.attributes.get("conditions")
    if isinstance(raw, list):
        return {c for c in raw if isinstance(c, str)}
    return set()


def is_incapacitated(entity: Entity) -> bool:
    return bool(entity_conditions(entity) & INCAPACITATING_CONDITIONS)


def entity_condition_meta(entity: Entity) -> dict[str, dict]:
    """The per-condition expiry spec on an entity, keyed by condition name.

    Companion to `conditions` (the plain list everything reads): a condition
    listed here carries a `{"duration": int}` (auto-expiry countdown in the
    bearer's own turns) and/or a `{"save": {"ability": str, "dc": int}}`
    (save-ends — re-rolled at the bearer's turn-end to shake it off). A
    condition with NO meta entry is permanent until cured. Malformed values
    are ignored (empty dict)."""
    raw = entity.attributes.get("condition_meta")
    if not isinstance(raw, dict):
        return {}
    return {k: v for k, v in raw.items() if isinstance(k, str) and isinstance(v, dict)}


def _combine_advantage(adv: bool, disadv: bool) -> str:
    """5e rule: advantage and disadvantage cancel to a straight roll."""
    if adv and disadv:
        return "none"
    if adv:
        return "advantage"
    if disadv:
        return "disadvantage"
    return "none"


def attack_advantage(attacker: Entity, target: Entity) -> str:
    """'advantage' | 'disadvantage' | 'none' for attacker → target, derived
    from both entities' conditions."""
    return _combine_advantage(
        adv=bool(entity_conditions(target) & ATTACKERS_ADVANTAGE_CONDITIONS),
        disadv=bool(entity_conditions(attacker) & SELF_DISADVANTAGE_CONDITIONS),
    )


def check_advantage(actor: Entity) -> str:
    """'disadvantage' | 'none' for an ability check, from the actor's own
    conditions (no target-granted advantage on a check)."""
    return _combine_advantage(
        adv=False,
        disadv=bool(entity_conditions(actor) & SELF_DISADVANTAGE_CONDITIONS),
    )


def _roll_d20(advantage: str, rng: random.Random) -> tuple[int, list[int]]:
    """Roll the d20 honoring advantage/disadvantage. Returns (chosen, raws).
    The chosen die is what counts for the total AND for crit/fumble (5e: a
    natural 20 on the kept die crits)."""
    if advantage == "none":
        r = rng.randint(1, 20)
        return r, [r]
    a, b = rng.randint(1, 20), rng.randint(1, 20)
    chosen = max(a, b) if advantage == "advantage" else min(a, b)
    return chosen, [a, b]


# ---------------------------------------------------------------------------
# M12 damage types + resistances (dnd5e_lite)
# ---------------------------------------------------------------------------
#
# An attack's damage carries an optional *type* (the attacker's
# `weapon_damage_type`, e.g. "slashing", "fire", "poison"). A target may carry
# `resistances` / `vulnerabilities` / `immunities` lists of damage-type names.
# Typed damage is scaled by them before it lands; UNTYPED damage (no
# weapon_damage_type) is never scaled, so older seeds behave exactly as before.


def _typed_damage_set(entity: Entity, attr: str) -> set[str]:
    """Lower-cased set of damage-type names in a target's list attribute
    (`resistances` / `vulnerabilities` / `immunities`)."""
    raw = entity.attributes.get(attr)
    if isinstance(raw, list):
        return {d.lower() for d in raw if isinstance(d, str)}
    return set()


def apply_damage_resistance(
    target: Entity, damage_type: str | None, amount: int
) -> tuple[int, str]:
    """Scale `amount` of `damage_type` damage by the target's defenses.
    Returns (final_amount, effect) where effect is one of
    'none' | 'immune' | 'resisted' | 'vulnerable'.

    5e rules: immunity → 0; vulnerability → ×2; resistance → half (round
    down); having BOTH resistance and vulnerability to the same type cancels
    to normal. Untyped damage (damage_type falsy) is returned unscaled."""
    if not isinstance(damage_type, str) or not damage_type:
        return amount, "none"
    dt = damage_type.lower()
    if dt in _typed_damage_set(target, "immunities"):
        return 0, "immune"
    resistant = dt in _typed_damage_set(target, "resistances")
    vulnerable = dt in _typed_damage_set(target, "vulnerabilities")
    if resistant and vulnerable:
        return amount, "none"
    if vulnerable:
        return amount * 2, "vulnerable"
    if resistant:
        return amount // 2, "resisted"
    return amount, "none"


@dataclass(frozen=True)
class AttackResolution:
    """
    Structured outcome of an attack. The beat-2 narration prompt is built
    from this — the LLM never sees a die roll the runner didn't compute,
    and never has to do arithmetic on its own.

    `damage_*` fields are None on a miss. `damage_total` is the ROLLED damage
    (dice + mod, after crit doubling); `damage_applied` is what actually came
    off hp after resistances — they differ only when a damage type is resisted
    or amplified.
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
    # M12 combat depth (defaults keep older call sites / tests valid):
    crit: bool = False                       # natural 20 — auto-hit, double dice
    fumble: bool = False                     # natural 1 — auto-miss
    advantage: str = "none"                  # "advantage" | "disadvantage" | "none"
    applied_conditions: tuple[str, ...] = () # conditions the hit inflicted
    rider_save: SaveResolution | None = None # the target's save vs an on-hit rider
    damage_type: str | None = None           # "slashing" | "fire" | … (None = untyped)
    damage_applied: int | None = None        # hp actually lost (after resistances)
    resistance_effect: str = "none"          # "none"|"immune"|"resisted"|"vulnerable"
    # A provider whose dice frame is not d20 (coc_lite d100 roll-under) supplies
    # its own roll narration here; None = the runner's d20 default text.
    roll_text: str | None = None


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

    # M12: advantage/disadvantage is derived from conditions (the rules grant
    # it — the player never chooses it), and a natural 20/1 auto-hits/misses.
    advantage = attack_advantage(attacker, target)
    d20, _raws = _roll_d20(advantage, rng)
    attack_total = d20 + attack_mod
    crit = d20 == 20
    fumble = d20 == 1
    hit = crit or (not fumble and attack_total >= target_ac)  # ties hit (5e)

    attack_formula = _format_d20_formula(attack_mod)
    adv_tag = "" if advantage == "none" else f" [{advantage}]"
    payloads: list[Payload] = [
        DiceRolled(
            formula=attack_formula,
            result=attack_total,
            reason=f"attack: {attacker.entity_id} -> {target.entity_id}{adv_tag}",
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
                crit=False,
                fumble=fumble,
                advantage=advantage,
            ),
            payloads,
        )

    damage_formula = attacker.attributes.get("weapon_damage")
    if not isinstance(damage_formula, str) or not damage_formula:
        raise MechanicsError(
            f"attacker {attacker.entity_id!r} hit but has no 'weapon_damage' attribute"
        )
    damage_roll = roll_detailed(damage_formula, rng)
    damage_dice = damage_roll.dice_total
    if crit:
        # 5e critical hit: roll the damage DICE again (the flat mod is not
        # doubled). A second roll keeps the rng record honest for replay.
        crit_extra = roll_detailed(damage_formula, rng)
        damage_dice += crit_extra.dice_total
    damage_total = damage_dice + damage_roll.mod

    # M12: typed damage is scaled by the target's resistances/vulnerabilities/
    # immunities before it lands. Untyped damage is unaffected.
    damage_type = attacker.attributes.get("weapon_damage_type")
    if not isinstance(damage_type, str) or not damage_type:
        damage_type = None
    damage_applied, resistance_effect = apply_damage_resistance(target, damage_type, damage_total)

    type_tag = f" [{damage_type}]" if damage_type else ""
    effect_tag = "" if resistance_effect == "none" else f" [{resistance_effect}]"
    payloads.append(
        DiceRolled(
            formula=damage_formula,
            result=damage_total,
            reason=f"damage: {attacker.entity_id} -> {target.entity_id}"
                   + type_tag + (" [CRIT]" if crit else "") + effect_tag,
        )
    )
    payloads.append(
        AttributeDelta(
            entity_id=target.entity_id,
            attr="hp",
            delta=-damage_applied,
        )
    )

    # On-hit condition rider: an attacker with an `applies_condition` attribute
    # (e.g. a venomous bite → "poisoned") inflicts it on a hit. The rider may be
    # a plain string (apply permanently) or a dict that lets the target make a
    # save to resist and/or attaches an expiry (duration / save-ends) — see
    # `_resolve_on_hit_condition`.
    rider_payloads, applied, rider_save = _resolve_on_hit_condition(attacker, target, rng)
    payloads.extend(rider_payloads)

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
            damage_dice=damage_dice,
            damage_mod=damage_roll.mod,
            damage_total=damage_total,
            target_hp_before=hp_before,
            crit=crit,
            fumble=False,
            advantage=advantage,
            applied_conditions=applied,
            rider_save=rider_save,
            damage_type=damage_type,
            damage_applied=damage_applied,
            resistance_effect=resistance_effect,
        ),
        payloads,
    )


def _resolve_on_hit_condition(
    attacker: Entity,
    target: Entity,
    rng: random.Random,
) -> tuple[list[Payload], tuple[str, ...], "SaveResolution | None"]:
    """Resolve an attacker's `applies_condition` rider against a just-hit
    target. Returns (payloads, applied_conditions, rider_save).

    Two authoring shapes:
      - plain string ("poisoned")  → apply permanently, no save, no expiry
        (backward-compatible with the M12 step-1 rider).
      - dict, e.g.
          {"condition": "poisoned", "save": "con", "dc": 12,
           "duration": 3, "save_ends": false}
        `save`+`dc` → the target rolls an initial save to AVOID it entirely
        (success = nothing sticks). `duration` → auto-expiry countdown (in the
        bearer's own turns). `save_ends` → the condition is re-saved each
        turn-end to shake off. Both expiry forms ride a `condition_meta`
        companion AttributeSet so the runner's per-turn tick can resolve them.
    """
    rider = attacker.attributes.get("applies_condition")

    # Plain-string rider — permanent, no save (unchanged behaviour).
    if isinstance(rider, str) and rider:
        if rider in entity_conditions(target):
            return [], (), None
        new_conditions = sorted(entity_conditions(target) | {rider})
        return (
            [AttributeSet(entity_id=target.entity_id, attr="conditions", value=new_conditions)],
            (rider,),
            None,
        )

    if not isinstance(rider, dict):
        return [], (), None

    condition = rider.get("condition")
    if not (isinstance(condition, str) and condition):
        return [], (), None

    dc = rider.get("dc")
    dc = dc if isinstance(dc, int) and not isinstance(dc, bool) else None
    save_ability = rider.get("save")
    has_initial_save = isinstance(save_ability, str) and bool(save_ability) and dc is not None

    payloads: list[Payload] = []
    rider_save: SaveResolution | None = None

    # Initial save-to-avoid: a success resists the condition outright.
    if has_initial_save:
        rider_save, save_payloads = resolve_save(target, save_ability, dc, rng)
        payloads.extend(save_payloads)
        if rider_save.success:
            return payloads, (), rider_save

    # Already on the target — record nothing new (don't refresh expiry here).
    if condition in entity_conditions(target):
        return payloads, (), rider_save

    new_conditions = sorted(entity_conditions(target) | {condition})
    payloads.append(
        AttributeSet(entity_id=target.entity_id, attr="conditions", value=new_conditions)
    )

    # Attach an expiry spec (duration and/or save-ends) via condition_meta.
    spec: dict[str, Any] = {}
    duration = rider.get("duration")
    if isinstance(duration, int) and not isinstance(duration, bool):
        spec["duration"] = duration
    if rider.get("save_ends") and dc is not None:
        ability = save_ability if (isinstance(save_ability, str) and save_ability) else "con"
        spec["save"] = {"ability": ability, "dc": dc}
    if spec:
        new_meta = {**entity_condition_meta(target), condition: spec}
        payloads.append(
            AttributeSet(entity_id=target.entity_id, attr="condition_meta", value=new_meta)
        )

    return payloads, (condition,), rider_save


# ---------------------------------------------------------------------------
# M12: multi-target / area attacks (save-based, breath-weapon shape)
# ---------------------------------------------------------------------------
#
# An entity authored with an `area_attack` attribute sweeps EVERY opposing
# target in its room when it attacks, instead of striking one. The shape is
# the 5e breath weapon / fireball primitive — one damage roll, each target
# makes a saving throw, save = half damage — because that is exactly the
# Tier-A spell op the spells milestone needs (see M12_PLANNING "Spells").
# Opt-in from content (invariant 6/8): no `area_attack` attribute → nothing
# changes; existing seeds replay byte-identical.
#
# Authoring shape (entity attributes):
#   "area_attack": {
#     "save": "dex", "dc": 12,            # required — the saving throw
#     "damage": "2d6",                    # required — rolled ONCE for all
#     "damage_type": "fire",              # optional — resistances apply
#     "half_on_save": true,               # optional, default true
#                                         #   (false = no damage on a save)
#     "applies_condition":                # optional — failed saves only
#         "blinded"  OR  {"condition": "blinded", "duration": 2}
#   }


@dataclass(frozen=True)
class AreaTargetOutcome:
    """One target's slice of an area attack."""

    target_id: str
    save: SaveResolution
    damage_after_save: int          # rolled total, halved/zeroed by the save
    damage_applied: int             # hp actually lost (after resistances)
    resistance_effect: str          # "none"|"immune"|"resisted"|"vulnerable"
    target_hp_before: int
    applied_conditions: tuple[str, ...] = ()


@dataclass(frozen=True)
class AreaAttackResolution:
    """Structured outcome of an area attack — one damage roll, N saves."""

    attacker_id: str
    save_ability: str
    dc: int
    damage_formula: str
    damage_type: str | None
    damage_total: int               # the single rolled total (before saves)
    targets: tuple[AreaTargetOutcome, ...]


def area_attack_spec(entity: Entity) -> dict | None:
    """The entity's authored `area_attack` spec, or None. The runner asks
    the provider this instead of reading attributes itself, so 'what makes
    an attack an area attack' stays ruleset knowledge (invariant 8)."""
    raw = entity.attributes.get("area_attack")
    return raw if isinstance(raw, dict) else None


def resolve_area_attack(
    attacker: Entity,
    targets: list[Entity],
    rng: random.Random,
) -> tuple[AreaAttackResolution, list[Payload]]:
    """Resolve one area attack against `targets` (the runner supplies the
    co-located opposing entities). Damage is rolled ONCE; each target rolls
    the spec's save — success halves (or zeroes) it; resistances then scale
    per target; an optional condition rider lands on FAILED saves only.

    Payload order: the area damage roll, then per target (in the given
    order): save roll, hp delta (if any), condition payloads (if any). The
    runner appends, re-projects, and settles downed state per target —
    mechanics never touches status (same contract as `resolve_attack`)."""
    spec = area_attack_spec(attacker)
    if spec is None:
        raise MechanicsError(
            f"attacker {attacker.entity_id!r} has no 'area_attack' spec"
        )
    save_ability = spec.get("save")
    dc = spec.get("dc")
    damage_formula = spec.get("damage")
    if not (isinstance(save_ability, str) and save_ability):
        raise MechanicsError("area_attack spec missing 'save' ability")
    if not isinstance(dc, int) or isinstance(dc, bool):
        raise MechanicsError("area_attack spec missing int 'dc'")
    if not (isinstance(damage_formula, str) and damage_formula):
        raise MechanicsError("area_attack spec missing 'damage' formula")
    if not targets:
        raise MechanicsError("area attack resolved with no targets")
    damage_type = spec.get("damage_type")
    if not isinstance(damage_type, str) or not damage_type:
        damage_type = None
    half_on_save = spec.get("half_on_save", True) is not False

    damage_roll = roll_detailed(damage_formula, rng)
    damage_total = damage_roll.dice_total + damage_roll.mod

    type_tag = f" [{damage_type}]" if damage_type else ""
    payloads: list[Payload] = [
        DiceRolled(
            formula=damage_formula,
            result=damage_total,
            reason=(
                f"area attack: {attacker.entity_id} "
                f"({save_ability} save DC {dc}, {len(targets)} targets){type_tag}"
            ),
        )
    ]

    outcomes: list[AreaTargetOutcome] = []
    for target in targets:
        hp_before = _require_int(target, "hp")
        save, save_payloads = resolve_save(target, save_ability, dc, rng)
        payloads.extend(save_payloads)

        if save.success:
            after_save = damage_total // 2 if half_on_save else 0
        else:
            after_save = damage_total
        applied, effect = apply_damage_resistance(target, damage_type, after_save)

        if applied > 0:
            payloads.append(
                AttributeDelta(entity_id=target.entity_id, attr="hp", delta=-applied)
            )

        applied_conditions: tuple[str, ...] = ()
        if not save.success:
            cond_payloads, applied_conditions = _stage_area_condition(
                spec.get("applies_condition"), target
            )
            payloads.extend(cond_payloads)

        outcomes.append(
            AreaTargetOutcome(
                target_id=target.entity_id,
                save=save,
                damage_after_save=after_save,
                damage_applied=applied,
                resistance_effect=effect,
                target_hp_before=hp_before,
                applied_conditions=applied_conditions,
            )
        )

    return (
        AreaAttackResolution(
            attacker_id=attacker.entity_id,
            save_ability=save.ability,
            dc=dc,
            damage_formula=damage_formula,
            damage_type=damage_type,
            damage_total=damage_total,
            targets=tuple(outcomes),
        ),
        payloads,
    )


def _stage_area_condition(
    rider: Any, target: Entity
) -> tuple[list[Payload], tuple[str, ...]]:
    """Apply an area attack's condition rider to a failed-save target.
    Accepts a plain condition name or `{"condition": str, "duration": int}`
    (the failed area save IS the resist roll, so no second save here —
    unlike the single-target rider in `_resolve_on_hit_condition`).
    Already-present conditions are not re-applied or refreshed."""
    if isinstance(rider, str) and rider:
        condition, duration = rider, None
    elif isinstance(rider, dict):
        condition = rider.get("condition")
        if not (isinstance(condition, str) and condition):
            return [], ()
        duration = rider.get("duration")
        if not isinstance(duration, int) or isinstance(duration, bool):
            duration = None
    else:
        return [], ()

    if condition in entity_conditions(target):
        return [], ()
    payloads: list[Payload] = [
        AttributeSet(
            entity_id=target.entity_id,
            attr="conditions",
            value=sorted(entity_conditions(target) | {condition}),
        )
    ]
    if duration is not None:
        new_meta = {**entity_condition_meta(target), condition: {"duration": duration}}
        payloads.append(
            AttributeSet(entity_id=target.entity_id, attr="condition_meta", value=new_meta)
        )
    return payloads, (condition,)


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
    advantage: str = "none"  # M12: "disadvantage" from conditions, else "none"
    roll_text: str | None = None  # non-d20 provider narration override


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

    # M12: the actor's conditions can impose disadvantage (poisoned, frightened…).
    advantage = check_advantage(actor)
    d20, _raws = _roll_d20(advantage, rng)
    total = d20 + stat_mod
    success = total >= dc  # ties succeed (5e standard)

    formula = _format_d20_formula(stat_mod)
    adv_tag = "" if advantage == "none" else f" [{advantage}]"
    reason = (
        f"check {purpose!r} ({stat}): {actor.entity_id} -> {target_id}{adv_tag}"
        if purpose
        else f"check ({stat}): {actor.entity_id} -> {target_id}{adv_tag}"
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
            advantage=advantage,
        ),
        payloads,
    )


# ---------------------------------------------------------------------------
# M12: saving throws
# ---------------------------------------------------------------------------
#
# A saving throw is the third d20 primitive (attack / check / save). It backs
# two things added in this slice: an on-hit rider's "save to avoid" and a
# condition's "save ends" shake-off at the bearer's turn-end. Like check/attack
# it only computes + returns payloads; the runner appends them.


@dataclass(frozen=True)
class SaveResolution:
    """Structured outcome of a saving throw (1d20 + save_mod vs DC)."""

    actor_id: str
    ability: str       # "con", "dex", "wis", …
    save_mod: int
    dc: int
    d20: int           # raw kept d20 (1..20)
    total: int         # d20 + save_mod
    success: bool
    advantage: str = "none"
    roll_text: str | None = None  # non-d20 provider narration override


def _save_mod(actor: Entity, ability: str) -> int:
    """Saving-throw modifier for an ability. Prefers an explicit
    `f"{ability}_save"` attribute (a proficient save authored on the seed),
    falling back to the raw `f"{ability}_mod"`, then 0. `ability` may be passed
    bare ("con") or already suffixed ("con_save"/"con_mod") — both resolve."""
    base = ability
    for suffix in ("_save", "_mod"):
        if base.endswith(suffix):
            base = base[: -len(suffix)]
            break
    for attr in (f"{base}_save", f"{base}_mod"):
        raw = actor.attributes.get(attr)
        if isinstance(raw, int) and not isinstance(raw, bool):
            return raw
    return 0


def resolve_save(
    actor: Entity,
    ability: str,
    dc: int,
    rng: random.Random,
    advantage: str = "none",
) -> tuple[SaveResolution, list[Payload]]:
    """Roll `1d20 + save_mod(actor, ability)` against `dc`. Ties succeed (5e).
    Saves are a straight roll unless a caller passes advantage explicitly —
    the self-disadvantage conditions apply to attacks/checks, not saves."""
    base = ability
    for suffix in ("_save", "_mod"):
        if base.endswith(suffix):
            base = base[: -len(suffix)]
            break
    save_mod = _save_mod(actor, ability)
    d20, _raws = _roll_d20(advantage, rng)
    total = d20 + save_mod
    success = total >= dc
    adv_tag = "" if advantage == "none" else f" [{advantage}]"
    payloads: list[Payload] = [
        DiceRolled(
            formula=_format_d20_formula(save_mod),
            result=total,
            reason=f"save ({base}): {actor.entity_id} vs DC {dc}{adv_tag}",
        )
    ]
    return (
        SaveResolution(
            actor_id=actor.entity_id,
            ability=base,
            save_mod=save_mod,
            dc=dc,
            d20=d20,
            total=total,
            success=success,
            advantage=advantage,
        ),
        payloads,
    )


# ---------------------------------------------------------------------------
# M12: death saves
# ---------------------------------------------------------------------------
#
# A downed PC (0 HP) makes a death saving throw on each of its turns. This is
# the dice half only — the success/failure *tally* and the unconscious →
# stable/dead transitions are the runner's state machine (it owns the event
# log). 5e: flat d20, no modifier. 10+ succeeds, <10 fails, nat 20 revives at
# 1 HP, nat 1 counts as two failures.

_DEATH_SAVE_REVIVE = "revive"
_DEATH_SAVE_SUCCESS = "success"
_DEATH_SAVE_FAILURE = "failure"
_DEATH_SAVE_DOUBLE_FAILURE = "double_failure"


@dataclass(frozen=True)
class DeathSaveResolution:
    """Outcome of one death saving throw. `outcome` is one of
    'revive' | 'success' | 'failure' | 'double_failure'."""

    actor_id: str
    d20: int
    outcome: str
    roll_text: str | None = None  # non-d20 provider narration override


def resolve_death_save(
    actor: Entity, rng: random.Random
) -> tuple[DeathSaveResolution, list[Payload]]:
    """Roll a flat d20 death save. Returns the classified outcome + the
    DiceRolled payload; the runner applies the tally/status change."""
    d20 = rng.randint(1, 20)
    if d20 == 20:
        outcome = _DEATH_SAVE_REVIVE
    elif d20 == 1:
        outcome = _DEATH_SAVE_DOUBLE_FAILURE
    elif d20 >= 10:
        outcome = _DEATH_SAVE_SUCCESS
    else:
        outcome = _DEATH_SAVE_FAILURE
    payloads: list[Payload] = [
        DiceRolled(formula="1d20", result=d20, reason=f"death save: {actor.entity_id}")
    ]
    return DeathSaveResolution(actor_id=actor.entity_id, d20=d20, outcome=outcome), payloads


# ---------------------------------------------------------------------------
# Mechanics provider registry (the third system-aware seam — invariant 8)
# ---------------------------------------------------------------------------
#
# `seed.py` keys the attribute schema by ruleset id, `ruleset.py` keys the
# action economy. Mechanics was the one seam still called by bare function from
# the runner. Promoting it to a provider keyed by ruleset id means a second
# system (CoC d100, Traveller 2d6) is a *new provider*, not a branch in the
# runner — and new D&D depth (saves, etc.) is a *new method on the provider*,
# not a new top-level function the runner has to import and dispatch.
#
# The dnd5e_lite provider delegates to the module-level resolvers above (which
# stay as the canonical implementation + direct-unit-test surface), so this
# refactor changes no behaviour.


class MechanicsProvider(Protocol):
    """Ruleset-keyed dice/resolution math the runner dispatches through."""

    name: str

    def resolve_attack(
        self, attacker: Entity, target: Entity, rng: random.Random
    ) -> tuple[Any, list[Payload]]: ...

    def resolve_check(
        self, actor: Entity, target_id: str, stat: str, dc: int,
        rng: random.Random, purpose: str = "",
    ) -> tuple[Any, list[Payload]]: ...

    def resolve_save(
        self, actor: Entity, ability: str, dc: int,
        rng: random.Random, advantage: str = "none",
    ) -> tuple[Any, list[Payload]]: ...

    def resolve_death_save(
        self, actor: Entity, rng: random.Random,
    ) -> tuple[Any, list[Payload]]: ...

    def area_attack_spec(self, attacker: Entity) -> dict | None: ...

    def resolve_area_attack(
        self, attacker: Entity, targets: list[Entity], rng: random.Random,
    ) -> tuple[Any, list[Payload]]: ...

    def interpret_check(
        self, actor: Entity, stat: str, dc: int, logged_result: int,
    ) -> tuple[bool, str]: ...


class DND5eLiteMechanics:
    """The d20 ruleset the engine ships with. Methods delegate to the
    module-level resolvers; future mechanics (saves, advantage, …) land as new
    methods here, not as new top-level functions."""

    name = "dnd5e_lite"

    def resolve_attack(
        self, attacker: Entity, target: Entity, rng: random.Random
    ) -> tuple[AttackResolution, list[Payload]]:
        return resolve_attack(attacker, target, rng)

    def resolve_check(
        self, actor: Entity, target_id: str, stat: str, dc: int,
        rng: random.Random, purpose: str = "",
    ) -> tuple[CheckResolution, list[Payload]]:
        return resolve_check(actor, target_id, stat, dc, rng, purpose=purpose)

    def resolve_save(
        self, actor: Entity, ability: str, dc: int,
        rng: random.Random, advantage: str = "none",
    ) -> tuple[SaveResolution, list[Payload]]:
        return resolve_save(actor, ability, dc, rng, advantage=advantage)

    def resolve_death_save(
        self, actor: Entity, rng: random.Random,
    ) -> tuple[DeathSaveResolution, list[Payload]]:
        return resolve_death_save(actor, rng)

    def area_attack_spec(self, attacker: Entity) -> dict | None:
        return area_attack_spec(attacker)

    def resolve_area_attack(
        self, attacker: Entity, targets: list[Entity], rng: random.Random,
    ) -> tuple[AreaAttackResolution, list[Payload]]:
        return resolve_area_attack(attacker, targets, rng)

    def interpret_check(
        self, actor: Entity, stat: str, dc: int, logged_result: int,
    ) -> tuple[bool, str]:
        """Re-derive a check's pass/fail + a human comparison string from the
        already-logged roll, WITHOUT consuming rng — for the UI verdict chip.
        `logged_result` is the d20 *total* (roll+mod) the runner recorded;
        5e ties succeed. Mirrors `resolve_check`'s rule exactly."""
        return logged_result >= dc, f"{logged_result} vs DC {dc}"


_PROVIDERS: dict[str, MechanicsProvider] = {"dnd5e_lite": DND5eLiteMechanics()}


def get_mechanics(name: str) -> MechanicsProvider:
    """Return the mechanics provider for a ruleset id. Mirrors
    `seed.get_ruleset` / `ruleset.get_action_economy`."""
    provider = _PROVIDERS.get(name)
    if provider is None:
        raise MechanicsError(
            f"unknown ruleset {name!r} (known: {sorted(_PROVIDERS)})"
        )
    return provider
