from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.base import get_db
from backend.app.db.models import Campaign, Character
from backend.app.db.models.session import Session, Turn

router = APIRouter(prefix="/stats", tags=["stats"])


@router.get("")
async def get_stats(db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    """Return aggregate platform statistics."""
    campaigns_total = await db.scalar(select(func.count(Campaign.id)))
    campaigns_active = await db.scalar(
        select(func.count(Campaign.id)).where(Campaign.status == "active")
    )
    characters_total = await db.scalar(select(func.count(Character.id)))
    sessions_total = await db.scalar(select(func.count(Session.id)))
    sessions_completed = await db.scalar(
        select(func.count(Session.id)).where(Session.status == "completed")
    )
    turns_total = await db.scalar(select(func.count(Turn.id)))

    return {
        "campaigns": campaigns_total or 0,
        "campaigns_active": campaigns_active or 0,
        "characters": characters_total or 0,
        "sessions": sessions_total or 0,
        "sessions_completed": sessions_completed or 0,
        "turns": turns_total or 0,
    }
