from __future__ import annotations

import json as _json
import re as _re
from typing import Any

from backend.app.services.ollama_client import generate

_NPC_SYSTEM_PROMPT = (
    "You are an NPC dialogue generator for D&D 5e. "
    "You will be given a list of NPC names, the DM narration, and the player's action. "
    "Write one short, in-character spoken line for each NPC — one punchy sentence that fits "
    "their personality and the situation.\n\n"
    "Return ONLY a JSON array of objects, each with keys 'npc_name' and 'dialogue'. "
    "Example: [{\"npc_name\": \"Gorrak\", \"dialogue\": \"You dare enter my domain, fool?\"}]\n\n"
    "STRICT RULES:\n"
    "- Only write dialogue for NPCs in the provided list — never invent new characters.\n"
    "- If a name looks like a spell, ability, or object (e.g. Fireball, Detect), skip it.\n"
    "- Never use placeholder text like '[NPC name]' or '[insert dialogue]'.\n"
    "- If no valid NPCs exist, return an empty array: []\n"
    "- Return only the JSON array — no explanation, no prose, nothing else.\n\n"
    "NPC PERSONA RULES — make dialogue feel real:\n"
    "- Hostile NPCs (combat context): threatening, aggressive, cold — they want the player dead.\n"
    "- Merchant/friendly NPCs: warm but self-interested — they want something in return.\n"
    "- Guard/authority NPCs: terse, commanding, suspicious — they enforce rules.\n"
    "- Unknown/mysterious NPCs: cryptic, indirect — they reveal nothing easily.\n"
    "- Match the tone to the action: if the player attacked, the NPC is reactive and angry. "
    "If the player talked, the NPC responds to what was said. "
    "If the player is sneaking, the NPC may be unaware or suspicious.\n"
    "- Never repeat what the DM just narrated — add new information or reaction."
)

_STOP_WORDS: frozenset[str] = frozenset(
    {
        "The", "A", "An", "And", "But", "Or", "In", "On", "At", "To", "For",
        "Of", "With", "By", "From", "Up", "As", "Is", "It", "Its", "Be",
        "Are", "Was", "Were", "Has", "Have", "Had", "Do", "Does", "Did",
        "Will", "Would", "Could", "Should", "May", "Might", "Must", "Shall",
        "You", "Your", "My", "Me", "We", "Us", "He", "She", "They", "Them",
        "His", "Her", "Their", "This", "That", "These", "Those", "Not", "No",
        "If", "So", "Then", "There", "Here", "When", "Where", "Who", "What",
        "How", "Why", "Which", "DM", "I", "Turn",
        # Sentence-starters / prose connectors
        "Suddenly", "Meanwhile", "However", "Although", "Despite", "Within",
        "Before", "After", "Around", "Beyond", "Through", "Across", "Against",
        "Inside", "Outside", "Above", "Below", "Player", "Action", "Narration",
        # Atmospheric / narrative words that appear capitalised but aren't NPCs
        "Time", "Shadows", "Shadow", "Dust", "Stone", "Stones", "Silence",
        "Darkness", "Light", "Fire", "Water", "Fortune", "Fate", "Chaos",
        "Order", "Death", "Life", "Blood", "Iron", "Gold", "Silver",
        "Air", "Earth", "Wind", "Storm", "Night", "Day", "Dawn", "Dusk",
        "Moment", "Heartbeat", "Void", "Mist", "Fog", "Flame", "Smoke",
        "Every", "Each", "Even", "Just", "Still", "Already", "Perhaps",
        "Something", "Someone", "Somewhere", "Nothing", "Nobody", "Nowhere",
        "Always", "Never", "Often", "Once", "Twice", "First", "Last",
        # Sentence-starters present in static narration templates
        "Whatever", "Every", "Only",
    }
)

# D&D spell, ability, and action words that can appear capitalised in narration
# but are never NPC names.
_DND_KEYWORDS: frozenset[str] = frozenset(
    {
        "Fireball", "Lightning", "Thunderwave", "Detect", "Magic", "Invisibility",
        "Teleport", "Healing", "Word", "Shield", "Prestidigitation", "Eldritch",
        "Blast", "Cantrip", "Concentration", "Initiative", "Advantage",
        "Disadvantage", "Saving", "Throw", "Attack", "Damage", "Critical",
        "Insight", "Perception", "Stealth", "Athletics", "Persuasion",
        "Deception", "Arcana", "Nature", "Religion", "History",
        "Investigation", "Survival", "Medicine", "Acrobatics", "Intimidation",
        "Performance", "Sleight", "Hand", "Tools", "Proficiency", "Bonus",
        "Action", "Reaction", "Bonus", "Movement", "Spell", "Slot", "Rest",
        "Short", "Long", "Hit", "Points", "Armor", "Class", "Strength",
        "Dexterity", "Constitution", "Intelligence", "Wisdom", "Charisma",
    }
)


def _extract_npc_names(narration_only: str) -> list[str]:
    """Extract candidate NPC names from DM narration text only.

    Filters stop-words and D&D mechanical keywords so spell/ability names
    are never mistaken for NPC names.
    """
    words = narration_only.split()
    names: list[str] = []
    seen: set[str] = set()
    for word in words:
        clean = word.strip(".,!?;:\"'()[]{}-")
        if (
            clean
            and len(clean) > 2
            and clean[0].isupper()
            and clean not in _STOP_WORDS
            and clean not in _DND_KEYWORDS
            and clean not in seen
        ):
            names.append(clean)
            seen.add(clean)
    return names[:6]


_ACTION_TYPE_LABELS: dict[str, str] = {
    "attack_melee": "MELEE ATTACK — the player is physically attacking",
    "attack_ranged": "RANGED ATTACK — the player is attacking from a distance",
    "spell": "SPELLCASTING — the player cast a spell",
    "cast_spell": "SPELLCASTING — the player cast a spell",
    "talk": "SOCIAL — the player is speaking or negotiating",
    "move": "MOVEMENT — the player is repositioning",
    "movement": "MOVEMENT — the player is repositioning",
    "use_item": "ITEM USE — the player used an item",
    "skill_check": "SKILL CHECK — the player attempted a skill",
    "puzzle_answer": "PUZZLE — the player answered a riddle or puzzle",
    "rest": "REST — the player is recovering",
    "roleplay": "ROLEPLAY — the player is interacting with the world",
}


def _build_enemy_context_block(npc_names: list[str], enemies: tuple[dict[str, Any], ...]) -> str:
    """Build a character context block for matched enemies.

    Only includes enemies whose names fuzzy-match an extracted NPC name.
    """
    if not enemies:
        return ""
    lines: list[str] = ["[Character context — NPC personalities in this scene]"]
    matched = False
    for enemy in enemies:
        name = enemy.get("name", "")
        if not name:
            continue
        name_lower = name.lower()
        if not any(name_lower in n.lower() or n.lower() in name_lower for n in npc_names):
            continue
        matched = True
        lines.append(f"  {name}:")
        if enemy.get("persona"):
            lines.append(f"    Persona: {enemy['persona']}")
        if enemy.get("disposition"):
            lines.append(f"    Disposition: {enemy['disposition']}")
        goals = enemy.get("goals")
        if goals and isinstance(goals, list) and any(goals):
            lines.append(f"    Goals: {'; '.join(str(g) for g in goals if g)}")
        if enemy.get("secret"):
            lines.append(
                f"    Private knowledge (do NOT volunteer; reveal only under pressure): "
                f"{enemy['secret']}"
            )
        if enemy.get("negotiation_levers"):
            lines.append(f"    What would move them: {enemy['negotiation_levers']}")
    return "\n".join(lines) if matched else ""


def _build_recent_talks_block(recent_talks: list[dict[str, str]]) -> str:
    """Format recent NPC dialogue lines as a context block for the prompt.

    Gives NPCs conversational memory so they can reference or contradict earlier statements.
    """
    if not recent_talks:
        return ""
    lines = ["[Recent NPC dialogue — NPCs may reference or react to these]"]
    for talk in recent_talks:
        name = talk.get("npc_name", "NPC")
        dialogue = talk.get("dialogue", "")
        if name and dialogue:
            lines.append(f'  {name}: "{dialogue}"')
    return "\n".join(lines) if len(lines) > 1 else ""


_COMBAT_TYPES = frozenset({"attack_melee", "attack_ranged", "cast_spell", "cast", "spell"})
_TALK_TYPES = frozenset({"talk", "speak", "roleplay"})


def get_npc_responses(
    campaign_id: str,
    dm_narration: str,
    action_text: str,
    action_type: str = "",
    enemies: tuple[dict[str, Any], ...] = (),
    recent_talks: list[dict[str, str]] | None = None,
) -> list[dict[str, str]]:
    """Generate short NPC dialogue lines for each named NPC detected in the DM narration."""
    # Only scan narration — never extract names from player-supplied action text
    npc_names = _extract_npc_names(dm_narration)

    # For combat/talk actions, supplement with alive enemy names from the enemies list
    # (LLMs often write enemy names in lowercase, missing the name extractor)
    if action_type in _COMBAT_TYPES or action_type in _TALK_TYPES:
        seen_lower = {n.lower() for n in npc_names}
        for e in enemies:
            if not isinstance(e, dict):
                continue
            name = (e.get("name") or "").strip()
            hp = e.get("hp")
            try:
                if hp is not None and int(hp) <= 0:
                    continue
            except (TypeError, ValueError):
                pass
            if name and name.lower() not in seen_lower:
                npc_names.append(name)
                seen_lower.add(name.lower())

    if not npc_names:
        return []

    action_label = _ACTION_TYPE_LABELS.get(action_type, "GENERAL ACTION")
    enemy_block = _build_enemy_context_block(npc_names, enemies)
    talks_block = _build_recent_talks_block(recent_talks or [])
    prompt = (
        f"DM Narration:\n{dm_narration}\n\n"
        f"Player Action ({action_label}):\n{action_text}\n\n"
        + (f"{enemy_block}\n\n" if enemy_block else "")
        + (f"{talks_block}\n\n" if talks_block else "")
        + f"NPCs present: {', '.join(npc_names[:3])}\n"
        f"Generate in-character dialogue for each NPC mentioned."
    )

    result = generate(
        prompt=prompt,
        system_prompt=_NPC_SYSTEM_PROMPT,
        action_text=action_text,
    )

    responses = _try_parse_json(result)
    if responses is None:
        responses = _keyword_fallback(dm_narration, action_text, npc_names)

    return responses[:3]


def _try_parse_json(text: str) -> list[dict[str, str]] | None:
    json_match = _re.search(r"\[.*?\]", text, _re.DOTALL)
    if json_match:
        try:
            data = _json.loads(json_match.group())
            if isinstance(data, list):
                return [
                    item for item in data
                    if isinstance(item, dict) and item.get("dialogue", "").strip()
                ]
        except (_json.JSONDecodeError, TypeError):
            pass
    return None


_FALLBACK_COMBAT = [
    "You'll regret setting foot here, fool.",
    "You cannot win — lay down your arms.",
    "I've faced worse than you and walked away.",
    "Your courage is admirable. Your survival, less certain.",
    "Don't make this harder than it needs to be.",
]

_FALLBACK_PARLEY = [
    "Choose your next words carefully.",
    "I'm listening — but my patience has limits.",
    "What is it you want from me?",
    "Speak plainly. I have no time for riddles.",
    "You've come a long way. That counts for something.",
]

_FALLBACK_NEUTRAL = [
    "Hmm. Interesting.",
    "We'll see how this plays out.",
    "Things rarely go as planned around here.",
    "I've seen your kind before. I'm still standing.",
    "Tread carefully — this place has a long memory.",
]


def _keyword_fallback(
    dm_narration: str,
    action_text: str,
    npc_names: list[str],
) -> list[dict[str, str]]:
    """Return varied context-aware fallback lines when the LLM fails to produce JSON."""
    combined = (dm_narration + " " + action_text).lower()
    combat_words = {"attack", "strike", "sword", "stab", "cast", "shoot", "fight", "battle"}
    is_combat = any(w in combined for w in combat_words)
    parley_words = {"talk", "speak", "ask", "persuade", "negotiate", "beg", "plead", "convince"}
    is_parley = any(w in combined for w in parley_words)

    pool = _FALLBACK_COMBAT if is_combat else _FALLBACK_PARLEY if is_parley else _FALLBACK_NEUTRAL

    responses: list[dict[str, str]] = []
    for i, name in enumerate(npc_names[:3]):
        responses.append({"npc_name": name, "dialogue": pool[i % len(pool)]})
    return responses
