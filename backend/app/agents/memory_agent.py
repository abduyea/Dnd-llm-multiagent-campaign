from __future__ import annotations

import asyncio
import json as _json
import re
import uuid as _uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.models import Memory
from backend.app.services.ollama_client import generate

_MEMORY_SYSTEM_PROMPT = (
    "You are a memory extraction agent for a D&D campaign. "
    "Given a player action and the DM's narration, extract 0 to 3 "
    "important story facts that future turns should remember.\n\n"
    "Return a JSON array of objects with keys 'fact_text', 'fact_type', 'importance'.\n"
    "fact_type must be one of: event, npc, location, lore, character, item.\n"
    "importance is an integer 1-10.\n\n"
    "IMPORTANCE GUIDE:\n"
    "  10 — A character died, a major quest item was found, a boss was defeated\n"
    "   8 — An NPC revealed critical information, a secret door was found, an alliance was made\n"
    "   6 — An enemy was defeated, a new location was entered, an item was acquired\n"
    "   4 — An NPC was spoken to, a clue was found, a skill check succeeded or failed\n"
    "   2 — Flavour detail worth keeping but not urgent\n\n"
    "FACT TEXT RULES:\n"
    "- Write the fact in past tense, third person: "
    "'The party discovered...', 'Aldric defeated...'\n"
    "- Be specific — include names, places, and outcomes. Not 'an NPC was met' but "
    "'The party met Gorrak the goblin chieftain in the throne room.'\n"
    "- If nothing important happened, return an empty array: []\n"
    "- Return only the JSON array — no explanation, no prose."
)


def _keyword_extract(
    action_text: str,
    narration: str,
) -> list[dict[str, Any]]:
    facts: list[dict[str, Any]] = []
    text = (action_text + " " + narration).lower()

    npc_triggers = [" says ", " speaks ", " introduces ", " meets "]
    location_triggers = [" enter ", " arrive at ", " discover "]
    location_words = ["cave", "dungeon", "temple", "castle", "forest", "room", "hall"]
    item_triggers = [
        " pick up ",
        " picks up ",
        " pick ",
        " acquires ",
        " acquire ",
        " loots ",
        " loot ",
    ]

    for kw in npc_triggers:
        if kw in text:
            facts.append(
                {"fact_text": "An NPC was encountered.", "fact_type": "npc", "importance": 5}
            )
            break

    for kw in location_triggers:
        if kw in text:
            facts.append(
                {
                    "fact_text": "A new location was discovered.",
                    "fact_type": "location",
                    "importance": 6,
                }
            )
            break
    if not any(f["fact_type"] == "location" for f in facts):
        for word in location_words:
            if f" {word} " in text:
                facts.append(
                    {
                        "fact_text": "A new location was discovered.",
                        "fact_type": "location",
                        "importance": 6,
                    }
                )
                break

    for kw in item_triggers:
        if kw in text:
            facts.append(
                {"fact_text": "An item was acquired.", "fact_type": "item", "importance": 4}
            )
            break

    return facts[:2]


async def extract_and_store(
    session_id: str,
    campaign_id: str,
    action_text: str,
    narration: str,
    agent_id: str = "memory_agent",
    db: AsyncSession | None = None,
) -> None:
    """Extract key facts from the turn narration and store them in the Memory table."""
    prompt = (
        f"Player Action:\n{action_text}\n\n"
        f"DM Narration:\n{narration}\n\n"
        f"Extract important story facts from this turn."
    )

    # Offload the blocking LLM call to a worker thread so the event loop stays
    # responsive while memory is extracted after the turn result is shown.
    result = await asyncio.to_thread(
        generate,
        prompt=prompt,
        system_prompt=_MEMORY_SYSTEM_PROMPT,
        action_text=action_text,
        format_json=True,
    )

    facts = _try_parse_json(result)
    if facts is None:
        facts = _keyword_extract(action_text, narration)

    if not facts:
        return

    if db is None:
        return

    for fact in facts[:3]:
        memory = Memory(
            id=str(_uuid.uuid4()),
            session_id=session_id,
            campaign_id=campaign_id,
            fact_text=fact.get("fact_text", ""),
            fact_type=fact.get("fact_type", "event"),
            importance=fact.get("importance", 1),
            extracted_by=agent_id,
        )
        db.add(memory)


def _try_parse_json(text: str) -> list[dict[str, Any]] | None:
    json_match = re.search(r"\[.*?\]", text, re.DOTALL)
    if json_match:
        try:
            data = _json.loads(json_match.group())
            if isinstance(data, list):
                return [
                    item for item in data
                    if isinstance(item, dict) and item.get("fact_text", "").strip()
                ]
        except (_json.JSONDecodeError, TypeError):
            pass
    return None
