from __future__ import annotations

import math
import re as _re
from typing import Any

from backend.app.engine.dice import roll_d20, roll_dice
from backend.app.engine.types import (
    NEUTRALIZED_STATUSES,
    ActionEconomy,
    ActionInput,
    AttackResult,
    CharacterState,
    CheckResolution,
    GameState,
    InitiativeEntry,
)

_STAT_ATTRS: dict[str, str] = {
    "strength": "strength",
    "str": "strength",
    "dexterity": "dexterity",
    "dex": "dexterity",
    "constitution": "constitution",
    "con": "constitution",
    "intelligence": "intelligence",
    "int": "intelligence",
    "wisdom": "wisdom",
    "wis": "wisdom",
    "charisma": "charisma",
    "cha": "charisma",
}


def resolve_check(
    character: CharacterState,
    stat: str,
    dc: int,
    seed: int | None = None,
) -> CheckResolution:
    """Roll a D&D 5e ability check for *character* against *dc*; return structured outcome.

    Pure function — no side effects.
    *stat* accepts full names or 3-letter abbreviations (case-insensitive).
    Missing or unrecognised stat defaults to a score of 10 (modifier +0).
    """
    canonical = _STAT_ATTRS.get(stat.lower(), stat.lower())
    score = getattr(character, canonical, 10)
    stat_mod = _ability_modifier(int(score))
    d20 = roll_d20(seed=seed)
    total = d20 + stat_mod
    return CheckResolution(
        stat=canonical,
        stat_mod=stat_mod,
        dc=dc,
        d20=d20,
        total=total,
        success=total >= dc,
    )


def compute_initiative_order(
    characters: list[CharacterState], seed: int | None = None
) -> tuple[InitiativeEntry, ...]:
    """Roll initiative for all living characters and return entries sorted highest-first."""
    entries: list[InitiativeEntry] = []
    for i, char in enumerate(characters):
        if not char.is_alive:
            continue
        init_roll = roll_d20(seed=seed + i if seed is not None else None)
        total_initiative = init_roll + char.initiative_bonus
        entries.append(InitiativeEntry(character_id=char.id, initiative=total_initiative, order=i))
    entries.sort(key=lambda e: (-e.initiative, -e.order))
    return tuple(entries)


def _ability_modifier(score: int) -> int:
    return math.floor((score - 10) / 2)


def compute_attack_roll(
    attacker: CharacterState,
    target: CharacterState,
    action: ActionInput,
    seed: int | None = None,
) -> AttackResult:
    """Resolve a single attack roll against target, returning full AttackResult with damage."""
    natural = roll_d20(seed=seed)
    is_critical = natural == 20
    is_fumble = natural == 1

    if action.action_type == "attack_melee":
        ability_mod = _ability_modifier(attacker.strength)
        dmg_mod = ability_mod
    elif action.action_type == "attack_ranged":
        ability_mod = _ability_modifier(attacker.dexterity)
        dmg_mod = ability_mod
    else:
        ability_mod = _ability_modifier(attacker.strength)
        dmg_mod = ability_mod

    attack_roll = natural + ability_mod

    if is_fumble:
        is_hit = False
        damage = 0
        damage_rolls: tuple[int, ...] = ()
    elif is_critical:
        is_hit = True
        raw_damage = _roll_damage(action, attacker, is_critical=True, seed=seed)
        damage = raw_damage + dmg_mod if raw_damage else 0
        damage_rolls = (raw_damage,) if raw_damage else ()
    else:
        is_hit = attack_roll >= target.armor_class
        if is_hit:
            raw_damage = _roll_damage(action, attacker, is_critical=False, seed=seed)
            damage = raw_damage + dmg_mod if raw_damage else max(1, dmg_mod)
            damage_rolls = (raw_damage,) if raw_damage else ()
        else:
            damage = 0
            damage_rolls = ()

    return AttackResult(
        attacker_id=attacker.id,
        target_id=target.id,
        attack_roll=attack_roll,
        natural_roll=natural,
        is_critical=is_critical,
        is_hit=is_hit,
        damage=max(0, damage),
        damage_rolls=damage_rolls,
    )


# Default weapon damage die used when the action carries no explicit dice
# expression (the UI does not attach one to basic attacks). Without this, an
# attack — including a critical hit — would resolve to 0 damage.
_DEFAULT_WEAPON_DICE: dict[str, str] = {
    "attack_melee": "1d8",
    "attack_ranged": "1d6",
}
_FALLBACK_WEAPON_DIE = "1d6"


def _roll_damage(
    action: ActionInput,
    attacker: CharacterState,
    is_critical: bool = False,
    seed: int | None = None,
) -> int:
    expression = action.dice_expression or _DEFAULT_WEAPON_DICE.get(
        action.action_type, _FALLBACK_WEAPON_DIE
    )
    try:
        result = roll_dice(expression, seed=seed)
    except ValueError:
        return 0
    # D&D 5e critical hits double the dice rolled (the flat modifier is added once
    # by the caller), so a crit always deals more than the equivalent normal hit.
    return result.total * 2 if is_critical else result.total


def apply_damage(target: CharacterState, damage: int) -> CharacterState:
    """Apply damage to a character, flooring HP at 0 and adding 'unconscious' condition."""
    new_hp = max(0, target.hp_current - damage)
    conditions = list(target.conditions)
    already_neutralized = bool(NEUTRALIZED_STATUSES.intersection(conditions))
    if new_hp == 0 and not already_neutralized:
        conditions.append("unconscious")
    return CharacterState(
        id=target.id,
        name=target.name,
        hp_current=new_hp,
        hp_max=target.hp_max,
        strength=target.strength,
        dexterity=target.dexterity,
        constitution=target.constitution,
        intelligence=target.intelligence,
        wisdom=target.wisdom,
        charisma=target.charisma,
        armor_class=target.armor_class,
        initiative_bonus=target.initiative_bonus,
        speed=target.speed,
        conditions=tuple(conditions),
        action_economy=target.action_economy,
    )


_GENERIC_ENEMY_AC = 12
_GENERIC_ENEMY_HP = 10
_TARGET_RE = _re.compile(r'\[Target:\s*([^\]]+)\]', _re.IGNORECASE)


def _make_generic_enemy(target_id: str, name: str = "enemy") -> CharacterState:
    """Synthetic stand-in used when attacking an NPC not registered as a character."""
    return CharacterState(
        id=target_id,
        name=name,
        hp_current=_GENERIC_ENEMY_HP,
        hp_max=_GENERIC_ENEMY_HP,
        strength=10,
        dexterity=10,
        constitution=10,
        intelligence=10,
        wisdom=10,
        charisma=10,
        armor_class=_GENERIC_ENEMY_AC,
        initiative_bonus=0,
        speed=30,
        action_economy=ActionEconomy(),
    )


def _enemy_from_context(action: ActionInput) -> CharacterState | None:
    """Build a CharacterState from the frontend's enemy context (HP/AC from encounter tracker).

    Extracts the target name from ``[Target: <name>]`` prefix in the description,
    then finds the matching enemy in ``action.enemies`` by name (case-insensitive).
    Falls back to the first alive enemy if no name match is found.
    """
    if not action.enemies:
        return None

    # Extract target name from "[Target: <name>] ..." prefix
    target_name: str = ""
    m = _TARGET_RE.search(action.description or "")
    if m:
        target_name = m.group(1).strip()
    elif action.target_id:
        target_name = action.target_id.strip()

    def _safe_int(val: object, default: int) -> int:
        try:
            if val is None:
                return default
            if isinstance(val, int | float | str):
                return int(val)
            return default
        except (TypeError, ValueError):
            return default

    def _build(e: dict[str, Any]) -> CharacterState:
        name = str(e.get("name", "Enemy"))
        hp = _safe_int(e.get("hp"), _GENERIC_ENEMY_HP)
        max_hp = _safe_int(e.get("max_hp") or e.get("maxHp"), hp)
        ac = _safe_int(e.get("ac"), _GENERIC_ENEMY_AC)
        safe_id = f"npc_{name.lower().replace(' ', '_')}"
        return CharacterState(
            id=safe_id,
            name=name,
            hp_current=max(0, hp),
            hp_max=max(1, max_hp),
            strength=10, dexterity=10, constitution=10,
            intelligence=10, wisdom=10, charisma=10,
            armor_class=max(1, ac),
            initiative_bonus=0,
            speed=30,
            action_economy=ActionEconomy(),
        )

    alive = [e for e in action.enemies if isinstance(e, dict) and _safe_int(e.get("hp"), 1) > 0]
    if not alive:
        return None

    if target_name:
        tl = target_name.lower()
        for e in alive:
            ename = (e.get("name") or "").lower()
            if ename == tl or tl in ename or ename in tl:
                return _build(e)

    # No name match — use first alive enemy
    return _build(alive[0])


def process_attack(
    state: GameState,
    action: ActionInput,
    seed: int | None = None,
) -> tuple[GameState, AttackResult]:
    """Execute a melee/ranged attack, update the game state, and return both."""
    attacker = state.character_by_id(action.character_id)

    if attacker is None:
        raise ValueError(f"Attacker {action.character_id} not found in game state")
    if not attacker.is_conscious:
        raise ValueError(f"Attacker {attacker.name} is not conscious")

    # Use registered target if available; then try frontier enemy context (real HP/AC);
    # fall back to generic enemy only if neither is available.
    target = state.character_by_id(action.target_id) if action.target_id else None
    generic_target_id = action.target_id or f"enemy_{action.character_id}"
    if target is None:
        context_enemy = _enemy_from_context(action)
        target = context_enemy if context_enemy else _make_generic_enemy(generic_target_id)
    elif not target.is_alive:
        raise ValueError(f"Target {target.name} is already dead")

    attack = compute_attack_roll(attacker, target, action, seed=seed)

    if attack.is_hit and attack.damage > 0:
        new_target = apply_damage(target, attack.damage)
        new_characters = dict(state.characters)
        new_characters[target.id] = new_target
        new_state = GameState(
            session_id=state.session_id,
            campaign_id=state.campaign_id,
            turn_number=state.turn_number,
            current_character_id=state.current_character_id,
            initiative_order=state.initiative_order,
            characters=new_characters,
            scene_id=state.scene_id,
        )
    else:
        new_state = state

    return new_state, attack
