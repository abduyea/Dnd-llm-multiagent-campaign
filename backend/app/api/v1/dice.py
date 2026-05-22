from __future__ import annotations

from fastapi import APIRouter, HTTPException

from backend.app.engine.dice import parse_dice, roll_dice
from backend.app.models.action import DiceRollRequest, DiceRollResponse

router = APIRouter(prefix="/dice", tags=["dice"])


@router.post("/roll", response_model=DiceRollResponse)
async def roll(body: DiceRollRequest) -> DiceRollResponse:
    """Roll a dice expression and return individual rolls, modifier, and total."""
    try:
        parsed = parse_dice(body.expression)
        result = roll_dice(body.expression, seed=body.seed)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return DiceRollResponse(
        expression=result.expression,
        rolls=list(result.rolls),
        modifier=parsed.modifier,
        total=result.total,
    )
