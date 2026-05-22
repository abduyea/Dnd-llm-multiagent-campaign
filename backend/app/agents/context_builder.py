from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.models import Character, Memory, Summary, Turn
from backend.app.db.models.campaign import Campaign

_HISTORY_COMPRESSION_THRESHOLD = 20
_COMPRESSED_HISTORY_LIMIT = 2

_ACTION_TYPE_CONTEXT: dict[str, str] = {
    "attack_melee": (
        "ACTION CONTEXT — MELEE COMBAT: The player is making a physical melee attack. "
        "Narrate the strike — steel, muscle, impact, and the enemy's reaction. "
        "Tone: urgent and visceral."
    ),
    "attack_ranged": (
        "ACTION CONTEXT — RANGED COMBAT: The player is attacking from a distance. "
        "Narrate the projectile's flight, the tension of release, "
        "and the moment of impact or near-miss."
    ),
    "spell": (
        "ACTION CONTEXT — SPELLCASTING: The player is casting a spell. "
        "Narrate the arcane energy, the visual spectacle, and the magical effect. "
        "Tone: dramatic and otherworldly."
    ),
    "skill_check": (
        "ACTION CONTEXT — SKILL CHECK: The player is attempting a skill or ability check. "
        "Narrate success or failure based on the dice result — "
        "describe what the character achieves or fails to do."
    ),
    "move": (
        "ACTION CONTEXT — MOVEMENT: The player is moving through the environment. "
        "Narrate their passage — terrain, atmosphere, and what they notice as they go."
    ),
    "dodge": (
        "ACTION CONTEXT — DEFENSIVE: The player is dodging or taking a defensive stance. "
        "Narrate the evasion — the narrowly avoided blow, the instinct kicking in, "
        "the relief of surviving."
    ),
    "hide": (
        "ACTION CONTEXT — STEALTH: The player is hiding or attempting to move unseen. "
        "Narrate the concealment — the held breath, the shadows embracing them, "
        "the tension of staying undetected."
    ),
    "help": (
        "ACTION CONTEXT — SUPPORT: The player is helping or assisting an ally. "
        "Narrate the moment of aid — the reassurance, the tactical assist, "
        "the bond between companions."
    ),
    "ready": (
        "ACTION CONTEXT — READYING: The player is preparing for something — holding their action. "
        "Narrate the tension of waiting — muscles coiled, eyes scanning, "
        "the electric stillness before the moment."
    ),
    "use_item": (
        "ACTION CONTEXT — ITEM USE: The player is using an item or object. "
        "Narrate the item's effect and the sensory experience of activating it."
    ),
    "rest": (
        "ACTION CONTEXT — REST: The player is resting or recovering. "
        "Narrate the brief respite — exhaustion, sounds of the environment, "
        "the quiet before what comes next."
    ),
    "roleplay": (
        "ACTION CONTEXT — ROLEPLAY: The player is performing a non-combat, non-movement action — "
        "examining, interacting, or expressing their character. "
        "Narrate their observations and the world's response."
    ),
    "talk": (
        "ACTION CONTEXT — SOCIAL INTERACTION: The player is speaking with an NPC or enemy. "
        "Narrate the conversation's tone, the listener's body language, and the NPC's immediate "
        "reaction. Reflect the NPC's personality — hostile NPCs may not cooperate, "
        "friendly NPCs may reveal information. Tone: character-driven and tense."
    ),
    "puzzle_answer": (
        "ACTION CONTEXT — PUZZLE / RIDDLE: The player is attempting to answer a puzzle or riddle. "
        "Their response is in the action text. Narrate whether the answer seems correct based on "
        "the story — if correct, describe the reward or consequence with drama and satisfaction. "
        "If incorrect, describe the world's reaction: silence, a groan of stone, a mocking echo. "
        "Tone: mysterious, satisfying on success, eerie on failure."
    ),
}

# Aliases: map frontend/engine variants to canonical context keys above
_ACTION_TYPE_ALIASES: dict[str, str] = {
    "cast_spell": "spell",
    "cast": "spell",
    "movement": "move",
    "dash": "move",
    "disengage": "move",
    "interact": "roleplay",
    "delay": "roleplay",
    "speak": "talk",
}

_DEFAULT_ACTION_CONTEXT = (
    "ACTION CONTEXT — EXPLORATION: The player is exploring, observing, or "
    "taking a general action. "
    "Narrate what they discover or what shifts in the world around them."
)

_DM_SYSTEM_PROMPT = (
    "You are the Dungeon Master. The game engine has already resolved all mechanics. "
    "Your only job is to narrate the outcome in 2-3 cinematic sentences.\n\n"
    "STRICT RULES — never break these:\n"
    "- Write in second-person present tense: 'You feel...', 'The goblin snarls...'\n"
    "- NEVER invent a number, hit, miss, or outcome not stated in the engine results below.\n"
    "- NEVER use the words 'critical', 'crit', 'advantage', 'disadvantage', 'saving throw', "
    "'fumble' unless the engine result explicitly states them.\n"
    "- NEVER speak dialogue for any NPC — the NPC agent handles that separately.\n"
    "- NEVER use placeholder text like '[character name]' or '[describe X]'.\n"
    "- NEVER describe what any character other than the player does as their own turn action — "
    "other characters may react, but they do not initiate during the player's beat.\n"
    "- If the action produced no result (missed, failed, or had no mechanical effect), "
    "narrate the dramatic absence — a failed attempt is still a vivid story beat.\n"
    "- If the action missed or failed, describe the dramatic consequence "
    "— not a mechanical reason.\n"
    "- Use specific sensory details: what the player sees, hears, smells, and feels.\n"
    "- Keep it tight — 2-3 punchy sentences. No filler, no repetition."
)


async def build_dm_context(
    session_id: str,
    campaign_id: str,
    character_id: str,
    action_text: str,
    dice_result: dict[str, Any] | None = None,
    db: AsyncSession | None = None,
    action_type: str = "",
    enemies: tuple[dict[str, Any], ...] = (),
    location: str | None = None,
) -> list[dict[str, str]]:
    """Assemble the message list (system + user) passed to the DM narration model."""
    messages: list[dict[str, str]] = [{"role": "system", "content": _DM_SYSTEM_PROMPT}]

    if db is not None:
        campaign_layer = await _build_campaign_layer(campaign_id, db)
        if campaign_layer:
            messages.append({"role": "system", "content": campaign_layer})

        char_layer = await _build_character_layer(character_id, db)
        if char_layer:
            messages.append({"role": "system", "content": char_layer})

        party_layer = await _build_party_layer(campaign_id, character_id, db)
        if party_layer:
            messages.append({"role": "system", "content": party_layer})

        memory_layer = await _build_memory_layer(session_id, db)
        if memory_layer:
            messages.append({"role": "system", "content": memory_layer})

        history_layer = await _build_history_layer(session_id, db)
        for msg in history_layer:
            messages.append(msg)

    if location and location.strip() and location not in ("Set Location", "Unknown Location"):
        messages.append({"role": "system", "content": f"CURRENT LOCATION: {location.strip()}"})

    if enemies:
        enemy_layer = _build_enemy_layer(enemies)
        if enemy_layer:
            messages.append({"role": "system", "content": enemy_layer})

    canonical_type = _ACTION_TYPE_ALIASES.get(action_type, action_type)
    action_context = _ACTION_TYPE_CONTEXT.get(canonical_type, _DEFAULT_ACTION_CONTEXT)
    messages.append({"role": "system", "content": action_context})

    if dice_result:
        dice_layer = _build_dice_layer(dice_result)
        if dice_layer:
            messages.append({"role": "system", "content": dice_layer})

    messages.append({"role": "user", "content": action_text})

    return messages


async def _build_campaign_layer(campaign_id: str, db: AsyncSession) -> str:
    """Inject campaign world-setting so the DM narrates in the right tone and genre."""
    result = await db.execute(select(Campaign).where(Campaign.id == campaign_id))
    campaign = result.scalar_one_or_none()
    if campaign is None:
        return ""
    parts = []
    if campaign.name:
        parts.append(f"Campaign: {campaign.name}.")
    if campaign.world_setting:
        parts.append(f"World setting: {campaign.world_setting}")
    if campaign.description:
        parts.append(f"Campaign description: {campaign.description}")
    return " ".join(parts) if parts else ""


def _ability_mod(score: int) -> str:
    """Return D&D 5e ability modifier string for a given ability score."""
    mod = (score - 10) // 2
    return f"+{mod}" if mod >= 0 else str(mod)


def _proficiency_bonus(level: int) -> int:
    """Return D&D 5e proficiency bonus for a given character level."""
    return max(2, (level - 1) // 4 + 2)


def _hp_status_short(hp_current: int, hp_max: int) -> str:
    """Return a short HP status label for party member display."""
    if hp_max <= 0:
        return "Healthy"
    pct = hp_current / hp_max * 100
    if pct <= 0:
        return "Dying"
    if pct <= 25:
        return "Critical"
    if pct <= 50:
        return "Bloodied"
    if pct <= 75:
        return "Hurt"
    return "Healthy"


async def _build_character_layer(character_id: str, db: AsyncSession) -> str:
    result = await db.execute(select(Character).where(Character.id == character_id))
    char = result.scalar_one_or_none()
    if char is None:
        return ""
    level = _safe_int(char.level, 1)
    hp_current = _safe_int(char.hp_current, 0)
    hp_max = _safe_int(char.hp_max, 0)
    strength = _safe_int(char.strength, 10)
    dexterity = _safe_int(char.dexterity, 10)
    constitution = _safe_int(char.constitution, 10)
    intelligence = _safe_int(char.intelligence, 10)
    wisdom = _safe_int(char.wisdom, 10)
    charisma = _safe_int(char.charisma, 10)

    hp_pct = (hp_current / hp_max * 100) if hp_max else 100
    if hp_pct <= 0:
        hp_status = "DYING — at death's door, every action may be their last"
    elif hp_pct <= 25:
        hp_status = "CRITICAL — badly wounded, desperate, struggling to stay upright"
    elif hp_pct <= 50:
        hp_status = "BLOODIED — clearly wounded, fighting through pain"
    elif hp_pct <= 75:
        hp_status = "HURT — some wounds, but still fighting strong"
    else:
        hp_status = "HEALTHY — fresh and at full fighting capacity"
    prof = _proficiency_bonus(level)
    parts = [
        f"Player Character: {char.character_name} "
        f"(Level {level} {char.race} {char.class_name}, "
        f"Proficiency Bonus +{prof}). "
        f"HP: {hp_current}/{hp_max} [{hp_status}]. "
        f"AC: {char.armor_class}. "
        f"Stats: STR {strength}({_ability_mod(strength)}), "
        f"DEX {dexterity}({_ability_mod(dexterity)}), "
        f"CON {constitution}({_ability_mod(constitution)}), "
        f"INT {intelligence}({_ability_mod(intelligence)}), "
        f"WIS {wisdom}({_ability_mod(wisdom)}), "
        f"CHA {charisma}({_ability_mod(charisma)}).",
    ]
    if char.backstory:
        parts.append(f"Character backstory: {char.backstory}")
    return " ".join(parts)


async def _build_party_layer(campaign_id: str, exclude_id: str, db: AsyncSession) -> str:
    result = await db.execute(
        select(Character).where(
            Character.campaign_id == campaign_id,
            Character.id != exclude_id,
        )
    )
    party = result.scalars().all()
    if not party:
        return ""
    names = [
        f"{c.character_name} "
        f"(HP {_safe_int(c.hp_current, 0)}/{_safe_int(c.hp_max, 0)} - "
        f"{_hp_status_short(_safe_int(c.hp_current, 0), _safe_int(c.hp_max, 0))})"
        for c in party
    ]
    return f"Party members: {', '.join(names)}."


async def _build_memory_layer(session_id: str, db: AsyncSession) -> str:
    top_result = await db.execute(
        select(Memory)
        .where(Memory.session_id == session_id)
        .order_by(Memory.importance.desc(), Memory.created_at.desc())
        .limit(3)
    )
    top_memories = list(top_result.scalars().all())

    recent_result = await db.execute(
        select(Memory)
        .where(Memory.session_id == session_id)
        .order_by(Memory.created_at.desc())
        .limit(3)
    )
    recent_memories = list(recent_result.scalars().all())

    # Deduplicate: combine both lists preserving importance-ordered ones first
    seen_ids: set[str] = set()
    memories: list[Memory] = []
    for m in top_memories + recent_memories:
        memory_id = str(m.id)
        if memory_id not in seen_ids:
            seen_ids.add(memory_id)
            memories.append(m)

    if not memories:
        return ""
    high = [m for m in memories if m.importance >= 7]
    rest = [m for m in memories if m.importance < 7]
    lines = ["[Story so far — key facts the DM must remember]"]
    for m in high:
        lines.append(f"  ★ {m.fact_text}")
    for m in rest:
        lines.append(f"  - {m.fact_text}")
    return "\n".join(lines)


async def _build_history_layer(
    session_id: str, db: AsyncSession, limit: int = 3
) -> list[dict[str, str]]:
    """Return recent turn history as message pairs.

    For long sessions (>20 turns) with a saved summary: inject the session
    chronicle as a system message and cap raw history to the last 4 turns.
    Keeps context window coherent without losing narrative continuity.
    """
    count_result = await db.execute(
        select(Turn).where(Turn.session_id == session_id)
    )
    all_turns = count_result.scalars().all()
    total_turns = len(all_turns)

    messages: list[dict[str, str]] = []

    # For long sessions, try to load summary and compress history
    if total_turns > _HISTORY_COMPRESSION_THRESHOLD:
        summary_result = await db.execute(
            select(Summary)
            .where(Summary.session_id == session_id)
            .order_by(Summary.created_at.desc())
            .limit(1)
        )
        summary = summary_result.scalar_one_or_none()
        if summary and summary.summary_text:
            chronicle = (
                f"[Session chronicle — events before the last "
                f"{_COMPRESSED_HISTORY_LIMIT} turns]\n{summary.summary_text}"
            )
            messages.append({"role": "system", "content": chronicle})
            limit = _COMPRESSED_HISTORY_LIMIT

    result = await db.execute(
        select(Turn)
        .where(Turn.session_id == session_id)
        .order_by(Turn.created_at.desc())
        .limit(limit)
    )
    turns = list(result.scalars().all())
    turns.reverse()
    for i, turn in enumerate(turns, start=1):
        action = str(turn.action_text or "")
        messages.append({"role": "user", "content": f"[Turn {i}] Player: {action}"})
        if turn.narration:
            messages.append({"role": "assistant", "content": f"DM: {turn.narration}"})
    return messages


def _safe_int(val: object, default: int = 1) -> int:
    try:
        if val is None:
            return default
        if isinstance(val, int | float | str):
            return int(val)
        return default
    except (TypeError, ValueError):
        return default


def _build_enemy_layer(enemies: tuple[dict[str, Any], ...]) -> str:
    """Build a combat encounter context block for DM narration.

    Uses HP/AC from the frontend tracker when provided, plus persona/disposition
    from the encounter metadata.
    """
    if not enemies:
        return ""
    alive = [e for e in enemies if isinstance(e, dict) and _safe_int(e.get("hp"), 1) > 0]
    if not alive:
        dead_names = [e["name"] for e in enemies if isinstance(e, dict) and e.get("name")]
        if dead_names:
            return f"ENCOUNTER: All enemies defeated — {', '.join(dead_names)} lie dead."
        return ""

    lines: list[str] = ["ENCOUNTER — Active enemies:"]
    for e in alive[:6]:
        name = e.get("name", "Unknown")
        hp = e.get("hp")
        max_hp = e.get("max_hp") or e.get("maxHp")
        ac = e.get("ac")

        condition = ""
        if hp is not None and max_hp:
            pct = _safe_int(hp) / max(_safe_int(max_hp), 1) * 100
            if pct <= 0:
                continue
            elif pct <= 25:
                condition = "near death"
            elif pct <= 50:
                condition = "badly wounded"
            elif pct <= 75:
                condition = "wounded"
            else:
                condition = "uninjured"

        parts = [f"  - {name}"]
        stat_parts = []
        if condition:
            stat_parts.append(condition)
        if ac is not None:
            stat_parts.append(f"AC {ac}")
        if hp is not None and max_hp:
            stat_parts.append(f"HP {hp}/{max_hp}")
        if stat_parts:
            parts.append(f"({', '.join(stat_parts)})")

        conds = e.get("conditions")
        if conds and isinstance(conds, list):
            cond_str = ", ".join(str(c) for c in conds if c)
            if cond_str:
                parts.append(f"[CONDITIONS: {cond_str}]")

        disposition = e.get("disposition", "")
        if disposition:
            parts.append(f"— {disposition}")

        persona = e.get("persona", "")
        if persona:
            parts.append(f"| {persona}")

        goals = e.get("goals")
        if goals and isinstance(goals, list):
            goal_str = "; ".join(str(g) for g in goals if g)
            if goal_str:
                parts.append(f"[Wants: {goal_str}]")

        lines.append(" ".join(parts))

    if len(lines) == 1:
        return ""

    in_combat = any(
        e.get("disposition", "").lower() in ("hostile", "aggressive", "combat")
        or _safe_int(e.get("hp"), 1) < _safe_int(e.get("max_hp") or e.get("maxHp"), 1)
        for e in alive
    )
    if in_combat:
        lines.append("COMBAT IS ACTIVE — narrate with urgency and tactical tension.")

    return "\n".join(lines)


def _build_dice_layer(dice_result: dict[str, Any]) -> str:
    """Format dice/attack outcomes so the DM narrates the right result."""
    if "dc" in dice_result and "total" in dice_result and "is_hit" not in dice_result:
        total = int(dice_result["total"])
        dc = int(dice_result["dc"])
        passed = total >= dc
        outcome = "PASS" if passed else "FAIL"
        flavor = (
            "The check succeeds — narrate confident, successful execution of the action."
            if passed
            else "The check fails — narrate a dramatic, consequence-laden failure or complication."
        )
        return (
            f"ENGINE RESULT — SKILL CHECK {outcome}: "
            f"Rolled {total} against DC {dc}. {flavor}"
        )
    if "is_hit" in dice_result:
        if dice_result.get("is_critical"):
            dmg = dice_result.get("damage", "?")
            return (
                f"ENGINE RESULT — CRITICAL HIT: The attack roll was a natural 20. "
                f"The blow lands with devastating force, dealing {dmg} damage. "
                f"Narrate this as a spectacular, dramatic strike "
                f"— something the enemy will not forget."
            )
        if dice_result["is_hit"]:
            dmg = dice_result.get("damage", "?")
            return (
                f"ENGINE RESULT — HIT: The attack connects, dealing {dmg} damage. "
                f"Narrate the impact — describe what the strike looks and feels like, "
                f"and how the enemy reacts to taking the blow."
            )
        total = dice_result.get("total", "?")
        return (
            f"ENGINE RESULT — MISS: The attack roll of {total} fails to connect. "
            f"Narrate the near-miss dramatically — the blade glances off armor, "
            f"the arrow whistles past, the enemy sidesteps at the last moment."
        )
    parts = []
    if "expression" in dice_result:
        parts.append(f"Rolled {dice_result['expression']}")
    if "total" in dice_result:
        parts.append(f"— result: {dice_result['total']}")
    if "rolls" in dice_result:
        parts.append(f"(individual dice: {', '.join(str(r) for r in dice_result['rolls'])})")
    if parts:
        return (
            f"ENGINE RESULT — DICE: {' '.join(parts)}. "
            f"Narrate success or failure based on this result. "
            f"A high roll means confident, dramatic success. "
            f"A low roll means failure or complication."
        )
    return ""
