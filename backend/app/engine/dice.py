from __future__ import annotations

import random
import re
from collections.abc import Sequence

from backend.app.engine.types import DiceResult, DiceRoll

_DICE_PATTERN = re.compile(r"^(\d+)[dD](\d+)(?:([+-])(\d+))?$")


def parse_dice(expression: str) -> DiceRoll:
    """Parse a dice expression string (e.g. '2d6+3') into a DiceRoll dataclass."""
    match = _DICE_PATTERN.match(expression.strip())
    if not match:
        raise ValueError(f"Invalid dice expression: {expression!r}")
    num = int(match.group(1))
    sides = int(match.group(2))
    modifier = 0
    if match.group(3) and match.group(4):
        sign = 1 if match.group(3) == "+" else -1
        modifier = sign * int(match.group(4))
    if num < 1:
        raise ValueError(f"Number of dice must be >= 1, got {num}")
    if sides < 2:
        raise ValueError(f"Number of sides must be >= 2, got {sides}")
    return DiceRoll(num_dice=num, sides=sides, modifier=modifier)


def roll_dice(expression: str, seed: int | None = None) -> DiceResult:
    """Parse and roll a dice expression, returning individual rolls and total."""
    parsed = parse_dice(expression)
    rng = random.Random(seed)  # noqa: S311
    rolls = tuple(rng.randint(1, parsed.sides) for _ in range(parsed.num_dice))
    total = sum(rolls) + parsed.modifier
    return DiceResult(
        rolls=rolls,
        modifier=parsed.modifier,
        total=total,
        expression=expression,
    )


def roll_d20(seed: int | None = None) -> int:
    """Roll a single d20 and return the integer result (1-20)."""
    rng = random.Random(seed)  # noqa: S311
    return rng.randint(1, 20)


def roll_multiple(expressions: Sequence[str], seed: int | None = None) -> list[DiceResult]:
    """Roll multiple dice expressions, offsetting seed per expression for independent results."""
    base_seed = seed
    results: list[DiceResult] = []
    for i, expr in enumerate(expressions):
        sub_seed = base_seed + i if base_seed is not None else None
        results.append(roll_dice(expr, seed=sub_seed))
    return results
