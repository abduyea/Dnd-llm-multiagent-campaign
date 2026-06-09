import pytest

from backend.app.engine.combat import (
    _enemy_from_context,
    apply_damage,
    compute_attack_roll,
    compute_initiative_order,
    process_attack,
    resolve_check,
)
from backend.app.engine.types import (
    ActionEconomy,
    ActionInput,
    CharacterState,
    GameState,
)


def _make_character(
    char_id: str = "pc1",
    name: str = "Aragorn",
    hp: int = 30,
    ac: int = 15,
    str_score: int = 16,
    dex_score: int = 14,
    init: int = 2,
) -> CharacterState:
    return CharacterState(
        id=char_id,
        name=name,
        hp_current=hp,
        hp_max=hp,
        strength=str_score,
        dexterity=dex_score,
        constitution=14,
        intelligence=10,
        wisdom=12,
        charisma=10,
        armor_class=ac,
        initiative_bonus=init,
        speed=30,
        action_economy=ActionEconomy(),
    )


class TestInitiative:
    def test_initiative_order(self) -> None:
        chars = [
            _make_character("pc1", "Fast", dex_score=18, init=4),
            _make_character("pc2", "Slow", dex_score=8, init=-1),
        ]
        order = compute_initiative_order(chars, seed=42)
        assert len(order) == 2
        assert order[0].character_id == "pc1"

    def test_dead_character_excluded(self) -> None:
        alive = _make_character("alive", "Alive")
        dead = CharacterState(
            id="dead",
            name="Dead",
            hp_current=0,
            hp_max=30,
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
        order = compute_initiative_order([alive, dead], seed=0)
        assert len(order) == 1
        assert order[0].character_id == "alive"


class TestAttackRoll:
    def test_attack_hits(self) -> None:
        attacker = _make_character("pc1", "Fighter", str_score=18)
        target = _make_character("npc1", "Goblin", ac=10)
        action = ActionInput(
            session_id="s1",
            character_id="pc1",
            action_type="attack_melee",
            target_id="npc1",
        )
        result = compute_attack_roll(attacker, target, action, seed=10)
        assert result.is_hit  # d20 roll of 10 + 4 = 14 vs AC 10
        assert result.attacker_id == "pc1"
        assert result.target_id == "npc1"

    def test_attack_misses(self) -> None:
        attacker = _make_character("pc1", "Weak", str_score=8)
        target = _make_character("npc1", "Armored", ac=20)
        action = ActionInput(
            session_id="s1",
            character_id="pc1",
            action_type="attack_melee",
            target_id="npc1",
        )
        result = compute_attack_roll(attacker, target, action, seed=42)
        assert not result.is_hit

    def test_critical_hit(self) -> None:
        attacker = _make_character("pc1", "Lucky", str_score=10)
        target = _make_character("npc1", "Victim", ac=30)
        action = ActionInput(
            session_id="s1",
            character_id="pc1",
            action_type="attack_melee",
            target_id="npc1",
            dice_expression="1d8",
        )
        result = compute_attack_roll(attacker, target, action, seed=5)
        assert result.is_critical
        assert result.is_hit  # critical always hits

    def test_hit_without_dice_expression_deals_damage(self) -> None:
        # The UI sends basic attacks with no dice_expression; a landed hit must
        # still deal damage (regression: previously resolved to 0).
        attacker = _make_character("pc1", "Fighter", str_score=16)
        target = _make_character("npc1", "Goblin", ac=5)
        action = ActionInput(
            session_id="s1", character_id="pc1",
            action_type="attack_melee", target_id="npc1",
        )
        for seed in range(100):
            result = compute_attack_roll(attacker, target, action, seed=seed)
            if result.is_hit and not result.is_critical:
                assert result.damage > 0
                return
        pytest.fail("no hitting seed found in range")

    def test_critical_without_dice_expression_deals_damage(self) -> None:
        # Regression: a critical hit with no weapon die used to deal 0 damage.
        attacker = _make_character("pc1", "Fighter", str_score=16)
        target = _make_character("npc1", "Tank", ac=99)  # only a natural 20 connects
        action = ActionInput(
            session_id="s1", character_id="pc1",
            action_type="attack_melee", target_id="npc1",
        )
        for seed in range(300):
            result = compute_attack_roll(attacker, target, action, seed=seed)
            if result.is_critical:
                assert result.damage > 0
                return
        pytest.fail("no critical-hit seed found in range")

    def test_natural_one_misses(self) -> None:
        attacker = _make_character("pc1", "Unlucky", str_score=20)
        target = _make_character("npc1", "Target", ac=10)
        action = ActionInput(
            session_id="s1",
            character_id="pc1",
            action_type="attack_melee",
            target_id="npc1",
        )
        result = compute_attack_roll(attacker, target, action, seed=104)
        assert not result.is_hit  # natural 1 always misses
        assert result.natural_roll == 1

    def test_deterministic_seed(self) -> None:
        attacker = _make_character("pc1", "Test")
        target = _make_character("npc1", "Test")
        action = ActionInput(
            session_id="s1",
            character_id="pc1",
            action_type="attack_melee",
            target_id="npc1",
            seed=42,
        )
        r1 = compute_attack_roll(attacker, target, action, seed=42)
        r2 = compute_attack_roll(attacker, target, action, seed=42)
        assert r1.attack_roll == r2.attack_roll
        assert r1.damage == r2.damage


class TestApplyDamage:
    def test_reduces_hp(self) -> None:
        char = _make_character(hp=30)
        damaged = apply_damage(char, 10)
        assert damaged.hp_current == 20

    def test_hp_floor_zero(self) -> None:
        char = _make_character(hp=10)
        damaged = apply_damage(char, 20)
        assert damaged.hp_current == 0

    def test_unconscious_on_zero(self) -> None:
        char = _make_character(hp=5)
        damaged = apply_damage(char, 5)
        assert "unconscious" in damaged.conditions


class TestProcessAttack:
    def test_full_attack_flow(self) -> None:
        pc = _make_character("pc1", "Fighter", hp=30, ac=15, str_score=16)
        npc = _make_character("npc1", "Goblin", hp=10, ac=10)
        state = GameState(
            session_id="s1",
            campaign_id="c1",
            turn_number=1,
            current_character_id="pc1",
            characters={"pc1": pc, "npc1": npc},
        )
        action = ActionInput(
            session_id="s1",
            character_id="pc1",
            action_type="attack_melee",
            target_id="npc1",
            dice_expression="1d8",
        )
        new_state, attack = process_attack(state, action, seed=3)
        assert attack.is_hit
        assert new_state.characters["npc1"].hp_current < 10

    def test_attack_unregistered_target_uses_generic_enemy(self) -> None:
        pc = _make_character("pc1")
        state = GameState(
            session_id="s1",
            campaign_id="c1",
            turn_number=1,
            current_character_id="pc1",
            characters={"pc1": pc},
        )
        action = ActionInput(
            session_id="s1",
            character_id="pc1",
            action_type="attack_melee",
            target_id="ghost",
        )
        # Unregistered targets fall back to a generic enemy — no exception raised.
        _new_state, attack = process_attack(state, action, seed=1)
        assert isinstance(attack.attack_roll, int)

    def test_ranged_attack_uses_dexterity(self) -> None:
        # Same character with DEX 18 (+4) and STR 8 (-1); same seed → same natural roll.
        # Ranged should exceed melee by 5 (the difference in modifiers).
        archer = _make_character("pc1", "Archer", dex_score=18, str_score=8)
        target = _make_character("npc1", "Goblin", ac=5)
        action_ranged = ActionInput(
            session_id="s1", character_id="pc1", action_type="attack_ranged", target_id="npc1"
        )
        action_melee = ActionInput(
            session_id="s1", character_id="pc1", action_type="attack_melee", target_id="npc1"
        )
        ranged_result = compute_attack_roll(archer, target, action_ranged, seed=10)
        melee_result = compute_attack_roll(archer, target, action_melee, seed=10)
        assert ranged_result.attack_roll == melee_result.attack_roll + 5  # DEX +4 vs STR -1

    def test_cast_action_uses_strength_modifier(self) -> None:
        attacker = _make_character("pc1", "Mage", str_score=14)
        target = _make_character("npc1", "Target", ac=5)
        action = ActionInput(
            session_id="s1",
            character_id="pc1",
            action_type="cast",
            target_id="npc1",
        )
        result = compute_attack_roll(attacker, target, action, seed=10)
        assert isinstance(result.attack_roll, int)
        assert result.attacker_id == "pc1"

    def test_attacker_not_found_raises(self) -> None:
        npc = _make_character("npc1", "Goblin")
        state = GameState(
            session_id="s1",
            campaign_id="c1",
            turn_number=1,
            current_character_id="ghost",
            characters={"npc1": npc},
        )
        action = ActionInput(
            session_id="s1",
            character_id="ghost",
            action_type="attack_melee",
            target_id="npc1",
        )
        with pytest.raises(ValueError, match="Attacker"):
            process_attack(state, action)

    def test_unconscious_attacker_raises(self) -> None:
        ko = CharacterState(
            id="ko",
            name="Downed",
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
        target = _make_character("npc1", "Target")
        state = GameState(
            session_id="s1",
            campaign_id="c1",
            turn_number=1,
            current_character_id="ko",
            characters={"ko": ko, "npc1": target},
        )
        action = ActionInput(
            session_id="s1",
            character_id="ko",
            action_type="attack_melee",
            target_id="npc1",
        )
        with pytest.raises(ValueError, match="not conscious"):
            process_attack(state, action)

    def test_attack_dead_raises(self) -> None:
        target = CharacterState(
            id="dead",
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
            conditions=("dead",),
            action_economy=ActionEconomy(),
        )
        pc = _make_character("pc1")
        state = GameState(
            session_id="s1",
            campaign_id="c1",
            turn_number=1,
            current_character_id="pc1",
            characters={"pc1": pc, "dead": target},
        )
        action = ActionInput(
            session_id="s1",
            character_id="pc1",
            action_type="attack_melee",
            target_id="dead",
        )
        with pytest.raises(ValueError, match="already dead"):
            process_attack(state, action)


class TestResolveCheck:
    def test_check_passes(self) -> None:
        char = _make_character("pc1", str_score=18)  # STR mod +4
        result = resolve_check(char, "strength", dc=10, seed=5)
        assert result.success
        assert result.stat == "strength"
        assert result.stat_mod == 4
        assert result.total == result.d20 + 4

    def test_check_fails(self) -> None:
        char = _make_character("pc1", str_score=8)  # STR mod -1
        result = resolve_check(char, "strength", dc=20, seed=2)
        assert not result.success

    def test_stat_abbreviation(self) -> None:
        char = _make_character("pc1", dex_score=16)  # DEX mod +3
        result = resolve_check(char, "dex", dc=1, seed=5)
        assert result.stat == "dexterity"
        assert result.stat_mod == 3

    def test_missing_stat_defaults_zero_modifier(self) -> None:
        char = _make_character("pc1", str_score=10)
        result = resolve_check(char, "nonexistent_stat", dc=15, seed=5)
        assert result.stat_mod == 0

    def test_deterministic_with_seed(self) -> None:
        char = _make_character("pc1")
        r1 = resolve_check(char, "wisdom", dc=12, seed=42)
        r2 = resolve_check(char, "wisdom", dc=12, seed=42)
        assert r1.d20 == r2.d20
        assert r1.total == r2.total
        assert r1.success == r2.success


class TestEnemyFromContext:
    """Targeting logic that maps the frontend encounter tracker to a combat enemy."""

    def _action(self, **kw: object) -> ActionInput:
        base: dict[str, object] = {
            "session_id": "s1",
            "character_id": "pc1",
            "action_type": "attack_melee",
        }
        base.update(kw)
        return ActionInput(**base)  # type: ignore[arg-type]

    def test_no_enemies_returns_none(self) -> None:
        assert _enemy_from_context(self._action()) is None

    def test_all_dead_enemies_returns_none(self) -> None:
        action = self._action(enemies=({"name": "Goblin", "hp": 0},))
        assert _enemy_from_context(action) is None

    def test_target_name_from_description_prefix(self) -> None:
        action = self._action(
            description="[Target: Orc] I swing my axe.",
            enemies=({"name": "Goblin", "hp": 5}, {"name": "Orc", "hp": 12, "ac": 14}),
        )
        enemy = _enemy_from_context(action)
        assert enemy is not None
        assert enemy.name == "Orc"
        assert enemy.armor_class == 14

    def test_substring_name_match(self) -> None:
        # "Warden" should match the tracked "The Bound Warden".
        action = self._action(
            description="[Target: Warden] strike",
            enemies=({"name": "The Bound Warden", "hp": 52},),
        )
        enemy = _enemy_from_context(action)
        assert enemy is not None
        assert enemy.name == "The Bound Warden"

    def test_falls_back_to_first_alive_when_no_match(self) -> None:
        action = self._action(
            description="[Target: Nobody] flail wildly",
            enemies=({"name": "Goblin", "hp": 0}, {"name": "Orc", "hp": 9}),
        )
        enemy = _enemy_from_context(action)
        assert enemy is not None
        assert enemy.name == "Orc"  # first *alive* enemy, the dead Goblin is skipped

    def test_target_id_used_when_no_description_prefix(self) -> None:
        action = self._action(
            target_id="Orc",
            enemies=({"name": "Goblin", "hp": 5}, {"name": "Orc", "hp": 12}),
        )
        enemy = _enemy_from_context(action)
        assert enemy is not None
        assert enemy.name == "Orc"

    def test_string_hp_and_ac_are_coerced(self) -> None:
        # The frontend sometimes sends HP/AC as strings; they must parse, not crash.
        action = self._action(enemies=({"name": "Goblin", "hp": "8", "ac": "13"},))
        enemy = _enemy_from_context(action)
        assert enemy is not None
        assert enemy.hp_current == 8
        assert enemy.armor_class == 13

    def test_missing_hp_ac_use_generic_defaults(self) -> None:
        action = self._action(enemies=({"name": "Mystery"},))
        enemy = _enemy_from_context(action)
        assert enemy is not None
        assert enemy.hp_current == 10  # _GENERIC_ENEMY_HP
        assert enemy.armor_class == 12  # _GENERIC_ENEMY_AC

    def test_camelcase_maxhp_alias_is_read(self) -> None:
        action = self._action(enemies=({"name": "Goblin", "hp": 5, "maxHp": 9},))
        enemy = _enemy_from_context(action)
        assert enemy is not None
        assert enemy.hp_max == 9

