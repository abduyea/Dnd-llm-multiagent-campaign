from fastapi import APIRouter

from backend.app.api.v1.actions import router as actions_router
from backend.app.api.v1.campaigns import router as campaigns_router
from backend.app.api.v1.characters import router as characters_router
from backend.app.api.v1.demo import router as demo_router
from backend.app.api.v1.dice import router as dice_router
from backend.app.api.v1.sessions import router as sessions_router
from backend.app.api.v1.stats import router as stats_router

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(demo_router)
api_router.include_router(campaigns_router)
api_router.include_router(characters_router)
api_router.include_router(sessions_router)
api_router.include_router(actions_router)
api_router.include_router(dice_router)
api_router.include_router(stats_router)

__all__ = ["api_router"]
