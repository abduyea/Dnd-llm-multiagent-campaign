from unittest.mock import patch

from backend.app.engine.turn import (
    _resolve_dice,
    _spend_action_economy,
    advance_turn,
    next_turn,
    process_turn,
)
from backend.app.engine.types import (
    ActionEconomy,
    ActionInput,
    CharacterState,
    GameState,
    InitiativeEntry,
)


def _make_char(
    char_id: str,
    name: str,
    hp: int = 20,
) -> CharacterState:
    return CharacterState(
        id=char_id,
        name=name,
        hp_current=hp,
        hp_max=20,
        strength=10,
        dexterity=10,
        constitution=10,
        intelligence=10,
        wisdom=10,
        charisma=10,
        armor_class=14,
        initiative_bonus=0,
        speed=30,
        action_economy=ActionEconomy(),
    )


class TestProcessTurn:
    def test_process_turn_valid(self) -> None:
        char = _make_char("pc1", "Hero")
        state = GameState(
            session_id="s1",
            campaign_id="c1",
            turn_number=1,
            current_character_id="pc1",
            characters={"pc1": char},
        )
        action = ActionInput(
            session_id="s1",
            character_id="pc1",
            action_type="move",
            description="Hero moves forward",
        )
        delta, violations = process_turn(state, action)
        assert delta is not None
        assert len(violations) == 0
        assert delta.character_id == "pc1"
        assert delta.action_type == "move"
        assert delta.turn_number == 1

    def test_process_turn_invalid_returns_violations(self) -> None:
        char = _make_char("pc1", "Hero")
        state = GameState(
            session_id="s1",
            campaign_id="c1",
            turn_number=1,
            current_character_id="pc2",
            characters={"pc1": char},
        )
        action = ActionInput(
            session_id="s1",
            character_id="pc1",
            action_type="attack_melee",
        )
        delta, violations = process_turn(state, action)
        assert delta is None
        assert len(violations) > 0

    def test_character_not_found_returns_violation(self) -> None:
        state = GameState(
            session_id="s1",
            campaign_id="c1",
            turn_number=1,
            current_character_id=None,
            characters={},
        )
        action = ActionInput(
            session_id="s1",
            character_id="ghost",
            action_type="move",
        )
        delta, violations = process_turn(state, action)
        assert delta is None
        assert len(violations) > 0

    def test_character_missing_after_validation_returns_violation(self) -> None:
        state = GameState(
            session_id="s1",
            campaign_id="c1",
            turn_number=1,
            current_character_id=None,
            characters={},
        )
        action = ActionInput(
            session_id="s1",
            character_id="ghost",
            action_type="move",
        )
        with patch("backend.app.engine.turn.validate_action", return_value=[]):
            delta, violations = process_turn(state, action)
        assert delta is None
        assert any(v.code == "character_not_found" for v in violations)


class TestNextTurn:
    def test_advance_turn_increments(self) -> None:
        entries = (
            InitiativeEntry(character_id="pc1", initiative=20, order=0),
            InitiativeEntry(character_id="npc1", initiative=10, order=1),
        )
        chars = {
            "pc1": _make_char("pc1", "Hero"),
            "npc1": _make_char("npc1", "Goblin"),
        }
        state = GameState(
            session_id="s1",
            campaign_id="c1",
            turn_number=1,
            current_character_id="pc1",
            initiative_order=entries,
            characters=chars,
        )
        next_state = next_turn(state)
        assert next_state.current_character_id == "npc1"

    def test_advance_turn_wraps_around(self) -> None:
        entries = (
            InitiativeEntry(character_id="pc1", initiative=20, order=0),
            InitiativeEntry(character_id="npc1", initiative=10, order=1),
        )
        chars = {
            "pc1": _make_char("pc1", "Hero"),
            "npc1": _make_char("npc1", "Goblin"),
        }
        state = GameState(
            session_id="s1",
            campaign_id="c1",
            turn_number=1,
            current_character_id="npc1",
            initiative_order=entries,
            characters=chars,
        )
        next_state = next_turn(state)
        assert next_state.current_character_id == "pc1"
        assert next_state.turn_number == 2  # wrapped -> new round

    def test_no_initiative_order_no_change(self) -> None:
        state = GameState(
            session_id="s1",
            campaign_id="c1",
            turn_number=1,
            current_character_id="pc1",
            characters={"pc1": _make_char("pc1", "Hero")},
        )
        next_state = next_turn(state)
        assert next_state == state

    def test_advance_turn_refreshes_economy(self) -> None:
        exhausted = CharacterState(
            id="pc1",
            name="Exhausted",
            hp_current=20,
            hp_max=20,
            strength=10,
            dexterity=10,
            constitution=10,
            intelligence=10,
            wisdom=10,
            charisma=10,
            armor_class=14,
            initiative_bonus=0,
            speed=30,
            action_economy=ActionEconomy(
                action=False, bonus_action=False, reaction=False, movement_remaining=0
            ),
        )
        entries = (InitiativeEntry(character_id="pc1", initiative=20, order=0),)
        state = GameState(
            session_id="s1",
            campaign_id="c1",
            turn_number=1,
            current_character_id="pc1",
            initiative_order=entries,
            characters={"pc1": exhausted},
        )
        new_state = advance_turn(state)
        refreshed = new_state.characters["pc1"]
        assert refreshed.action_economy.action
        assert refreshed.action_economy.movement_remaining == 30


class TestHelpers:
    def test_spend_action_economy_attack_spends_action(self) -> None:
        economy = ActionEconomy(
            action=True, bonus_action=True, reaction=True, movement_remaining=30
        )
        result = _spend_action_economy(economy, "attack_melee")
        assert not result.action
        assert result.bonus_action
        assert result.movement_remaining == 30

    def test_spend_action_economy_unrecognized_returns_same(self) -> None:
        economy = ActionEconomy(
            action=True, bonus_action=True, reaction=True, movement_remaining=30
        )
        result = _spend_action_economy(economy, "roleplay")
        assert result is economy

    def test_resolve_dice_with_expression(self) -> None:
        action = ActionInput(
            session_id="s1",
            character_id="pc1",
            action_type="attack_melee",
            dice_expression="1d6",
            seed=42,
        )
        results = _resolve_dice(action)
        assert len(results) == 1
        assert 1 <= results[0].total <= 6

    def test_resolve_dice_no_expression_returns_empty(self) -> None:
        action = ActionInput(
            session_id="s1",
            character_id="pc1",
            action_type="move",
        )
        assert _resolve_dice(action) == []

    def test_game_state_alive_characters(self) -> None:
        dead = CharacterState(
            id="dead",
            name="Dead",
            hp_current=0,
            hp_max=20,
            strength=10,
            dexterity=10,
            constitution=10,
            intelligence=10,
            wisdom=10,
            charisma=10,
            armor_class=10,
            initiative_bonus=0,
            speed=30,
            conditions=("dead",),
            action_economy=ActionEconomy(),
        )
        alive = _make_char("alive", "Alive")
        state = GameState(
            session_id="s1",
            campaign_id="c1",
            turn_number=1,
            current_character_id="alive",
            characters={"alive": alive, "dead": dead},
        )
        assert len(state.alive_characters()) == 1
        assert state.alive_characters()[0].id == "alive"

    def test_game_state_conscious_characters(self) -> None:
        ko = CharacterState(
            id="ko",
            name="KO",
            hp_current=0,
            hp_max=20,
            strength=10,
            dexterity=10,
            constitution=10,
            intelligence=10,
            wisdom=10,
            charisma=10,
            armor_class=10,
            initiative_bonus=0,
            speed=30,
            conditions=("unconscious",),
            action_economy=ActionEconomy(),
        )
        conscious = _make_char("c1", "Conscious")
        state = GameState(
            session_id="s1",
            campaign_id="c1",
            turn_number=1,
            current_character_id="c1",
            characters={"c1": conscious, "ko": ko},
        )
        assert len(state.conscious_characters()) == 1
        assert state.conscious_characters()[0].id == "c1"
