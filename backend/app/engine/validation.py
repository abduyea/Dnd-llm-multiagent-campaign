from __future__ import annotations

import re as _re

from backend.app.engine.types import NEUTRALIZED_STATUSES, ActionInput, GameState, Violation

_VALID_ACTION_TYPES: frozenset[str] = frozenset(
    {
        "attack_melee",
        "attack_ranged",
        "cast",
        "cast_spell",
        "move",
        "movement",
        "dash",
        "disengage",
        "dodge",
        "help",
        "hide",
        "ready",
        "use_item",
        "interact",
        "delay",
        "roleplay",
        "skill_check",
        "talk",
        "speak",
        "puzzle_answer",
    }
)

# Articles to strip before fuzzy-matching puzzle answers.
_ARTICLE_RE = _re.compile(r"^\s*(?:a|an|the)\s+", _re.IGNORECASE)


def puzzle_answer_matches(submitted: str, authored: str) -> bool:
    """Return True if *submitted* matches the *authored* puzzle answer.

    Tolerates leading articles (a/an/the), case differences, and allows the
    canonical answer to appear as a substring of the full submission.
    """
    def _norm(text: str) -> str:
        return _ARTICLE_RE.sub("", text.strip().lower())

    norm_sub = _norm(submitted)
    norm_auth = _norm(authored)
    return bool(norm_auth and norm_sub and (norm_auth in norm_sub or norm_sub in norm_auth))


def validate_action(state: GameState, action: ActionInput) -> list[Violation]:
    """Check action legality against current game state; returns empty list if valid."""
    violations: list[Violation] = []

    if action.action_type not in _VALID_ACTION_TYPES:
        violations.append(
            Violation(
                field="action_type",
                message=f"Invalid action type: {action.action_type}",
                code="invalid_action_type",
            )
        )

    character = state.character_by_id(action.character_id)
    if character is None:
        violations.append(
            Violation(
                field="character_id",
                message=f"Character {action.character_id} not found",
                code="character_not_found",
            )
        )
        return violations

    neutralized = NEUTRALIZED_STATUSES.intersection(character.conditions)
    if not character.is_alive or neutralized:
        status_label = next(iter(neutralized), "dead") if neutralized else "dead"
        violations.append(
            Violation(
                field="character_id",
                message=f"Character {character.name} is {status_label}",
                code="character_neutralized",
            )
        )
        return violations

    if character.action_economy.is_empty():
        violations.append(
            Violation(
                field="character_id",
                message=f"Character {character.name} has no actions remaining",
                code="no_actions_remaining",
            )
        )

    if action.action_type in ("attack_melee", "attack_ranged") and action.target_id:
        target = state.character_by_id(action.target_id)
        if target is None:
            violations.append(
                Violation(
                    field="target_id",
                    message=f"Target {action.target_id} not found",
                    code="target_not_found",
                )
            )
        elif not target.is_alive:
            violations.append(
                Violation(
                    field="target_id",
                    message=f"Target {target.name} is already dead",
                    code="target_dead",
                )
            )

    if state.current_character_id is not None and action.character_id != state.current_character_id:
        violations.append(
            Violation(
                field="character_id",
                message=f"It is not {character.name}'s turn",
                code="not_character_turn",
            )
        )

    return violations
