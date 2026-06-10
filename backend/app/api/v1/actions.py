from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.base import get_db
from backend.app.engine.types import ActionInput
from backend.app.models.action import ActionRequest, ActionResultResponse, AttackResultResponse
from backend.app.orchestrator import process_action as orchestrator_process_action
from backend.app.orchestrator import process_action_stream as orchestrator_stream

router = APIRouter(prefix="/sessions", tags=["actions"])


def _build_action_input(session_id: str, body: ActionRequest) -> ActionInput:
    """Map an incoming ActionRequest (plus the path session id) to an engine ActionInput."""
    return ActionInput(
        session_id=session_id,
        character_id=body.character_id,
        action_type=body.action_type,
        target_id=body.target_id,
        dice_expression=body.dice_expression,
        description=body.description,
        seed=body.seed,
        enemies=tuple(e.model_dump() for e in body.enemies),
        location=body.location,
        stat=body.stat,
        purpose=body.purpose,
    )


@router.post("/{session_id}/actions", response_model=ActionResultResponse)
async def submit_action(
    session_id: str,
    body: ActionRequest,
    db: AsyncSession = Depends(get_db),
) -> ActionResultResponse:
    """Submit a player action, run the engine + AI pipeline, and return the result."""
    action_input = _build_action_input(session_id, body)

    result = await orchestrator_process_action(action_input=action_input, db=db)

    if "error" in result:
        status_code = result.get("status", 400)
        violations = result.get("violations", [])
        detail = result["error"]
        if violations:
            detail = f"{detail}: {', '.join(v['message'] for v in violations)}"
        raise HTTPException(status_code=status_code, detail=detail)

    dice_results = result.get("dice_results", [])
    raw_attack = result.get("attack_result")

    errors = result.get("errors", [])
    attack_result_resp: AttackResultResponse | None = None
    if raw_attack:
        attack_result_resp = AttackResultResponse(
            is_hit=raw_attack["is_hit"],
            is_critical=raw_attack["is_critical"],
            damage=raw_attack["damage"],
            natural_roll=raw_attack["natural_roll"],
            total_roll=raw_attack["total_roll"],
        )
        if not raw_attack["is_hit"]:
            errors = [f"Attack missed (rolled {raw_attack['natural_roll']})"]

    return ActionResultResponse(
        turn_number=result["turn_number"],
        character_id=result["character_id"],
        action_type=result["action_type"],
        description=result["description"],
        dice_results=dice_results,
        attack_result=attack_result_resp,
        narration=result.get("narration", ""),
        npc_responses=result.get("npc_responses", []),
        state_changes=result.get("state_changes", {}),
        errors=errors,
    )


@router.post("/{session_id}/actions/stream")
async def submit_action_stream(
    session_id: str,
    body: ActionRequest,
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    """Submit a player action and receive narration as a Server-Sent Events stream.

    Events: ``result`` (immediate game state) → ``token`` (narration tokens) → ``done``.
    Error events use ``type: error`` with a ``message`` field.
    """
    action_input = _build_action_input(session_id, body)
    return StreamingResponse(
        orchestrator_stream(action_input, db),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
