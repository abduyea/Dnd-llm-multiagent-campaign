from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.base import get_db
from backend.app.db.models import Campaign, Character
from backend.app.models.character import CharacterCreate, CharacterResponse, CharacterUpdate

router = APIRouter(tags=["characters"])


@router.get(
    "/campaigns/{campaign_id}/characters",
    response_model=list[CharacterResponse],
)
async def list_characters(
    campaign_id: str,
    db: AsyncSession = Depends(get_db),
) -> list[CharacterResponse]:
    """List all characters belonging to a campaign, ordered by creation time."""
    result = await db.execute(
        select(Character).where(Character.campaign_id == campaign_id).order_by(Character.created_at)
    )
    chars = result.scalars().all()
    return [
        CharacterResponse(
            id=c.id,
            campaign_id=c.campaign_id,
            player_name=c.player_name or "",
            character_name=c.character_name,
            race=c.race or "",
            class_name=c.class_name or "",
            level=c.level,
            experience=c.experience or 0,
            hp_current=c.hp_current,
            hp_max=c.hp_max,
            strength=c.strength,
            dexterity=c.dexterity,
            constitution=c.constitution,
            intelligence=c.intelligence,
            wisdom=c.wisdom,
            charisma=c.charisma,
            armor_class=c.armor_class,
            initiative=c.initiative,
            speed=c.speed,
            backstory=c.backstory or "",
            created_at=c.created_at,
            updated_at=c.updated_at,
        )
        for c in chars
    ]


@router.get(
    "/characters/{character_id}",
    response_model=CharacterResponse,
)
async def get_character(
    character_id: str,
    db: AsyncSession = Depends(get_db),
) -> CharacterResponse:
    """Fetch a single character by ID; returns 404 if not found."""
    result = await db.execute(select(Character).where(Character.id == character_id))
    char = result.scalar_one_or_none()
    if char is None:
        raise HTTPException(status_code=404, detail="Character not found")
    return CharacterResponse(
        id=char.id,
        campaign_id=char.campaign_id,
        player_name=char.player_name or "",
        character_name=char.character_name,
        race=char.race or "",
        class_name=char.class_name or "",
        level=char.level,
        experience=char.experience or 0,
        hp_current=char.hp_current,
        hp_max=char.hp_max,
        strength=char.strength,
        dexterity=char.dexterity,
        constitution=char.constitution,
        intelligence=char.intelligence,
        wisdom=char.wisdom,
        charisma=char.charisma,
        armor_class=char.armor_class,
        initiative=char.initiative,
        speed=char.speed,
        backstory=char.backstory or "",
        created_at=char.created_at,
        updated_at=char.updated_at,
    )


@router.post(
    "/campaigns/{campaign_id}/characters",
    response_model=CharacterResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_character(
    campaign_id: str,
    body: CharacterCreate,
    db: AsyncSession = Depends(get_db),
) -> CharacterResponse:
    """Create a character under a campaign; auto-calculates HP if not supplied."""
    campaign_check = await db.execute(select(Campaign).where(Campaign.id == campaign_id))
    if campaign_check.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Campaign not found")

    con_mod = (body.constitution - 10) // 2
    default_hp = max(1, body.level * 8 + con_mod * body.level)
    hp = body.hp_max if body.hp_max is not None else default_hp

    char = Character(
        id=str(uuid.uuid4()),
        campaign_id=campaign_id,
        player_name=body.player_name,
        character_name=body.character_name,
        race=body.race,
        class_name=body.class_name,
        level=body.level,
        hp_current=hp,
        hp_max=hp,
        strength=body.strength,
        dexterity=body.dexterity,
        constitution=body.constitution,
        intelligence=body.intelligence,
        wisdom=body.wisdom,
        charisma=body.charisma,
        armor_class=body.armor_class,
        initiative=body.initiative,
        speed=body.speed,
        backstory=body.backstory,
    )
    db.add(char)
    await db.flush()
    return CharacterResponse(
        id=char.id,
        campaign_id=char.campaign_id,
        player_name=char.player_name or "",
        character_name=char.character_name,
        race=char.race or "",
        class_name=char.class_name or "",
        level=char.level,
        experience=char.experience or 0,
        hp_current=char.hp_current,
        hp_max=char.hp_max,
        strength=char.strength,
        dexterity=char.dexterity,
        constitution=char.constitution,
        intelligence=char.intelligence,
        wisdom=char.wisdom,
        charisma=char.charisma,
        armor_class=char.armor_class,
        initiative=char.initiative,
        speed=char.speed,
        backstory=char.backstory or "",
        created_at=char.created_at,
        updated_at=char.updated_at,
    )


@router.put("/characters/{character_id}", response_model=CharacterResponse)
async def update_character(
    character_id: str,
    body: CharacterUpdate,
    db: AsyncSession = Depends(get_db),
) -> CharacterResponse:
    """Partially update any character fields; ignores None values."""
    result = await db.execute(select(Character).where(Character.id == character_id))
    char = result.scalar_one_or_none()
    if char is None:
        raise HTTPException(status_code=404, detail="Character not found")

    if body.player_name is not None:
        char.player_name = body.player_name
    if body.character_name is not None:
        char.character_name = body.character_name
    if body.race is not None:
        char.race = body.race
    if body.class_name is not None:
        char.class_name = body.class_name
    if body.level is not None:
        char.level = body.level
    if body.hp_current is not None:
        char.hp_current = body.hp_current
    if body.hp_max is not None:
        char.hp_max = body.hp_max
    if body.strength is not None:
        char.strength = body.strength
    if body.dexterity is not None:
        char.dexterity = body.dexterity
    if body.constitution is not None:
        char.constitution = body.constitution
    if body.intelligence is not None:
        char.intelligence = body.intelligence
    if body.wisdom is not None:
        char.wisdom = body.wisdom
    if body.charisma is not None:
        char.charisma = body.charisma
    if body.armor_class is not None:
        char.armor_class = body.armor_class
    if body.initiative is not None:
        char.initiative = body.initiative
    if body.speed is not None:
        char.speed = body.speed
    if body.backstory is not None:
        char.backstory = body.backstory

    await db.flush()
    return CharacterResponse(
        id=char.id,
        campaign_id=char.campaign_id,
        player_name=char.player_name or "",
        character_name=char.character_name,
        race=char.race or "",
        class_name=char.class_name or "",
        level=char.level,
        experience=char.experience or 0,
        hp_current=char.hp_current,
        hp_max=char.hp_max,
        strength=char.strength,
        dexterity=char.dexterity,
        constitution=char.constitution,
        intelligence=char.intelligence,
        wisdom=char.wisdom,
        charisma=char.charisma,
        armor_class=char.armor_class,
        initiative=char.initiative,
        speed=char.speed,
        backstory=char.backstory or "",
        created_at=char.created_at,
        updated_at=char.updated_at,
    )


@router.delete("/characters/{character_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_character(
    character_id: str,
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete a character. Blocked if the character has turns in an active session."""
    from backend.app.db.models.session import Session, Turn

    result = await db.execute(select(Character).where(Character.id == character_id))
    char = result.scalar_one_or_none()
    if char is None:
        raise HTTPException(status_code=404, detail="Character not found")

    active_session = await db.execute(
        select(Session).where(
            Session.campaign_id == char.campaign_id, Session.status == "active"
        )
    )
    if active_session.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=409,
            detail="Cannot delete a character while a session is active",
        )

    await db.execute(delete(Turn).where(Turn.character_id == character_id))
    await db.delete(char)
    await db.flush()
