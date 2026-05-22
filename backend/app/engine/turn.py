from __future__ import annotations

from backend.app.engine.dice import roll_dice
from backend.app.engine.types import (
    ActionEconomy,
    ActionInput,
    CharacterState,
    DiceResult,
    GameState,
    TurnDelta,
    Violation,
)
from backend.app.engine.validation import validate_action


def _spend_action_economy(economy: ActionEconomy, action_type: str) -> ActionEconomy:
    if action_type in (
        "attack_melee",
        "attack_ranged",
        "cast",
        "dash",
        "disengage",
        "dodge",
        "help",
        "hide",
        "ready",
    ):
        return ActionEconomy(
            action=False,
            bonus_action=economy.bonus_action,
            reaction=economy.reaction,
            movement_remaining=economy.movement_remaining,
        )
    if action_type in ("move",):
        return ActionEconomy(
            action=economy.action,
            bonus_action=economy.bonus_action,
            reaction=economy.reaction,
            movement_remaining=0,
        )
    return economy


def _resolve_dice(action: ActionInput) -> list[DiceResult]:
    if action.dice_expression:
        return [roll_dice(action.dice_expression, seed=action.seed)]
    return []


def next_turn(state: GameState) -> GameState:
    """Advance current_character_id to the next entry in initiative order."""
    if not state.initiative_order:
        return state

    entries = list(state.initiative_order)
    current_idx = -1
    for i, entry in enumerate(entries):
        if entry.character_id == state.current_character_id:
            current_idx = i
            break

    next_idx = (current_idx + 1) % len(entries)
    next_char_id = entries[next_idx].character_id

    return GameState(
        session_id=state.session_id,
        campaign_id=state.campaign_id,
        turn_number=state.turn_number + 1 if next_idx <= current_idx else state.turn_number,
        current_character_id=next_char_id,
        initiative_order=state.initiative_order,
        characters=state.characters,
        scene_id=state.scene_id,
    )


def _refresh_action_economy(char: CharacterState) -> CharacterState:
    return CharacterState(
        id=char.id,
        name=char.name,
        hp_current=char.hp_current,
        hp_max=char.hp_max,
        strength=char.strength,
        dexterity=char.dexterity,
        constitution=char.constitution,
        intelligence=char.intelligence,
        wisdom=char.wisdom,
        charisma=char.charisma,
        armor_class=char.armor_class,
        initiative_bonus=char.initiative_bonus,
        speed=char.speed,
        conditions=char.conditions,
        action_economy=ActionEconomy(movement_remaining=char.speed),
    )


def process_turn(
    state: GameState,
    action: ActionInput,
) -> tuple[TurnDelta | None, list[Violation]]:
    """Validate an action, spend action economy, resolve dice, and return a TurnDelta."""
    violations = validate_action(state, action)
    if violations:
        return None, violations

    character = state.character_by_id(action.character_id)
    if character is None:
        return None, [Violation("character_id", "Character not found", "character_not_found")]

    dice_results = _resolve_dice(action)

    new_economy = _spend_action_economy(character.action_economy, action.action_type)
    refreshed_char = _refresh_action_economy(character)
    updated_char = CharacterState(
        id=refreshed_char.id,
        name=refreshed_char.name,
        hp_current=refreshed_char.hp_current,
        hp_max=refreshed_char.hp_max,
        strength=refreshed_char.strength,
        dexterity=refreshed_char.dexterity,
        constitution=refreshed_char.constitution,
        intelligence=refreshed_char.intelligence,
        wisdom=refreshed_char.wisdom,
        charisma=refreshed_char.charisma,
        armor_class=refreshed_char.armor_class,
        initiative_bonus=refreshed_char.initiative_bonus,
        speed=refreshed_char.speed,
        conditions=refreshed_char.conditions,
        action_economy=new_economy,
    )

    delta = TurnDelta(
        turn_number=state.turn_number,
        character_id=action.character_id,
        action_type=action.action_type,
        action_description=action.description,
        dice_results=dice_results,
        attack_results=[],
        state_changes={action.character_id: updated_char},
        initiative_order=state.initiative_order,
    )

    return delta, []


def advance_turn(state: GameState) -> GameState:
    """Refresh action economy for all characters, then move to the next initiative slot."""
    refreshed_chars = {}
    for cid, char in state.characters.items():
        refreshed_chars[cid] = _refresh_action_economy(char)
    new_state = GameState(
        session_id=state.session_id,
        campaign_id=state.campaign_id,
        turn_number=state.turn_number,
        current_character_id=state.current_character_id,
        initiative_order=state.initiative_order,
        characters=refreshed_chars,
        scene_id=state.scene_id,
    )
    return next_turn(new_state)
