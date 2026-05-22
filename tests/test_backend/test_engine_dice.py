import pytest

from backend.app.engine.dice import parse_dice, roll_d20, roll_dice, roll_multiple
from backend.app.engine.types import DiceResult, DiceRoll


class TestParseDice:
    def test_parse_basic(self) -> None:
        result = parse_dice("2d6")
        assert result.num_dice == 2
        assert result.sides == 6
        assert result.modifier == 0

    def test_parse_with_modifier(self) -> None:
        result = parse_dice("1d20+5")
        assert result.num_dice == 1
        assert result.sides == 20
        assert result.modifier == 5

    def test_parse_negative_modifier(self) -> None:
        result = parse_dice("3d8-2")
        assert result.num_dice == 3
        assert result.sides == 8
        assert result.modifier == -2

    def test_parse_case_insensitive(self) -> None:
        result = parse_dice("4D6")
        assert result.num_dice == 4
        assert result.sides == 6

    def test_parse_invalid_raises(self) -> None:
        with pytest.raises(ValueError, match="Invalid dice expression"):
            parse_dice("abc")

    def test_parse_zero_dice_raises(self) -> None:
        with pytest.raises(ValueError, match="Number of dice must be >= 1"):
            parse_dice("0d6")

    def test_parse_one_side_raises(self) -> None:
        with pytest.raises(ValueError, match="Number of sides must be >= 2"):
            parse_dice("1d1")

    def test_expression_output(self) -> None:
        dr = DiceRoll(num_dice=2, sides=6, modifier=3)
        assert dr.expression() == "2d6+3"
        dr2 = DiceRoll(num_dice=1, sides=20, modifier=-1)
        assert dr2.expression() == "1d20-1"
        dr3 = DiceRoll(num_dice=1, sides=20)
        assert dr3.expression() == "1d20+0"


class TestRollDice:
    def test_roll_deterministic(self) -> None:
        r1 = roll_dice("2d6", seed=42)
        r2 = roll_dice("2d6", seed=42)
        assert r1.rolls == r2.rolls
        assert r1.total == r2.total

    def test_roll_range(self) -> None:
        for _ in range(20):
            result = roll_dice("1d20", seed=None)
            assert len(result.rolls) == 1
            assert 1 <= result.rolls[0] <= 20

    def test_roll_total(self) -> None:
        result = roll_dice("2d6+3", seed=99)
        assert result.total == sum(result.rolls) + result.modifier

    def test_roll_result_type(self) -> None:
        result = roll_dice("3d8", seed=1)
        assert isinstance(result, DiceResult)
        assert isinstance(result.rolls, tuple)
        assert len(result.rolls) == 3

    def test_roll_multiple_expressions(self) -> None:
        results = roll_multiple(["1d20", "2d6", "1d4"], seed=42)
        assert len(results) == 3
        assert all(isinstance(r, DiceResult) for r in results)

    def test_d20_range(self) -> None:
        for seed in range(100):
            roll = roll_d20(seed=seed)
            assert 1 <= roll <= 20

    def test_post_init_total(self) -> None:
        result = DiceResult(rolls=(3, 5), modifier=2)
        assert result.total == 10

    def test_post_init_zero_rolls(self) -> None:
        result = DiceResult(rolls=(), modifier=0)
        assert result.total == 0

    def test_zero_total_zero_rolls(self) -> None:
        result = DiceResult(rolls=(), modifier=0, total=0)
        assert result.total == 0
