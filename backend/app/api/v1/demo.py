"""Demo campaign seed endpoint.

POST /campaigns/demo — creates a pre-built starter campaign with two characters
so new users can jump straight into the game without any setup.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.base import get_db
from backend.app.db.models.campaign import Campaign
from backend.app.db.models.character import Character

router = APIRouter(prefix="/campaigns", tags=["demo"])

_DEMO_CAMPAIGN = {
    "name": "The Sunken Vault",
    "description": (
        "A crumbling keep half-swallowed by floodwater conceals a sealed vault "
        "said to hold the Heartstone — a gem that can unmake a lich. "
        "The party has three days before the tide rises for good."
    ),
    "world_setting": (
        "Dark fantasy: flooded ruins, cursed undead, desperate time pressure. "
        "Tone: tense survival horror with moments of grim heroism."
    ),
}

# M11 stage 1: aligned to the authored PCs in demo_dungeon_m95.json so the DB
# roster and the engine entities are identical (clean HP-sync + matching
# narration vs UI names). Names/scores/hp/ac mirror ent_pc_brakka /
# ent_pc_sylvi. initiative/speed are display-only metadata (the engine derives
# initiative from dex), kept as before.
_DEMO_CHARACTERS = [
    {
        "character_name": "Brakka Ironhide",
        "class_name": "Fighter",
        "race": "Half-Orc",
        "level": 3,
        "backstory": (
            "A disgraced arena champion turned mercenary. Brakka fights for coin "
            "and the slim hope of buying back her honour — or dying with her axe in hand."
        ),
        "hp_current": 28,
        "hp_max": 28,
        "armor_class": 16,
        "strength": 16,
        "dexterity": 12,
        "constitution": 15,
        "intelligence": 9,
        "wisdom": 11,
        "charisma": 10,
        "initiative": 1,
        "speed": 30,
    },
    {
        "character_name": "Sylvi Quill",
        "class_name": "Rogue",
        "race": "Wood Elf",
        "level": 3,
        "backstory": (
            "A scout who lost her whole patrol to the vault's first expedition. "
            "She returned alone, barely alive, and refuses to leave until the Heartstone "
            "is destroyed — or she is."
        ),
        "hp_current": 18,
        "hp_max": 18,
        "armor_class": 13,
        "strength": 9,
        "dexterity": 16,
        "constitution": 12,
        "intelligence": 14,
        "wisdom": 13,
        "charisma": 15,
        "initiative": 3,
        "speed": 35,
    },
]


@router.post("/demo", status_code=201)
async def create_demo_campaign(
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """Create the Sunken Vault starter campaign with two pre-built characters.

    Returns the campaign ID so the client can redirect immediately.
    Idempotent in the sense that each call creates a fresh copy — useful for resets.
    """
    campaign_id = str(uuid.uuid4())
    campaign = Campaign(
        id=campaign_id,
        name=_DEMO_CAMPAIGN["name"],
        description=_DEMO_CAMPAIGN["description"],
        world_setting=_DEMO_CAMPAIGN["world_setting"],
        status="active",
    )
    db.add(campaign)

    for char_data in _DEMO_CHARACTERS:
        character = Character(
            id=str(uuid.uuid4()),
            campaign_id=campaign_id,
            **char_data,
        )
        db.add(character)

    await db.flush()

    return {"campaign_id": campaign_id, "name": _DEMO_CAMPAIGN["name"]}
