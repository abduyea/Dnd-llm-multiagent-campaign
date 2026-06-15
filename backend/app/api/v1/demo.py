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

# M11 maps demo characters to engine PCs by first name, so the existing DB
# roster names remain stable while the engine seed can keep its authored names.
_DEMO_CHARACTERS = [
    {
        "character_name": "Brakka Ironjaw",
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
        "strength": 17,
        "dexterity": 13,
        "constitution": 15,
        "intelligence": 9,
        "wisdom": 11,
        "charisma": 10,
        "initiative": 1,
        "speed": 30,
    },
    {
        "character_name": "Sylvi Ashwhisper",
        "class_name": "Rogue",
        "race": "Wood Elf",
        "level": 3,
        "backstory": (
            "A scout who lost her whole patrol to the vault's first expedition. "
            "She returned alone, barely alive, and refuses to leave until the Heartstone "
            "is destroyed — or she is."
        ),
        "hp_current": 21,
        "hp_max": 21,
        "armor_class": 14,
        "strength": 10,
        "dexterity": 17,
        "constitution": 13,
        "intelligence": 14,
        "wisdom": 14,
        "charisma": 12,
        "initiative": 3,
        "speed": 35,
    },
]


# CoC quick start: the campaign NAME is the binding key — the engine glue maps
# "The Boarding House on Halsey Street" → coc_scenario.json + the coc_lite
# ruleset (see m11_adapter._CAMPAIGNS). The roster's D&D-shaped columns carry
# display approximations of the investigators' CoC characteristics (pct/5);
# the engine plays from the authored seed attributes, not these rows.
_COC_CAMPAIGN = {
    "name": "The Boarding House on Halsey Street",
    "description": (
        "Arkham, 1924. A quiet lodger came back from Innsmouth with something "
        "wrapped in oilcloth, chanted in the cellar for weeks, and vanished. "
        "Now something else knocks under the floorboards of Number 13."
    ),
    "world_setting": (
        "Call of Cthulhu: 1920s cosmic horror. Investigators are fragile, "
        "skills beat force, and some things cost sanity just to behold. "
        "Percentile (d100 roll-under) resolution."
    ),
}

_COC_CHARACTERS = [
    {
        "character_name": "Eleanor Voss",  # first-name keyed to ent_pc_eleanor
        "class_name": "Archaeologist",
        "race": "Human",
        "level": 1,
        "backstory": (
            "A Miskatonic University archaeologist, precise and skeptical, "
            "carrying her late husband's revolver she half hopes never to use. "
            "She believes every horror has a catalogue number."
        ),
        "hp_current": 10,
        "hp_max": 10,
        "armor_class": 10,
        "strength": 8,
        "dexterity": 11,
        "constitution": 10,
        "intelligence": 16,
        "wisdom": 13,
        "charisma": 12,
        "initiative": 1,
        "speed": 30,
    },
    {
        "character_name": "Jack Murphy",
        "class_name": "Private Investigator",
        "race": "Human",
        "level": 1,
        "backstory": (
            "A PI out of Boston, all shoe leather and brass knuckles. "
            "Unimaginative in the way that keeps a man sane, loyal in the way "
            "that gets him hurt."
        ),
        "hp_current": 12,
        "hp_max": 12,
        "armor_class": 10,
        "strength": 12,
        "dexterity": 12,
        "constitution": 12,
        "intelligence": 11,
        "wisdom": 12,
        "charisma": 10,
        "initiative": 2,
        "speed": 30,
    },
]

_DEMOS_BY_RULESET = {
    "dnd5e_lite": (_DEMO_CAMPAIGN, _DEMO_CHARACTERS),
    "coc_lite": (_COC_CAMPAIGN, _COC_CHARACTERS),
}


@router.post("/demo", status_code=201)
async def create_demo_campaign(
    ruleset: str = "dnd5e_lite",
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """Create a starter campaign with two pre-built characters.

    ``ruleset`` selects the game system: ``dnd5e_lite`` → The Sunken Vault
    (D&D), ``coc_lite`` → The Boarding House on Halsey Street (Call of
    Cthulhu). Returns the campaign ID so the client can redirect immediately.
    Idempotent in the sense that each call creates a fresh copy — useful for resets.
    """
    demo = _DEMOS_BY_RULESET.get(ruleset)
    if demo is None:
        from fastapi import HTTPException

        raise HTTPException(
            status_code=422,
            detail=f"unknown ruleset {ruleset!r} "
                   f"(known: {sorted(_DEMOS_BY_RULESET)})",
        )
    campaign_data, characters = demo

    campaign_id = str(uuid.uuid4())
    campaign = Campaign(
        id=campaign_id,
        name=campaign_data["name"],
        description=campaign_data["description"],
        world_setting=campaign_data["world_setting"],
        status="active",
    )
    db.add(campaign)

    for char_data in characters:
        character = Character(
            id=str(uuid.uuid4()),
            campaign_id=campaign_id,
            **char_data,
        )
        db.add(character)

    await db.flush()

    return {"campaign_id": campaign_id, "name": campaign_data["name"]}
