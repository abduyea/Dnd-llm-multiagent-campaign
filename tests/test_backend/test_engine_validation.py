from backend.app.engine.types import (
    NEUTRALIZED_STATUSES,
    ActionEconomy,
    ActionInput,
    CharacterState,
    GameState,
)
from backend.app.engine.validation import puzzle_answer_matches, validate_action


def _make_state(
    char_id: str = "pc1",
    hp: int = 20,
    ac: int = 14,
    conscious: bool = True,
) -> GameState:
    conditions = ()
    if not conscious:
        conditions = ("unconscious",)
    char = CharacterState(
        id=char_id,
        name="Test",
        hp_current=hp,
        hp_max=20,
        strength=10,
        dexterity=10,
        constitution=10,
        intelligence=10,
        wisdom=10,
        charisma=10,
        armor_class=ac,
        initiative_bonus=0,
        speed=30,
        conditions=conditions,
        action_economy=ActionEconomy(),
    )
    return GameState(
        session_id="s1",
        campaign_id="c1",
        turn_number=1,
        current_character_id=char_id,
        characters={char_id: char},
    )


class TestValidateAction:
    def test_valid_action(self) -> None:
        npc = CharacterState(
            id="npc1",
            name="Goblin",
            hp_current=10,
            hp_max=10,
            strength=10,
            dexterity=10,
            constitution=10,
            intelligence=8,
            wisdom=8,
            charisma=8,
            armor_class=10,
            initiative_bonus=0,
            speed=30,
            action_economy=ActionEconomy(),
        )
        state = GameState(
            session_id="s1",
            campaign_id="c1",
            turn_number=1,
            current_character_id="pc1",
            characters={"pc1": _make_state().characters["pc1"], "npc1": npc},
        )
        action = ActionInput(
            session_id="s1",
            character_id="pc1",
            action_type="attack_melee",
            target_id="npc1",
        )
        violations = validate_action(state, action)
        assert len(violations) == 0

    def test_invalid_action_type(self) -> None:
        state = _make_state()
        action = ActionInput(
            session_id="s1",
            character_id="pc1",
            action_type="fly",
        )
        violations = validate_action(state, action)
        assert any(v.code == "invalid_action_type" for v in violations)

    def test_character_not_found(self) -> None:
        state = _make_state()
        action = ActionInput(
            session_id="s1",
            character_id="ghost",
            action_type="move",
        )
        violations = validate_action(state, action)
        assert any(v.code == "character_not_found" for v in violations)

    def test_dead_character(self) -> None:
        state = _make_state(hp=0)
        action = ActionInput(
            session_id="s1",
            character_id="pc1",
            action_type="move",
        )
        violations = validate_action(state, action)
        assert any(v.code == "character_neutralized" for v in violations)

    def test_unconscious_character(self) -> None:
        state = _make_state(conscious=False)
        action = ActionInput(
            session_id="s1",
            character_id="pc1",
            action_type="move",
        )
        violations = validate_action(state, action)
        # "unconscious" is in NEUTRALIZED_STATUSES → code is "character_neutralized"
        assert any(v.code == "character_neutralized" for v in violations)

    def test_attack_without_target_is_valid(self) -> None:
        # Engine falls back to a generic enemy when target_id is absent — no violation.
        state = _make_state()
        action = ActionInput(
            session_id="s1",
            character_id="pc1",
            action_type="attack_melee",
            target_id=None,
        )
        violations = validate_action(state, action)
        assert not any(v.code == "target_required" for v in violations)

    def test_target_not_found(self) -> None:
        state = _make_state()
        action = ActionInput(
            session_id="s1",
            character_id="pc1",
            action_type="attack_melee",
            target_id="ghost",
        )
        violations = validate_action(state, action)
        assert any(v.code == "target_not_found" for v in violations)

    def test_target_dead(self) -> None:
        target = CharacterState(
            id="npc1",
            name="DeadGoblin",
            hp_current=0,
            hp_max=10,
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
        pc = CharacterState(
            id="pc1",
            name="Hero",
            hp_current=20,
            hp_max=20,
            strength=10,
            dexterity=10,
            constitution=10,
            intelligence=10,
            wisdom=10,
            charisma=10,
            armor_class=14,
            initiative_bonus=2,
            speed=30,
            action_economy=ActionEconomy(),
        )
        state = GameState(
            session_id="s1",
            campaign_id="c1",
            turn_number=1,
            current_character_id="pc1",
            characters={"pc1": pc, "npc1": target},
        )
        action = ActionInput(
            session_id="s1",
            character_id="pc1",
            action_type="attack_melee",
            target_id="npc1",
        )
        violations = validate_action(state, action)
        assert any(v.code == "target_dead" for v in violations)

    def test_not_character_turn(self) -> None:
        char = CharacterState(
            id="pc1",
            name="Hero",
            hp_current=20,
            hp_max=20,
            strength=10,
            dexterity=10,
            constitution=10,
            intelligence=10,
            wisdom=10,
            charisma=10,
            armor_class=14,
            initiative_bonus=2,
            speed=30,
            action_economy=ActionEconomy(),
        )
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
            action_type="move",
        )
        violations = validate_action(state, action)
        assert any(v.code == "not_character_turn" for v in violations)

    def test_talk_and_puzzle_action_types_valid(self) -> None:
        """talk and puzzle_answer are now valid action types."""
        state = _make_state()
        for atype in ("talk", "speak", "puzzle_answer"):
            action = ActionInput(
                session_id="s1", character_id="pc1", action_type=atype
            )
            violations = validate_action(state, action)
            assert not any(v.code == "invalid_action_type" for v in violations), atype

    def test_neutralized_statuses_constant_is_frozenset(self) -> None:
        assert isinstance(NEUTRALIZED_STATUSES, frozenset)
        assert "dead" in NEUTRALIZED_STATUSES
        assert "unconscious" in NEUTRALIZED_STATUSES
        assert "fled" in NEUTRALIZED_STATUSES
        assert "surrender" in NEUTRALIZED_STATUSES

    def test_no_actions_remaining(self) -> None:
        char = CharacterState(
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
            initiative_bonus=2,
            speed=30,
            action_economy=ActionEconomy(
                action=False, bonus_action=False, reaction=False, movement_remaining=0
            ),
        )
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
        )
        violations = validate_action(state, action)
        assert any(v.code == "no_actions_remaining" for v in violations)


class TestPuzzleAnswerMatches:
    def test_exact_match(self) -> None:
        assert puzzle_answer_matches("echo", "echo")

    def test_case_insensitive(self) -> None:
        assert puzzle_answer_matches("ECHO", "echo")
        assert puzzle_answer_matches("Echo", "ECHO")

    def test_leading_article_stripped(self) -> None:
        assert puzzle_answer_matches("an echo", "echo")
        assert puzzle_answer_matches("a shadow", "shadow")
        assert puzzle_answer_matches("the void", "void")

    def test_authored_substring_of_submission(self) -> None:
        assert puzzle_answer_matches("the answer is an echo in the dark", "echo")

    def test_no_match(self) -> None:
        assert not puzzle_answer_matches("fire", "water")

    def test_empty_authored_returns_false(self) -> None:
        assert not puzzle_answer_matches("something", "")

    def test_empty_submitted_returns_false(self) -> None:
        assert not puzzle_answer_matches("", "echo")
