from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.agents.context_builder import (
    _ability_mod,
    _build_dice_layer,
    _build_history_layer,
    _hp_status_short,
    _proficiency_bonus,
    build_dm_context,
)
from backend.app.agents.dm_agent import narrate
from backend.app.agents.memory_agent import _keyword_extract, extract_and_store
from backend.app.agents.memory_agent import _try_parse_json as memory_try_parse_json
from backend.app.agents.npc_agent import (
    _build_recent_talks_block,
    _extract_npc_names,
    _keyword_fallback,
    get_npc_responses,
)
from backend.app.agents.npc_agent import (
    _try_parse_json as npc_try_parse_json,
)
from backend.app.agents.summary_agent import summarise_session


class TestNpcAgent:
    def test_extract_npc_names(self) -> None:
        text = "Gandalf the Grey spoke to Frodo"
        names = _extract_npc_names(text)
        assert "Gandalf" in names
        assert "Frodo" in names

    def test_extract_npc_names_empty(self) -> None:
        assert _extract_npc_names("") == []

    def test_keyword_fallback_returns_expected_format(self) -> None:
        result = _keyword_fallback("Gandalf speaks", "Hello", ["Gandalf"])
        assert len(result) == 1
        assert result[0]["npc_name"] == "Gandalf"
        assert isinstance(result[0]["dialogue"], str)
        assert len(result[0]["dialogue"]) > 0

    def test_keyword_fallback_max_three(self) -> None:
        result = _keyword_fallback("", "", ["A", "B", "C", "D", "E"])
        assert len(result) == 3

    def test_get_npc_responses_no_names_returns_empty(self) -> None:
        result = get_npc_responses(
            campaign_id="c1",
            dm_narration="nothing happened here.",
            action_text="you do a thing",
        )
        assert result == []

    def test_npc_try_parse_json_valid_list(self) -> None:
        text = '[{"npc_name": "Zara", "dialogue": "Hello adventurer."}]'
        result = npc_try_parse_json(text)
        assert result is not None
        assert result[0]["npc_name"] == "Zara"

    def test_npc_try_parse_json_invalid_brackets(self) -> None:
        result = npc_try_parse_json("[not valid json at all!!!]")
        assert result is None

    def test_npc_try_parse_json_no_bracket(self) -> None:
        assert npc_try_parse_json("plain text no brackets") is None

    def test_get_npc_responses_with_names_uses_generate(self) -> None:
        """Lines 103-120: when NPC names are found, generate() is called and result parsed."""
        json_response = '[{"npc_name": "Garrick", "dialogue": "Greetings, traveller!"}]'
        with patch("backend.app.agents.npc_agent.generate", return_value=json_response):
            result = get_npc_responses(
                campaign_id="c1",
                dm_narration="Garrick the blacksmith steps forward.",
                action_text="You approach the forge.",
            )
        assert len(result) == 1
        assert result[0]["npc_name"] == "Garrick"
        assert result[0]["dialogue"] == "Greetings, traveller!"

    def test_get_npc_responses_unparseable_falls_back_to_keyword(self) -> None:
        """Line 118: when JSON parse fails, keyword fallback is used."""
        with patch("backend.app.agents.npc_agent.generate", return_value="not json at all"):
            result = get_npc_responses(
                campaign_id="c1",
                dm_narration="Mira the innkeeper smiles warmly.",
                action_text="You enter the inn.",
            )
        assert len(result) >= 1
        assert all("npc_name" in r and "dialogue" in r for r in result)

    def test_get_npc_responses_action_type_included_in_prompt(self) -> None:
        """Action type label is injected into the NPC prompt for better persona matching."""
        captured_prompts: list[str] = []

        def capture_generate(prompt: str, **kwargs: object) -> str:
            captured_prompts.append(prompt)
            return '[{"npc_name": "Bors", "dialogue": "You dare attack me?"}]'

        with patch("backend.app.agents.npc_agent.generate", side_effect=capture_generate):
            get_npc_responses(
                campaign_id="c1",
                dm_narration="Bors the guard blocks your path.",
                action_text="I attack the guard.",
                action_type="attack_melee",
            )
        assert len(captured_prompts) == 1
        assert "MELEE ATTACK" in captured_prompts[0]

    def test_get_npc_responses_default_action_type(self) -> None:
        """When action_type is omitted, GENERAL ACTION label is used."""
        captured_prompts: list[str] = []

        def capture_generate(prompt: str, **kwargs: object) -> str:
            captured_prompts.append(prompt)
            return "[]"

        with patch("backend.app.agents.npc_agent.generate", side_effect=capture_generate):
            get_npc_responses(
                campaign_id="c1",
                dm_narration="Kira the merchant nods at you.",
                action_text="I look around the market.",
            )
        assert len(captured_prompts) == 1
        assert "GENERAL ACTION" in captured_prompts[0]

    def test_build_enemy_context_block_injects_persona(self) -> None:
        """Matched enemy persona/disposition/goals/secret are injected into the prompt block."""
        from backend.app.agents.npc_agent import _build_enemy_context_block

        enemies = (
            {
                "name": "Gorrak",
                "persona": "Arrogant warlord",
                "disposition": "hostile",
                "goals": ["protect the vault", "capture the rogue"],
                "secret": "Fears the dark",
                "negotiation_levers": "Offer gold",
            },
        )
        block = _build_enemy_context_block(["Gorrak"], enemies)
        assert "Gorrak" in block
        assert "Arrogant warlord" in block
        assert "hostile" in block
        assert "protect the vault" in block
        assert "Fears the dark" in block
        assert "Offer gold" in block

    def test_build_enemy_context_block_no_match_returns_empty(self) -> None:
        """Enemy whose name doesn't match extracted NPC list produces empty block."""
        from backend.app.agents.npc_agent import _build_enemy_context_block

        enemies = ({"name": "Zarkon", "persona": "Sinister overlord"},)
        block = _build_enemy_context_block(["Gorrak", "Bors"], enemies)
        assert block == ""

    def test_get_npc_responses_enemies_injected_in_prompt(self) -> None:
        """Enemies tuple is forwarded and matched enemy context appears in the LLM prompt."""
        captured_prompts: list[str] = []

        def capture_generate(prompt: str, **kwargs: object) -> str:
            captured_prompts.append(prompt)
            return '[{"npc_name": "Gorrak", "dialogue": "You dare challenge me?"}]'

        enemies = ({"name": "Gorrak", "persona": "Brutal warlord", "disposition": "hostile"},)
        with patch("backend.app.agents.npc_agent.generate", side_effect=capture_generate):
            result = get_npc_responses(
                campaign_id="c1",
                dm_narration="Gorrak the warlord blocks the exit.",
                action_text="I try to talk my way past.",
                action_type="talk",
                enemies=enemies,
            )
        assert len(captured_prompts) == 1
        assert "Brutal warlord" in captured_prompts[0]
        assert len(result) == 1

    def test_get_npc_responses_talk_action_type(self) -> None:
        """SOCIAL label appears in prompt for talk action type."""
        captured_prompts: list[str] = []

        def capture_generate(prompt: str, **kwargs: object) -> str:
            captured_prompts.append(prompt)
            return "[]"

        with patch("backend.app.agents.npc_agent.generate", side_effect=capture_generate):
            get_npc_responses(
                campaign_id="c1",
                dm_narration="Mira the innkeeper watches you carefully.",
                action_text="I ask about the missing merchant.",
                action_type="talk",
            )
        assert "SOCIAL" in captured_prompts[0]


class TestMemoryAgent:
    def test_keyword_extract_npc(self) -> None:
        facts = _keyword_extract("The king says hello", "The king greets you warmly.")
        assert any(f["fact_type"] == "npc" for f in facts)

    def test_keyword_extract_location(self) -> None:
        facts = _keyword_extract("I enter the cave", "You arrive at a dark cave entrance.")
        assert any(f["fact_type"] == "location" for f in facts)

    def test_keyword_extract_item(self) -> None:
        facts = _keyword_extract("I pick up the sword", "You acquire a gleaming longsword.")
        assert any(f["fact_type"] == "item" for f in facts)

    def test_keyword_extract_empty(self) -> None:
        facts = _keyword_extract("I walk forward", "Nothing happens.")
        assert len(facts) == 0

    def test_keyword_extract_max_two(self) -> None:
        facts = _keyword_extract(
            "I enter the cave and meet the king and find a sword",
            "You discover a cave, meet a king, and acquire a sword.",
        )
        assert len(facts) <= 2

    def test_try_parse_json_valid(self) -> None:
        text = '[{"fact_text": "Met a dragon", "fact_type": "npc", "importance": 8}]'
        result = memory_try_parse_json(text)
        assert result is not None
        assert len(result) == 1
        assert result[0]["fact_text"] == "Met a dragon"

    def test_try_parse_json_invalid(self) -> None:
        assert memory_try_parse_json("not json") is None

    def test_try_parse_json_brackets_invalid_json(self) -> None:
        assert memory_try_parse_json("[not valid json!!!]") is None

    @pytest.mark.asyncio
    async def test_extract_and_store_empty_facts_returns_early(self) -> None:
        await extract_and_store(
            session_id="s1",
            campaign_id="c1",
            action_text="I walk forward",
            narration="Nothing special happens.",
            db=None,
        )

    @pytest.mark.asyncio
    async def test_extract_and_store_no_db_skips_write(self) -> None:
        await extract_and_store(
            session_id="s1",
            campaign_id="c1",
            action_text="The king says hello",
            narration="The king greets you warmly.",
            db=None,
        )


class TestSummaryAgentTranscript:
    @pytest.mark.asyncio
    async def test_summarise_transcript_includes_turn_numbers(self) -> None:
        """summarise_session now labels turns with numbers and action types."""
        import json

        turn_mock = MagicMock()
        turn_mock.action_type = "attack_melee"
        turn_mock.action_text = "I swing my axe at the goblin."
        turn_mock.attack_result = json.dumps(
            {"is_hit": True, "is_critical": False, "damage": 8}
        )
        turn_mock.narration = "The axe bites deep."
        turn_mock.dice_results = "[]"

        async def mock_execute(*args: object, **kwargs: object) -> MagicMock:
            result_mock = MagicMock()
            result_mock.scalars.return_value.all.return_value = [turn_mock]
            return result_mock

        captured_prompts: list[str] = []

        def capture_generate(prompt: str, **kwargs: object) -> str:
            captured_prompts.append(prompt)
            return "The session was short but fierce."

        mock_db = AsyncMock(spec=AsyncSession)
        mock_db.execute = mock_execute
        mock_db.add = MagicMock()

        with patch("backend.app.agents.summary_agent.generate", side_effect=capture_generate):
            await summarise_session(session_id="s1", db=mock_db)

        assert len(captured_prompts) == 1
        assert "Turn 1" in captured_prompts[0]
        assert "attack_melee" in captured_prompts[0]
        assert "HIT" in captured_prompts[0]
        assert "8 damage" in captured_prompts[0]


class TestDmAgent:
    def test_narrate_returns_static_fallback(self) -> None:
        with patch("backend.app.services.ollama_client._call_ollama", return_value=None):
            result = narrate(
                messages=[
                    {"role": "system", "content": "You are a Dungeon Master"},
                    {"role": "user", "content": "I attack the goblin"},
                ]
            )
            assert len(result) > 20

    def test_narrate_empty_messages(self) -> None:
        with patch("backend.app.services.ollama_client._call_ollama", return_value=None):
            result = narrate(messages=[])
            assert len(result) > 0

    def test_narrate_retries_on_short_response(self) -> None:
        call_count = 0

        def mock_generate(**kwargs: object) -> str:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return "OK"  # Too short — should trigger retry
            return "The goblin staggers back, blood dripping from the wound."

        with patch("backend.app.agents.dm_agent.generate", side_effect=mock_generate):
            result = narrate(
                messages=[{"role": "user", "content": "I attack the goblin"}]
            )
        assert call_count == 2
        assert len(result) > 30
        assert "goblin" in result

    def test_narrate_does_not_retry_on_good_response(self) -> None:
        call_count = 0

        def mock_generate(**kwargs: object) -> str:
            nonlocal call_count
            call_count += 1
            return "Your blade cuts deep into the goblin's side, drawing a howl of pain."

        with patch("backend.app.agents.dm_agent.generate", side_effect=mock_generate):
            result = narrate(
                messages=[{"role": "user", "content": "I attack"}]
            )
        assert call_count == 1
        assert len(result) > 30


class TestSummaryAgent:
    @pytest.mark.asyncio
    async def test_summarise_session_no_turns_returns_none(self) -> None:
        async def mock_execute(*args: object, **kwargs: object) -> MagicMock:
            result_mock = MagicMock()
            result_mock.scalars.return_value.all.return_value = []
            return result_mock

        mock_db = AsyncMock(spec=AsyncSession)
        mock_db.execute = mock_execute

        result = await summarise_session(session_id="s1", db=mock_db)
        assert result is None

    @pytest.mark.asyncio
    async def test_summarise_session_long_transcript_truncated(self) -> None:
        long_turn = MagicMock()
        long_turn.action_text = "A" * 4000
        long_turn.narration = "B" * 4500
        long_turn.dice_results = "{}"

        async def mock_execute(*args: object, **kwargs: object) -> MagicMock:
            result_mock = MagicMock()
            result_mock.scalars.return_value.all.return_value = [long_turn]
            return result_mock

        mock_db = AsyncMock(spec=AsyncSession)
        mock_db.execute = mock_execute

        result = await summarise_session(session_id="s1", db=mock_db)
        assert result is not None


class TestAbilityHelpers:
    def test_ability_mod_average(self) -> None:
        assert _ability_mod(10) == "+0"
        assert _ability_mod(11) == "+0"

    def test_ability_mod_positive(self) -> None:
        assert _ability_mod(16) == "+3"
        assert _ability_mod(20) == "+5"

    def test_ability_mod_negative(self) -> None:
        assert _ability_mod(8) == "-1"
        assert _ability_mod(6) == "-2"

    def test_proficiency_bonus_levels(self) -> None:
        assert _proficiency_bonus(1) == 2
        assert _proficiency_bonus(4) == 2
        assert _proficiency_bonus(5) == 3
        assert _proficiency_bonus(9) == 4
        assert _proficiency_bonus(17) == 6
        assert _proficiency_bonus(20) == 6

    def test_hp_status_short_healthy(self) -> None:
        assert _hp_status_short(20, 20) == "Healthy"
        assert _hp_status_short(16, 20) == "Healthy"

    def test_hp_status_short_hurt(self) -> None:
        assert _hp_status_short(15, 20) == "Hurt"

    def test_hp_status_short_bloodied(self) -> None:
        assert _hp_status_short(10, 20) == "Bloodied"

    def test_hp_status_short_critical(self) -> None:
        assert _hp_status_short(4, 20) == "Critical"

    def test_hp_status_short_dying(self) -> None:
        assert _hp_status_short(0, 20) == "Dying"

    def test_hp_status_short_zero_max(self) -> None:
        assert _hp_status_short(0, 0) == "Healthy"


class TestContextBuilder:
    def test_build_dice_layer_full(self) -> None:
        result = _build_dice_layer({"expression": "1d6+2", "total": 5, "rolls": [3]})
        assert "1d6+2" in result
        assert "5" in result
        assert "3" in result

    def test_build_dice_layer_partial(self) -> None:
        result = _build_dice_layer({"expression": "2d8"})
        assert "2d8" in result
        assert "Result" not in result

    def test_build_dice_layer_empty_dict(self) -> None:
        assert _build_dice_layer({}) == ""

    def test_build_dice_layer_skill_check_pass(self) -> None:
        result = _build_dice_layer({"total": 17, "dc": 15})
        assert "PASS" in result
        assert "17" in result
        assert "15" in result
        assert "succeeds" in result

    def test_build_dice_layer_skill_check_fail(self) -> None:
        result = _build_dice_layer({"total": 9, "dc": 12})
        assert "FAIL" in result
        assert "9" in result
        assert "12" in result
        assert "fail" in result.lower()

    def test_build_dice_layer_attack_takes_priority_over_dc(self) -> None:
        # is_hit present → attack path, not skill check path
        result = _build_dice_layer({"is_hit": True, "damage": 5, "dc": 10})
        assert "HIT" in result
        assert "SKILL CHECK" not in result

    @pytest.mark.asyncio
    async def test_build_dm_context_with_dice_result(self) -> None:
        messages = await build_dm_context(
            session_id="s1",
            campaign_id="c1",
            character_id="pc1",
            action_text="I roll for initiative",
            dice_result={"expression": "1d20", "total": 15, "rolls": [15]},
            db=None,
        )
        assert any("1d20" in msg["content"] for msg in messages)
        assert messages[-1] == {"role": "user", "content": "I roll for initiative"}

    @pytest.mark.asyncio
    async def test_build_dm_context_includes_action_type_context(self) -> None:
        messages = await build_dm_context(
            session_id="s1",
            campaign_id="c1",
            character_id="pc1",
            action_text="I swing my sword",
            action_type="attack_melee",
            db=None,
        )
        assert any("MELEE" in msg["content"] for msg in messages)
        assert messages[-1] == {"role": "user", "content": "I swing my sword"}

    @pytest.mark.asyncio
    async def test_build_dm_context_default_action_type_context(self) -> None:
        messages = await build_dm_context(
            session_id="s1",
            campaign_id="c1",
            character_id="pc1",
            action_text="I look around",
            db=None,
        )
        # Default action context should be present
        assert any(
            "EXPLORATION" in msg["content"] or "ACTION CONTEXT" in msg["content"]
            for msg in messages
        )
        assert messages[-1] == {"role": "user", "content": "I look around"}

    @pytest.mark.asyncio
    async def test_build_dm_context_talk_action_type(self) -> None:
        messages = await build_dm_context(
            session_id="s1",
            campaign_id="c1",
            character_id="pc1",
            action_text="I speak to the merchant",
            action_type="talk",
            db=None,
        )
        assert any("SOCIAL" in msg["content"] for msg in messages)

    @pytest.mark.asyncio
    async def test_build_character_layer_missing_returns_empty(self) -> None:
        from backend.app.agents.context_builder import _build_character_layer

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db = AsyncMock(spec=AsyncSession)
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await _build_character_layer("nonexistent_id", mock_db)
        assert result == ""

    @pytest.mark.asyncio
    async def test_build_character_layer_includes_backstory(self) -> None:
        """context_builder.py line 92: backstory appended when present."""
        from backend.app.agents.context_builder import _build_character_layer

        char_mock = MagicMock()
        char_mock.character_name = "Thorn"
        char_mock.race = "Human"
        char_mock.class_name = "Fighter"
        char_mock.level = 2
        char_mock.hp_current = 18
        char_mock.hp_max = 18
        char_mock.armor_class = 14
        char_mock.strength = 14
        char_mock.dexterity = 12
        char_mock.constitution = 12
        char_mock.intelligence = 10
        char_mock.wisdom = 10
        char_mock.charisma = 10
        char_mock.backstory = "A wandering mercenary from the north."

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = char_mock
        mock_db = AsyncMock(spec=AsyncSession)
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await _build_character_layer("char-1", mock_db)
        assert "wandering mercenary" in result
        assert "+2" in result  # STR 14 → +2 modifier
        assert "Proficiency Bonus" in result

    @pytest.mark.asyncio
    async def test_build_dm_context_puzzle_answer_action_type(self) -> None:
        """puzzle_answer action type injects PUZZLE / RIDDLE context into messages."""
        messages = await build_dm_context(
            session_id="s1",
            campaign_id="c1",
            character_id="pc1",
            action_text="The answer is: an echo.",
            action_type="puzzle_answer",
            db=None,
        )
        assert any("PUZZLE" in msg["content"] for msg in messages)
        assert messages[-1] == {"role": "user", "content": "The answer is: an echo."}

    @pytest.mark.asyncio
    async def test_build_dm_context_speak_alias_resolves_to_talk(self) -> None:
        """speak is an alias for talk — SOCIAL context should appear."""
        messages = await build_dm_context(
            session_id="s1",
            campaign_id="c1",
            character_id="pc1",
            action_text="I speak to the wizard.",
            action_type="speak",
            db=None,
        )
        assert any("SOCIAL" in msg["content"] for msg in messages)


class TestOrchestratorGetGameState:
    @pytest.mark.asyncio
    async def test_get_game_state_returns_none_for_missing_session(self) -> None:
        """orchestrator/__init__.py line 37: returns None when session not found."""
        from backend.app.orchestrator import get_game_state

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db = AsyncMock(spec=AsyncSession)
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await get_game_state(session_id="no-such-session", db=mock_db)
        assert result is None


class TestRecentTalksBlock:
    def test_empty_list_returns_empty_string(self) -> None:
        assert _build_recent_talks_block([]) == ""

    def test_single_talk_included(self) -> None:
        talks = [{"npc_name": "Zara", "dialogue": "Welcome, traveller."}]
        result = _build_recent_talks_block(talks)
        assert "Zara" in result
        assert "Welcome, traveller." in result

    def test_multiple_talks_all_included(self) -> None:
        talks = [
            {"npc_name": "Zara", "dialogue": "Hello."},
            {"npc_name": "Brak", "dialogue": "Stand back!"},
        ]
        result = _build_recent_talks_block(talks)
        assert "Zara" in result
        assert "Brak" in result

    def test_entry_missing_dialogue_skipped(self) -> None:
        talks = [{"npc_name": "Ghost", "dialogue": ""}]
        assert _build_recent_talks_block(talks) == ""

    def test_get_npc_responses_recent_talks_injected_in_prompt(self) -> None:
        """recent_talks block reaches the generate() call."""
        talks = [{"npc_name": "Merchant", "dialogue": "Buy my wares!"}]
        with patch("backend.app.agents.npc_agent.generate") as mock_gen:
            mock_gen.return_value = '[{"npc_name": "Merchant", "dialogue": "Indeed."}]'
            get_npc_responses(
                campaign_id="c1",
                dm_narration="A merchant approaches. Merchant called out to you.",
                action_text="I talk to the merchant.",
                recent_talks=talks,
            )
            assert mock_gen.called
            # generate() is called with prompt= as a keyword arg
            prompt_arg = mock_gen.call_args.kwargs.get("prompt", "")
            assert "Merchant" in prompt_arg
            assert "Buy my wares!" in prompt_arg


class TestSkillDcParsing:
    def test_dc_extracted_from_description(self) -> None:
        from backend.app.orchestrator import _parse_skill_dc

        assert _parse_skill_dc("DC 15 Athletics check") == 15

    def test_dc_extracted_case_insensitive(self) -> None:
        from backend.app.orchestrator import _parse_skill_dc

        assert _parse_skill_dc("difficulty 12 to climb the wall") == 12

    def test_dc_default_when_absent(self) -> None:
        from backend.app.orchestrator import _parse_skill_dc

        assert _parse_skill_dc("I try to pick the lock") == 15

    def test_dc_first_match_wins(self) -> None:
        from backend.app.orchestrator import _parse_skill_dc

        assert _parse_skill_dc("DC 10 or DC 20 — pick one") == 10


class TestHistoryCompression:
    @pytest.mark.asyncio
    async def test_short_session_uses_full_limit(self) -> None:
        """Fewer than 20 turns → no compression, default limit of 8 turns fetched."""
        turn_mock = MagicMock()
        turn_mock.action_text = "I attack!"
        turn_mock.narration = "You swing and miss."

        count_result = MagicMock()
        count_result.scalars.return_value.all.return_value = [turn_mock] * 5

        turns_result = MagicMock()
        turns_result.scalars.return_value.all.return_value = [turn_mock] * 5

        mock_db = AsyncMock(spec=AsyncSession)
        mock_db.execute = AsyncMock(side_effect=[count_result, turns_result])

        messages = await _build_history_layer("s1", mock_db)
        assert len(messages) > 0
        assert not any("[Session chronicle" in m["content"] for m in messages)

    @pytest.mark.asyncio
    async def test_long_session_without_summary_no_compression(self) -> None:
        """More than 20 turns but no summary → chronicle block NOT injected."""
        turn_mock = MagicMock()
        turn_mock.action_text = "I move north."
        turn_mock.narration = "You move north."

        count_result = MagicMock()
        count_result.scalars.return_value.all.return_value = [turn_mock] * 25

        summary_result = MagicMock()
        summary_result.scalar_one_or_none.return_value = None

        turns_result = MagicMock()
        turns_result.scalars.return_value.all.return_value = [turn_mock] * 4

        mock_db = AsyncMock(spec=AsyncSession)
        mock_db.execute = AsyncMock(side_effect=[count_result, summary_result, turns_result])

        messages = await _build_history_layer("s1", mock_db)
        assert not any("[Session chronicle" in m["content"] for m in messages)

    @pytest.mark.asyncio
    async def test_long_session_with_summary_injects_chronicle(self) -> None:
        """More than 20 turns AND a saved summary → chronicle block injected first."""
        turn_mock = MagicMock()
        turn_mock.action_text = "I search the room."
        turn_mock.narration = "You find a key."

        count_result = MagicMock()
        count_result.scalars.return_value.all.return_value = [turn_mock] * 25

        summary_mock = MagicMock()
        summary_mock.summary_text = "The party cleared the dungeon entrance."
        summary_result = MagicMock()
        summary_result.scalar_one_or_none.return_value = summary_mock

        turns_result = MagicMock()
        turns_result.scalars.return_value.all.return_value = [turn_mock] * 4

        mock_db = AsyncMock(spec=AsyncSession)
        mock_db.execute = AsyncMock(side_effect=[count_result, summary_result, turns_result])

        messages = await _build_history_layer("s1", mock_db)
        assert messages[0]["role"] == "system"
        assert "[Session chronicle" in messages[0]["content"]
        assert "dungeon entrance" in messages[0]["content"]


class TestXpAward:
    @pytest.mark.asyncio
    async def test_xp_award_increases_experience(self) -> None:
        from backend.app.orchestrator import _award_xp_for_kill

        char_mock = MagicMock()
        char_mock.experience = 0
        char_mock.level = 1

        mock_db = AsyncMock(spec=AsyncSession)
        mock_db.get = AsyncMock(return_value=char_mock)

        result = await _award_xp_for_kill("pc1", mock_db, xp=25)

        assert result["xp_gained"] == 25
        assert result["new_xp"] == 25
        assert char_mock.experience == 25

    @pytest.mark.asyncio
    async def test_xp_award_triggers_level_up(self) -> None:
        from backend.app.orchestrator import _award_xp_for_kill

        char_mock = MagicMock()
        char_mock.experience = 280  # 20 XP away from level 2 threshold (300)
        char_mock.level = 1

        mock_db = AsyncMock(spec=AsyncSession)
        mock_db.get = AsyncMock(return_value=char_mock)

        result = await _award_xp_for_kill("pc1", mock_db, xp=25)

        assert result["new_level"] == 2
        assert char_mock.level == 2

    @pytest.mark.asyncio
    async def test_xp_award_missing_character_returns_zeros(self) -> None:
        from backend.app.orchestrator import _award_xp_for_kill

        mock_db = AsyncMock(spec=AsyncSession)
        mock_db.get = AsyncMock(return_value=None)

        result = await _award_xp_for_kill("ghost", mock_db)

        assert result["xp_gained"] == 0
        assert result["new_xp"] == 0
        assert result["new_level"] == 1

    @pytest.mark.asyncio
    async def test_xp_does_not_exceed_level_20(self) -> None:
        from backend.app.orchestrator import _award_xp_for_kill

        char_mock = MagicMock()
        char_mock.experience = 354999  # just below level 20 cap
        char_mock.level = 19

        mock_db = AsyncMock(spec=AsyncSession)
        mock_db.get = AsyncMock(return_value=char_mock)

        result = await _award_xp_for_kill("pc1", mock_db, xp=100)

        assert result["new_level"] == 20
        assert char_mock.level == 20
