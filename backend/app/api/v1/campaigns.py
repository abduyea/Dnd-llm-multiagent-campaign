from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.base import get_db
from backend.app.db.models import Campaign
from backend.app.db.models.character import Character
from backend.app.db.models.memory import Summary
from backend.app.db.models.session import Session
from backend.app.models.campaign import (
    CampaignBundle,
    CampaignCreate,
    CampaignMetaExport,
    CampaignResponse,
    CampaignUpdate,
    CharacterExport,
)

router = APIRouter(prefix="/campaigns", tags=["campaigns"])


@router.get("", response_model=list[CampaignResponse])
async def list_campaigns(
    db: AsyncSession = Depends(get_db),
) -> list[CampaignResponse]:
    """List all campaigns with character and session counts."""
    result = await db.execute(select(Campaign).order_by(Campaign.created_at.desc()))
    campaigns = result.scalars().all()

    char_counts_result = await db.execute(
        select(Character.campaign_id, func.count(Character.id).label("cnt"))
        .group_by(Character.campaign_id)
    )
    char_counts = {row.campaign_id: row.cnt for row in char_counts_result}

    sess_counts_result = await db.execute(
        select(Session.campaign_id, func.count(Session.id).label("cnt"))
        .group_by(Session.campaign_id)
    )
    sess_counts = {row.campaign_id: row.cnt for row in sess_counts_result}

    return [
        CampaignResponse(
            id=c.id,
            name=c.name,
            description=c.description or "",
            world_setting=c.world_setting or "",
            status=c.status,
            created_at=c.created_at,
            updated_at=c.updated_at,
            character_count=char_counts.get(c.id, 0),
            session_count=sess_counts.get(c.id, 0),
        )
        for c in campaigns
    ]


@router.get("/{campaign_id}", response_model=CampaignResponse)
async def get_campaign(
    campaign_id: str,
    db: AsyncSession = Depends(get_db),
) -> CampaignResponse:
    """Get a single campaign with character and session counts."""
    result = await db.execute(select(Campaign).where(Campaign.id == campaign_id))
    campaign = result.scalar_one_or_none()
    if campaign is None:
        raise HTTPException(status_code=404, detail="Campaign not found")

    char_count_result = await db.execute(
        select(func.count(Character.id)).where(Character.campaign_id == campaign_id)
    )
    sess_count_result = await db.execute(
        select(func.count(Session.id)).where(Session.campaign_id == campaign_id)
    )

    return CampaignResponse(
        id=campaign.id,
        name=campaign.name,
        description=campaign.description or "",
        world_setting=campaign.world_setting or "",
        status=campaign.status,
        created_at=campaign.created_at,
        updated_at=campaign.updated_at,
        character_count=char_count_result.scalar() or 0,
        session_count=sess_count_result.scalar() or 0,
    )


@router.post("", response_model=CampaignResponse, status_code=status.HTTP_201_CREATED)
async def create_campaign(
    body: CampaignCreate,
    db: AsyncSession = Depends(get_db),
) -> CampaignResponse:
    """Create a new campaign with the supplied name, description, and world setting."""
    campaign = Campaign(
        id=str(uuid.uuid4()),
        name=body.name,
        description=body.description,
        world_setting=body.world_setting,
    )
    db.add(campaign)
    await db.flush()
    return CampaignResponse(
        id=campaign.id,
        name=campaign.name,
        description=campaign.description or "",
        world_setting=campaign.world_setting or "",
        status=campaign.status,
        created_at=campaign.created_at,
        updated_at=campaign.updated_at,
        character_count=0,
        session_count=0,
    )


@router.get("/{campaign_id}/sessions")
async def list_campaign_sessions(
    campaign_id: str,
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    """List all sessions for a campaign, each with their latest summary text."""
    campaign_check = await db.execute(select(Campaign).where(Campaign.id == campaign_id))
    if campaign_check.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Campaign not found")

    result = await db.execute(
        select(Session)
        .where(Session.campaign_id == campaign_id)
        .order_by(Session.started_at.desc())
    )
    sessions = result.scalars().all()

    output = []
    for s in sessions:
        summary_result = await db.execute(
            select(Summary)
            .where(Summary.session_id == s.id)
            .order_by(Summary.created_at.desc())
            .limit(1)
        )
        summary = summary_result.scalar_one_or_none()
        output.append(
            {
                "id": s.id,
                "name": s.name,
                "status": s.status,
                "started_at": s.started_at,
                "ended_at": s.ended_at,
                "turn_count": s.turn_count,
                "summary": summary.summary_text if summary else None,
            }
        )
    return output


@router.get("/{campaign_id}/export", response_model=CampaignBundle)
async def export_campaign(
    campaign_id: str,
    db: AsyncSession = Depends(get_db),
) -> CampaignBundle:
    """Export a campaign with all its characters as a portable JSON bundle."""
    result = await db.execute(select(Campaign).where(Campaign.id == campaign_id))
    campaign = result.scalar_one_or_none()
    if campaign is None:
        raise HTTPException(status_code=404, detail="Campaign not found")

    chars_result = await db.execute(
        select(Character)
        .where(Character.campaign_id == campaign_id)
        .order_by(Character.created_at)
    )
    chars = chars_result.scalars().all()

    return CampaignBundle(
        exported_at=datetime.now(UTC).isoformat(),
        campaign=CampaignMetaExport(
            name=campaign.name,
            description=campaign.description or "",
            world_setting=campaign.world_setting or "",
            status=campaign.status,
        ),
        characters=[
            CharacterExport(
                character_name=c.character_name,
                player_name=c.player_name or "",
                race=c.race or "",
                class_name=c.class_name or "",
                level=c.level,
                experience=c.experience,
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
            )
            for c in chars
        ],
    )


@router.post("/import", response_model=CampaignResponse, status_code=status.HTTP_201_CREATED)
async def import_campaign(
    body: CampaignBundle,
    db: AsyncSession = Depends(get_db),
) -> CampaignResponse:
    """Import a campaign bundle, creating a fresh campaign with new IDs for all records."""
    campaign_id = str(uuid.uuid4())
    campaign = Campaign(
        id=campaign_id,
        name=body.campaign.name,
        description=body.campaign.description,
        world_setting=body.campaign.world_setting,
        status="active",
    )
    db.add(campaign)

    for char_data in body.characters:
        db.add(
            Character(
                id=str(uuid.uuid4()),
                campaign_id=campaign_id,
                character_name=char_data.character_name,
                player_name=char_data.player_name,
                race=char_data.race,
                class_name=char_data.class_name,
                level=char_data.level,
                experience=char_data.experience,
                hp_current=char_data.hp_current,
                hp_max=char_data.hp_max,
                strength=char_data.strength,
                dexterity=char_data.dexterity,
                constitution=char_data.constitution,
                intelligence=char_data.intelligence,
                wisdom=char_data.wisdom,
                charisma=char_data.charisma,
                armor_class=char_data.armor_class,
                initiative=char_data.initiative,
                speed=char_data.speed,
                backstory=char_data.backstory,
            )
        )

    await db.flush()
    return CampaignResponse(
        id=campaign_id,
        name=campaign.name,
        description=campaign.description or "",
        world_setting=campaign.world_setting or "",
        status=campaign.status,
        created_at=campaign.created_at,
        updated_at=campaign.updated_at,
        character_count=len(body.characters),
        session_count=0,
    )


@router.put("/{campaign_id}", response_model=CampaignResponse)
async def update_campaign(
    campaign_id: str,
    body: CampaignUpdate,
    db: AsyncSession = Depends(get_db),
) -> CampaignResponse:
    """Partially update campaign fields; returns 404 if the campaign does not exist."""
    result = await db.execute(select(Campaign).where(Campaign.id == campaign_id))
    campaign = result.scalar_one_or_none()
    if campaign is None:
        raise HTTPException(status_code=404, detail="Campaign not found")

    if body.name is not None:
        campaign.name = body.name
    if body.description is not None:
        campaign.description = body.description
    if body.world_setting is not None:
        campaign.world_setting = body.world_setting
    if body.status is not None:
        campaign.status = body.status

    await db.flush()
    char_count_result = await db.execute(
        select(func.count(Character.id)).where(Character.campaign_id == campaign_id)
    )
    sess_count_result = await db.execute(
        select(func.count(Session.id)).where(Session.campaign_id == campaign_id)
    )
    return CampaignResponse(
        id=campaign.id,
        name=campaign.name,
        description=campaign.description or "",
        world_setting=campaign.world_setting or "",
        status=campaign.status,
        created_at=campaign.created_at,
        updated_at=campaign.updated_at,
        character_count=char_count_result.scalar() or 0,
        session_count=sess_count_result.scalar() or 0,
    )


@router.delete("/{campaign_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_campaign(
    campaign_id: str,
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete a campaign and all its data after active sessions have ended."""
    result = await db.execute(select(Campaign).where(Campaign.id == campaign_id))
    campaign = result.scalar_one_or_none()
    if campaign is None:
        raise HTTPException(status_code=404, detail="Campaign not found")

    active_session_result = await db.execute(
        select(Session).where(Session.campaign_id == campaign_id, Session.status == "active")
    )
    if active_session_result.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=409,
            detail="Cannot delete a campaign while a session is active",
        )

    await db.delete(campaign)
    await db.flush()
