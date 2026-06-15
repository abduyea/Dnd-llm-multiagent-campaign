"""
coc_lite — a Call of Cthulhu (7e-flavored) ruleset behind the three
system-aware registries (invariant 8).

This module is the second system the registries were built for. It adds:
  - `CoCLiteSchema`     -> seed._RULESETS["coc_lite"]      (attribute schema)
  - `CoCLiteEconomy`    -> ruleset._VALIDATORS["coc_lite"] (action economy)
  - `CoCLiteMechanics`  -> mechanics._PROVIDERS["coc_lite"] (dice frame)

Importing this module registers all three. The spine, runner, scheduler,
projection, and prompts are untouched — the runner dispatches through
`get_mechanics(ruleset)` and narrates from each resolution's `roll_text`.

Dice frame: percentile roll-under. A skill or characteristic is a flat int
attribute named `<skill>_pct` (0..100); a check succeeds when d100 <= skill.
Conventions (deliberate coc_lite simplifications, documented here):
  - Difficulty: a content-authored DC < 15 is a Regular check (d100 <= skill);
    DC >= 15 is Hard (d100 <= skill // 2). The numeric DC is otherwise unused.
  - Critical: a roll of 01, or an Extreme success (<= skill // 5) on attacks
    (deals maximum damage). Fumble: 96-100 when skill < 50, else 100.
  - Combat: attacker rolls their own skill (named by `attack_skill`, default
    `fighting_pct`); there is no AC. The target's `armor` int reduces damage
    flat (min 0). No opposed dodge rolls in coc_lite.
  - Sanity: a check with stat `sanity_pct` is a SAN roll. On a failure the
    actor loses 1d6 sanity (an AttributeDelta payload the runner stages like
    any other), and a loss of 4+ inflicts a 2-turn `shaken` condition. On a
    success the loss is 0. (Real CoC authors loss per horror; coc_lite uses
    one global 0/1d6 so the provider needs no target data.)
  - Dying: the engine's downing machinery is system-neutral; coc_lite backs
    it with a CON roll (d100 <= con_pct) instead of a flat d20.
  - Initiative: the runner rolls 1d20+dex_mod; CoC entities author dex_mod
    (~DEX/10) so turn order still favors high-DEX investigators.
"""
from __future__ import annotations

import random
import re
from typing import Any

import mechanics
import ruleset
import seed
from dice import roll_detailed
from mechanics import (
    AttackResolution,
    CheckResolution,
    DeathSaveResolution,
    MechanicsError,
    SaveResolution,
)
from models import AttributeDelta, AttributeSet, DiceRolled, Entity, Payload
from seed import SeedValidationError

# Difficulty: content DCs at or above this are Hard (roll <= skill // 2).
HARD_DC_THRESHOLD = 15

# Sanity: global coc_lite loss rule (success/failure), and the failed-loss
# size that inflicts the temporary `shaken` condition.
SAN_LOSS_FAIL_FORMULA = "1d6"
SHAKEN_LOSS_THRESHOLD = 4
SHAKEN_DURATION_TURNS = 2


# ---------------------------------------------------------------------------
# Attribute schema (seed-time validation)
# ---------------------------------------------------------------------------


class CoCLiteSchema:
    name = "coc_lite"

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
        # Investigators must have a sanity to lose.
        if entity_kind == "pc" and "sanity_pct" not in attrs:
            raise SeedValidationError(
                "coc_lite PCs require a 'sanity_pct' attribute"
            )


# ---------------------------------------------------------------------------
# Action economy
# ---------------------------------------------------------------------------


class CoCLiteEconomy(ruleset.DND5eLiteEconomy):
    """coc_lite keeps the engine's one-action/one-move turn shape — CoC's
    economy is no richer at this fidelity, and reusing the validator keeps
    the player-prompt affordance text identical."""

    name = "coc_lite"


# ---------------------------------------------------------------------------
# Mechanics provider (d100 roll-under)
# ---------------------------------------------------------------------------


def _skill_label(stat: str) -> str:
    """'spot_hidden_pct' -> 'Spot Hidden'."""
    base = stat[:-4] if stat.endswith("_pct") else stat
    return base.replace("_", " ").title()


def _skill_value(entity: Entity, stat: str) -> tuple[str, int]:
    """Resolve a stat name to (attribute_key, int value). Accepts the bare
    form ('sanity') when only the suffixed attribute ('sanity_pct') exists,
    so a model that drops the suffix still rolls the right skill."""
    attrs = entity.attributes
    key = stat
    if key not in attrs and not key.endswith("_pct") and f"{key}_pct" in attrs:
        key = f"{key}_pct"
    raw = attrs.get(key, 0)
    if isinstance(raw, int) and not isinstance(raw, bool):
        return key, raw
    return key, 0


def _is_fumble(roll: int, skill: int) -> bool:
    return roll >= 96 if skill < 50 else roll == 100


def _max_damage(formula: str) -> int:
    """Maximum result of an NdM(+/-K) formula (extreme-success damage)."""
    m = re.fullmatch(r"\s*(\d*)d(\d+)\s*([+-]\s*\d+)?\s*", formula)
    if not m:
        try:
            return int(formula)
        except ValueError as exc:
            raise MechanicsError(f"cannot parse damage formula {formula!r}") from exc
    n = int(m.group(1) or "1")
    sides = int(m.group(2))
    mod = int(m.group(3).replace(" ", "")) if m.group(3) else 0
    return n * sides + mod


class CoCLiteMechanics:
    """Percentile roll-under resolution. Same provider protocol, same
    payload vocabulary — only the dice frame and narration change."""

    name = "coc_lite"

    # -- checks -------------------------------------------------------------

    def resolve_check(
        self, actor: Entity, target_id: str, stat: str, dc: int,
        rng: random.Random, purpose: str = "",
    ) -> tuple[CheckResolution, list[Payload]]:
        stat_key, skill = _skill_value(actor, stat)
        hard = dc >= HARD_DC_THRESHOLD
        threshold = skill // 2 if hard else skill
        roll = rng.randint(1, 100)
        if roll == 1:
            success = True
        elif _is_fumble(roll, skill):
            success = False
        else:
            success = roll <= threshold

        label = _skill_label(stat_key)
        diff_tag = f" [Hard {threshold}]" if hard else ""
        roll_text = f"d100={roll} vs {label} {skill}{diff_tag}"

        reason = (
            f"check {purpose!r} ({stat_key}): {actor.entity_id} -> {target_id}"
            if purpose
            else f"check ({stat_key}): {actor.entity_id} -> {target_id}"
        )
        payloads: list[Payload] = [
            DiceRolled(formula="1d100", result=roll, reason=reason),
        ]

        if stat_key == "sanity_pct":
            payloads.extend(self._sanity_loss_payloads(actor, success, rng))

        return (
            CheckResolution(
                actor_id=actor.entity_id,
                target_id=target_id,
                stat=stat_key,
                stat_mod=skill,
                dc=dc,
                d20=roll,        # the raw percentile roll (field name is historic)
                total=roll,
                success=success,
                purpose=purpose,
                roll_text=roll_text,
            ),
            payloads,
        )

    def _sanity_loss_payloads(
        self, actor: Entity, success: bool, rng: random.Random,
    ) -> list[Payload]:
        """A failed SAN roll costs 1d6 sanity; 4+ lost also inflicts a
        temporary `shaken` condition (expires via the runner's generic
        condition ticker). A success costs nothing."""
        if success:
            return []
        loss_roll = roll_detailed(SAN_LOSS_FAIL_FORMULA, rng)
        loss = loss_roll.total
        payloads: list[Payload] = [
            DiceRolled(
                formula=SAN_LOSS_FAIL_FORMULA, result=loss,
                reason=f"sanity loss: {actor.entity_id}",
            ),
            AttributeDelta(entity_id=actor.entity_id, attr="sanity_pct", delta=-loss),
        ]
        if loss >= SHAKEN_LOSS_THRESHOLD:
            conditions = mechanics.entity_conditions(actor) | {"shaken"}
            meta = dict(mechanics.entity_condition_meta(actor))
            meta["shaken"] = {"duration": SHAKEN_DURATION_TURNS}
            payloads.append(AttributeSet(
                entity_id=actor.entity_id, attr="conditions",
                value=sorted(conditions),
            ))
            payloads.append(AttributeSet(
                entity_id=actor.entity_id, attr="condition_meta", value=meta,
            ))
        return payloads

    # -- attacks ------------------------------------------------------------

    def resolve_attack(
        self, attacker: Entity, target: Entity, rng: random.Random,
    ) -> tuple[AttackResolution, list[Payload]]:
        skill_attr = attacker.attributes.get("attack_skill", "fighting_pct")
        if not isinstance(skill_attr, str) or not skill_attr:
            skill_attr = "fighting_pct"
        skill_key, skill = _skill_value(attacker, skill_attr)
        hp_before_raw = target.attributes.get("hp", 0)
        hp_before = hp_before_raw if isinstance(hp_before_raw, int) else 0

        roll = rng.randint(1, 100)
        fumble = _is_fumble(roll, skill)
        extreme = roll == 1 or (not fumble and roll <= skill // 5)
        hit = not fumble and (roll == 1 or roll <= skill)

        label = _skill_label(skill_key)
        roll_text = f"d100={roll} vs {label} {skill}"

        payloads: list[Payload] = [
            DiceRolled(
                formula="1d100", result=roll,
                reason=f"attack: {attacker.entity_id} -> {target.entity_id}",
            )
        ]

        if not hit:
            return (
                AttackResolution(
                    attacker_id=attacker.entity_id,
                    target_id=target.entity_id,
                    attack_d20=roll,
                    attack_mod=skill,
                    attack_total=roll,
                    target_ac=0,
                    hit=False,
                    damage_formula=None,
                    damage_dice=None,
                    damage_mod=None,
                    damage_total=None,
                    target_hp_before=hp_before,
                    fumble=fumble,
                    roll_text=roll_text,
                ),
                payloads,
            )

        damage_formula = attacker.attributes.get("weapon_damage")
        if not isinstance(damage_formula, str) or not damage_formula:
            raise MechanicsError(
                f"attacker {attacker.entity_id!r} hit but has no 'weapon_damage' attribute"
            )
        if extreme:
            # Extreme success (roll <= skill/5): maximum damage.
            damage_total = _max_damage(damage_formula)
            damage_dice = damage_total
            damage_mod = 0
        else:
            damage_roll = roll_detailed(damage_formula, rng)
            damage_dice = damage_roll.dice_total
            damage_mod = damage_roll.mod
            damage_total = damage_dice + damage_mod

        armor_raw = target.attributes.get("armor", 0)
        armor = armor_raw if isinstance(armor_raw, int) and not isinstance(armor_raw, bool) else 0
        damage_applied = max(0, damage_total - armor)

        extreme_tag = " [EXTREME — max damage]" if extreme else ""
        armor_tag = f" [armor -{armor}]" if armor else ""
        payloads.append(
            DiceRolled(
                formula=damage_formula, result=damage_total,
                reason=f"damage: {attacker.entity_id} -> {target.entity_id}"
                       + extreme_tag + armor_tag,
            )
        )
        payloads.append(
            AttributeDelta(entity_id=target.entity_id, attr="hp", delta=-damage_applied)
        )

        if extreme:
            roll_text += " — EXTREME success"
        if armor:
            roll_text += f"; armor absorbs {min(armor, damage_total)}"

        # San-loss-on-hit rider (content opt-in, the CoC sibling of the D&D
        # `applies_condition` rider): an attacker authored with
        # `san_loss_on_hit: "1d4"` sears the mind of any sanity-bearing
        # target it strikes — no save; some things cost sanity to touch.
        san_formula = attacker.attributes.get("san_loss_on_hit")
        if (
            isinstance(san_formula, str) and san_formula
            and isinstance(target.attributes.get("sanity_pct"), int)
        ):
            san_roll = roll_detailed(san_formula, rng)
            payloads.append(DiceRolled(
                formula=san_formula, result=san_roll.total,
                reason=f"sanity loss: {target.entity_id}",
            ))
            payloads.append(AttributeDelta(
                entity_id=target.entity_id, attr="sanity_pct",
                delta=-san_roll.total,
            ))
            roll_text += f"; its touch costs {target.display_name} {san_roll.total} SAN"

        return (
            AttackResolution(
                attacker_id=attacker.entity_id,
                target_id=target.entity_id,
                attack_d20=roll,
                attack_mod=skill,
                attack_total=roll,
                target_ac=armor,
                hit=True,
                damage_formula=damage_formula,
                damage_dice=damage_dice,
                damage_mod=damage_mod,
                damage_total=damage_total,
                target_hp_before=hp_before,
                crit=extreme,
                damage_applied=damage_applied,
                roll_text=roll_text,
            ),
            payloads,
        )

    # -- saves --------------------------------------------------------------

    def resolve_save(
        self, actor: Entity, ability: str, dc: int,
        rng: random.Random, advantage: str = "none",
    ) -> tuple[SaveResolution, list[Payload]]:
        """A 'save' in coc_lite is a characteristic roll: d100 <= the
        actor's `<ability>_pct`. The numeric DC is ignored (roll-under
        carries its own difficulty); it is kept on the resolution for
        the event record."""
        base = ability
        for suffix in ("_save", "_mod", "_pct"):
            if base.endswith(suffix):
                base = base[: -len(suffix)]
                break
        _, value = _skill_value(actor, f"{base}_pct")
        roll = rng.randint(1, 100)
        success = roll == 1 or (not _is_fumble(roll, value) and roll <= value)
        roll_text = f"d100={roll} vs {base.upper()} {value}"
        payloads: list[Payload] = [
            DiceRolled(
                formula="1d100", result=roll,
                reason=f"save ({base}): {actor.entity_id}",
            )
        ]
        return (
            SaveResolution(
                actor_id=actor.entity_id,
                ability=base,
                save_mod=value,
                dc=dc,
                d20=roll,
                total=roll,
                success=success,
                roll_text=roll_text,
            ),
            payloads,
        )

    # -- dying --------------------------------------------------------------

    def resolve_death_save(
        self, actor: Entity, rng: random.Random,
    ) -> tuple[DeathSaveResolution, list[Payload]]:
        """A dying investigator clings to life on a CON roll. Outcomes map
        onto the runner's system-neutral tally: 01 = a miraculous rally
        (back to 1 HP), <= CON = success, 96+ = two failures, else failure."""
        _, con = _skill_value(actor, "con_pct")
        roll = rng.randint(1, 100)
        if roll == 1:
            outcome = "revive"
        elif roll >= 96:
            outcome = "double_failure"
        elif roll <= con:
            outcome = "success"
        else:
            outcome = "failure"
        roll_text = f"d100={roll} vs CON {con}"
        payloads: list[Payload] = [
            DiceRolled(
                formula="1d100", result=roll,
                reason=f"death save: {actor.entity_id}",
            )
        ]
        return (
            DeathSaveResolution(
                actor_id=actor.entity_id, d20=roll, outcome=outcome,
                roll_text=roll_text,
            ),
            payloads,
        )

    # -- area attacks (not in coc_lite) ---------------------------------------

    def area_attack_spec(self, attacker: Entity) -> dict | None:
        return None

    def resolve_area_attack(
        self, attacker: Entity, targets: list[Entity], rng: random.Random,
    ) -> tuple[Any, list[Payload]]:
        raise MechanicsError("coc_lite has no area attacks")

    # -- UI chip support ----------------------------------------------------

    def interpret_check(
        self, actor: Entity, stat: str, dc: int, logged_result: int,
    ) -> tuple[bool, str]:
        """Re-derive a check's pass/fail + a human comparison from the logged
        d100, WITHOUT consuming rng — for the UI verdict chip. Mirrors
        `resolve_check`'s roll-UNDER rule (the logged result is the raw d100):
        a content DC >= HARD_DC_THRESHOLD halves the skill; 01 always succeeds,
        a fumble always fails."""
        _, skill = _skill_value(actor, stat)
        hard = dc >= HARD_DC_THRESHOLD
        threshold = skill // 2 if hard else skill
        roll = logged_result
        tier = " (Hard)" if hard else ""
        if roll == 1:
            return True, "rolled 01 — critical"
        if _is_fumble(roll, skill):
            return False, f"rolled {roll} — fumble"
        success = roll <= threshold
        op = "≤" if success else ">"
        return success, f"rolled {roll} {op} {threshold}{tier}"


# ---------------------------------------------------------------------------
# Registration — importing this module makes "coc_lite" a known ruleset id
# in all three registries.
# ---------------------------------------------------------------------------

seed._RULESETS["coc_lite"] = CoCLiteSchema()
ruleset._VALIDATORS["coc_lite"] = CoCLiteEconomy()
mechanics._PROVIDERS["coc_lite"] = CoCLiteMechanics()
