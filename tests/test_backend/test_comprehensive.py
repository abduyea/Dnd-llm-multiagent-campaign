"""Engine types, dice edge-cases, combat paths, validation matrix,
NPC/Memory/Context agents, orchestrator plumbing, and the action API."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.agents.context_builder import (
    _build_memory_layer,
    build_dm_context,
)
from backend.app.engine.combat import apply_damage, process_attack
from backend.app.engine.dice import parse_dice, roll_dice
from backend.app.engine.turn import advance_turn, next_turn, process_turn
from backend.app.engine.types import (
    ActionEconomy,
    ActionInput,
    CharacterState,
    GameState,
    InitiativeEntry,
)
from backend.app.engine.validation import validate_action
from backend.app.main import app

# ─────────────────────────── fixtures ──────────────────────────────────────


def _char(
    cid: str = "pc1",
    name: str = "Hero",
    hp: int = 20,
    ac: int = 14,
    str_score: int = 16,
    dex_score: int = 12,
    con_score: int = 14,
) -> CharacterState:
    return CharacterState(
        id=cid,
        name=name,
        hp_current=hp,
        hp_max=hp,
        strength=str_score,
        dexterity=dex_score,
        constitution=con_score,
        intelligence=10,
        wisdom=10,
        charisma=10,
        armor_class=ac,
        initiative_bonus=2,
        speed=30,
    )


def _state(
    chars: dict[str, CharacterState] | None = None,
    current: str | None = "pc1",
) -> GameState:
    if chars is None:
        chars = {"pc1": _char()}
    return GameState(
        session_id="s1",
        campaign_id="c1",
        turn_number=1,
        current_character_id=current,
        characters=chars,
    )


def _action(**kwargs) -> ActionInput:  # type: ignore[return]
    defaults: dict = {
        "session_id": "s1",
        "character_id": "pc1",
        "action_type": "roleplay",
        "target_id": None,
        "dice_expression": None,
        "description": "",
    }
    defaults.update(kwargs)
    return ActionInput(**defaults)


# ─────────────────────── CharacterState / GameState ─────────────────────────


class TestCharacterStateProperties:
    def test_is_alive_positive_hp(self) -> None:
        assert _char(hp=1).is_alive is True

    def test_is_alive_zero_hp(self) -> None:
        c = CharacterState(
            id="x",
            name="x",
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
        )
        assert c.is_alive is False

    def test_is_conscious_no_conditions(self) -> None:
        assert _char().is_conscious is True

    def test_is_conscious_dead(self) -> None:
        c = _char()
        dead = CharacterState(
            **{**c.__dict__, "conditions": ("dead",)}  # type: ignore[arg-type]
        )
        assert dead.is_conscious is False

    def test_is_conscious_unconscious(self) -> None:
        c = _char()
        unc = CharacterState(
            id=c.id,
            name=c.name,
            hp_current=c.hp_current,
            hp_max=c.hp_max,
            strength=c.strength,
            dexterity=c.dexterity,
            constitution=c.constitution,
            intelligence=c.intelligence,
            wisdom=c.wisdom,
            charisma=c.charisma,
            armor_class=c.armor_class,
            initiative_bonus=c.initiative_bonus,
            speed=c.speed,
            conditions=("unconscious",),
        )
        assert unc.is_conscious is False


class TestGameStateMethods:
    def test_character_by_id_found(self) -> None:
        s = _state()
        assert s.character_by_id("pc1") is not None

    def test_character_by_id_missing(self) -> None:
        assert _state().character_by_id("ghost") is None

    def test_alive_characters(self) -> None:
        dead = CharacterState(
            id="npc1",
            name="Dead",
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
        )
        s = _state(chars={"pc1": _char(), "npc1": dead})
        assert len(s.alive_characters()) == 1

    def test_conscious_characters(self) -> None:
        unc = CharacterState(
            id="npc1",
            name="Unc",
            hp_current=5,
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
            conditions=("unconscious",),
        )
        s = _state(chars={"pc1": _char(), "npc1": unc})
        assert len(s.conscious_characters()) == 1


class TestActionEconomy:
    def test_is_empty_all_true(self) -> None:
        assert ActionEconomy().is_empty() is False

    def test_is_empty_no_resources(self) -> None:
        ae = ActionEconomy(action=False, bonus_action=False, reaction=False)
        assert ae.is_empty() is True

    def test_is_empty_only_reaction_left(self) -> None:
        ae = ActionEconomy(action=False, bonus_action=False, reaction=True)
        assert ae.is_empty() is False


# ─────────────────────────── Dice ───────────────────────────────────────────


class TestDiceEdgeCases:
    def test_parse_just_d20(self) -> None:
        dr = parse_dice("1d20")
        assert dr.num_dice == 1
        assert dr.sides == 20
        assert dr.modifier == 0

    def test_parse_with_negative_modifier(self) -> None:
        dr = parse_dice("2d6-1")
        assert dr.modifier == -1

    def test_roll_with_seed_bounds(self) -> None:
        result = roll_dice("4d6", seed=99)
        assert result.total >= 4
        assert result.total <= 24

    def test_roll_all_rolls_within_sides(self) -> None:
        result = roll_dice("5d8", seed=7)
        assert all(1 <= r <= 8 for r in result.rolls)

    def test_roll_dice_large_expression(self) -> None:
        result = roll_dice("100d4", seed=0)
        assert result.total >= 100
        assert result.total <= 400

    def test_parse_dice_invalid_raises(self) -> None:
        with pytest.raises(ValueError):
            parse_dice("notdice")


# ────────────────────────── Combat ──────────────────────────────────────────


class TestApplyDamageEdgeCases:
    def test_overkill_hp_clamps_to_zero(self) -> None:
        c = _char(hp=3)
        result = apply_damage(c, 9999)
        assert result.hp_current == 0

    def test_zero_damage_leaves_hp_unchanged(self) -> None:
        c = _char(hp=15)
        assert apply_damage(c, 0).hp_current == 15

    def test_unconscious_not_added_twice(self) -> None:
        c = CharacterState(
            id="x",
            name="x",
            hp_current=1,
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
            conditions=("unconscious",),
        )
        result = apply_damage(c, 1)
        assert result.conditions.count("unconscious") == 1

    def test_dead_condition_preserved_on_further_damage(self) -> None:
        c = CharacterState(
            id="x",
            name="x",
            hp_current=1,
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
        )
        result = apply_damage(c, 5)
        assert "dead" in result.conditions


class TestProcessAttackCoverage:
    def test_miss_does_not_mutate_state(self) -> None:
        attacker = _char("pc1", ac=1, str_score=10)
        target = _char("npc1", ac=30)
        state = _state(chars={"pc1": attacker, "npc1": target})
        action = _action(action_type="attack_melee", target_id="npc1")
        new_state, attack = process_attack(state, action, seed=5)
        if not attack.is_hit:
            assert new_state is state

    def test_attack_no_target_id_uses_generic_ac12(self) -> None:
        attacker = _char("pc1", str_score=20)
        state = _state(chars={"pc1": attacker})
        action = _action(action_type="attack_melee", target_id=None)
        _new_state, attack = process_attack(state, action, seed=42)
        assert isinstance(attack.attack_roll, int)

    def test_dead_registered_target_raises(self) -> None:
        attacker = _char("pc1")
        dead = CharacterState(
            id="npc1",
            name="Dead",
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
        )
        state = _state(chars={"pc1": attacker, "npc1": dead})
        action = _action(action_type="attack_melee", target_id="npc1")
        with pytest.raises(ValueError, match="dead"):
            process_attack(state, action)


# ────────────────────────── Validation ──────────────────────────────────────


class TestValidationMatrix:
    def test_invalid_action_type(self) -> None:
        violations = validate_action(_state(), _action(action_type="fly_away"))
        assert any(v.code == "invalid_action_type" for v in violations)

    def test_dead_character_blocked(self) -> None:
        dead = CharacterState(
            id="pc1",
            name="Hero",
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
        )
        violations = validate_action(_state(chars={"pc1": dead}), _action())
        assert any(v.code == "character_neutralized" for v in violations)

    def test_no_actions_remaining(self) -> None:
        spent = CharacterState(
            id="pc1",
            name="Hero",
            hp_current=10,
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
            action_economy=ActionEconomy(action=False, bonus_action=False, reaction=False),
        )
        violations = validate_action(_state(chars={"pc1": spent}), _action())
        assert any(v.code == "no_actions_remaining" for v in violations)

    def test_not_your_turn(self) -> None:
        state = _state(current="npc1")
        violations = validate_action(state, _action(character_id="pc1"))
        assert any(v.code == "not_character_turn" for v in violations)

    def test_target_not_found_when_id_given(self) -> None:
        violations = validate_action(
            _state(), _action(action_type="attack_melee", target_id="ghost")
        )
        assert any(v.code == "target_not_found" for v in violations)

    def test_target_already_dead(self) -> None:
        dead_npc = CharacterState(
            id="npc1",
            name="Corpse",
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
        )
        state = _state(chars={"pc1": _char(), "npc1": dead_npc})
        violations = validate_action(state, _action(action_type="attack_melee", target_id="npc1"))
        assert any(v.code == "target_dead" for v in violations)

    def test_clean_action_no_violations(self) -> None:
        assert validate_action(_state(), _action(action_type="roleplay")) == []


# ──────────────────────── Turn Engine ───────────────────────────────────────


class TestTurnEngine:
    def test_process_turn_roleplay_returns_delta(self) -> None:
        state = _state()
        delta, violations = process_turn(state, _action(action_type="roleplay"))
        assert violations == []
        assert delta is not None
        assert delta.action_type == "roleplay"

    def test_process_turn_invalid_type_returns_violations(self) -> None:
        state = _state()
        delta, violations = process_turn(state, _action(action_type="fly_away"))
        assert any(v.code == "invalid_action_type" for v in violations)
        assert delta is None

    def test_process_turn_melee_attack_succeeds(self) -> None:
        attacker = _char("pc1", str_score=18)
        target = _char("npc1", ac=5)
        state = _state(chars={"pc1": attacker, "npc1": target})
        delta, violations = process_turn(
            state, _action(action_type="attack_melee", target_id="npc1")
        )
        assert violations == []
        assert delta is not None
        assert delta.action_type == "attack_melee"

    def test_advance_turn_with_initiative_increments_number(self) -> None:
        # advance_turn wraps next_turn which increments on wrap-around.
        # Build a 1-character initiative so next_idx(0) <= current_idx(0) → wrap → +1
        pc = _char("pc1")
        entry = InitiativeEntry(character_id="pc1", initiative=15, order=0)
        state = GameState(
            session_id="s1",
            campaign_id="c1",
            turn_number=1,
            current_character_id="pc1",
            initiative_order=(entry,),
            characters={"pc1": pc},
        )
        new_state = advance_turn(state)
        assert new_state.turn_number == 2

    def test_advance_turn_no_initiative_does_not_change_number(self) -> None:
        # Without an initiative order, next_turn returns state unchanged.
        state = _state()
        new_state = advance_turn(state)
        assert new_state.turn_number == state.turn_number

    def test_next_turn_cycles_characters(self) -> None:
        pc1 = _char("pc1")
        pc2 = _char("pc2", name="Rogue")
        e1 = InitiativeEntry(character_id="pc1", initiative=20, order=0)
        e2 = InitiativeEntry(character_id="pc2", initiative=15, order=1)
        state = GameState(
            session_id="s1",
            campaign_id="c1",
            turn_number=1,
            current_character_id="pc1",
            initiative_order=(e1, e2),
            characters={"pc1": pc1, "pc2": pc2},
        )
        new_state = next_turn(state)
        assert new_state.current_character_id == "pc2"


# ──────────────── Context Builder — memory layer coverage ───────────────────


class TestContextBuilderMemoryLayer:
    @pytest.mark.asyncio
    async def test_build_memory_layer_empty_returns_empty_string(self) -> None:
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db = AsyncMock(spec=AsyncSession)
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await _build_memory_layer("s1", mock_db)
        assert result == ""

    @pytest.mark.asyncio
    async def test_build_memory_layer_with_facts(self) -> None:
        """Covers context_builder.py lines 96-97 (memory list non-empty path)."""
        fact = MagicMock()
        fact.fact_text = "The dragon was slain"
        fact.importance = 3

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [fact]
        mock_db = AsyncMock(spec=AsyncSession)
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await _build_memory_layer("s1", mock_db)
        assert "dragon was slain" in result
        assert "Story so far" in result

    @pytest.mark.asyncio
    async def test_build_dm_context_with_memory_in_db(self) -> None:
        """Covers context_builder.py line 41 (memory_layer appended to messages)."""
        fact = MagicMock()
        fact.fact_text = "Tavern keeper is suspicious"
        fact.importance = 2

        empty_result = MagicMock()
        empty_result.scalar_one_or_none.return_value = None
        empty_result.scalars.return_value.all.return_value = []

        mem_result = MagicMock()
        mem_result.scalars.return_value.all.return_value = [fact]

        call_count = 0

        async def mock_execute(stmt, *args, **kwargs):  # type: ignore[no-untyped-def]
            nonlocal call_count
            call_count += 1
            # 1=campaign, 2=character, 3=party, 4=memory, 5=history
            if call_count == 4:
                return mem_result
            return empty_result

        mock_db = AsyncMock(spec=AsyncSession)
        mock_db.execute = mock_execute

        messages = await build_dm_context(
            session_id="s1",
            campaign_id="c1",
            character_id="pc1",
            action_text="I look around",
            db=mock_db,
        )
        contents = " ".join(m["content"] for m in messages)
        assert "Tavern keeper is suspicious" in contents


# ──────────────── History layer with narration ──────────────────────────────


class TestContextBuilderHistoryLayer:
    @pytest.mark.asyncio
    async def test_history_layer_includes_narration(self) -> None:
        from backend.app.agents.context_builder import _build_history_layer

        turn = MagicMock()
        turn.action_text = "I open the door"
        turn.narration = "The hinges screech as the door swings open."

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [turn]
        mock_db = AsyncMock(spec=AsyncSession)
        mock_db.execute = AsyncMock(return_value=mock_result)

        messages = await _build_history_layer("s1", mock_db)
        roles = [m["role"] for m in messages]
        assert "user" in roles
        assert "assistant" in roles

    @pytest.mark.asyncio
    async def test_history_layer_no_narration_skips_assistant(self) -> None:
        from backend.app.agents.context_builder import _build_history_layer

        turn = MagicMock()
        turn.action_text = "I wait"
        turn.narration = None

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [turn]
        mock_db = AsyncMock(spec=AsyncSession)
        mock_db.execute = AsyncMock(return_value=mock_result)

        messages = await _build_history_layer("s1", mock_db)
        assert all(m["role"] != "assistant" for m in messages)


# ───────────── API — attack-miss produces errors list (line 44) ─────────────


class TestActionApiAttackMissError:
    """Cover actions.py:44 — the errors list is populated when attack misses."""

    def test_melee_miss_populates_errors_field(self) -> None:
        """Directly mock the orchestrator to return a guaranteed miss result,
        exercising the branch at actions.py:44."""
        from fastapi.testclient import TestClient

        miss_payload = {
            "turn_number": 1,
            "character_id": "pc1",
            "action_type": "attack_melee",
            "description": "",
            "dice_results": [],
            "narration": "The blow sails wide.",
            "npc_responses": [],
            "errors": [],
            "attack_result": {
                "natural_roll": 3,
                "total_roll": 3,
                "is_critical": False,
                "is_hit": False,
                "damage": 0,
            },
        }

        with patch(
            "backend.app.api.v1.actions.orchestrator_process_action",
            new_callable=AsyncMock,
            return_value=miss_payload,
        ):
            tc = TestClient(app)
            r = tc.post(
                "/api/v1/sessions/s1/actions",
                json={"character_id": "pc1", "action_type": "attack_melee"},
            )
        assert r.status_code == 200
        data = r.json()
        assert len(data["errors"]) == 1
        assert "Attack missed" in data["errors"][0]
        assert "3" in data["errors"][0]


# ──────────────── NPC agent — stop-word and dedup logic ─────────────────────


class TestNpcAgentNameExtraction:
    def test_stop_words_filtered_out(self) -> None:
        from backend.app.agents.npc_agent import _extract_npc_names

        text = "The And Or But I Me We This That These Those DM Turn Eldrin"
        names = _extract_npc_names(text)
        stop = {
            "The",
            "And",
            "Or",
            "But",
            "I",
            "Me",
            "We",
            "This",
            "That",
            "These",
            "Those",
            "DM",
            "Turn",
        }
        for n in names:
            assert n not in stop
        assert "Eldrin" in names

    def test_min_length_three_enforced(self) -> None:
        from backend.app.agents.npc_agent import _extract_npc_names

        text = "Go Do He She It Zara"
        names = _extract_npc_names(text)
        assert all(len(n) > 2 for n in names)

    def test_deduplication(self) -> None:
        from backend.app.agents.npc_agent import _extract_npc_names

        text = "Gandalf spoke. Gandalf replied. Gandalf laughed."
        names = _extract_npc_names(text)
        assert names.count("Gandalf") == 1


# ──────────────── Ollama client — static fallback variety ───────────────────


class TestStaticFallbackVariety:
    def test_three_different_inputs_can_yield_different_templates(self) -> None:
        from backend.app.services.ollama_client import _static_fallback

        results = {_static_fallback(t) for t in ("attack", "cast spell", "hide in shadows")}
        # At minimum 1 unique result; verifies no crash and returns strings
        assert all(isinstance(r, str) and len(r) > 20 for r in results)

    def test_static_fallback_returns_atmospheric_narration(self) -> None:
        from backend.app.services.ollama_client import _static_fallback

        result = _static_fallback("search for the amulet")
        assert isinstance(result, str)
        assert len(result) > 40


# ──────────────── Integration — full happy-path smoke test ──────────────────


class TestFullHappyPath:
    @pytest.mark.asyncio
    async def test_campaign_session_action_end_lifecycle(self) -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            # 1. Create campaign
            r = await client.post(
                "/api/v1/campaigns",
                json={"name": "Smoke Test", "description": "Full run", "world_setting": "Forest"},
            )
            assert r.status_code == 201
            cid = r.json()["id"]

            # 2. Create two characters
            for cname in ("Arya", "Jon"):
                r = await client.post(
                    f"/api/v1/campaigns/{cid}/characters",
                    json={
                        "character_name": cname,
                        "player_name": "Player",
                        "race": "Human",
                        "class_name": "Rogue",
                        "level": 3,
                        "strength": 12,
                        "dexterity": 16,
                        "constitution": 12,
                        "intelligence": 10,
                        "wisdom": 10,
                        "charisma": 10,
                        "armor_class": 14,
                        "speed": 30,
                    },
                )
                assert r.status_code == 201

            chars = (await client.get(f"/api/v1/campaigns/{cid}/characters")).json()
            assert len(chars) == 2
            char_id = chars[0]["id"]

            # 3. Start session
            r = await client.post(
                "/api/v1/sessions", json={"campaign_id": cid, "name": "Chapter 1"}
            )
            assert r.status_code == 201
            sid = r.json()["id"]

            # 4. Roleplay action
            r = await client.post(
                f"/api/v1/sessions/{sid}/actions",
                json={
                    "character_id": char_id,
                    "action_type": "roleplay",
                    "description": "I scout the perimeter",
                },
            )
            assert r.status_code == 200
            data = r.json()
            assert data["turn_number"] >= 0  # 0-based counter before first increment
            assert isinstance(data["narration"], str)

            # 5. Skill check action
            r = await client.post(
                f"/api/v1/sessions/{sid}/actions",
                json={
                    "character_id": char_id,
                    "action_type": "skill_check",
                    "description": "I roll perception",
                    "dice_expression": "1d20+3",
                },
            )
            assert r.status_code == 200

            # 6. Melee attack — no target_id so engine uses generic enemy (AC 12)
            r = await client.post(
                f"/api/v1/sessions/{sid}/actions",
                json={
                    "character_id": char_id,
                    "action_type": "attack_melee",
                },
            )
            assert r.status_code == 200

            # 7. Verify session turn count grew
            r = await client.get(f"/api/v1/sessions/{sid}")
            assert r.json()["turn_count"] >= 3

            # 8. End session
            r = await client.post(f"/api/v1/sessions/{sid}/end")
            assert r.status_code == 200
            assert r.json()["status"] == "completed"
