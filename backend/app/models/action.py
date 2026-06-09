from typing import Any

from pydantic import BaseModel, Field


class EnemyContext(BaseModel):
    """Rich NPC context from the frontend encounter tracker, passed to the AI agents."""

    name: str
    persona: str | None = None
    disposition: str | None = None
    goals: list[str] | None = None
    secret: str | None = None
    negotiation_levers: str | None = None
    hp: int | None = None
    max_hp: int | None = None
    ac: int | None = None
    conditions: list[str] | None = None


class ActionRequest(BaseModel):
    character_id: str
    action_type: str = Field(
        ...,
        pattern=(
            r"^(attack_melee|attack_ranged|cast_spell|cast|skill_check|roleplay|"
            r"movement|move|dash|disengage|dodge|help|hide|ready|use_item|interact|"
            r"delay|talk|speak|puzzle_answer)$"
        ),
    )
    target_id: str | None = None
    dice_expression: str | None = Field(default=None, pattern=r"^\d+[dD]\d+([+-]\d+)?$")
    description: str = ""
    seed: int | None = None
    enemies: list[EnemyContext] = Field(default_factory=list)
    location: str | None = None
    # skill_check: which ability modifier to roll (e.g. "wis_mod") and what the
    # check is for ("insight", "search", …) — the engine derives the DC from the
    # target's `{purpose}_dc`. Ignored by other action types.
    stat: str | None = None
    purpose: str | None = None


class DiceRollRequest(BaseModel):
    expression: str = Field(..., pattern=r"^\d+[dD]\d+([+-]\d+)?$")
    seed: int | None = None


class DiceRollResponse(BaseModel):
    expression: str
    rolls: list[int]
    modifier: int
    total: int


class AttackResultResponse(BaseModel):
    is_hit: bool
    is_critical: bool
    damage: int
    natural_roll: int
    total_roll: int


class ActionResultResponse(BaseModel):
    turn_number: int
    character_id: str
    action_type: str
    description: str
    dice_results: list[DiceRollResponse]
    attack_result: AttackResultResponse | None = None
    narration: str
    npc_responses: list[dict[str, str]] = Field(default_factory=list)
    state_changes: dict[str, Any] = Field(default_factory=dict)
    errors: list[str] = Field(default_factory=list)


class ViolationResponse(BaseModel):
    field: str
    message: str
    code: str
